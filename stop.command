#!/bin/bash
# 이 파일을 더블클릭하면 서버를 종료하거나 자동 시작을 해제할 수 있습니다

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PLIST_FILE="$HOME/Library/LaunchAgents/com.hailey.cut-agent.plist"
AUTO_ENABLED=false
[ -f "$PLIST_FILE" ] && AUTO_ENABLED=true

# ── 메뉴 ──────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   🎬  Hailey Cut Agent  종료 메뉴"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if $AUTO_ENABLED; then
    echo "   1) 지금만 종료  (다음 로그인 때 다시 자동 시작)"
    echo "   2) 종료 + 자동 시작 해제"
    echo ""
    echo -n "   선택 (1 또는 2): "
    read -r CHOICE
else
    CHOICE="1"
fi

# ── 서버 종료 ─────────────────────────────────────────────
_stop_server() {
    local stopped=false
    if [ -f ".server.pid" ]; then
        kill "$(cat .server.pid)" 2>/dev/null && stopped=true
        rm -f .server.pid
    fi
    if lsof -ti:8000 &>/dev/null; then
        lsof -ti:8000 | xargs kill -9 2>/dev/null
        stopped=true
    fi
    $stopped
}

case "$CHOICE" in
    2)
        if $AUTO_ENABLED; then
            launchctl unload "$PLIST_FILE" 2>/dev/null
            rm -f "$PLIST_FILE"
            _stop_server
            osascript -e 'display notification "서버 종료 + 자동 시작 해제 완료" with title "Hailey Cut Agent"'
        fi
        ;;
    *)
        if $AUTO_ENABLED; then
            launchctl stop com.hailey.cut-agent 2>/dev/null
        fi
        _stop_server
        osascript -e 'display notification "서버가 종료됐어요 (자동 시작은 유지)" with title "Hailey Cut Agent"'
        ;;
esac

sleep 0.3
osascript -e 'tell application "Terminal" to close front window' 2>/dev/null
