"""요소 하나를 문서 안에서 유일하게 가리키는 CSS 선택자를 만드는 브라우저 함수.

요강 location 규칙: 태그명과 클래스를 함께 적고 ' > ' 로 잇는다. 클래스로 형제와 구분되지
않을 때만 :nth-of-type(n) 순번을 붙인다. 만든 선택자가 문서에서 정확히 한 요소만 가리킬 때까지
위로 올라가며 늘린다. 주요 4종 추출·추가 유형 추출·iframe 위치가 모두 이 함수 하나를 쓴다.

태그 이름만으로 된 선택자('span', 'div > span')는 지금 유일해도 쓰지 않는다. 댓글을 더 불러오거나
배너가 바뀌면 같은 태그가 늘어나 여러 요소를 가리키게 되고, 채점에서 오답이 된다.
클래스나 순번이 하나라도 들어간 선택자까지 올라간다.
"""

BUILD_SELECTOR = r"""
  function buildSelector(el) {
    const path = [];
    let cur = el;
    while (cur && cur.nodeType === 1 && cur.tagName !== 'BODY' && cur.tagName !== 'HTML') {
      let s = cur.tagName.toLowerCase();
      const cls = Array.from(cur.classList).filter(c => /^[A-Za-z_-][\w-]*$/.test(c));
      if (cls.length) s += '.' + cls.join('.');
      const parent = cur.parentElement;
      if (parent) {
        const sameTag = Array.from(parent.children).filter(x => x.tagName === cur.tagName);
        let matching;
        try { matching = Array.from(parent.children).filter(x => x.matches(s)); }
        catch (e) { matching = sameTag; }
        if (matching.length > 1) s += ':nth-of-type(' + (sameTag.indexOf(cur) + 1) + ')';
      }
      path.unshift(s);
      for (let i = 0; i < path.length; i++) {
        const cand = path.slice(i).join(' > ');
        if (!/[.:#]/.test(cand)) continue;
        try { if (document.querySelectorAll(cand).length === 1) return cand; } catch (e) {}
      }
      cur = cur.parentElement;
    }
    return path.join(' > ');
  }
"""

# (el) => 선택자. frame.evaluate(SELECTOR_OF, 요소핸들) 로 바로 쓸 수 있다.
SELECTOR_OF = "(el) => {" + BUILD_SELECTOR + " return buildSelector(el); }"
