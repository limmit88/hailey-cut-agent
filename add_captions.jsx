/**
 * add_captions.jsx
 * 현재 열린(활성) 시퀀스에 SRT를 캡션 트랙으로 자동 부착.
 * 경로는 open_in_premiere.sh 가 {{SRT_PATH}} 치환.
 */
#target premierepro

(function () {
    var SRT_PATH = "{{SRT_PATH}}";

    var proj = app.project;
    if (!proj) { return; }

    var seq = proj.activeSequence;
    if (!seq) { return; }

    // 1) SRT 임포트 → 프로젝트 패널에 캡션 항목 생성
    var bin = proj.rootItem;
    proj.importFiles([SRT_PATH], true, bin, false);

    // 2) 임포트된 캡션 항목 찾기 (.srt 이름 매칭)
    var base = SRT_PATH.split("/").pop().replace(/\.srt$/i, "");
    var captionItem = null;
    function walk(item) {
        for (var i = 0; i < item.children.numItems; i++) {
            var c = item.children[i];
            if (c.type === ProjectItemType.BIN) {
                var f = walk(c);
                if (f) return f;
            } else if (c.name && c.name.indexOf(base) !== -1) {
                return c;
            }
        }
        return null;
    }
    captionItem = walk(bin);
    if (!captionItem) { return; }

    // 3) 활성 시퀀스 0초 지점에 캡션 삽입 (캡션 트랙 자동 생성)
    var t = new Time();
    t.ticks = "0";
    try {
        seq.insertClip(captionItem, t);
    } catch (e) {
        try {
            // 폴백: 첫 비디오 트랙에 오버라이트
            seq.videoTracks[0].insertClip(captionItem, t);
        } catch (e2) {}
    }
})();
