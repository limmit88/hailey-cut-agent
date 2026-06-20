"""
번역 — DeepL API 무료 버전 기반 번역 (fallback: Google Translate)
"""
import json
import os
import re
import warnings
warnings.filterwarnings("ignore")

from deep_translator import GoogleTranslator, DeeplTranslator

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


def _translate_with_deepl(text: str, target: str = "ko", source: str = "auto") -> str:
    """
    DeepL 무료 API로 번역. DEEPL_API_KEY 환경변수 필요.
    """
    api_key = os.environ.get("DEEPL_API_KEY", "")
    if not api_key:
        return None

    try:
        # DeepL 언어 코드 변환 (ko → KO, auto → auto)
        target_lang = target.upper() if target != "auto" else "KO"
        source_lang = source.upper() if source != "auto" else None

        translator = DeeplTranslator(
            api_key=api_key,
            source=source_lang or "auto",
            target=target_lang,
            use_free_api=True  # 무료 API 사용
        )
        return translator.translate(text)
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
    우선순위: DeepL API → Google Translate (폴백)
    """
    result = []
    for seg in segments:
        text = seg.get("text", "").strip()

        if not text:
            result.append({**seg, "text_translated": text})
            continue

        # DeepL 먼저 시도
        translated = _translate_with_deepl(text, target, source)

        # 실패 시 Google Translate 폴백
        if not translated:
            translated = _translate_with_google(text, target, source)

        if concise:
            translated = _make_concise(translated)

        result.append({**seg, "text_translated": translated})

    return result
