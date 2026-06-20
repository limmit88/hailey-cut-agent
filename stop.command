#!/bin/bash
# 이 파일을 더블클릭하면 Hailey Cut Agent 서버가 종료됩니다

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

STOPPED=false

# PID 파일로 종료
if [ -f ".server.pid" ]; then
    PID=$(cat .server.pid)
    if kill "$PID" 2>/dev/null; then
        STOPPED=true
    fi
    rm -f .server.pid
fi

# 포트 8000 강제 정리
if lsof -ti:8000 &>/dev/null; then
    lsof -ti:8000 | xargs kill -9 2>/dev/null
    STOPPED=true
fi

if $STOPPED; then
    osascript -e 'display notification "Hailey Cut Agent가 종료됐어요" with title "Hailey Cut Agent"'
else
    osascript -e 'display notification "실행 중인 서버가 없어요" with title "Hailey Cut Agent"'
fi

sleep 0.3
osascript -e 'tell application "Terminal" to close front window' 2>/dev/null
