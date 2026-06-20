#!/bin/bash
# 이 파일을 더블클릭하면 Hailey Cut Agent가 실행됩니다

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; B='\033[1;34m'; N='\033[0m'

# ── 설치 여부 확인 ────────────────────────────────────────
if [ ! -d ".venv" ]; then
    echo -e "${R}❌ 먼저 setup.command 를 실행해 주세요${N}"
    read -p "   Enter 를 눌러 창을 닫으세요…" _
    exit 1
fi

# ── 이미 실행 중인지 확인 ─────────────────────────────────
if lsof -ti:8000 &>/dev/null; then
    echo -e "${G}✅ Hailey Cut Agent 가 이미 실행 중이에요${N}"
    echo    "   브라우저를 열게요…"
    open http://localhost:8000
    exit 0
fi

source .venv/bin/activate

echo ""
echo -e "${B}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${N}"
echo -e "${B}   🎬  Hailey Cut Agent  시작 중…          ${N}"
echo -e "${B}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${N}"
echo ""

# ── 서버 실행 ─────────────────────────────────────────────
python3 main.py &
SERVER_PID=$!

# 서버 준비 대기 (최대 15초)
echo -n "   서버 준비 중"
for i in $(seq 1 30); do
    sleep 0.5
    if curl -s http://localhost:8000 &>/dev/null; then
        echo ""
        break
    fi
    echo -n "."
done

# ── 브라우저 열기 ─────────────────────────────────────────
open http://localhost:8000

echo -e "${G}   ✅ 브라우저에서 열렸습니다 → http://localhost:8000${N}"
echo ""
echo    "   ⛔  종료하려면 이 창을 닫으세요"
echo ""

# 서버 유지 (창 닫으면 같이 종료)
trap "kill $SERVER_PID 2>/dev/null; echo ''; echo '서버가 종료됐습니다.'" EXIT
wait $SERVER_PID
