#!/bin/bash
# open_in_premiere.sh <job_id>
# JSX 경로 치환 후 osascript DoScript로 Premiere에 프로젝트 자동 생성·임포트

JOB_ID="$1"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUTPUT_DIR="$SCRIPT_DIR/outputs/$JOB_ID"
PREMIERE_NAME="Adobe Premiere Pro 2025"
PREMIERE_APP="/Applications/$PREMIERE_NAME/$PREMIERE_NAME.app"

if [ -z "$JOB_ID" ] || [ ! -d "$OUTPUT_DIR" ]; then
  echo "❌ 잘못된 job_id 또는 출력 폴더 없음"; exit 1
fi

# 파일 탐색 (_cut.xml 우선, 구버전 _premiere.xml 폴백)
XML_PATH=$(find "$OUTPUT_DIR" -name "*_cut.xml" | head -1)
[ -z "$XML_PATH" ] && XML_PATH=$(find "$OUTPUT_DIR" -name "*_premiere.xml" | head -1)
SRT_PATH=$(find "$OUTPUT_DIR" \( -name "*_caption.srt" -o -name "*.srt" \) | head -1)
VIDEO_PATH=$(find "$OUTPUT_DIR" \( -name "*.mp4" -o -name "*.mov" -o -name "*.avi" -o -name "*.mkv" \) | head -1)

if [ -z "$XML_PATH" ];   then echo "❌ XML 없음";  exit 1; fi
if [ -z "$VIDEO_PATH" ]; then echo "❌ 영상 없음"; exit 1; fi

STEM=$(basename "$VIDEO_PATH")
STEM="${STEM%.*}"
PROJ_PATH="$OUTPUT_DIR/${STEM}.prproj"

echo "📄 XML:    $XML_PATH"
echo "💬 SRT:    ${SRT_PATH:-없음}"
echo "🎬 영상:   $VIDEO_PATH"
echo "📁 프로젝트: $PROJ_PATH"

# JSX 템플릿 경로 치환 → 임시 파일
JSX_TMP="$OUTPUT_DIR/_open.jsx"
sed -e "s|{{VIDEO_PATH}}|$VIDEO_PATH|g" \
    -e "s|{{XML_PATH}}|$XML_PATH|g" \
    -e "s|{{SRT_PATH}}|${SRT_PATH:-}|g" \
    -e "s|{{PROJ_PATH}}|$PROJ_PATH|g" \
    "$SCRIPT_DIR/open_in_premiere.jsx" > "$JSX_TMP"

# Premiere Pro 실행 (미실행 시 기동)
if ! pgrep -xq "$PREMIERE_NAME"; then
  echo "🚀 Premiere Pro 시작 중…"
  open -a "$PREMIERE_APP"
  # 응답 가능 상태가 될 때까지 최대 60초 대기
  for i in $(seq 1 30); do
    sleep 2
    if osascript -e 'tell application "'"$PREMIERE_NAME"'" to return name of application' 2>/dev/null | grep -q "$PREMIERE_NAME"; then
      echo "✅ Premiere Pro 준비됨 (${i}번째 시도)"
      break
    fi
  done
  sleep 4  # UI 완전 초기화 여유
else
  echo "✅ Premiere Pro 이미 실행 중"
  sleep 1
fi

# AppleScript: 파일 내용을 읽어 DoScript에 전달 (경로 문자열 직접 전달 불가)
AS_TMP="$OUTPUT_DIR/_open.applescript"
cat > "$AS_TMP" << APEOF
tell application "${PREMIERE_NAME}"
    activate
    set jsxContent to read POSIX file "${JSX_TMP}" as «class utf8»
    DoScript jsxContent
end tell
APEOF

echo "📜 스크립트 실행: $JSX_TMP"
osascript "$AS_TMP"
RESULT=$?

if [ $RESULT -eq 0 ]; then
  echo "✅ 프로젝트 열기 완료"
else
  echo "❌ DoScript 실패 (종료코드 $RESULT)"
  exit 1
fi
