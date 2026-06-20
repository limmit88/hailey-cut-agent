#!/bin/bash
# 이 파일을 더블클릭하면 백그라운드에서 서버가 실행되고 브라우저가 열립니다

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── 설치 여부 확인 ────────────────────────────────────────
if [ ! -d ".venv" ]; then
    osascript -e 'display alert "먼저 setup.command를 실행해 주세요" as critical'
    exit 1
fi

# ── 이미 실행 중이면 브라우저만 열기 ─────────────────────
if lsof -ti:8000 &>/dev/null; then
    open http://localhost:8000
    # 터미널 창 닫기
    osascript -e 'tell application "Terminal" to close front window' 2>/dev/null
    exit 0
fi

# ── 가상환경 활성화 ───────────────────────────────────────
source .venv/bin/activate

# ── 백그라운드로 서버 시작 ────────────────────────────────
mkdir -p logs
nohup python3 main.py > logs/server.log 2>&1 &
echo $! > .server.pid
disown

# ── 서버 준비 대기 (최대 15초) ───────────────────────────
for i in $(seq 1 30); do
    sleep 0.5
    if curl -s http://localhost:8000 &>/dev/null; then
        break
    fi
done

# ── 브라우저 열기 ─────────────────────────────────────────
open http://localhost:8000

# ── 터미널 창 자동 닫기 ───────────────────────────────────
sleep 0.5
osascript -e 'tell application "Terminal" to close front window' 2>/dev/null
