"""
번역 — Claude API 기반 컨텍스트 인식 번역 (fallback: Google Translate)
전체 세그먼트를 한 번에 전달해 발음 불명확·전사 오류를 문맥으로 교정한 뒤 번역
"""
import json
import os
import re
import warnings
warnings.filterwarnings("ignore")

from deep_translator import GoogleTranslator

_CONCISE_RULES = [
    (r"당신의\s*", ""),
    (r"당신\s*자신을?", "본인"),
    (r"당신을?\s*", ""),
    (r"하실\s*수\s*있나요\??", "해주세요"),
    (r"할\s*수\s*있나요\??", "해주세요"),
    (r"해\s*주시겠어요\??", "해주세요"),
    (r"말씀해\s*주시겠어요\??", "말해주세요"),
    (r"수\s*있습니까\??", "되나요"),
    (r"\s+", " "),
]


def _make_concise(text: str) -> str:
    out = text
    for pat, repl in _CONCISE_RULES:
        out = re.sub(pat, repl, out)
    return out.strip()


def _translate_with_claude(segments: list[dict]):
    """
    Claude에게 전체 세그먼트를 한 번에 전달.
    문맥과 어긋나는 발음 오류를 교정한 뒤 한국어로 번역.
    반환값: {세그먼트 인덱스: 번역문} 또는 None(실패 시)
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        seg_list = [
            {"id": i, "text": s.get("text", "").strip()}
            for i, s in enumerate(segments)
            if s.get("text", "").strip()
        ]
        if not seg_list:
            return {}

        prompt = f"""아래는 영상 자동 전사(ASR) 세그먼트 목록입니다.
각 세그먼트를 한국어 자막으로 번역하되, 다음 규칙을 따르세요.

규칙:
1. 전체 문맥을 먼저 파악하세요.
2. 발음 불명확·전사 오류로 의심되는 단어는 앞뒤 문맥에서 올바른 표현을 유추해 교정한 뒤 번역하세요.
3. 자막이므로 간결하게 작성하세요 (한 줄 18자 이하 권장).
4. 결과는 JSON 배열만 출력하세요. 다른 설명은 불필요합니다.
   형식: [{{"id": 0, "translated": "번역문"}}, ...]

세그먼트:
{json.dumps(seg_list, ensure_ascii=False, indent=2)}"""

        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = message.content[0].text.strip()
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if not match:
            return None

        items = json.loads(match.group())
        return {item["id"]: item["translated"] for item in items}

    except Exception:
        return None


def _translate_with_google(text: str, target: str, source: str) -> str:
    try:
        translator = GoogleTranslator(source=source, target=target)
        return translator.translate(text) or text
    except Exception:
        return text


def translate_segments(segments: list[dict], target: str = "ko", source: str = "auto",
                       concise: bool = True) -> list[dict]:
    """
    각 세그먼트의 text를 번역해 'text_translated' 필드에 저장.
    Claude API 가능 시 전체 문맥 인식 번역, 불가 시 Google Translate 폴백.
    """
    # Claude로 전체 일괄 번역 시도
    claude_map = _translate_with_claude(segments)

    result = []
    for i, seg in enumerate(segments):
        text = seg.get("text", "").strip()

        if not text:
            result.append({**seg, "text_translated": text})
            continue

        if claude_map is not None:
            translated = claude_map.get(i, text)
        else:
            # 폴백: Google Translate 개별 번역
            translated = _translate_with_google(text, target, source)

        if concise:
            translated = _make_concise(translated)

        result.append({**seg, "text_translated": translated})

    return result
