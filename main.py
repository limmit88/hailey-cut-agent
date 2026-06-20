"""
Hailey Cut Agent — FastAPI 서버
POST /upload   → 영상 업로드 + 처리 시작 (job_id 반환)
GET  /stream/{job_id} → SSE 진행 상황
GET  /result/{job_id} → XML/SRT 다운로드 정보
GET  /download/{job_id}/{filename} → 파일 다운로드
"""
import asyncio
import io
import json
import os
import platform
import shutil
import uuid
import zipfile
from pathlib import Path

import aiofiles
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from fastapi import FastAPI, File, Request, UploadFile, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from core.silence import detect_silence, get_video_fps, get_video_duration, get_video_dimensions
from core.asr import transcribe
from core.filler import detect_fillers
from core.stutter import trim_stutters
from core.translate import translate_segments
from core.xml_builder import build_fcp7_xml

BASE_DIR   = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# 서버 설정
ACCESS_TOKEN   = os.environ.get("ACCESS_TOKEN", "")        # 비어있으면 인증 없음(로컬)
MAX_UPLOAD_MB  = int(os.environ.get("MAX_UPLOAD_MB", "500"))
IS_LOCAL       = platform.system() == "Darwin"             # Mac이면 로컬 모드

app = FastAPI(title="Hailey Cut Agent")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

_queues: dict[str, asyncio.Queue] = {}
_results: dict[str, dict] = {}

_AUTH_COOKIE = "hca_token"
_AUTH_SKIP   = {"/static", "/favicon.ico"}


# ── 인증 미들웨어 ─────────────────────────────────────────
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if not ACCESS_TOKEN:
        return await call_next(request)

    # 정적 파일·헬스체크는 통과
    if any(request.url.path.startswith(p) for p in _AUTH_SKIP):
        return await call_next(request)

    token_cookie = request.cookies.get(_AUTH_COOKIE, "")
    token_param  = request.query_params.get("token", "")
    authed = token_cookie == ACCESS_TOKEN or token_param == ACCESS_TOKEN

    if not authed:
        if "text/html" in request.headers.get("accept", ""):
            return HTMLResponse(_login_page(), status_code=401)
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    response = await call_next(request)
    # URL 토큰으로 첫 인증 → 쿠키 발급 후 클린 URL로 리다이렉트
    if token_param == ACCESS_TOKEN and token_cookie != ACCESS_TOKEN:
        clean_url = str(request.url).split("?")[0]
        response = RedirectResponse(clean_url)
        response.set_cookie(_AUTH_COOKIE, ACCESS_TOKEN, max_age=86400 * 30, httponly=True, samesite="lax")
    return response


def _login_page() -> str:
    return """<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hailey Cut Agent</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0a0a0a;color:#e5e5e5;font-family:'Pretendard Variable','Pretendard',sans-serif;
     display:flex;align-items:center;justify-content:center;height:100vh}
.box{background:#161616;border:1px solid #2a2a2a;border-radius:12px;padding:40px;width:340px;text-align:center}
h1{font-size:18px;font-weight:600;margin-bottom:6px}
p{color:#737373;font-size:13px;margin-bottom:24px}
input{width:100%;background:#0a0a0a;border:1px solid #2a2a2a;border-radius:7px;
      padding:10px 14px;color:#e5e5e5;font-size:14px;outline:none;margin-bottom:12px}
button{width:100%;background:#22c55e;color:#000;border:none;border-radius:7px;
       padding:11px;font-size:14px;font-weight:600;cursor:pointer}
</style></head><body>
<div class="box">
  <h1>Hailey Cut Agent</h1>
  <p>초대된 사용자만 이용할 수 있어요</p>
  <input id="t" type="password" placeholder="액세스 토큰 입력" autofocus>
  <button onclick="go()">입장</button>
</div>
<script>
function go(){const t=document.getElementById('t').value.trim();if(t)location.href='/?token='+encodeURIComponent(t);}
document.getElementById('t').addEventListener('keydown',e=>{if(e.key==='Enter')go();});
</script></body></html>"""


# ── 설정 엔드포인트 (JS에서 서버 모드 판단용) ──────────────
@app.get("/config")
async def config():
    return {"local_mode": IS_LOCAL}


# ── 루트: HTML 서빙 ───────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index():
    html = (BASE_DIR / "static" / "index.html").read_text()
    return HTMLResponse(html)


# ── 업로드 + 처리 시작 ────────────────────────────────────
@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    job_id = str(uuid.uuid4())[:8]
    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".mp4", ".mov", ".avi", ".mkv"}:
        raise HTTPException(400, "mp4/mov/avi/mkv 파일만 지원합니다")

    video_path = UPLOAD_DIR / f"{job_id}{suffix}"
    total = 0
    max_bytes = MAX_UPLOAD_MB * 1024 * 1024
    async with aiofiles.open(video_path, "wb") as f:
        while chunk := await file.read(1 << 20):
            total += len(chunk)
            if total > max_bytes:
                await f.close()
                video_path.unlink(missing_ok=True)
                raise HTTPException(413, f"파일이 너무 큽니다 (최대 {MAX_UPLOAD_MB}MB)")
            await f.write(chunk)

    q: asyncio.Queue = asyncio.Queue()
    _queues[job_id] = q
    asyncio.create_task(_process(job_id, str(video_path), q))

    return {"job_id": job_id}


# ── Premiere Pro 자동 열기 ───────────────────────────────
@app.post("/open/{job_id}")
async def open_in_premiere(job_id: str):
    import subprocess, shlex
    out_dir = OUTPUT_DIR / job_id
    if not out_dir.exists():
        raise HTTPException(404, "결과 없음")

    # 파일 탐색
    xml_files  = sorted(out_dir.glob("*_cut.xml")) or sorted(out_dir.glob("*_premiere.xml"))
    srt_files  = sorted(out_dir.glob("*_caption.srt")) or sorted(out_dir.glob("*.srt"))
    video_exts = {".mp4", ".mov", ".avi", ".mkv"}
    video_files = [f for f in out_dir.iterdir() if f.suffix.lower() in video_exts and not f.name.startswith("_")]

    if not xml_files:   raise HTTPException(404, "XML 없음")
    if not video_files: raise HTTPException(404, "영상 없음")

    xml_path   = str(xml_files[0])
    srt_path   = str(srt_files[0]) if srt_files else ""
    video_path = str(video_files[0])
    proj_path  = str(out_dir / (Path(video_path).stem + ".prproj"))

    # JSX 템플릿 치환
    jsx_content = (BASE_DIR / "open_in_premiere.jsx").read_text()
    for placeholder, value in [
        ("{{VIDEO_PATH}}", video_path),
        ("{{XML_PATH}}",   xml_path),
        ("{{SRT_PATH}}",   srt_path),
        ("{{PROJ_PATH}}",  proj_path),
    ]:
        jsx_content = jsx_content.replace(placeholder, value)

    jsx_tmp = out_dir / "_open.jsx"
    jsx_tmp.write_text(jsx_content, encoding="utf-8")

    premiere_name = "Adobe Premiere Pro 2025"
    premiere_app  = f"/Applications/{premiere_name}/{premiere_name}.app"

    # 경로에 쌍따옴표가 없다고 가정 (macOS 경로 일반 케이스)
    xml_esc = xml_path.replace('"', '\\"')
    srt_esc = srt_path.replace('"', '\\"') if srt_path else ""

    # Premiere Pro 2025은 DoScript 미지원 → open POSIX file 으로 임포트
    files_as = f'open POSIX file "{xml_esc}"'
    if srt_esc:
        files_as += f'\n    open POSIX file "{srt_esc}"'

    applescript = f'''tell application "{premiere_name}"
    activate
    {files_as}
end tell'''

    result = subprocess.run(
        ["osascript", "-"],
        input=applescript, text=True,
        capture_output=True
    )

    # AppleScript open이 안 되면 OS open -a 폴백
    if result.returncode != 0:
        files_to_open = [xml_path] + ([srt_path] if srt_path else [])
        subprocess.Popen(["open", "-a", premiere_app] + files_to_open)

    return {"status": "ok", "log": result.stdout or "open 요청 완료"}


# ── 프로젝트 ZIP 다운로드 ─────────────────────────────────
@app.get("/download-project/{job_id}")
async def download_project(job_id: str):
    out_dir = OUTPUT_DIR / job_id
    if not out_dir.exists():
        raise HTTPException(404, "결과 없음")

    video_exts  = {".mp4", ".mov", ".avi", ".mkv"}
    skip_names  = {"_open.jsx", "_open.applescript"}

    targets = [
        f for f in out_dir.iterdir()
        if f.is_file()
        and f.name not in skip_names
        and not f.name.startswith("_")
    ]
    if not targets:
        raise HTTPException(404, "다운로드할 파일 없음")

    video_files  = [f for f in targets if f.suffix.lower() in video_exts]
    xml_files    = [f for f in targets if f.suffix.lower() == ".xml"]
    prproj_files = [f for f in targets if f.suffix.lower() == ".prproj"]
    stem = video_files[0].stem if video_files else job_id
    zip_name = f"{stem}_project.zip"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in targets:
            zf.write(f, arcname=f.name)

        # .prproj 없으면 더블클릭으로 Premiere에서 열리는 .command 스크립트 포함
        if not prproj_files and xml_files:
            xml_name = xml_files[0].name
            command_script = (
                "#!/bin/bash\n"
                'DIR="$(cd "$(dirname "$0")" && pwd)"\n'
                f'open -a "Adobe Premiere Pro 2025" "$DIR/{xml_name}"\n'
            )
            info = zipfile.ZipInfo("프로젝트_열기.command")
            info.external_attr = 0o755 << 16   # 실행 권한
            zf.writestr(info, command_script)

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_name}"'},
    )


# ── SSE 스트림 ────────────────────────────────────────────
@app.get("/stream/{job_id}")
async def stream(job_id: str):
    if job_id not in _queues:
        raise HTTPException(404, "job not found")

    async def generator():
        q = _queues[job_id]
        while True:
            event = await q.get()
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            if event.get("type") == "done" or event.get("type") == "error":
                break

    return StreamingResponse(generator(), media_type="text/event-stream",
                              headers={"Cache-Control": "no-cache",
                                       "X-Accel-Buffering": "no"})


# ── 결과 조회 ─────────────────────────────────────────────
@app.get("/result/{job_id}")
async def result(job_id: str):
    if job_id not in _results:
        raise HTTPException(404, "결과 없음 (아직 처리 중이거나 잘못된 job_id)")
    return _results[job_id]


# ── 파일 다운로드 ─────────────────────────────────────────
@app.get("/download/{job_id}/{filename}")
async def download(job_id: str, filename: str):
    path = OUTPUT_DIR / job_id / filename
    if not path.exists():
        raise HTTPException(404, "파일 없음")
    return FileResponse(str(path), filename=filename)


# ── 핵심 파이프라인 ───────────────────────────────────────
async def _process(job_id: str, video_path: str, q: asyncio.Queue):
    out_dir = str(OUTPUT_DIR / job_id)
    os.makedirs(out_dir, exist_ok=True)

    async def emit(type_: str, **kwargs):
        await q.put({"type": type_, **kwargs})
        await asyncio.sleep(0.5)  # 애니메이션 가시화

    try:
        # ── 0. 영상을 출력 폴더로 이동 (XML이 참조할 최종 경로 확정) ──
        final_video = os.path.join(out_dir, Path(video_path).name)
        os.rename(video_path, final_video)
        video_path = final_video

        # ── 1. silence_detect ─────────────────────────────
        await emit("step", step="silence", label="무음 구간 탐지 중…", progress=10)
        fps      = get_video_fps(video_path)
        duration = get_video_duration(video_path)
        width, height = get_video_dimensions(video_path)
        segments = detect_silence(video_path)
        await emit("step", step="silence", label=f"무음 제거 완료 — {len(segments)}개 발화 구간", progress=25,
                   stats={"segments": len(segments), "fps": fps, "duration": round(duration, 1)})

        # ── 2. ASR ────────────────────────────────────────
        await emit("step", step="asr", label="Whisper 전사 중… (최초 실행 시 모델 다운로드)", progress=30)
        asr = await transcribe(video_path)
        full_script = asr["text"]
        asr_segs    = asr["segments"]

        # silence 세그먼트에 ASR 텍스트 병합
        merged = _merge_asr(segments, asr_segs)

        # 말 더듬음 트림 (단어 타임스탬프 기반)
        before = len(merged)
        merged = trim_stutters(merged)
        await emit("step", step="asr", label=f"전사 완료 — {len(full_script)}자 (더듬음 정리)", progress=55,
                   transcript=full_script[:500] + ("…" if len(full_script) > 500 else ""))

        # ── 3. filler / NG ────────────────────────────────
        await emit("step", step="filler", label="잔말·NG·더듬음 탐지 중…", progress=60)
        annotated = await detect_fillers(merged)
        cut_count  = sum(1 for s in annotated if s.get("action") == "cut")
        keep_count = len(annotated) - cut_count
        await emit("step", step="filler", label=f"탐지 완료 — 유지 {keep_count} / 컷 {cut_count}", progress=78,
                   segments=annotated)

        # ── 3.5. 한글 번역 ────────────────────────────────
        await emit("step", step="filler", label="자막 한글 번역 중…", progress=82)
        keep_only = [s for s in annotated if s.get("action", "keep") == "keep"]
        translated = await asyncio.get_event_loop().run_in_executor(
            None, translate_segments, keep_only
        )
        # 번역 결과를 annotated에 다시 매핑
        trans_map = {(t["start"], t["end"]): t.get("text_translated") for t in translated}
        for s in annotated:
            tt = trans_map.get((s["start"], s["end"]))
            if tt:
                s["text_translated"] = tt

        # ── 4. XML + SRT 빌드 ─────────────────────────────
        await emit("step", step="draft", label="Premiere XML · 한글 SRT 생성 중…", progress=85)
        xml_path, srt_path = build_fcp7_xml(
            video_path=video_path,
            segments=annotated,
            output_dir=out_dir,
            fps=fps,
            width=width,
            height=height,
            sequence_name=Path(video_path).stem,
            total_duration=duration,
        )
        xml_name = Path(xml_path).name
        srt_name = Path(srt_path).name

        # 파일 크기 계산
        video_exts = {".mp4", ".mov", ".avi", ".mkv"}
        xml_size  = Path(xml_path).stat().st_size
        srt_size  = Path(srt_path).stat().st_size
        proj_size = sum(
            f.stat().st_size for f in Path(out_dir).iterdir()
            if f.is_file() and not f.name.startswith("_")
        )

        await emit("step", step="draft", label="드래프트 완성!", progress=100)

        _results[job_id] = {
            "job_id": job_id,
            "xml": xml_name,
            "srt": srt_name,
            "sizes": {
                "xml":     xml_size,
                "srt":     srt_size,
                "project": proj_size,
            },
            "stats": {
                "total_segments": len(annotated),
                "keep": keep_count,
                "cut": cut_count,
                "duration_original": round(duration, 1),
                "duration_edited": round(sum(
                    s["end"] - s["start"]
                    for s in annotated if s.get("action", "keep") == "keep"
                ), 1),
                "transcript": full_script,
            }
        }

        await emit("done",
                   xml=f"/download/{job_id}/{xml_name}",
                   srt=f"/download/{job_id}/{srt_name}",
                   result=_results[job_id])

    except Exception as e:
        import traceback
        traceback.print_exc()
        await emit("error", message=f"{type(e).__name__}: {e}")
    finally:
        # 영상은 0단계에서 이미 out_dir로 이동됨 (Premiere 참조용 보존)
        pass


def _merge_asr(silence_segs, asr_segs, tail_buffer: float = 1.0) -> list[dict]:
    """
    편집 단위 = ASR 문장 세그먼트.
    각 ASR 세그먼트가 발화 구간(silence_segs) 안에 실제로 걸쳐 있는 것만 채택.
    (정정/NG 판정은 문장 단위 granularity가 필요하므로 silence 덩어리가 아닌 ASR을 단위로 씀)
    """
    units = []
    for a in asr_segs:
        text = a.get("text", "").strip()
        if not text:
            continue
        # 발화 구간과 겹치는지 확인 (무음에 통째로 묻힌 환청 세그먼트 제외)
        if silence_segs:
            overlaps = any(
                min(ss.end, a["end"]) - max(ss.start, a["start"]) > 0.1
                for ss in silence_segs
            )
            if not overlaps:
                continue
        units.append({
            "start": round(a["start"], 3),
            "end": round(a["end"], 3),
            "text": text,
            "words": a.get("words", []),   # 더듬음 트림용
            "action": "keep",
            "reason": "",
        })

    # ASR이 비어 있으면 silence 구간으로 폴백 (자막 없는 점프컷)
    if not units:
        for ss in silence_segs:
            units.append({"start": ss.start, "end": ss.end, "text": "",
                          "action": "keep", "reason": ""})

    # 각 컷 끝에 여유 시간 추가 (다음 컷 시작을 넘지 않도록)
    for i, unit in enumerate(units):
        if i + 1 < len(units):
            next_start = units[i + 1]["start"]
            max_end = next_start  # 다음 컷 시작 직전까지만
        else:
            max_end = unit["end"] + tail_buffer  # 마지막 컷은 제한 없음
        unit["end"] = round(min(unit["end"] + tail_buffer, max_end), 3)

    return units


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
