"""
ASR — Mac(Apple Silicon): mlx_whisper / 서버(Linux): faster_whisper
캐시: content hash 기반
"""
import asyncio
import hashlib
import json
import os
import platform
import subprocess
from pathlib import Path

ASR_LOCK = asyncio.Lock()
CACHE_DIR = Path(__file__).parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

# LaunchAgent 등 PATH가 제한된 환경에서도 ffmpeg를 찾기 위해 Homebrew 경로 추가
_BREW_PATHS = ["/opt/homebrew/bin", "/usr/local/bin"]
_env = os.environ.copy()
_env["PATH"] = ":".join(_BREW_PATHS) + ":" + _env.get("PATH", "")

# 백엔드 선택
_IS_APPLE = platform.system() == "Darwin" and platform.machine() == "arm64"
_BACKEND = "mlx"
if _IS_APPLE:
    try:
        import mlx_whisper as _mlx
    except ImportError:
        _BACKEND = "faster"
else:
    _BACKEND = "faster"

if _BACKEND == "faster":
    from faster_whisper import WhisperModel as _FWModel
    _fw_model: "_FWModel | None" = None

    def _get_fw_model():
        global _fw_model
        if _fw_model is None:
            size = os.environ.get("WHISPER_MODEL", "base")
            _fw_model = _FWModel(size, device="cpu", compute_type="int8")
        return _fw_model


def _content_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()[:16]


def _extract_audio(video_path: str) -> str:
    wav_path = str(Path(video_path).with_suffix(".wav"))
    subprocess.run(
        ["ffmpeg", "-y", "-i", video_path,
         "-ar", "16000", "-ac", "1", "-vn", wav_path],
        capture_output=True, check=True, env=_env
    )
    return wav_path


def _transcribe_mlx(wav_path: str, model: str) -> dict:
    return _mlx.transcribe(
        wav_path,
        path_or_hf_repo=model,
        word_timestamps=True,
        verbose=False,
        condition_on_previous_text=False,
    )


def _transcribe_faster(wav_path: str) -> dict:
    fw = _get_fw_model()
    segments_gen, _ = fw.transcribe(
        wav_path,
        beam_size=5,
        word_timestamps=True,
        condition_on_previous_text=False,
        vad_filter=True,
    )
    segments = []
    full_text_parts = []
    for seg in segments_gen:
        words = [
            {"word": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3)}
            for w in (seg.words or [])
        ]
        segments.append({
            "start": round(seg.start, 3),
            "end": round(seg.end, 3),
            "text": seg.text.strip(),
            "words": words,
        })
        full_text_parts.append(seg.text.strip())
    return {"text": " ".join(full_text_parts), "segments": segments}


async def transcribe(
    video_path: str,
    model: str = "mlx-community/whisper-large-v3-turbo",
) -> dict:
    cache_key = _content_hash(video_path)
    cache_file = CACHE_DIR / f"{cache_key}.json"

    if cache_file.exists():
        with open(cache_file) as f:
            return json.load(f)

    async with ASR_LOCK:
        if cache_file.exists():
            with open(cache_file) as f:
                return json.load(f)

        wav_path = _extract_audio(video_path)
        try:
            loop = asyncio.get_event_loop()
            if _BACKEND == "mlx":
                raw = await loop.run_in_executor(
                    None, lambda: _transcribe_mlx(wav_path, model)
                )
                output = {
                    "text": raw.get("text", "").strip(),
                    "segments": [
                        {
                            "start": round(s["start"], 3),
                            "end": round(s["end"], 3),
                            "text": s["text"].strip(),
                            "words": [
                                {"word": w.get("word", "").strip(),
                                 "start": round(w.get("start", s["start"]), 3),
                                 "end": round(w.get("end", s["end"]), 3)}
                                for w in (s.get("words") or [])
                            ],
                        }
                        for s in raw.get("segments", [])
                    ],
                }
            else:
                output = await loop.run_in_executor(
                    None, lambda: _transcribe_faster(wav_path)
                )
        finally:
            if os.path.exists(wav_path):
                os.remove(wav_path)

    with open(cache_file, "w") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    return output
