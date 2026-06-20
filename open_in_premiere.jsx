/**
 * open_in_premiere.jsx
 * 1. 새 프로젝트 생성
 * 2. 원본 영상 임포트
 * 3. FCP7 XML 시퀀스 임포트
 * 4. SRT 자막 임포트
 *
 * 실행: Premiere Pro → 파일 → 스크립트 → 스크립트 실행
 * 또는 osascript로 자동 실행 (open_in_premiere.sh 참고)
 */

// ── 경로 설정 (open_in_premiere.sh 가 치환해서 넘김) ───────
var VIDEO_PATH = "{{VIDEO_PATH}}";
var XML_PATH   = "{{XML_PATH}}";
var SRT_PATH   = "{{SRT_PATH}}";
var PROJ_PATH  = "{{PROJ_PATH}}";

(function () {
    // ── 1. 새 프로젝트 생성 ────────────────────────────────
    app.newProject(PROJ_PATH);
    var project = app.project;

    // ── 2. 원본 영상 임포트 ────────────────────────────────
    var importArr = [VIDEO_PATH];
    project.importFiles(importArr, false, project.rootItem, false);

    // ── 3. FCP7 XML 시퀀스 임포트 ─────────────────────────
    // XML은 시퀀스로 임포트됨
    project.importFiles([XML_PATH], false, project.rootItem, false);

    // ── 4. SRT 자막 임포트 (캡션 트랙으로) ────────────────
    project.importFiles([SRT_PATH], false, project.rootItem, false);

    // ── 5. 임포트된 시퀀스를 타임라인에서 열기 ────────────
    var seq = null;
    for (var i = 0; i < project.sequences.numSequences; i++) {
        var s = project.sequences[i];
        if (s.name.indexOf("_cut") !== -1 || s.name.indexOf("Agent") !== -1) {
            seq = s;
            break;
        }
    }
    // 못 찾으면 첫 번째 시퀀스라도 열기
    if (!seq && project.sequences.numSequences > 0) {
        seq = project.sequences[0];
    }
    if (seq) {
        app.project.openSequence(seq.sequenceID);
    }

    // 프로젝트 저장 → ZIP에 포함될 수 있도록
    app.project.save();

    alert("✅ Hailey Cut Agent 프로젝트 열기 완료!\n\n"
        + "· 영상: " + VIDEO_PATH.split("/").pop() + "\n"
        + "· 편집 시퀀스 타임라인 확인 후 재생으로 검증하세요.\n"
        + "· SRT 자막은 프로젝트 패널에서 시퀀스로 드래그하세요.");
})();
