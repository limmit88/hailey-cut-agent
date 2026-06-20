#!/bin/bash
# 이 파일을 더블클릭하면 터미널이 열리며 자동 설치됩니다

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; B='\033[1;34m'; N='\033[0m'

echo ""
echo -e "${B}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${N}"
echo -e "${B}   🎬  Hailey Cut Agent  설치 시작         ${N}"
echo -e "${B}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${N}"
echo ""

# ── 1. Homebrew ───────────────────────────────────────────
if ! command -v brew &>/dev/null; then
    echo -e "${Y}[1/6] Homebrew 설치 중… (비밀번호 입력이 필요할 수 있어요)${N}"
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    if [ -f "/opt/homebrew/bin/brew" ]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
        echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> "$HOME/.zprofile"
    fi
else
    echo -e "${G}[1/6] Homebrew ✓${N}"
fi

# ── 2. FFmpeg ─────────────────────────────────────────────
if ! command -v ffmpeg &>/dev/null; then
    echo -e "${Y}[2/6] FFmpeg 설치 중…${N}"
    brew install ffmpeg
else
    echo -e "${G}[2/6] FFmpeg ✓${N}"
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
    echo -e "${Y}[3/6] Python 3.11 설치 중…${N}"
    brew install python@3.11
    PYTHON=python3.11
else
    echo -e "${G}[3/6] Python ($("$PYTHON" --version)) ✓${N}"
fi

# ── 4. 가상환경 + 패키지 ──────────────────────────────────
echo -e "${Y}[4/6] 가상환경 및 패키지 설치 중… (5~10분 소요)${N}"

if [ ! -d ".venv" ]; then
    "$PYTHON" -m venv .venv
fi
source .venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt

if [ "$(uname -m)" = "arm64" ]; then
    echo -e "   ${Y}→ Apple Silicon 감지: mlx-whisper 설치 중…${N}"
    pip install mlx-whisper -q
fi

# ── 5. .env 설정 ──────────────────────────────────────────
echo ""
echo -e "${B}[5/6] API 키 설정${N}"
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

# ── 6. 맥 시작 시 자동 실행 설정 ─────────────────────────
echo ""
echo -e "${B}[6/6] 맥북 재시작 시 자동 실행 설정${N}"
echo    "   설정하면 맥북을 켤 때마다 서버가 자동으로 시작돼요."
echo -n "   자동 시작을 설정할까요? (y/n): "
read -r AUTO_START

PLIST_FILE="$HOME/Library/LaunchAgents/com.hailey.cut-agent.plist"

if [ "$AUTO_START" = "y" ] || [ "$AUTO_START" = "Y" ]; then
    mkdir -p "$HOME/Library/LaunchAgents" logs

    cat > "$PLIST_FILE" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.hailey.cut-agent</string>
    <key>ProgramArguments</key>
    <array>
        <string>$SCRIPT_DIR/.venv/bin/python</string>
        <string>$SCRIPT_DIR/main.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$SCRIPT_DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$SCRIPT_DIR/logs/server.log</string>
    <key>StandardErrorPath</key>
    <string>$SCRIPT_DIR/logs/server.log</string>
</dict>
</plist>
PLIST

    launchctl load "$PLIST_FILE" 2>/dev/null
    echo -e "${G}   ✅ 자동 시작 설정 완료 — 지금 바로 서버도 켜졌어요${N}"
else
    echo    "   건너뜀 — run.command 로 수동 실행하면 돼요"
fi

# ── 완료 ──────────────────────────────────────────────────
echo ""
echo -e "${G}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${N}"
echo -e "${G}   ✅  설치 완료!                           ${N}"
echo -e "${G}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${N}"
echo ""
if [ "$AUTO_START" = "y" ] || [ "$AUTO_START" = "Y" ]; then
    echo    "   ▶  run.command 를 더블클릭하면 브라우저가 열려요"
    echo    "   ⛔  자동 시작을 끄려면 stop.command 를 더블클릭하세요"
else
    echo    "   ▶  run.command 를 더블클릭하면 실행돼요"
fi
echo ""
read -p "   Enter 를 눌러 창을 닫으세요…" _
