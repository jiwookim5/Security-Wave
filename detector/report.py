"""붙임4 표준 스키마에 맞춰 결과 파일을 쓴다.

스키마를 어기면 평가 대상에서 제외되므로 필드 구성과 인코딩을 엄격히 지킨다.
- UTF-8, BOM 없음
- 최상위는 meta 와 findings 두 키
- 검출이 없어도 findings 는 빈 배열로 반드시 존재
- technique 은 코드 1개만 (배열·복수 나열 금지)
"""
import os

from fileio import write_json

MAIN_CODES = {"HOMOGLYPH", "JAMO", "TRANSPARENT", "OFFSCREEN"}
TOOL_VERSION = "1.0.0"
COVERAGE_FILE = "scan_coverage.json"

# 열지 못한 사유 (session.fail_reason)
FAIL_NAMES = {
    "timeout": "응답 시간 초과", "network": "접속 오류", "server": "서버 오류(5xx)",
    "blocked": "접근 거부(401·403·429)", "error": "열기 오류", "partial": "열렸지만 끝까지 읽지 못함",
}
STOP_NAMES = {
    "user": "담당자가 탐지를 중지해 일부 페이지만 점검했습니다.",
    "time": "점검 시간 상한에 닿아 일부 페이지만 점검했습니다.",
    "blocked": "페이지가 잇달아 열리지 않아 점검을 멈췄습니다. 서버가 요청을 막았거나 접속 장애가 의심됩니다.",
}


def coverage_lines(res):
    """점검 범위를 사람이 읽을 문장 몇 줄로. 아무 문제 없으면 빈 목록."""
    cov = res.get("coverage") or {}
    out = []
    if res.get("stopped") in STOP_NAMES:
        out.append(STOP_NAMES[res["stopped"]])
    if cov.get("failed_count"):
        kinds = cov.get("failed_kinds") or {}
        out.append(f"열지 못했거나 끝까지 읽지 못한 페이지 {cov['failed_count']}개 ("
                   + ", ".join(f"{FAIL_NAMES.get(k, k)} {n}" for k, n in kinds.items()) + ")")
    if (res.get("ocr_images") or {}).get("unavailable"):
        out.append("그림 속 글자 검사를 하지 못했습니다: " + res["ocr_images"]["unavailable"])
    if cov.get("left_count") and not res.get("stopped"):
        out.append(f"최대 페이지 수({cov.get('max_pages')})에 닿아 주소 {cov['left_count']}개를 열지 않았습니다.")
    elif cov.get("left_count"):
        out.append(f"열지 않은 주소 {cov['left_count']}개가 남았습니다.")
    return out


def _meta(entry_url, res):
    return {
        "topic": "TOPIC",
        "entry_url": entry_url,
        "started_at": res["started"].isoformat(timespec="seconds"),
        "finished_at": res["finished"].isoformat(timespec="seconds"),
        "elapsed_sec": round(res["elapsed"], 3),
        "tool_version": TOOL_VERSION,
    }


def write(entry_url, res, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    main_rows, extra_rows = [], []
    for r in res["findings"]:
        (main_rows if r["technique"] in MAIN_CODES else extra_rows).append(r)

    main = {"meta": _meta(entry_url, res), "findings": [
        {
            "id": f"f_{i:03d}",
            "url": r["url"],
            "is_violation": True,
            "location": r["location"],
            "evidence_text": r["evidence_text"],
            "technique": r["technique"],
        } for i, r in enumerate(main_rows, 1)
    ]}

    extra = {"meta": _meta(entry_url, res), "findings": [
        {
            "id": f"e_{i:03d}",
            "url": r["url"],
            # 검색창 반사 '취약'처럼 광고가 아직 없는 예방 점검 결과는 위반이 아니다
            "is_violation": r.get("is_violation", True),
            "location": r["location"],
            "evidence_text": r["evidence_text"],
            "technique": "ETC",
            "extra_finding": r.get("extra_finding") or r["technique"],
        } for i, r in enumerate(extra_rows, 1)
    ]}

    # 점검 범위(열지 못한 페이지·못 본 주소)는 표준 스키마에 넣을 자리가 없어 따로 쓴다.
    # '검출 0건'이 깨끗해서인지 열지 못해서인지 이 파일로 가린다.
    cov = {"meta": _meta(entry_url, res), "stopped": res.get("stopped"),
           **(res.get("coverage") or {})}

    paths = {}
    for name, doc in (("result.json", main), ("result_extra.json", extra), (COVERAGE_FILE, cov)):
        path = os.path.join(out_dir, name)
        write_json(path, doc, indent=2)
        paths[name] = path
    return paths, len(main_rows), len(extra_rows)
