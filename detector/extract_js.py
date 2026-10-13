"""브라우저 안에서 실행되는 추출 스크립트.

페이지당 한 번만 호출해서 텍스트를 가진 요소 전체의 스타일 정보와
유일성이 검증된 CSS 선택자를 한꺼번에 가져온다. 왕복을 줄여야
검출 시간 배점(20점)을 지킬 수 있다.

일반 텍스트 노드 외에 ::before/::after content 와 Shadow DOM 내부도 훑는다.
선택자로 지목할 수 없는 영역(가상 요소·섀도 내부)은 호스트 요소를 위치로 보고한다.

숨긴 상자 안에서 <span>안전</span><span>놀이터</span> 처럼 광고를 여러 요소로 쪼개면
조각마다 점수가 모자라 빠진다. 그래서 가장 바깥 숨김 상자 단위로 조각을 합친 글도 함께 돌려준다
(parts: 합친 조각의 번호). 조각 가운데 하나라도 따로 광고로 잡혔으면 합친 글은 보고하지 않는다(scan.py).
"""

from selector_js import BUILD_SELECTOR

EXTRACT = r"""
() => {
  const OFFSCREEN_LIMIT = -1000;
  // 화면에 글자로 나타나지 않는 태그. 스크립트 소스를 본문으로 오인하면 오탐이 쏟아진다.
  const NON_TEXT = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'TITLE', 'META', 'LINK']);
  const out = [];
  const els = [];     // out[i] 가 요소 자신의 글자일 때 그 요소 (가상 요소·섀도 내부는 null)

  // 요강 표기 규칙에 맞는 선택자를 만들되, 반드시 유일해야 한다 (selector_js.py).
  BUILD_SELECTOR

  function parseRGB(v) {
    const m = (v || '').match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(',').map(x => parseFloat(x.trim()));
    return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
  }

  const up = (cur) => cur.parentElement || (cur.getRootNode() && cur.getRootNode().host);

  // 글자 뒤에 칠해지는 바탕색들. 그림 바탕(url)이면 색을 알 수 없으므로 null 을 돌려준다
  // (어두운 배너 그림 위 흰 글씨를 '흰 바탕 흰 글씨'로 오판하지 않기 위함).
  // 그라데이션은 그 안의 색들을 모두 돌려주고, 판정은 어느 색과도 구분되지 않을 때만 투명으로 본다.
  // html·body 에 깐 무늬 그림은 바탕색이 함께 지정돼 있으면 그 색으로 본다.
  // 요소마다 조상을 끝까지 다시 오르지 않도록 요소별 결과를 기억한다 (추출 중에는 DOM 이 바뀌지 않는다)
  const bgCache = new Map();
  function effectiveBgs(el) {
    if (!el || el.nodeType !== 1) return [{ r: 255, g: 255, b: 255, a: 1 }];
    if (bgCache.has(el)) return bgCache.get(el);
    const cs = getComputedStyle(el);
    const c = parseRGB(cs.backgroundColor);
    const img = cs.backgroundImage || 'none';
    let r;
    if (img !== 'none' && /url\(/.test(img)) {
      const page = el === document.body || el === document.documentElement;
      r = page && c && c.a > 0.1 ? [c] : null;
    } else {
      const stops = img === 'none' ? [] :
        (img.match(/rgba?\([^)]+\)/g) || []).map(parseRGB).filter((x) => x && x.a > 0.1);
      r = stops.length ? stops : c && c.a > 0.1 ? [c] : effectiveBgs(up(el));
    }
    bgCache.set(el, r);
    return r;
  }

  function luminance(c) {
    const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
  }

  // 길이 값 하나를 px 로. 퍼센트는 기준 길이(base)에 대한 비율.
  function len(v, base) {
    v = (v || '').trim();
    if (v.endsWith('%')) return parseFloat(v) / 100 * base;
    return parseFloat(v) || 0;
  }

  // clip-path 가 남기는 영역이 사실상 0 인가. 원·타원 반지름 0, inset 이 서로 맞닿음, 넓이 0 인 다각형.
  function clipPathZero(cp, rect) {
    if (!cp || cp === 'none') return false;
    const w = rect.width, h = rect.height;
    let m;
    if ((m = cp.match(/^circle\(\s*([-\d.]+)(px|%)?/))) return parseFloat(m[1]) <= 0.5;
    if ((m = cp.match(/^ellipse\(\s*([-\d.]+)(px|%)?\s+([-\d.]+)(px|%)?/)))
      return parseFloat(m[1]) <= 0.5 || parseFloat(m[3]) <= 0.5;
    if ((m = cp.match(/^inset\(([^)]*?)(\s+round\b[^)]*)?\)/))) {
      const p = m[1].trim().split(/\s+/);
      const [t, r, b, l] = [p[0], p[1] || p[0], p[2] || p[0], p[3] || p[1] || p[0]];
      return len(t, h) + len(b, h) >= h - 0.5 || len(l, w) + len(r, w) >= w - 0.5;
    }
    if ((m = cp.match(/^polygon\(([^)]*)\)/))) {
      const pts = m[1].replace(/^\s*(nonzero|evenodd)\s*,/, '').split(',')
        .map(s => s.trim().split(/\s+/)).map(([x, y]) => [len(x, w), len(y, h)]);
      let area = 0;
      for (let i = 0; i < pts.length; i++) {
        const [x1, y1] = pts[i], [x2, y2] = pts[(i + 1) % pts.length];
        area += x1 * y2 - x2 * y1;
      }
      return Math.abs(area) / 2 < 1;
    }
    return false;
  }

  // clip: rect(top, right, bottom, left) — 절대 위치 요소에만 적용된다. auto 는 제한 없음.
  function clipRectZero(cs) {
    if (!/^(absolute|fixed)$/.test(cs.position)) return false;
    const m = (cs.clip || '').match(/^rect\(([^)]*)\)/);
    if (!m) return false;
    const v = m[1].split(/[\s,]+/).filter(Boolean).map(x => x === 'auto' ? null : parseFloat(x));
    if (v.length !== 4) return false;
    const [t, r, b, l] = v;
    return (r !== null && l !== null && r - l <= 0.5) || (b !== null && t !== null && b - t <= 0.5);
  }

  // filter: opacity(0.02) 처럼 필터로 흐리게 만든 정도
  function filterOpacity(f) {
    let o = 1;
    for (const m of (f || '').matchAll(/opacity\(\s*([\d.]+)(%)?\s*\)/g))
      o *= m[2] ? parseFloat(m[1]) / 100 : parseFloat(m[1]);
    return o;
  }

  // 조상 사슬에서 결정되는 은닉 (섀도 호스트도 거슬러 올라간다). 부모의 결과에 자신을 더해 기억한다
  const NOT_HIDDEN = { displayNone: false, opacityZero: false, clipPath: false };
  const inhCache = new Map();
  function inherited(el) {
    if (!el || el.nodeType !== 1) return NOT_HIDDEN;
    let v = inhCache.get(el);
    if (v) return v;
    const p = inherited(up(el));
    const s = getComputedStyle(el);
    v = {
      displayNone: p.displayNone || s.display === 'none',
      // 0.02 처럼 0에 가까운 값도 은닉이다. filter:opacity() 도 같은 효과다.
      opacityZero: p.opacityZero || parseFloat(s.opacity) <= 0.05 || filterOpacity(s.filter) <= 0.05,
      clipPath: p.clipPath || (!!s.clipPath && s.clipPath !== 'none' &&
                               clipPathZero(s.clipPath, el.getBoundingClientRect())),
    };
    inhCache.set(el, v);
    return v;
  }

  // 글자가 실제로 칠해지는 자리. 들여쓰기·줄바꿈 금지로 상자 밖에 나간 글자도 잡으려면
  // 요소 상자가 아니라 텍스트 노드의 범위를 재야 한다.
  function textRect(el) {
    let box = null;
    for (const n of el.childNodes) {
      if (n.nodeType !== 3 || !n.nodeValue.trim()) continue;
      const range = document.createRange();
      range.selectNodeContents(n);
      const r = range.getBoundingClientRect();
      if (!r.width && !r.height) continue;
      box = box ? { left: Math.min(box.left, r.left), top: Math.min(box.top, r.top),
                    right: Math.max(box.right, r.right), bottom: Math.max(box.bottom, r.bottom) }
                : { left: r.left, top: r.top, right: r.right, bottom: r.bottom };
    }
    return box;
  }

  // 조상의 overflow:hidden/clip 영역 밖으로 완전히 밀려났는가.
  // 절대 위치 요소는 위치가 지정된 조상(담는 블록)에서만 잘린다.
  function clippedByAncestor(el, box) {
    const pos = getComputedStyle(el).position;
    if (pos === 'fixed') return false;
    let escaping = pos === 'absolute';
    let cur = up(el);
    while (cur && cur.nodeType === 1 && cur !== document.documentElement && cur !== document.body) {
      const s = getComputedStyle(cur);
      const positioned = s.position !== 'static' || s.transform !== 'none';
      if (!(escaping && !positioned)) {
        const cx = /hidden|clip/.test(s.overflowX), cy = /hidden|clip/.test(s.overflowY);
        if (cx || cy) {
          const a = cur.getBoundingClientRect();
          const w = cx ? Math.min(box.right, a.right) - Math.max(box.left, a.left) : 1e9;
          const h = cy ? Math.min(box.bottom, a.bottom) - Math.max(box.top, a.top) : 1e9;
          if (w <= 1 || h <= 1) return true;
        }
        if (escaping && positioned) escaping = false;
      }
      if (s.position === 'fixed') return false;
      if (s.position === 'absolute') escaping = true;
      cur = up(cur);
    }
    return false;
  }

  // 가로 스크롤이 막혀 있으면 화면 오른쪽 밖은 볼 방법이 없다
  const rootX = [getComputedStyle(document.documentElement).overflowX,
                 document.body ? getComputedStyle(document.body).overflowX : 'visible'];
  const noScrollX = rootX.some(v => /hidden|clip/.test(v));

  function styleVerdict(el, cs, inh, pseudo) {
    const rect = el.getBoundingClientRect();
    // transform 으로 줄였으면 화면에 그려지는 글자 크기는 그만큼 작다
    const scale = el.offsetHeight > 0 ? rect.height / el.offsetHeight : 1;
    const fontSize = (parseFloat(cs.fontSize) || 0) * Math.min(scale, 1);
    // -webkit-text-fill-color 가 있으면 글자는 color 가 아니라 그 색으로 칠해진다
    const color = parseRGB(cs.webkitTextFillColor) || parseRGB(cs.color) || { r: 0, g: 0, b: 0, a: 1 };
    const bgs = effectiveBgs(el);
    const colorAlphaZero = color.a === 0;
    // 바탕색을 알 수 없으면(그림 바탕) 대비비로는 판정하지 않는다
    let contrast = 21;
    if (bgs) {
      contrast = 0;
      for (const bg of bgs) {
        const blended = {
          r: color.a * color.r + (1 - color.a) * bg.r,
          g: color.a * color.g + (1 - color.a) * bg.g,
          b: color.a * color.b + (1 - color.a) * bg.b,
        };
        const l1 = luminance(blended), l2 = luminance(bg);
        contrast = Math.max(contrast, (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05));
      }
    }

    const indent = parseFloat(cs.textIndent) || 0;
    const indented = indent <= -500;
    const clipped = clipRectZero(cs) || inh.clipPath;
    // visibility 는 상속되지만 자식이 visible 로 되돌릴 수 있어, 조상이 아니라 자신의 계산값을 본다
    const visHidden = cs.visibility === 'hidden' || cs.visibility === 'collapse';

    const box = (!pseudo && textRect(el)) || rect;
    const sx = window.scrollX, sy = window.scrollY;
    // 크기가 0 인 상자(렌더링되지 않은 영역)는 좌표가 (0,0) 으로 나오므로 화면 밖 판정에서 뺀다
    const hasBox = box.right - box.left > 0 || box.bottom - box.top > 0;
    const movedOut = !inh.displayNone && hasBox && (
      box.right + sx <= 0 || box.bottom + sy <= 0 ||                  // 문서 왼쪽·위쪽 밖
      box.left < OFFSCREEN_LIMIT || box.top < OFFSCREEN_LIMIT ||
      box.left + sx >= innerWidth + (noScrollX ? 0 : 1000));          // 오른쪽 밖
    const overflowHidden = !inh.displayNone && !movedOut && clippedByAncestor(el, box);
    const collapsed = !inh.displayNone && (
      (rect.width <= 1 && rect.height <= 1) ||
      ((rect.width <= 1 || rect.height <= 1) && cs.overflow !== 'visible'));

    const transparent = inh.opacityZero || colorAlphaZero || contrast < 1.2;
    const offscreen = inh.displayNone || visHidden || fontSize <= 1 ||
                      movedOut || collapsed || indented || clipped || overflowHidden;

    const reasons = [];
    if (inh.opacityZero) reasons.push('opacity:0');
    if (colorAlphaZero) reasons.push(parseRGB(cs.webkitTextFillColor) && parseRGB(cs.webkitTextFillColor).a === 0
                                     ? '-webkit-text-fill-color:transparent' : 'color:transparent');
    if (!inh.opacityZero && !colorAlphaZero && contrast < 1.2) reasons.push('배경 대비비 ' + contrast.toFixed(2));
    if (inh.displayNone) reasons.push('display:none');
    if (visHidden) reasons.push('visibility:hidden');
    if (fontSize <= 1) reasons.push(scale < 0.99 ? `transform 축소 후 글자 ${fontSize.toFixed(2)}px`
                                                 : 'font-size:' + cs.fontSize);
    if (movedOut) reasons.push('화면 밖 좌표 left:' + Math.round(box.left) + 'px, top:' + Math.round(box.top) + 'px');
    if (indented) reasons.push('text-indent:' + cs.textIndent);
    if (clipped) reasons.push('clip 영역 0');
    if (overflowHidden) reasons.push('상위 요소 overflow:hidden 영역 밖');
    if (collapsed) reasons.push('크기 ' + Math.round(rect.width) + 'x' + Math.round(rect.height));

    return { transparent, offscreen, reasons, rect };
  }

  // 다른 요소에 완전히 덮여 보이지 않는가 (요강 주요 4종 밖이라 추가 유형으로 다룬다)
  function isOccluded(el, rect) {
    if (rect.width < 3 || rect.height < 3) return false;
    const cx = rect.left + rect.width / 2, cy = rect.top + rect.height / 2;
    if (cx < 0 || cy < 0 || cx > innerWidth || cy > innerHeight) return false;
    let top;
    try { top = document.elementFromPoint(cx, cy); } catch (e) { return false; }
    if (!top || top === el) return false;
    return !el.contains(top) && !top.contains(el);
  }

  function scanRoot(root, hostSelector) {
    const all = root.querySelectorAll('*');
    for (const el of all) {
      if (NON_TEXT.has(el.tagName)) continue;
      if (el.shadowRoot) {
        scanRoot(el.shadowRoot, hostSelector || buildSelector(el));
      }
      const cs = getComputedStyle(el);
      const inh = inherited(el);
      // 선택자는 문서를 여러 번 검색하므로 비싸다. 글자를 가진 요소에만 만든다.
      let selector = null;
      const sel = () => selector || (selector = hostSelector || buildSelector(el));

      // 1) 요소가 직접 들고 있는 텍스트 (부모와 중복 보고를 막는다)
      let own = '';
      for (const n of el.childNodes) if (n.nodeType === 3) own += n.nodeValue;
      if (own.trim()) {
        const v = styleVerdict(el, cs, inh);
        const occluded = !v.transparent && !v.offscreen && !hostSelector && isOccluded(el, v.rect);
        out.push({
          text: own, selector: sel(), transparent: v.transparent, offscreen: v.offscreen,
          occluded, reasons: v.reasons.concat(hostSelector ? ['Shadow DOM 내부'] : []),
        });
        els.push(hostSelector ? null : el);
      }

      // 2) 가상 요소로 끼워 넣은 문자열
      for (const pe of ['::before', '::after']) {
        let cs2;
        try { cs2 = getComputedStyle(el, pe); } catch (e) { continue; }
        const raw = cs2 && cs2.content;
        if (!raw || raw === 'none' || raw === 'normal') continue;
        const m = raw.match(/^"([\s\S]*)"$/) || raw.match(/^'([\s\S]*)'$/);
        if (!m || !m[1].trim()) continue;
        const v = styleVerdict(el, cs2, inh, true);
        out.push({
          text: m[1], selector: sel(), transparent: v.transparent, offscreen: v.offscreen,
          occluded: false, reasons: v.reasons.concat([pe + ' content 삽입']),
        });
        els.push(null);
      }
    }
  }

  scanRoot(document.body, null);

  // 3) 쪼갠 글 합치기: 숨긴 조각마다 위로 올라가며 숨김이 이어지는 가장 바깥 상자를 찾는다
  const verdicts = new Map();
  const hiddenBox = (el) => {
    if (!verdicts.has(el)) {
      let v = null;
      try { v = styleVerdict(el, getComputedStyle(el), inherited(el)); } catch (e) {}
      verdicts.set(el, v && (v.transparent || v.offscreen) ? v : null);
    }
    return verdicts.get(el);
  };
  const indexOf = new Map();
  els.forEach((el, i) => { if (el) indexOf.set(el, i); });

  // 숨긴 문장 안의 꾸밈 태그(<p>먹튀검증 <b>안전놀이터</b> 텔레그램</p>)는 문장의 일부다.
  // 같은 숨김이 걸린 꾸밈 태그에 문장 번호(sp)를 달고, 문장에는 꾸밈 태그 글자까지 넣은 전체 글(full)을 단다.
  // 둘 다 광고로 잡히면 scan.py 가 문장 한 건으로 합친다 (따로 세면 한 광고가 두 건이 되고 근거 문구가 깨진다).
  const INLINE = new Set(['A', 'B', 'STRONG', 'EM', 'I', 'U', 'S', 'SPAN', 'FONT', 'MARK', 'SMALL', 'BIG',
                          'SUB', 'SUP', 'CODE', 'ABBR', 'CITE', 'Q', 'INS', 'DEL', 'TIME', 'LABEL']);
  const sameHide = (i, j) => out[i].transparent === out[j].transparent && out[i].offscreen === out[j].offscreen;
  const sentenceOwners = new Set();
  for (let i = 0; i < els.length; i++) {
    const el = els[i];
    if (!el || !(out[i].transparent || out[i].offscreen) || !INLINE.has(el.tagName)) continue;
    let cur = el.parentElement;
    while (cur && !indexOf.has(cur) && INLINE.has(cur.tagName)) cur = cur.parentElement;
    if (!cur || !indexOf.has(cur)) continue;
    const p = indexOf.get(cur);
    if (!sameHide(i, p)) continue;
    out[i].sp = p;
    sentenceOwners.add(p);
  }
  const sentence = (node, p) => {
    let text = '';
    for (const n of node.childNodes) {
      if (n.nodeType === 3) { text += n.nodeValue; continue; }
      if (n.nodeType !== 1 || !INLINE.has(n.tagName)) continue;
      const j = indexOf.get(n);
      if (j === undefined || out[j].sp === p) text += sentence(n, p);
    }
    return text;
  };
  for (const p of sentenceOwners) out[p].full = sentence(els[p], p);
  const groups = new Map();
  const n0 = out.length;
  for (let i = 0; i < n0; i++) {
    const el = els[i];
    if (!el || !(out[i].transparent || out[i].offscreen)) continue;
    let root = el;
    while (root.parentElement && root.parentElement !== document.body && hiddenBox(root.parentElement))
      root = root.parentElement;
    if (root === el) continue;
    if (!groups.has(root)) groups.set(root, new Set(indexOf.has(root) ? [indexOf.get(root)] : []));
    groups.get(root).add(i);
  }
  for (const [root, set] of groups) {
    const parts = [...set].sort((a, b) => a - b);
    if (parts.length < 2) continue;
    const v = hiddenBox(root);
    if (!v) continue;
    out.push({
      text: parts.map((i) => out[i].text.trim()).join(' '), selector: buildSelector(root),
      transparent: v.transparent, offscreen: v.offscreen, occluded: false,
      reasons: v.reasons.concat(['여러 요소로 쪼갠 글을 합쳐 판정']), parts,
    });
  }
  return out;
}
"""

EXTRACT = EXTRACT.replace("BUILD_SELECTOR", BUILD_SELECTOR.strip(), 1)
