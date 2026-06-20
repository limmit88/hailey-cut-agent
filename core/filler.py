"""
규칙 기반 잔말·NG·중복(질문/답변) 탐지 — API 없이 로컬 동작

핵심 규칙:
1. 잔말 단독 세그먼트 → cut
2. 미완성 발화 (짧고 단어 적음) → cut
3. 중복 제거 (forward-dedup):
   - 같은 타입(질문↔질문, 답변↔답변)끼리 비교
   - 뒤쪽 window 안에 동일 내용(단어 60%↑ 겹침)이 또 나오면 → 앞의 것 cut, 마지막만 keep
   - 질문 중복 = 같은 질문 반복 → 최종 질문만 남김
   - 답변 중복 = 정정 전 동일 발화 → 최종 발화만 남김
4. 질문-답변 구조 보존: 고유한 질문은 절대 컷되지 않음
"""
import re

# 뒤로 몇 세그먼트까지 중복을 탐색할지 (정정/반복은 직후에 발생: Q→A시도→Q'→A' 거리 2)
DEDUP_WINDOW = 2
# 동일 내용으로 간주할 단어 겹침 임계값
DEDUP_THRESHOLD = 0.6
# 두 세그먼트의 핵심 단어 수 비율 (조각 vs 긴 문장 오매칭 방지)
LENGTH_RATIO_GUARD = 0.7

_FILLER_ONLY = re.compile(
    r"^[\s,\.]*"
    r"(음+|어+|그+|아+|저+|뭐+|어어+|있잖아?|잠깐만?|네+|예+|응+|으음+|흠+|"
    r"uh+|um+|er+|ah+|like|you know|so|well|okay|ok|right|hmm+)"
    r"[\s,\.]*$",
    re.IGNORECASE
)

_QUESTION = re.compile(
    r"(\?|할까요|인가요|인지|나요|까요|세요|ㄴ가요|"
    r"what|who|when|where|why|how|can you|could you|do you|did you|"
    r"tell me|would you|introduce)",
    re.IGNORECASE
)

# 의미 비교에서 제외할 불용어 (정정 표현 + 인사 + 기능어)
_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "and", "or", "but",
    "my", "your", "his", "her", "i", "you", "he", "she", "it",
    "to", "of", "in", "on", "at", "for", "with", "by",
    "hello", "hi", "okay", "ok", "good", "well", "so", "um", "uh",
    "wait", "sorry", "actually", "can", "could", "would",
    "one", "more", "time", "again", "say", "please",
}


def _is_question(text: str) -> bool:
    return bool(_QUESTION.search(text))


def _is_fragment(seg: dict) -> bool:
    words = seg.get("text", "").split()
    dur = seg["end"] - seg["start"]
    return len(words) <= 2 and dur < 3.0


def _content_words(text: str) -> set:
    """불용어 제거한 핵심 단어 집합 (소문자, 구두점 제거)"""
    words = re.findall(r"[\w가-힣]+", text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 1}


def _content_overlap(a: str, b: str) -> float:
    wa, wb = _content_words(a), _content_words(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / min(len(wa), len(wb))


def _length_ratio(a: str, b: str) -> float:
    """핵심 단어 수 비율 (작은 쪽/큰 쪽). 조각-긴문장 오매칭 차단용."""
    la, lb = len(_content_words(a)), len(_content_words(b))
    if not la or not lb:
        return 0.0
    return min(la, lb) / max(la, lb)


async def detect_fillers(segments: list[dict]) -> list[dict]:
    if not segments:
        return []

    result = [{**s, "action": "keep", "reason": ""} for s in segments]
    n = len(result)

    # ── 1·2단계: 잔말 / 미완성 발화 컷 ────────────────────
    for i, seg in enumerate(result):
        text = seg.get("text", "").strip()
        if _is_question(text):
            continue  # 질문은 잔말/미완성으로 보지 않음
        if _FILLER_ONLY.match(text):
            result[i]["action"] = "cut"
            result[i]["reason"] = "잔말"
        elif _is_fragment(seg):
            result[i]["action"] = "cut"
            result[i]["reason"] = "미완성 발화"

    # ── 3단계: forward-dedup (같은 타입끼리 마지막만 유지) ──
    for i in range(n):
        if result[i]["action"] == "cut":
            continue
        text_i = result[i].get("text", "")
        is_q = _is_question(text_i)

        # 뒤쪽 window에서 같은 타입 + 동일 내용 탐색
        for j in range(i + 1, min(i + 1 + DEDUP_WINDOW, n)):
            if result[j]["action"] == "cut":
                continue
            text_j = result[j].get("text", "")
            if _is_question(text_j) != is_q:
                continue  # 타입 다르면 비교 안 함 (질문↔답변 혼동 방지)
            if _length_ratio(text_i, text_j) < LENGTH_RATIO_GUARD:
                continue  # 길이 차이 크면 (조각 vs 긴 문장) 중복 아님
            if _content_overlap(text_i, text_j) >= DEDUP_THRESHOLD:
                # i(앞)를 컷, j(뒤=최종)를 유지
                result[i]["action"] = "cut"
                kind = "질문" if is_q else "발화"
                result[i]["reason"] = f"중복 {kind} (#{j+1}에서 최종 진술)"
                result[j]["reason"] = f"최종 {kind} 유지"
                break

    return result
