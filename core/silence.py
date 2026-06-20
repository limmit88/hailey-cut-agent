"""
ffmpeg silencedetect → keep_segments (말하는 구간 리스트)
"""
import re
import subprocess
from dataclasses import dataclass


@dataclass
class Segment:
    start: float
    end: float
    text: str = ""  # ASR 결과 채워짐


def detect_silence(video_path: str, noise_db: float = -40, min_silence: float = 0.4) -> list[Segment]:
    """무음 구간을 제거하고 발화 구간만 반환"""
    cmd = [
        "ffmpeg", "-i", video_path,
        "-af", f"silencedetect=noise={noise_db}dB:d={min_silence}",
        "-f", "null", "-"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    stderr = result.stderr

    # silence_start / silence_end 파싱
    starts = [float(m) for m in re.findall(r"silence_start: ([\d.]+)", stderr)]
    ends   = [float(m) for m in re.findall(r"silence_end: ([\d.]+)", stderr)]

    # 영상 총 길이
    dur_match = re.search(r"Duration: (\d+):(\d+):([\d.]+)", stderr)
    total = 0.0
    if dur_match:
        h, m, s = dur_match.groups()
        total = int(h) * 3600 + int(m) * 60 + float(s)

    # silence 구간의 역(= 발화 구간) 계산
    keep: list[Segment] = []
    cursor = 0.0

    for s_start, s_end in zip(starts, ends):
        if s_start > cursor + 0.05:
            tail_end = min(s_start + 1.0, s_end)
            keep.append(Segment(start=round(cursor, 3), end=round(tail_end, 3)))
        cursor = s_end

    if total > cursor + 0.05:
        keep.append(Segment(start=round(cursor, 3), end=round(total, 3)))

    return keep


def get_video_fps(video_path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=r_frame_rate",
         "-of", "default=noprint_wrappers=1:nokey=1", video_path],
        capture_output=True, text=True
    )
    raw = result.stdout.strip()
    if "/" in raw:
        num, den = raw.split("/")
        return round(float(num) / float(den), 3)
    return 30.0


def get_video_duration(video_path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", video_path],
        capture_output=True, text=True
    )
    return float(result.stdout.strip() or "0")


def get_video_dimensions(video_path: str) -> tuple[int, int]:
    """영상 가로·세로 픽셀 반환"""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height",
         "-of", "csv=s=x:p=0", video_path],
        capture_output=True, text=True
    )
    raw = result.stdout.strip()
    if "x" in raw:
        w, h = raw.split("x")[:2]
        return int(w), int(h)
    return 1920, 1080
