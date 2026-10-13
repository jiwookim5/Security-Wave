"""판정과 검출: 글 하나가 광고인지(classify), 요소 하나에서 어떤 기법의 검출이 나오는지,
프레임 하나와 그 안의 iframe 을 재귀로 훑어 검출을 모으는 방법(walk_frame).
"""
import re

import attachments as attach_mod
import evidence as evidence_mod
import lexicon
from extract_extra_js import BLOCK_SELECTORS, EXTRACT_EXTRA
from extract_js import EXTRACT
from normalize import (deleet_all, describe_homoglyph, describe_jamo, has_homoglyph,
                       has_jamo_obfuscation, normalize)
from selector_js import BUILD_SELECTOR
from urls import page_key


# 자식 iframe 요소 하나에 대해 (절대 src, 그 src 가 문서에서 유일한가, 유일하지 않을 때의 선택자)를
# 한 번의 왕복으로 구한다. iframe 마다 frame_element·get_property·json_value·개수 세기로 네 번 오가던 것을 줄였다.
FRAME_STEP_JS = "(el) => {" + BUILD_SELECTOR + """
  const s = el.src || '';
  const unique = !!s && !s.includes('"') &&
    Array.from(document.querySelectorAll('iframe')).filter((f) => (f.src || '') === s).length === 1;
  return { src: s, unique, selector: unique ? null : buildSelector(el) };
}"""


# 숨긴 글 추출(EXTRACT)과 추가 유형 추출(EXTRACT_EXTRA)을 한 번의 왕복으로 한다 (왕복 한 번이 수 ms 다).
# 둘 다 DOM 을 읽기만 하므로 순서대로 붙여 실행해도 따로 부를 때와 결과가 같다. 추가 유형이 실패하면 null.
EXTRACT_BOTH = ("() => { const nodes = (" + EXTRACT + ")(); let extra = null; try { extra = ("
                + EXTRACT_EXTRA + ")(); } catch (e) {} return [nodes, extra]; }")


def frame_step(parent, child):
    """부모 프레임에서 자식 iframe을 가리키는 location 조각을 만든다.

    요강은 src가 상대경로여도 절대주소로 적도록 요구한다.
    같은 src의 iframe이 여럿이거나 src가 없으면(스크립트로 채운 iframe) 일반 요소처럼
    유일한 선택자를 만든다. 문서 전체 순번을 :nth-of-type 에 넣으면, iframe 들이 서로 다른
    부모 안에 있을 때 아무것도 못 가리키거나 여럿을 가리킨다 (nth-of-type 은 형제 사이 순번).
    """
    info = parent.evaluate(FRAME_STEP_JS, child.frame_element())
    if info["unique"]:
        return f'iframe[src="{info["src"]}"]', info["src"]
    return info["selector"], info["src"]


VISIBLE_CODE = "VISIBLE_AD(게시판 노출 광고)"
VISIBLE_GUIDE = ("게시글·댓글을 삭제하고 작성자(아이피)를 차단합니다. 같은 문구가 반복해 올라오면 "
                 "자동 등록 방지(캡차)와 금칙어 필터에 이 문구의 연락처·핵심어를 추가합니다.")
_BOARDISH = re.compile(r"(board|bbs|visit|guest|comment|reply|cmt|view|article|post|content|"
                       r"subject|title|notice|qna|free)", re.I)


def visible_findings(frame, prefix, url, texts, hidden_texts):
    """화면에 그대로 보이는 광고 글. 숨긴 광고(주요 4종)와 겹치는 글은 빼고 보고한다."""
    picked = []
    for t in texts:
        text = t["text"]
        if any(h and (h in text or text in h) for h in hidden_texts):
            continue
        verdict = classify(text, strict=True)
        if verdict["is_ad"]:
            picked.append((t["i"], text, verdict))
    if not picked:
        return []
    try:
        sels = frame.evaluate(BLOCK_SELECTORS, [i for i, _, _ in picked])
    except Exception:
        return []
    rows = []
    for (_, text, verdict), selector in zip(picked, sels):
        if not selector:
            continue
        # 자모·닮은꼴 글자를 여러 요소에 나눠 쓴 글(<span>ㅋㅏ</span><span>ㅈㅣ</span>...)은
        # 조각마다 보면 광고가 아니고, 문단으로 합쳐야 위장이 드러난다. 보여도 주요 4종이다.
        disguise = disguise_techniques(text, verdict)
        for code, reason in disguise:
            rows.append({
                "url": url, "location": prefix + selector, "technique": code,
                "evidence_text": text, "normalized": verdict["normalized"],
                "reason": reason + " (여러 요소에 나눠 쓴 글을 합쳐 판정)",
                "keywords": verdict["evidence"], "extra_finding": None,
            })
        if disguise:
            continue
        where = "게시글·댓글" if _BOARDISH.search(selector + " " + url) else "본문"
        rows.append({
            "url": url, "location": prefix + selector, "technique": "ETC",
            "evidence_text": text, "normalized": verdict["normalized"],
            "reason": f"{where}에 그대로 보이는 광고 문구", "keywords": verdict["evidence"],
            "extra_finding": VISIBLE_CODE, "guide": VISIBLE_GUIDE,
        })
    return rows


def extra_findings(frame, prefix, url, data, attach=None, reflect=None, hidden_texts=(), linkcheck=None):
    """주요 4종 밖의 추가 탐지 유형을 모은다 (data: EXTRACT_EXTRA 결과). 결과는 result_extra.json 으로 간다."""
    if not data:
        return []
    rows = []

    def add(text, location, kind, reason):
        verdict = classify(text)
        if not verdict["is_ad"]:
            return
        rows.append({
            "url": url, "location": prefix + location, "technique": "ETC",
            "evidence_text": text, "normalized": verdict["normalized"],
            "reason": reason, "keywords": verdict["evidence"],
            "extra_finding": kind,
        })

    for m in data.get("metas", []):
        add(m["text"], m["selector"], "META_SPAM(메타 태그 오염)",
            f"{m['where']} 값에 광고 문구")
    for a in data.get("attrs", []):
        add(a["text"], a["selector"], "ATTR_SPAM(속성값 은닉)",
            f"{a['attr']} 속성에 광고 문구")
    for link in data.get("links", []):
        target = f"{link['text']} {link['href']}"
        add(target, link["selector"], "LINK_SPAM(외부 링크 삽입)",
            f"외부 주소로 나가는 링크: {link['href'][:60]}")
    if linkcheck is not None:
        linkcheck.collect(url, data.get("links", []), prefix)
    if attach is not None:
        files = [f for f in data.get("files", [])
                 if attach_mod.looks_like_attachment(f["href"], f["text"])]
        rows.extend(attach.check(url, files, prefix))
    if reflect is not None:
        rows.extend(reflect.check(url, data.get("forms", []), prefix))
    rows.extend(visible_findings(frame, prefix, url, data.get("texts", []), hidden_texts))
    return rows


class EvidenceMap(dict):
    """증거 키 -> 사진·원본. 같은 위치·같은 문구의 광고(공통 서식·위젯)는 처음 한 번만 찍고 다시 쓴다."""

    def __init__(self):
        super().__init__()
        self.by_content = {}


def walk_frame(frame, prefix, url, results, iframe_urls, evidence_dir=None, evid_map=None,
               attach=None, reflect=None, linkcheck=None):
    """프레임 하나를 훑고, 중첩된 iframe까지 재귀적으로 내려간다."""
    hits = []
    try:
        nodes, extra = frame.evaluate(EXTRACT_BOTH)
    except Exception:
        # 페이지 본문을 못 읽었으면 '광고 없음'이 아니라 '못 봄'이다. 부른 쪽이 실패로 남긴다.
        # 하위 iframe(바깥 위젯 등)은 막혀 있는 일이 흔해 그대로 넘어간다.
        if not prefix:
            raise
        nodes, extra = [], None
    # 숨긴 문장과 그 안의 꾸밈 태그(<b>·<a> 등)가 둘 다 광고면 문장 한 건으로 합친다 (extract_js.py 의 sp·full)
    merged_into, absorbed = set(), set()
    for i, node in enumerate(nodes):
        p = node.get("sp")
        if p is not None and findings_from_node(url, node) and findings_from_node(url, nodes[p]):
            absorbed.add(i)
            merged_into.add(p)
    reported = set()                     # 따로 광고로 잡힌 조각의 번호
    for i, node in enumerate(nodes):
        if i in absorbed:
            reported.add(i)
            continue
        # 쪼갠 조각을 합친 글은, 조각 가운데 하나라도 이미 잡혔으면 같은 광고를 두 번 세지 않도록 뺀다
        if node.get("parts") and reported.intersection(node["parts"]):
            continue
        if i in merged_into:
            node = dict(node, text=node["full"])
        rows = findings_from_node(url, node, prefix=prefix)
        if rows and node.get("full") and i not in merged_into:
            # 꾸밈 태그 글자를 빼면 근거 문구가 중간이 빈 문장이 된다. 원문 문장 그대로 적는다
            for r in rows:
                r["evidence_text"] = node["full"].strip()
        if not rows:
            continue
        reported.add(i)
        key = evidence_mod.key_for(url, rows[0]["location"])
        for r in rows:
            r["evidence_key"] = key
        hits.append((node, key))
        results.extend(rows)

    hidden_texts = [n["text"].strip() for n, _ in hits]
    results.extend(extra_findings(frame, prefix, url, extra, attach, reflect, hidden_texts, linkcheck))

    # 증거 촬영은 추출이 모두 끝난 뒤에 한다.
    # 은닉 해제가 DOM 을 바꾸므로 판정 도중에 섞이면 안 된다.
    if evidence_dir is not None and evid_map is not None:
        reuse = getattr(evid_map, "by_content", {})
        for node, key in hits:
            if key in evid_map:
                continue
            same = (prefix + node["selector"], node["text"].strip())
            if same not in reuse:
                image, outer = evidence_mod.capture(
                    frame, node["selector"], url, node["selector"], evidence_dir)
                reuse[same] = {"image": image, "html": outer}
            evid_map[key] = reuse[same]
    for child in frame.child_frames:
        # Playwright 는 페이지를 옮겨 사라진 iframe 을 최상위 프레임의 child_frames 에서 지우지 않는다.
        # 그대로 두면 페이지마다 사라진 iframe 이 하나씩 쌓여, 점검 시간이 페이지 수의 제곱으로 는다
        # (iframe 위젯이 있는 180페이지 누리집에서 실패 호출 1만 5천 번·18초).
        if child.is_detached():
            continue
        try:
            step, src = frame_step(frame, child)
        except Exception:
            continue
        if src:
            iframe_urls.add(page_key(src))
        walk_frame(child, prefix + step + " >>> ", url, results, iframe_urls,
                   evidence_dir, evid_map, attach, reflect, linkcheck)


_VERDICTS = {}           # (사전 판, 글, strict) -> 판정. 메뉴·하단 글은 페이지마다 같아 다시 판정하지 않는다
_VERDICTS_MAX = 50000


def classify(text: str, strict: bool = False):
    """한 텍스트 덩어리에 적용된 문자 난독화 기법과 광고 여부를 판정한다.

    strict 는 화면에 그대로 보이는 글에 쓴다 (lexicon.match 참고).
    같은 글은 기억해 둔 판정을 돌려준다 (돌려받은 dict 를 고치면 안 된다).
    """
    key = (lexicon.VERSION, text, strict)
    hit = _VERDICTS.get(key)
    if hit is None:
        if len(_VERDICTS) >= _VERDICTS_MAX:
            _VERDICTS.clear()
        hit = _VERDICTS[key] = _classify(text, strict)
    return hit


def _classify(text, strict):
    norm = normalize(text)
    homoglyph = has_homoglyph(text)
    jamo = has_jamo_obfuscation(text)
    is_ad, evidence = lexicon.match(norm, obfuscated=homoglyph or jamo, raw=text, strict=strict)
    # 요강의 닮은꼴 글자 위장에는 숫자로 글자를 바꾼 것(cas1n0)도 든다. 숫자를 되돌려야만
    # 사전 낱말이 읽히는 경우만 위장으로 본다 (모델명 'mp3'·'5G' 같은 표기는 해당 없음)
    leet = [w for w in evidence if w not in norm and any(w in a for a in deleet_all(norm))]
    if leet and not homoglyph:
        homoglyph = True
        if not jamo:            # 위장 신호를 반영해 다시 판정한다
            is_ad, evidence = lexicon.match(norm, obfuscated=True, raw=text, strict=strict)
    return {
        "normalized": norm,
        "is_ad": is_ad,
        "evidence": evidence,
        "leet": leet,
        "homoglyph": homoglyph,
        "jamo": jamo,
    }


def disguise_techniques(text, verdict):
    """문자 위장 기법(HOMOGLYPH·JAMO)과 그 설명."""
    out = []
    if verdict["homoglyph"]:
        out.append(("HOMOGLYPH", describe_homoglyph(text) if has_homoglyph(text) else
                    f"숫자를 글자 대신 섞음 ({', '.join(verdict['leet'])})"))
    if verdict["jamo"]:
        out.append(("JAMO", describe_jamo(text)))
    return out


def findings_from_node(url, node, prefix=""):
    """추출된 요소 하나에서 (기법별로 분리된) 검출 건들을 만든다."""
    text = node["text"].strip()
    if not text:
        return []
    # 화면에 보이는 글(닮은꼴·자모 위장만 있는 글)은 보이는 글 기준으로 엄격하게 본다
    hidden = node["transparent"] or node["offscreen"] or node.get("occluded")
    verdict = classify(text, strict=not hidden)
    if not verdict["is_ad"]:
        return []                      # 감춰져 있어도 광고가 아니면 보고하지 않는다

    location = prefix + node["selector"]
    techniques = disguise_techniques(text, verdict)
    if node["transparent"]:
        techniques.append(("TRANSPARENT", ", ".join(node["reasons"]) or "투명 처리"))
    if node["offscreen"]:
        techniques.append(("OFFSCREEN", ", ".join(node["reasons"]) or "화면 밖 은닉"))
    # 요강의 주요 4종에 없는 기법은 추가 유형으로 돌린다.
    # 주요 유형으로 올리면 정답셋에 없는 항목이 되어 정확도 배점만 깎인다.
    if node.get("occluded"):
        techniques.append(("OCCLUDED", "다른 요소에 덮여 보이지 않음"))

    out = []
    for code, reason in techniques:
        out.append({
            "url": url,
            "location": location,
            "technique": code,
            "evidence_text": text,
            "normalized": verdict["normalized"],
            "reason": reason,
            "keywords": verdict["evidence"],
            "extra_finding": "OCCLUDED(레이어 은폐)" if code == "OCCLUDED" else None,
        })
    return out
