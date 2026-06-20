#!/bin/bash
# 이 파일을 더블클릭하면 터미널이 열리며 자동 설치됩니다

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── 색상 ──────────────────────────────────────────────────
G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; B='\033[1;34m'; N='\033[0m'

echo ""
echo -e "${B}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${N}"
echo -e "${B}   🎬  Hailey Cut Agent  설치 시작         ${N}"
echo -e "${B}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${N}"
echo ""

# ── 1. Homebrew ───────────────────────────────────────────
if ! command -v brew &>/dev/null; then
    echo -e "${Y}[1/5] Homebrew 설치 중… (비밀번호 입력이 필요할 수 있어요)${N}"
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    # Apple Silicon PATH 설정
    if [ -f "/opt/homebrew/bin/brew" ]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
        echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> "$HOME/.zprofile"
    fi
else
    echo -e "${G}[1/5] Homebrew ✓${N}"
fi

# ── 2. FFmpeg ─────────────────────────────────────────────
if ! command -v ffmpeg &>/dev/null; then
    echo -e "${Y}[2/5] FFmpeg 설치 중…${N}"
    brew install ffmpeg
else
    echo -e "${G}[2/5] FFmpeg ✓${N}"
fi

# ── 3. Python 3.10+ ───────────────────────────────────────
PYTHON=""
for cmd in python3.12 python3.11 python3.10 python3; do
    if command -v "$cmd" &>/dev/null; then
        VER=$("$cmd" -c "import sys; print(sys.version_info >= (3,10))" 2>/dev/null)
        if [ "$VER" = "True" ]; then PYTHON="$cmd"; break; fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo -e "${Y}[3/5] Python 3.11 설치 중…${N}"
    brew install python@3.11
    PYTHON=python3.11
else
    echo -e "${G}[3/5] Python ($("$PYTHON" --version)) ✓${N}"
fi

# ── 4. 가상환경 + 패키지 ──────────────────────────────────
echo -e "${Y}[4/5] 가상환경 및 패키지 설치 중… (5~10분 소요)${N}"

if [ ! -d ".venv" ]; then
    "$PYTHON" -m venv .venv
fi
source .venv/bin/activate
pip install --upgrade pip -q

pip install -r requirements.txt

# Apple Silicon → mlx-whisper 추가 (빠른 로컬 ASR)
if [ "$(uname -m)" = "arm64" ]; then
    echo -e "   ${Y}→ Apple Silicon 감지: mlx-whisper 설치 중…${N}"
    pip install mlx-whisper -q
fi

# ── 5. .env 설정 ──────────────────────────────────────────
echo ""
echo -e "${B}[5/5] API 키 설정${N}"
if [ -f ".env" ] && grep -q "ANTHROPIC_API_KEY=sk-" .env 2>/dev/null; then
    echo -e "${G}   Anthropic API 키가 이미 설정돼 있어요 ✓${N}"
else
    echo    "   Anthropic API 키를 입력하면 번역 품질이 높아져요."
    echo    "   없으면 그냥 Enter를 누르세요 (Google Translate 사용)"
    echo -n "   API 키 (sk-ant-...): "
    read -r API_KEY
    if [ -n "$API_KEY" ]; then
        echo "ANTHROPIC_API_KEY=$API_KEY" > .env
        echo -e "${G}   저장 완료 ✓${N}"
    else
        touch .env
        echo    "   건너뜀 — Google Translate로 동작해요"
    fi
fi

# ── 완료 ──────────────────────────────────────────────────
echo ""
echo -e "${G}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${N}"
echo -e "${G}   ✅  설치 완료!                           ${N}"
echo -e "${G}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${N}"
echo ""
echo    "   ▶  run.command 를 더블클릭하면 실행돼요"
echo ""
read -p "   Enter 를 눌러 창을 닫으세요…" _
