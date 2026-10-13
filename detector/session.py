"""브라우저 세션: 페이지를 열고 판정해도 될 때까지 기다리는 방법, 지연 불러오기·'더보기', 열기 실패 사유.

전체 점검(scan)과 조치 확인(recheck)이 같은 세션을 써야 점검 때 잡힌 광고를 확인 때 놓치지 않는다.
"""
import re

from browser import launch_browser

import js_links as js_mod
from politeness import USER_AGENT

# 판정에 쓰지 않는 글꼴·영상. 주소 끝으로 골라 이것만 가로채 막는다 (그림은 브라우저 설정으로 막는다)
HEAVY_URL = re.compile(r"\.(woff2?|ttf|otf|eot|mp4|webm|ogg|ogv|mp3|m4a|wav|avi|mov)(\?|#|$)", re.I)
AJAX_WAIT_MS = 2000     # 비동기로 불러오는 댓글 등을 기다리는 최대 시간
LAZY_WAIT_MS = 100      # 화면을 내린 뒤 지연 불러오기가 시작될 때까지 기다리는 시간


def fail_reason(exc=None, status=None):
    """페이지를 못 연 까닭. (사유 코드, 다시 시도할 만한가).

    timeout·network·server·blocked 는 실패로 보고하고, gone(없는 주소)은 따로 센다.
    """
    if exc is not None:
        name, msg = type(exc).__name__, str(exc)
        if "Timeout" in name:
            return "timeout", True
        if "net::" in msg or "NS_ERROR" in msg:
            return "network", True
        return "error", False
    if status in (401, 403, 429):
        return "blocked", status == 429
    if status >= 500:
        return "server", True
    return "gone", False


def fail_entry(url, reason, status=None, detail=""):
    return {"url": url, "reason": reason, "status": status, "detail": detail[:200]}

# 모든 외부 스타일시트가 실제로 적용되었는지 확인한다.
STYLES_READY = """() => Array.from(document.querySelectorAll('link[rel~=\"stylesheet\"]'))
  .every(l => l.sheet || l.disabled)"""

# 페이지가 '화면을 내리면 더 불러오는' 장치를 쓰는지 표시해 둔다 (모든 페이지를 내려 보면 느리다).
# IntersectionObserver 를 만들거나 scroll 이벤트를 다는 페이지만 내려 본다.
LAZY_HOOK = r"""
(() => {
  const mark = () => { window.__hwonhiLazy = true; };
  const IO = window.IntersectionObserver;
  if (IO) {
    const Wrapped = function (cb, opt) { mark(); return new IO(cb, opt); };
    Wrapped.prototype = IO.prototype;
    window.IntersectionObserver = Wrapped;
  }
  // 페이지를 불러오는 동안 짧게 미뤄 둔 작업(setTimeout 1.5초 이내)이 언제 끝나는지 적어 둔다.
  // 광고를 0.7초 뒤에 끼워 넣는 식의 지연 삽입을 기다리기 위함이다. 스크립트 본문이 처음 실행될 때
  // (document.currentScript)와 load 이벤트가 끝나기 전에 건 타이머만 센다. 다 불러온 뒤 다시 거는
  // 반복 타이머(슬라이드)는 세지 않는다. 다만 '더보기'를 누르거나 화면을 내린 직후(__hwonhiTrack)에
  // 건 타이머는 그 동작이 미뤄 둔 삽입이므로 센다.
  const st = window.setTimeout;
  window.__hwonhiDue = 0;
  window.addEventListener('load', () => st.call(window, () => { window.__hwonhiLoaded = true; }, 0));
  window.setTimeout = function (fn, ms, ...rest) {
    const d = Number(ms) || 0;
    if ((document.currentScript || !window.__hwonhiLoaded || window.__hwonhiTrack) && d > 0 && d <= DELAY_MAX_MS)
      window.__hwonhiDue = Math.max(window.__hwonhiDue, performance.now() + d);
    return st.call(this, fn, ms, ...rest);
  };
  const add = EventTarget.prototype.addEventListener;
  EventTarget.prototype.addEventListener = function (type, ...rest) {
    if (type === 'scroll' || type === 'wheel') mark();
    return add.call(this, type, ...rest);
  };
})();
"""
DELAY_MAX_MS = 1500     # 이 안에 실행되도록 미뤄 둔 삽입만 기다린다
LOAD_WAIT_MS = 3000     # load 이벤트를 기다리는 최대 시간 (그림은 받지 않으므로 보통 바로 온다)
LAZY_HOOK = LAZY_HOOK.replace("DELAY_MAX_MS", str(DELAY_MAX_MS))

# 판정을 시작해도 되는지 한 번에 확인한다. load 이벤트(스타일시트·iframe 이 모두 붙은 시점)까지
# 기다리고, load 처리기가 끼워 넣은 글이 반영되도록 한 박자 쉰 뒤, 스타일 적용 여부와
# 미뤄 둔 삽입까지 남은 시간을 돌려준다. 예전처럼 모든 페이지에서 고정 시간을 쉬지 않는다.
PAGE_READY = """async () => {
  if (document.readyState !== 'complete')
    await new Promise((r) => { addEventListener('load', r, { once: true }); setTimeout(r, LOAD_WAIT_MS); });
  await new Promise((r) => setTimeout(r, 0));
  return { styles: (STYLES_READY)(), left: Math.max(0, (window.__hwonhiDue || 0) - performance.now()) };
}""".replace("LOAD_WAIT_MS", str(LOAD_WAIT_MS)).replace("STYLES_READY", STYLES_READY)
# iframe 안에서 미뤄 둔 삽입까지 남은 시간 (다른 출처 iframe 은 바깥 페이지에서 볼 수 없어 따로 묻는다)
DELAY_LEFT = "() => Math.max(0, (window.__hwonhiDue || 0) - performance.now())"


def delay_left(page, left):
    """페이지(left: 페이지 자신의 남은 시간)와 그 안 iframe 들이 미뤄 둔 삽입 가운데
    가장 늦게 끝나는 것까지 남은 시간(ms)."""
    for fr in page.frames[1:]:
        try:
            left = max(left, fr.evaluate(DELAY_LEFT))
        except Exception:
            pass
    return left


# 창 말고 글 상자 안(overflow:auto 인 댓글 상자 등)을 내려야 불러오는 경우도 있다
SCROLL_BOXES = """(go) => {
  let n = 0;
  for (const el of document.querySelectorAll('body *')) {
    if (n >= 20) break;
    if (el.scrollHeight <= el.clientHeight + 20) continue;
    const s = getComputedStyle(el).overflowY;
    if (s !== 'auto' && s !== 'scroll') continue;
    n++;
    if (go) el.scrollTop = el.scrollHeight;
  }
  return n;
}"""
LAZY_CHECK = ("() => !!window.__hwonhiLazy && (document.documentElement.scrollHeight > innerHeight + 50"
              " || (" + SCROLL_BOXES + ")(false) > 0)")
SCROLL_END = ("() => { window.scrollTo(0, document.documentElement.scrollHeight); (" + SCROLL_BOXES
              + ")(true); }")
SCROLL_TOP = "() => window.scrollTo(0, 0)"
REACT_MAX_MS = 2000     # 누르거나 내린 뒤 미뤄 둔 삽입·비동기 요청·iframe 을 기다리는 최대 시간
FRAME_WAIT_MS = 1500    # 그 사이 주소가 바뀐 iframe 이 다 열릴 때까지 기다리는 최대 시간


def wait_reactions(page, inflight, settle_ms):
    """'더보기'·탭을 누르거나 화면을 내린 뒤, 그 동작이 불러오는 글이 다 붙을 때까지 기다린다.

    비동기 요청이 끝난 뒤 다시 타이머를 거는 경우(받아 와서 0.1초 뒤에 끼워 넣기)가 있어
    남은 타이머와 요청이 모두 없어질 때까지 되풀이한다. 끝나면 추적 표시를 끈다.
    """
    waited = 0
    try:
        while waited < REACT_MAX_MS:
            if inflight:
                _settle_ajax(page, inflight, settle_ms)
                waited += settle_ms
            left = delay_left(page, page.evaluate(DELAY_LEFT))
            if left <= 0 and not inflight:
                break
            step = min(int(left) + 20, REACT_MAX_MS - waited) if left > 0 else 50
            page.wait_for_timeout(step)
            waited += step
        for fr in page.frames[1:]:
            try:
                fr.wait_for_load_state("load", timeout=FRAME_WAIT_MS)
            except Exception:
                pass
    finally:
        try:
            page.evaluate(js_mod.TRACK_OFF)
        except Exception:
            pass


def _settle_ajax(page, inflight, settle_ms):
    """비동기 요청이 남아 있을 때만 끝날 때까지 기다린다 (없으면 지연 0)."""
    if not inflight:
        return
    waited = 0
    while inflight and waited < AJAX_WAIT_MS:
        page.wait_for_timeout(50)
        waited += 50
    page.wait_for_timeout(settle_ms)


# 내려 볼 페이지인지와 '더보기' 후보를 한 번의 왕복으로 묻는다. 내려 봐야 하면 후보는 내린 뒤에 다시 찾는다.
EXPAND_PROBE = ("(limit) => { const lazy = (" + LAZY_CHECK + ")(); "
                "return { lazy, more: lazy ? null : (" + js_mod.MORE_CANDIDATES + ")(limit) }; }")


def reveal_lazy(page, inflight, settle_ms):
    """화면을 내려야 불러오는 댓글·목록을 불러온 뒤 맨 위로 돌아온다 (LAZY_CHECK 가 참인 페이지)."""
    page.evaluate(js_mod.TRACK_ON)
    page.evaluate(SCROLL_END)
    page.wait_for_timeout(LAZY_WAIT_MS)      # scroll 이벤트는 다음 화면 갱신 때 온다
    wait_reactions(page, inflight, settle_ms)
    page.evaluate(SCROLL_TOP)


class BrowserSession:
    """브라우저 하나와 그 위에서 페이지를 여는 방법. 전체 점검(scan)과 조치 확인(recheck)이 함께 쓴다.

    두 곳이 같은 대기·같은 '더보기' 처리를 거쳐야, 점검 때 잡힌 광고를 확인 때 놓치는 일이 없다.
    """

    def __init__(self, p, timeout_ms=15000, settle_ms=60):
        self.timeout_ms, self.settle_ms = timeout_ms, settle_ms
        self.browser, self.engine = launch_browser(p)
        # 정체를 밝히는 User-Agent 를 쓴다. 로그를 보는 담당자가
        # 정상 점검임을 알 수 있어야 관제에서 불필요한 대응을 하지 않는다.
        self.ctx = self.browser.new_context(ignore_https_errors=True, user_agent=USER_AGENT)
        self.ctx.add_init_script(LAZY_HOOK)
        # 판정에 CSS 는 반드시 필요하지만 이미지·폰트·영상은 쓰지 않는다.
        # 받지 않는 것만으로 페이지당 시간이 크게 줄고 대상 서버 부담도 준다.
        self.ctx.route(HEAVY_URL, lambda route: route.abort())
        # 자바스크립트 링크를 눌러 볼 때만 모든 요청을 가로채 페이지 이동과 GET 이 아닌 요청을 막는다.
        self.guard = js_mod.NavGuard(self.ctx)
        # 댓글처럼 페이지를 연 뒤 비동기로 불러오는 영역을 기다리기 위해 진행 중인 요청을 센다.
        self.inflight = set()
        self.crashed = []
        self.probed = set()   # 이미 눌러 본 자바스크립트 링크의 생김새 (공통 메뉴를 페이지마다 다시 누르지 않게)
        self.page = self._open_page()

    def _open_page(self):
        pg = self.ctx.new_page()
        pg.set_default_timeout(self.timeout_ms)
        pg.on("request", lambda r: self.inflight.add(r)
              if r.resource_type in ("xhr", "fetch") else None)
        pg.on("requestfinished", lambda r: self.inflight.discard(r))
        pg.on("requestfailed", lambda r: self.inflight.discard(r))
        pg.on("crash", lambda *_: self.crashed.append(True))
        return pg

    def settle(self):
        _settle_ajax(self.page, self.inflight, self.settle_ms)

    def open(self, url):
        """페이지를 열고 판정해도 될 때까지 기다린다. HTTP 상태 코드를 돌려준다 (접속 실패는 예외)."""
        # 탭이 죽었으면(메모리 부족 등) 새 탭으로 이어 간다. 그대로 두면 남은 페이지가 모두 실패한다.
        if self.crashed or self.page.is_closed():
            try:
                self.page.close()
            except Exception:
                pass
            self.crashed.clear()
            self.inflight.clear()
            self.page = self._open_page()
        page = self.page
        resp = page.goto(url, wait_until="domcontentloaded")
        status = resp.status if resp is not None else 200
        if status >= 400:
            return status
        # 스타일시트가 적용되기 전에 판정하면 display:none 같은 은닉을 통째로 놓친다.
        # load 까지 기다린 뒤에도 CSS 가 덜 붙었으면 더 기다리고, 페이지가 미뤄 둔
        # 삽입(setTimeout)이 남았으면 그때까지 기다린다.
        try:
            ready = page.evaluate(PAGE_READY)
            if not ready["styles"]:
                page.wait_for_function(STYLES_READY, timeout=4000)
            left = delay_left(page, ready["left"])
            if left > 0:
                page.wait_for_timeout(min(left, DELAY_MAX_MS) + 50)
        except Exception:
            pass
        self.settle()
        return status

    def expand(self):
        """화면을 내리거나 '더보기'를 눌러야 나오는 댓글을 불러온다."""
        try:
            probe = self.page.evaluate(EXPAND_PROBE, js_mod.MORE_LIMIT)
        except Exception:
            return
        if probe["lazy"]:
            try:
                reveal_lazy(self.page, self.inflight, self.settle_ms)
            except Exception:
                pass
        try:
            js_mod.expand_more(self.page, self.guard, self.react, first=probe["more"])
        except Exception:
            pass

    def react(self):
        wait_reactions(self.page, self.inflight, self.settle_ms)

    def switch_views(self, before=None, ids=None):
        """탭·'다음 페이지'처럼 같은 주소에서 화면을 바꾸는 단추를 하나씩 누른다.

        누를 때마다 멈추므로(yield) 부른 쪽이 바뀐 화면을 다시 훑는다. 바꾸면 앞 화면이 사라지므로
        처음 화면을 훑은 뒤에 불러야 한다. before 는 누를 단추가 있을 때 처음 누르기 전에 한 번 부른다.
        """
        yield from js_mod.switch_views(self.page, self.guard, self.react, before, ids)

    def close(self):
        try:
            self.browser.close()
        except Exception:
            pass
