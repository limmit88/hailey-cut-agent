"""
말 더듬음(stutter) 트림 — 단어 타임스탬프 기반
같은 단어가 연달아 반복되면(사이에 음/어 같은 필러가 끼어도) 마지막 1개만 남기고
앞의 반복 + 끼인 필러의 시간 구간을 잘라낸다.

예) "By, by, um, by making..."  → "by making..." (앞 'By, by, um,' 컷)
    "Because, because we..."    → "because we..." (앞 'Because,' 컷)
"""
import re

# 더듬음 사이에 끼는 필러 (이것들은 반복 사이에 있으면 함께 제거)
_STUTTER_FILLERS = {
    "um", "uh", "er", "ah", "hmm", "mm", "uhh", "umm",
    "음", "어", "그", "에", "저", "아",
}
# 반복으로 셀 때 무시할 앞뒤 위치 (단어 사이에 필러 몇 개까지 허용)
LOOKAHEAD = 3


def _norm(word: str) -> str:
    return re.sub(r"[^\w가-힣]", "", word.lower()).strip()


def _is_filler(norm_word: str) -> bool:
    return norm_word in _STUTTER_FILLERS


def trim_stutters(segments: list[dict]) -> list[dict]:
    """
    각 세그먼트의 words를 보고 더듬음 구간을 제거.
    더듬음이 중간에 있으면 세그먼트를 분할(앞뒤 깨끗한 구간만 유지).
    words가 없으면 원본 그대로 반환.
    """
    result: list[dict] = []

    for seg in segments:
        words = seg.get("words") or []
        if len(words) < 2:
            result.append(seg)
            continue

        norm = [_norm(w["word"]) for w in words]
        n = len(words)
        bad = [False] * n

        i = 0
        while i < n:
            wi = norm[i]
            if not wi or _is_filler(wi):
                i += 1
                continue
            # i 단어가 앞으로 LOOKAHEAD 안에서 다시 등장하면(사이 필러 허용) 더듬음
            k = i + 1
            steps = 0
            matched = -1
            while k < n and steps < LOOKAHEAD:
                if _is_filler(norm[k]):
                    k += 1
                    steps += 1
                    continue
                if norm[k] == wi:
                    matched = k
                break
            if matched != -1:
                # i..matched-1 (앞 반복 + 끼인 필러) 제거, matched(최종)만 유지
                for m in range(i, matched):
                    bad[m] = True
                i = matched
            else:
                i += 1

        # 살아남은 단어들을 연속 구간(group)으로 묶어 sub-segment 생성
        groups: list[list[dict]] = []
        cur: list[dict] = []
        prev_idx = None
        for idx in range(n):
            if bad[idx]:
                continue
            if prev_idx is None or idx == prev_idx + 1:
                cur.append(words[idx])
            else:
                if cur:
                    groups.append(cur)
                cur = [words[idx]]
            prev_idx = idx
        if cur:
            groups.append(cur)

        if not groups:
            result.append(seg)
            continue

        # 더듬음이 없었으면(모두 유지 + 1그룹) 원본 유지
        if len(groups) == 1 and not any(bad):
            result.append(seg)
            continue

        for g in groups:
            text = " ".join(w["word"].strip() for w in g)
            text = " ".join(text.split())
            if not text:
                continue
            result.append({
                **seg,
                "start": g[0]["start"],
                "end": g[-1]["end"],
                "text": text,
                "words": g,
            })

    return result
