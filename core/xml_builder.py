"""
FCP7 XML 빌더 — Premiere Pro File > Import 로 바로 열리는 시퀀스 생성
+ 별도 .srt 자막 파일 생성
"""
import math
import os
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.dom import minidom


def _frames(seconds: float, fps: float) -> int:
    return math.floor(seconds * fps)


def _srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


import re

# 한 줄 캡션 최대/최소 글자 수 (한글 기준)
MAX_CAPTION_CHARS = 18
MIN_CAPTION_CHARS = 7


def _split_caption(text: str, max_chars: int = MAX_CAPTION_CHARS,
                   min_chars: int = MIN_CAPTION_CHARS) -> list[str]:
    """
    긴 자막을 한 줄(max_chars 이하) 청크로 분할.
    - 문장부호(. ? !)에서만 끊음 (쉼표로는 안 끊어 조각화 방지)
    - max_chars까지 단어 단위로 채움
    - min_chars 미만 짧은 조각은 이웃과 병합 (깜빡임 방지)
    """
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return [text]

    sentences = re.split(r"(?<=[\.\?\!])\s+", text)

    chunks: list[str] = []
    for sent in sentences:
        words = sent.split()
        cur = ""
        for w in words:
            cand = w if not cur else f"{cur} {w}"
            if len(cand) > max_chars and cur:
                chunks.append(cur)
                cur = w
            else:
                cur = cand
        if cur:
            chunks.append(cur)

    # 한 단어가 너무 길면 강제 분할
    hard: list[str] = []
    for c in chunks:
        while len(c) > max_chars:
            hard.append(c[:max_chars])
            c = c[max_chars:]
        if c:
            hard.append(c)

    # 짧은 조각 병합 (이전 조각과 합쳐 max_chars+여유 이내면 병합)
    merged: list[str] = []
    for c in hard:
        if merged and (len(c) < min_chars or len(merged[-1]) < min_chars):
            if len(merged[-1]) + 1 + len(c) <= max_chars + 6:
                merged[-1] = f"{merged[-1]} {c}"
                continue
        merged.append(c)
    return merged or [text]


def _timebase_ntsc(fps: float) -> tuple[int, str]:
    """실수 fps → (정수 timebase, ntsc 플래그). 29.97/59.94 등 처리."""
    rounded = round(fps)
    # 소수 fps(NTSC 계열)면 올림 정수 + ntsc TRUE
    if abs(fps - rounded) > 0.01:
        return math.ceil(fps), "TRUE"
    # 29.97/59.94처럼 이미 반올림됐지만 NTSC인 흔한 값 보정
    if rounded in (30, 60, 24) and abs(fps - rounded) > 0.001:
        return rounded, "TRUE"
    return rounded, "FALSE"


def build_fcp7_xml(
    video_path: str,
    segments: list[dict],      # {start, end, text, action: keep|cut}
    output_dir: str,
    fps: float = 30.0,
    width: int = 1920,
    height: int = 1080,
    sequence_name: str = "Premiere Agent Export",
    total_duration: float = 0.0,
) -> tuple[str, str]:
    """
    Returns (xml_path, srt_path)
    segments의 action=="keep" 인 것만 시퀀스에 포함.
    video_path 는 XML이 참조할 최종 영상 경로여야 함 (이동 후 경로).
    """
    keep = [s for s in segments if s.get("action", "keep") == "keep"]
    if not keep:
        keep = segments  # 모두 자르면 원본 유지

    video_abs = str(Path(video_path).resolve())
    file_url = "file://" + video_abs
    stem = Path(video_path).stem
    timebase, ntsc = _timebase_ntsc(fps)

    def add_rate(parent):
        r = ET.SubElement(parent, "rate")
        ET.SubElement(r, "timebase").text = str(timebase)
        ET.SubElement(r, "ntsc").text = ntsc

    # ── 시퀀스 ────────────────────────────────────────────
    xmeml = ET.Element("xmeml", version="5")
    sequence = ET.SubElement(xmeml, "sequence", id="sequence-1")
    ET.SubElement(sequence, "name").text = sequence_name
    seq_duration = _frames(total_duration, fps) if total_duration > 0 else _frames(
        max(s["end"] for s in keep), fps
    )
    ET.SubElement(sequence, "duration").text = str(seq_duration)
    add_rate(sequence)

    media = ET.SubElement(sequence, "media")

    # ── 비디오 ────────────────────────────────────────────
    video = ET.SubElement(media, "video")
    # 시퀀스 포맷 특성
    vformat = ET.SubElement(video, "format")
    vsc = ET.SubElement(vformat, "samplecharacteristics")
    add_rate(vsc)
    ET.SubElement(vsc, "width").text = str(width)
    ET.SubElement(vsc, "height").text = str(height)
    ET.SubElement(vsc, "pixelaspectratio").text = "square"
    v_track = ET.SubElement(video, "track")

    # ── 오디오 ────────────────────────────────────────────
    audio = ET.SubElement(media, "audio")
    a_track = ET.SubElement(audio, "track")

    file_id = f"file-{stem}"

    def make_file_elem(parent):
        """첫 클립에 들어가는 완전한 file 정의"""
        felem = ET.SubElement(parent, "file", id=file_id)
        ET.SubElement(felem, "name").text = Path(video_path).name
        ET.SubElement(felem, "pathurl").text = file_url
        add_rate(felem)
        fmedia = ET.SubElement(felem, "media")
        fv = ET.SubElement(fmedia, "video")
        fvsc = ET.SubElement(fv, "samplecharacteristics")
        add_rate(fvsc)
        ET.SubElement(fvsc, "width").text = str(width)
        ET.SubElement(fvsc, "height").text = str(height)
        fa = ET.SubElement(fmedia, "audio")
        fasc = ET.SubElement(fa, "samplecharacteristics")
        ET.SubElement(fasc, "depth").text = "16"
        ET.SubElement(fasc, "samplerate").text = "48000"
        ET.SubElement(fa, "channelcount").text = "2"

    first = True
    for idx, seg in enumerate(keep):
        clip_in  = _frames(seg["start"], fps)
        clip_out = _frames(seg["end"],   fps)
        duration = clip_out - clip_in
        if duration <= 0:
            continue

        # 비디오 clipitem — 원본 타임코드 위치 그대로 배치 (갭 유지)
        ci = ET.SubElement(v_track, "clipitem", id=f"clipitem-v{idx}")
        ET.SubElement(ci, "name").text = stem
        ET.SubElement(ci, "duration").text = str(duration)
        add_rate(ci)
        ET.SubElement(ci, "start").text = str(clip_in)
        ET.SubElement(ci, "end").text   = str(clip_out)
        ET.SubElement(ci, "in").text    = str(clip_in)
        ET.SubElement(ci, "out").text   = str(clip_out)
        if first:
            make_file_elem(ci)
        else:
            ET.SubElement(ci, "file", id=file_id)
        # 비디오-오디오 링크
        for ltype, lref in (("video", f"clipitem-v{idx}"), ("audio", f"clipitem-a{idx}")):
            link = ET.SubElement(ci, "link")
            ET.SubElement(link, "linkclipref").text = lref
            ET.SubElement(link, "mediatype").text = ltype

        # 오디오 clipitem
        ai = ET.SubElement(a_track, "clipitem", id=f"clipitem-a{idx}")
        ET.SubElement(ai, "name").text = stem
        ET.SubElement(ai, "duration").text = str(duration)
        add_rate(ai)
        ET.SubElement(ai, "start").text = str(clip_in)
        ET.SubElement(ai, "end").text   = str(clip_out)
        ET.SubElement(ai, "in").text    = str(clip_in)
        ET.SubElement(ai, "out").text   = str(clip_out)
        ET.SubElement(ai, "file", id=file_id)
        atrk = ET.SubElement(ai, "sourcetrack")
        ET.SubElement(atrk, "mediatype").text = "audio"
        for ltype, lref in (("video", f"clipitem-v{idx}"), ("audio", f"clipitem-a{idx}")):
            link = ET.SubElement(ai, "link")
            ET.SubElement(link, "linkclipref").text = lref
            ET.SubElement(link, "mediatype").text = ltype

        first = False

    # ── SRT 생성 (원본 타임코드 기준) ────────────────────
    srt_lines = []
    srt_idx = 1
    for seg in keep:
        dur = seg["end"] - seg["start"]
        # 번역문이 있으면 우선 사용 (한글 자막)
        text = (seg.get("text_translated") or seg.get("text", "")).strip()
        text = " ".join(text.split())
        if text:
            # 긴 자막은 한 줄 청크로 분할, 시간은 글자 수 비례 분배
            chunks = _split_caption(text)
            total_chars = sum(len(c) for c in chunks) or 1
            chunk_cursor = seg["start"]
            for c in chunks:
                c_dur = dur * (len(c) / total_chars)
                srt_lines += [
                    str(srt_idx),
                    f"{_srt_time(chunk_cursor)} --> {_srt_time(chunk_cursor + c_dur)}",
                    c,
                    ""
                ]
                srt_idx += 1
                chunk_cursor += c_dur

    # ── 저장 ──────────────────────────────────────────────
    os.makedirs(output_dir, exist_ok=True)
    xml_path = os.path.join(output_dir, f"{stem}_cut.xml")
    srt_path = os.path.join(output_dir, f"{stem}_caption.srt")

    raw_xml = ET.tostring(xmeml, encoding="unicode")
    dom = minidom.parseString(raw_xml)
    pretty = dom.toprettyxml(indent="  ")
    lines = pretty.split("\n")
    lines.insert(1, '<!DOCTYPE xmeml>')
    with open(xml_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # Premiere 캡션 호환: UTF-8 BOM + CRLF 줄바꿈 + 끝에 빈 줄
    # (BOM 없으면 한글 등 비ASCII가 빈 캡션으로 임포트됨)
    srt_body = "\r\n".join(srt_lines)
    if not srt_body.endswith("\r\n"):
        srt_body += "\r\n"
    with open(srt_path, "wb") as f:
        f.write(b"\xef\xbb\xbf" + srt_body.encode("utf-8"))

    return xml_path, srt_path
