"""결재·보고에 붙일 수 있는 인쇄용 점검 결과 보고서.

화면의 결과를 한 장짜리 HTML 로 만든다. 앱 창에서 열어 [인쇄]를 누르면
PDF 로 저장하거나 종이로 출력할 수 있다. 증거 사진은 같은 서버에서 불러온다.
"""
import html
from collections import Counter

from report import FAIL_NAMES

TECH_NAMES = {
    "HOMOGLYPH": "닮은꼴 글자 위장", "JAMO": "자모 분해",
    "TRANSPARENT": "투명 텍스트", "OFFSCREEN": "화면 밖 은닉", "ETC": "추가 유형",
}
STATUS_NAMES = {"open": "미조치", "done": "조치완료", "fp": "오탐 처리"}
CHECK_NAMES = {"gone": "사라짐", "deleted": "페이지 삭제됨", "present": "아직 있음",
               "unknown": "확인 못 함", "skipped": "다시 점검으로 확인"}


def check_text(f):
    """'10/02 14:03 확인: 사라짐' 처럼 조치 확인 결과를 한 줄로. 확인한 적 없으면 빈 문자열."""
    if not f.get("check"):
        return ""
    when = (f.get("checked_at") or "").replace("T", " ")[5:16].replace("-", "/")
    return f"{when} 확인: {CHECK_NAMES.get(f['check'], f['check'])}"
STOP_NOTE = {
    "user": "담당자가 탐지를 중지해 일부 페이지만 점검한 결과입니다.",
    "time": "점검 시간 상한에 닿아 일부 페이지만 점검한 결과입니다.",
    "blocked": "페이지가 잇달아 열리지 않아 점검을 멈췄습니다. 서버가 요청을 막았거나 접속 장애가 의심됩니다.",
}
FAIL_SHOW = 100     # 보고서에 적는 열지 못한 페이지 수 (나머지는 scan_coverage.json)


def _e(v):
    return html.escape("" if v is None else str(v))


def _kind(f):
    if f["technique"] == "ETC" and f.get("extra_finding"):
        return f["extra_finding"].split("(", 1)[-1].rstrip(")")
    return TECH_NAMES.get(f["technique"], f["technique"])


def _when(iso):
    return (iso or "").replace("T", " ")[:16]


def _manner(p):
    """요청 간격·robots.txt 준수 여부. 대상 기관에 점검 방식을 설명할 때 쓴다."""
    if not p or not p.get("enabled"):
        return "빠른 점검 (요청 간격 없음)"
    text = f"천천히 점검 (페이지 사이 {p.get('delay', 0):g}초 간격"
    if p.get("respect_robots"):
        text += ", robots.txt 준수"
        if p.get("skipped_by_robots"):
            text += f" — 막힌 주소 {p['skipped_by_robots']}개 건너뜀"
    return text + ")"


SHARED_MIN = 3     # 이만큼 많은 페이지에 같은 광고가 있으면 공통 서식에 든 것으로 보고 한 줄로 묶는다


def shared_groups(rows):
    """(같은 위치·기법·문구로 여러 페이지에 든 광고 묶음들, 그 밖의 항목들)."""
    groups = {}
    for f in rows:
        groups.setdefault((f["technique"], f["location"], f["evidence_text"]), []).append(f)
    shared = [g for g in groups.values() if len({f["url"] for f in g}) >= SHARED_MIN]
    inside = {id(f) for g in shared for f in g}
    return shared, [f for f in rows if id(f) not in inside]


def build(payload, review=None):
    meta = payload.get("meta") or {}
    rows = payload.get("findings") or []
    if not meta:
        return "<!doctype html><meta charset=utf-8><p style='font:15px sans-serif;padding:24px'>" \
               "아직 탐지 결과가 없습니다.</p>"
    kinds = Counter(_kind(f) for f in rows)
    states = Counter(f["status"] for f in rows)
    pages = len({f["url"] for f in rows})
    hist = meta.get("history")

    parts = [f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<title>불법광고 점검 결과 보고</title>
<style>
@font-face{{font-family:"Pretendard";src:url("/fonts/PretendardVariable.woff2") format("woff2");font-weight:45 920}}
:root{{--line:#d4d4d8;--faint:#52525b;--red:#b91c1c}}
*{{box-sizing:border-box}}
body{{font-family:"Pretendard","Malgun Gothic",sans-serif;color:#18181b;background:#fff;margin:0;
  padding:28px 32px;font-size:13.5px;line-height:1.55}}
h1{{font-size:22px;margin:0 0 4px}}
h2{{font-size:16px;margin:26px 0 8px;padding-bottom:4px;border-bottom:2px solid #18181b}}
.sub{{color:var(--faint);margin:0 0 18px}}
table{{border-collapse:collapse;width:100%}}
th,td{{border:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}}
th{{background:#f4f4f5;font-weight:600;white-space:nowrap}}
table.meta th{{width:130px}}
td.num{{text-align:right;font-variant-numeric:tabular-nums;width:80px}}
.ev{{word-break:break-all}}
code{{font-family:Consolas,monospace;font-size:12px;word-break:break-all}}
.new{{display:inline-block;background:var(--red);color:#fff;border-radius:4px;padding:0 6px;
  font-size:11.5px;margin-left:4px}}
.note{{border:1px solid var(--red);color:var(--red);padding:8px 12px;border-radius:6px;margin:12px 0}}
.shot img{{max-width:320px;max-height:180px;border:1px solid var(--line);margin-top:6px}}
.bar{{position:sticky;top:0;background:#fff;padding:8px 0 12px;display:flex;gap:8px}}
.bar button{{font:inherit;padding:6px 14px;border:1px solid #18181b;background:#18181b;color:#fff;
  border-radius:6px;cursor:pointer}}
.bar button.ghost{{background:#fff;color:#18181b}}
.sign{{margin-top:30px;width:auto;margin-left:auto}}
.sign td{{width:90px;height:56px}}
@media print{{.bar{{display:none}} body{{padding:0}} tr{{break-inside:avoid}} h2{{break-after:avoid}}}}
</style></head><body>
<div class="bar"><button onclick="print()">인쇄 · PDF로 저장</button>
<button class="ghost" onclick="window.close()">닫기</button></div>
<h1>누리집 불법광고 점검 결과 보고</h1>
<p class="sub">훤히 — 공공 누리집 숨은 불법광고 탐지 도구로 자동 점검한 결과입니다.</p>
<table class="meta">
<tr><th>점검 대상</th><td>{_e(meta.get("entry_url"))}</td></tr>
<tr><th>점검 완료 시각</th><td>{_e(_when(meta.get("finished_at")))}</td></tr>
<tr><th>확인한 페이지</th><td>{_e(meta.get("page_count"))}개 · 소요 {_e(meta.get("elapsed_sec"))}초</td></tr>
<tr><th>점검하지 못한 곳</th><td>{_e(" / ".join(meta.get("coverage_lines") or []) or "없음")}</td></tr>
<tr><th>점검 방식</th><td>{_e(_manner(meta.get("politeness")))}</td></tr>
<tr><th>찾은 광고</th><td><b>{len(rows)}건</b> (광고가 있는 페이지 {pages}개)</td></tr>
<tr><th>조치 상태</th><td>미조치 {states.get("open", 0)}건 · 조치완료 {states.get("done", 0)}건 ·
 오탐 처리 {states.get("fp", 0)}건</td></tr>
</table>"""]
    if meta.get("stopped"):
        parts.append(f'<p class="note">{_e(STOP_NOTE.get(meta["stopped"], ""))}</p>')

    cov = meta.get("coverage") or {}
    if cov.get("failed"):
        parts.append("<h2>열지 못한 페이지</h2><p>아래 페이지는 이번 점검에서 확인하지 못했습니다. "
                     "광고가 없다는 뜻이 아니므로 접속 상태를 확인한 뒤 다시 점검하십시오.</p>"
                     "<table><tr><th>페이지</th><th>사유</th></tr>")
        for f in cov["failed"][:FAIL_SHOW]:
            why = FAIL_NAMES.get(f["reason"], f["reason"]) + (f" ({f['status']})" if f.get("status") else "")
            parts.append(f'<tr><td class="ev">{_e(f["url"])}</td><td>{_e(why)}</td></tr>')
        if cov.get("failed_count", 0) > FAIL_SHOW:
            parts.append(f'<tr><td colspan="2">외 {cov["failed_count"] - FAIL_SHOW}개 (scan_coverage.json)</td></tr>')
        parts.append("</table>")

    parts.append("<h2>유형별 건수</h2><table><tr><th>유형</th><th>건수</th></tr>")
    for k, n in kinds.most_common():
        parts.append(f'<tr><td>{_e(k)}</td><td class="num">{n}</td></tr>')
    if not kinds:
        parts.append('<tr><td colspan="2">찾은 광고가 없습니다.</td></tr>')
    parts.append("</table>")

    if hist:
        new = sum(1 for f in rows if f.get("is_new"))
        parts.append(f"""<h2>지난 점검과 비교</h2>
<table class="meta">
<tr><th>지난 점검</th><td>{_e(_when(hist.get("prev_finished")))} · {hist.get("prev_count", 0)}건</td></tr>
<tr><th>이번에 새로 생김</th><td>{new}건</td></tr>
<tr><th>이번에 사라짐</th><td>{hist.get("gone_count", 0)}건 (지워졌거나 조치된 것으로 보임)</td></tr>
</table>""")
        if hist.get("gone"):
            parts.append("<table style='margin-top:8px'><tr><th>페이지</th><th>유형</th><th>지난번 원문</th></tr>")
            for g in hist["gone"]:
                parts.append(f'<tr><td class="ev">{_e(g.get("url"))}</td><td>{_e(_kind(g))}</td>'
                             f'<td class="ev">{_e((g.get("evidence_text") or "")[:160])}</td></tr>')
            parts.append("</table>")

    parts.append("<h2>상세 목록</h2>")
    if rows:
        parts.append("<table><tr><th>번호</th><th>페이지 · 위치</th><th>유형 · 근거</th>"
                     "<th>광고 원문</th><th>조치</th></tr>")
        shared, rest = shared_groups(rows)
        items = [(g[0], g) for g in shared] + [(f, None) for f in rest]
        for f, same in items:
            where = f'{_e(f["url"])}'
            if same:
                urls = sorted({r["url"] for r in same})
                more = f" 외 {len(urls) - 5}곳" if len(urls) > 5 else ""
                where = (f'<b>공통 서식 · 페이지 {len(urls)}곳</b><br>'
                         + "<br>".join(_e(u) for u in urls[:5]) + more)
                states_in = Counter(STATUS_NAMES.get(r["status"], r["status"]) for r in same)
            shot = (f'<div class="shot"><img src="{_e(f["evidence_image"])}" alt="증거 사진"></div>'
                    if f.get("evidence_image") else "")
            memo = f'<br><small>{_e(f["memo"])}</small>' if f.get("memo") else ""
            if check_text(f):
                memo = f'<br><small>{_e(check_text(f))}</small>' + memo
            parts.append(
                f'<tr><td>{_e(f["id"])}{"<span class=new>새로</span>" if f.get("is_new") else ""}</td>'
                f'<td class="ev">{where}<br><code>{_e(f["location"])}</code></td>'
                f'<td>{_e(_kind(f))}<br><small>{_e(f.get("reason"))}</small></td>'
                f'<td class="ev">{_e(f["evidence_text"][:300])}{shot}</td>'
                f'<td>{_e(" · ".join(f"{k} {n}" for k, n in states_in.items()) if same else STATUS_NAMES.get(f["status"], f["status"]))}{memo}</td></tr>')
        parts.append("</table>")
    else:
        parts.append("<p>찾은 광고가 없습니다.</p>")

    parts.append("""<table class="sign"><tr><th>담당</th><th>검토</th><th>승인</th></tr>
<tr><td></td><td></td><td></td></tr></table>
</body></html>""")
    return "\n".join(parts)
