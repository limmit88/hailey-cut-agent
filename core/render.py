"""
편집 구간 이어붙이기 + 자막 굽기 (ffmpeg)
- keep 세그먼트만 잘라 concat → 편집본
- SRT 자막을 영상에 burn-in
"""
import os
import subprocess
from pathlib import Path


def render_with_subtitles(
    video_path: str,
    segments: list[dict],     # {start, end, action}
    srt_path: str,
    output_path: str,
    font_size: int = 22,
) -> str:
    """
    keep 세그먼트를 이어붙이고 SRT 자막을 burn-in 한 mp4 생성.
    반환: output_path
    """
    keep = [s for s in segments if s.get("action", "keep") == "keep"]
    if not keep:
        keep = segments

    # ── filter_complex: 각 keep 구간 trim → concat ────────
    parts = []
    concat_v = ""
    concat_a = ""
    for i, seg in enumerate(keep):
        s, e = seg["start"], seg["end"]
        parts.append(
            f"[0:v]trim=start={s}:end={e},setpts=PTS-STARTPTS[v{i}];"
            f"[0:a]atrim=start={s}:end={e},asetpts=PTS-STARTPTS[a{i}]"
        )
        concat_v += f"[v{i}]"
        concat_a += f"[a{i}]"

    n = len(keep)
    filtergraph = ";".join(parts)
    filtergraph += f";{concat_v}concat=n={n}:v=1:a=0[vout]"
    filtergraph += f";{concat_a}concat=n={n}:v=0:a=1[aout]"

    out_dir = str(Path(output_path).parent)
    os.makedirs(out_dir, exist_ok=True)

    # ── Pass 1: keep 구간 concat → 임시 편집본 ────────────
    tmp_edited = os.path.join(out_dir, "_tmp_edited.mp4")
    cmd1 = [
        "ffmpeg", "-y", "-i", video_path,
        "-filter_complex", filtergraph,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        tmp_edited,
    ]
    r1 = subprocess.run(cmd1, capture_output=True, text=True)
    if r1.returncode != 0:
        raise RuntimeError(f"ffmpeg concat 실패:\n{r1.stderr[-2000:]}")

    # ── Pass 2: 자막 burn-in (작업 디렉토리에서 파일명만 사용) ──
    # 쉘 없이 호출하므로 따옴표 X, force_style 내부 콤마는 \, 로 이스케이프
    style = (
        f"FontSize={font_size}\\,"
        "PrimaryColour=&H00FFFFFF\\,"
        "OutlineColour=&H00000000\\,"
        "BorderStyle=1\\,Outline=2\\,Shadow=1\\,"
        "Alignment=2\\,MarginV=40"
    )
    srt_name = Path(srt_path).name
    out_name = Path(output_path).name
    cmd2 = [
        "ffmpeg", "-y", "-i", "_tmp_edited.mp4",
        "-vf", f"subtitles={srt_name}:force_style={style}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "copy",
        out_name,
    ]
    r2 = subprocess.run(cmd2, capture_output=True, text=True, cwd=out_dir)
    if r2.returncode != 0:
        raise RuntimeError(f"ffmpeg 자막 굽기 실패:\n{r2.stderr[-2000:]}")

    if os.path.exists(tmp_edited):
        os.remove(tmp_edited)
    return output_path
