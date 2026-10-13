"""진입 URL에서 시작해 하위 페이지를 돌며 은닉 불법광고를 탐지한다.

점검 흐름(대기열·상한·실패 처리·중간 저장)만 여기 두고, 주소 다루기는 urls, 브라우저 세션은 session,
판정과 검출은 findings 에 있다.
"""
import hashlib
import os
import re
import time
from collections import deque
from datetime import datetime, timezone, timedelta
from urllib.parse import urldefrag, urljoin

from playwright.sync_api import sync_playwright

import attachments as attach_mod
import cloaking as cloaking_mod
import image_text as image_text_mod
import index_check as index_mod
import js_links as js_mod
import link_check as link_mod
import search_reflect as reflect_mod
from politeness import DEFAULT_DELAY, Politeness
from findings import EvidenceMap, classify, walk_frame
from session import BrowserSession, fail_entry, fail_reason
from urls import SKIP_EXT, SiteScope, clean_url, low_priority, page_key

KST = timezone(timedelta(hours=9))

LINK_JS = "() => Array.from(document.querySelectorAll('a[href]')).map(a => a.href)" \
          ".filter(h => /^https?:/i.test(h))"
CHECKPOINT_EVERY = 20   # 이만큼 페이지를 볼 때마다 중간 결과를 남긴다
CHECKPOINT_MIN_SEC = 15  # 다만 앞 저장에서 이만큼 지나지 않았으면 미룬다 (저장할 때마다 결과 전체를 다시 쓴다)
DEFAULT_MAX_PAGES = 1000  # 큰 게시판도 끝까지 보도록. 페이지가 적으면 대기열이 먼저 비고, 많아도 시간 상한이 지킨다
TIME_LIMIT_SEC = 25 * 60  # 평가 상한(30분) 안에 결과 파일을 쓰도록 탐색을 멈추는 시점
BLOCK_STREAK = 8        # 이만큼 잇달아 열리지 않으면 차단·장애로 보고 멈춘다 (계속 두드리면 공격처럼 보인다)
# 서버 오류(5xx)는 세지 않는다. 전자정부 프레임워크 누리집은 값이 빠진 주소에 404 대신 500 을 흔히 돌려주어,
# 스크립트·폼에서 추정한 주소가 몇 개 이어지면 정상 페이지가 많이 남았는데도 점검이 끝나 버린다.
STREAK_REASONS = ("timeout", "network", "blocked", "error")
SAMPLE_MAX = 200        # 열리지 않은 주소·못 본 주소를 이만큼까지 적어 둔다


# 판정을 마친 페이지에서 링크·화면 바꾸기 단추·눌러 볼 요소를 한 번의 왕복으로 모은다 (왕복 한 번이 수 ms 다).
# 화면을 바꿀 단추가 있으면 바꾼 뒤 페이지를 다시 열므로, 눌러 볼 요소는 그때 다시 찾는다(cand 는 null).
PAGE_TAIL = ("([swLimit, candArgs]) => { const links = (" + LINK_JS + ")(); const sw = ("
             + js_mod.SWITCH_CANDIDATES + ")(swLimit); return { links, sw, cand: sw.length ? null : ("
             + js_mod.JS_CANDIDATES + ")(candArgs) }; }")


# 탭을 바꾸면 앞 탭이 숨겨진다. 처음 화면에서 이미 보이던 글이 숨겨졌다고 광고로 세지 않도록,
# 바꾼 화면에서는 처음 화면에 보이지 않던 글만 검출로 남긴다.
VISIBLE_TEXT = "() => (document.body ? document.body.innerText : '').replace(/\\s+/g, '')"


def frame_links(page, frames=None):
    """페이지와 그 안 모든 프레임(frames 를 주면 그 프레임들)의 <a href> 주소.
    frameset·iframe 누리집은 메뉴·게시판 링크가 프레임 안에 있다."""
    hrefs = []
    for fr in page.frames if frames is None else frames:
        try:
            hrefs += fr.evaluate(LINK_JS)
        except Exception:
            pass
    return hrefs


def switch_views_and_walk(ses, url, results, iframe_urls, evidence_dir, evid_map, hrefs, ids=None):
    """같은 주소에서 바뀌는 화면을 하나씩 훑는다. 화면을 바꿨으면 True."""
    page = ses.page
    shown = []                 # 바꾸기 전 화면 글 (누를 단추가 있을 때만 읽는다)

    def remember():
        shown.append(page.evaluate(VISIBLE_TEXT))

    switched = False
    try:
        for _ in ses.switch_views(before=remember, ids=ids):
            switched = True
            rows = []
            try:
                walk_frame(page.main_frame, "", url, rows, iframe_urls, evidence_dir, evid_map)
            except Exception:
                pass
            results.extend(r for r in rows
                           if re.sub(r"\s+", "", r.get("evidence_text") or "") not in shown[0])
            hrefs += frame_links(page)
    except Exception:
        pass
    return switched


def scan(entry_url, max_pages=DEFAULT_MAX_PAGES, timeout_ms=15000, progress=None, evidence_dir=None,
         snapshot_dir=None, polite=False, delay=None, respect_robots=True,
         settle_ms=60, cloaking=False, cloaking_limit=40, attachments=False,
         search_reflect=False, index_urls=None, subdomains=False, check_links=False, ocr_images=False,
         time_limit=TIME_LIMIT_SEC, should_stop=None, checkpoint=None):
    """누리집을 돌며 탐지한다.

    time_limit  이 시간(초)이 지나면 새 페이지를 열지 않고 지금까지의 결과로 마친다
    should_stop 참을 돌려주면 멈춘다 (화면의 '탐지 중지')
    checkpoint  페이지를 CHECKPOINT_EVERY 개 볼 때마다 중간 결과를 받아 파일로 남긴다
                (도중에 프로그램이 죽어도 그때까지의 result.json 이 남는다)
    """
    started = datetime.now(KST)
    t0 = time.perf_counter()
    scope = SiteScope(entry_url, subdomains)

    seen, queue, low_queue, results, visited_pages = set(), deque([entry_url]), deque(), [], []
    queued = {page_key(entry_url)}   # 대기열에 이미 넣은 주소. 공통 메뉴 링크를 페이지마다 다시 넣지 않는다
    # 열지 못한 페이지는 조용히 버리지 않고 사유와 함께 남긴다. '0건'이 '깨끗함'인지 '못 봄'인지 가려야 한다.
    # 잠깐의 장애(시간 초과·접속 오류·서버 오류)는 대기열이 다 빈 뒤 한 번만 다시 연다.
    failed, gone, retry_queue, retried, retrying = [], [], deque(), set(), set()
    streak = 0
    iframe_urls = set()
    evid_map = EvidenceMap() if evidence_dir else None
    snapshots = {}
    cloaking_checked = 0
    stopped = None
    attach = prober = indexer = linkcheck = imgtext = None
    engine = "?"
    manners = Politeness(enabled=polite, respect_robots=respect_robots,
                         delay=DEFAULT_DELAY if delay is None else delay)

    def assemble():
        # iframe 안에서 이미 본 내용을 독립 페이지로 다시 세지 않는다
        rows = [r for r in results if page_key(r["url"]) not in iframe_urls]
        # (url + location + technique) 중복 제거
        uniq, seen_keys = [], set()
        for r in rows:
            k = (page_key(r["url"]), r["location"], r["technique"])
            if k in seen_keys:
                continue
            seen_keys.add(k)
            uniq.append(r)
        return {
            "engine": engine,
            "politeness": manners.summary(),
            "evidence": dict(evid_map or {}),
            "attachments_fetched": attach.fetched if attach else 0,
            "search_probes": prober.probed if prober else 0,
            "index_checked": indexer.checked if indexer else 0,
            "index_other_site": indexer.skipped_other_site if indexer else 0,
            "links_checked": linkcheck.checked if linkcheck else 0,
            "ocr_images": ({"read": imgtext.read, "unavailable": imgtext.unavailable} if imgtext else None),
            "snapshots": dict(snapshots),
            "started": started,
            "finished": datetime.now(KST),
            "elapsed": time.perf_counter() - t0,
            "pages": list(visited_pages),
            "findings": uniq,
            "stopped": stopped,
            "coverage": coverage(),
        }

    def coverage():
        """점검 범위. 몇 페이지를 봤고 무엇을 왜 못 봤는가."""
        # 대기열에 남은 주소 (페이지 수·시간 상한, 중지, 차단으로 열지 못한 곳)
        left, left_keys = [], set()
        for u in (*queue, *low_queue, *retry_queue):
            k = page_key(u)
            if (k in seen and k not in retrying) or k in left_keys:
                continue
            left_keys.add(k)
            left.append(u)
        return {
            "visited": len(visited_pages),
            "failed": failed[:SAMPLE_MAX], "failed_count": len(failed),
            "failed_kinds": {r: sum(1 for f in failed if f["reason"] == r)
                             for r in dict.fromkeys(f["reason"] for f in failed)},
            "gone": gone[:SAMPLE_MAX], "gone_count": len(gone),
            "left": left[:SAMPLE_MAX], "left_count": len(left),
            "max_pages": max_pages,
            "robots": manners.summary().get("skipped_by_robots", 0),
        }

    def give_up(url, key, reason, retry, status=None, detail=""):
        """열지 못한 페이지. 다시 열어 볼 만하면 한 번만 미루고, 아니면 실패로 남긴다."""
        nonlocal streak
        if retry and key not in retried:
            retrying.add(key)            # 다시 열 때 이미 본 주소로 걸러지지 않게 표시한다
        if reason == "gone":
            gone.append(fail_entry(url, reason, status))
            return
        if reason in STREAK_REASONS:
            streak += 1
        if retry and key not in retried:
            retried.add(key)
            retry_queue.append(url)
            return
        failed.append(fail_entry(url, reason, status, detail))

    last_checkpoint = time.perf_counter()

    def out_of_time():
        return bool(time_limit) and time.perf_counter() - t0 > time_limit

    with sync_playwright() as p:
        ses = BrowserSession(p, timeout_ms, settle_ms)
        engine, ctx, guard = ses.engine, ses.ctx, ses.guard
        # 첨부파일은 페이지 이동 없이 같은 쿠키·UA 로 직접 받는다.
        attach = (attach_mod.AttachmentScanner(ctx.request, manners, classify, deadline=out_of_time)
                  if attachments else None)
        # 검색 폼마다 무해한 표식으로 한 번 조회해 검색어 반사 여부를 본다.
        # 색인 목록 점검도 같은 조회기를 써서, 이미 본 검색 경로를 다시 조회하지 않는다.
        prober = (reflect_mod.SearchReflectScanner(ctx.request, manners)
                  if search_reflect or index_urls else None)
        reflect = prober if search_reflect else None
        # 누리집이 걸어 둔 바깥 링크를 모았다가 탐색이 끝난 뒤 목적지를 한 번씩 확인한다
        linkcheck = (link_mod.LinkChecker(ctx.request, manners, classify, scope.allows)
                     if check_links else None)
        # 본문 그림 속 글자를 글자 인식으로 읽는다 (선택 기능)
        imgtext = (image_text_mod.ImageTextScanner(ctx.request, manners, classify, deadline=out_of_time)
                   if ocr_images else None)

        while (queue or low_queue or retry_queue) and len(visited_pages) < max_pages:
            if should_stop and should_stop():
                stopped = "user"
                break
            if out_of_time():
                stopped = "time"
                break
            if streak >= BLOCK_STREAK:
                stopped = "blocked"
                break
            url = queue.popleft() if queue else low_queue.popleft() if low_queue else retry_queue.popleft()
            key = page_key(url)
            if key in seen and key not in retrying:
                continue
            if key in retried:
                retrying.discard(key)       # 다시 여는 것은 한 번뿐
            seen.add(key)
            if not manners.allowed(url):
                continue
            manners.wait()
            try:
                # 없는 주소(404)나 오류 응답은 점검할 페이지가 아니다.
                # POST 폼을 GET 주소로 바꿔 본 후보가 GET 을 받지 않는 경우도 여기서 걸러진다.
                status = ses.open(url)
            except Exception as exc:
                reason, retry = fail_reason(exc=exc)
                give_up(url, key, reason, retry, detail=f"{type(exc).__name__}: {exc}".splitlines()[0])
                continue
            if status >= 400:
                reason, retry = fail_reason(status=status)
                give_up(url, key, reason, retry, status=status)
                continue
            streak = 0
            page = ses.page

            if not visited_pages and page.url:
                scope.add(page.url)      # 진입 주소가 넘겨진 곳(리다이렉트)도 같은 누리집이다
            # 넘겨진(리다이렉트) 주소가 실제 페이지다. 옛 주소·짧은 주소로 같은 글을 다시 보고하지 않고,
            # 보고하는 url 도 실제로 열린 주소로 적는다.
            if (page.url or "").startswith(("http://", "https://")):
                final = clean_url(urldefrag(page.url)[0])
                fkey = page_key(final)
                if fkey != key:
                    if fkey in seen or not scope.allows(final):
                        continue
                    seen.add(fkey)
                    url = final

            ses.expand()

            visited_pages.append(url)
            if progress:
                progress(len(visited_pages), url)

            # 1~2) 메인 프레임과 그 하위 iframe 전체를 재귀로 훑는다
            try:
                walk_frame(page.main_frame, "", url, results, iframe_urls,
                           evidence_dir, evid_map, attach, reflect, linkcheck)
            except Exception as exc:
                # 열리기는 했지만 끝까지 훑지 못했다. 이 페이지에서 찾은 것만 남는다
                failed.append(fail_entry(url, "partial", None,
                                         f"{type(exc).__name__}: {exc}".splitlines()[0]))

            # 자바스크립트로 내려받는 첨부(fn_egov_downFile 등)는 <a href> 가 아니라 위에서 못 본다. 눌러 주소를 알아낸다
            if attach is not None:
                try:
                    files = [f for f in js_mod.download_links(page, guard)
                             if attach_mod.looks_like_attachment(f["href"], f["text"])]
                    results.extend(attach.check(url, files))
                except Exception:
                    pass

            if imgtext is not None:
                try:
                    results.extend(imgtext.check(page.main_frame, url))
                except Exception:
                    pass

            # 페이지를 탐지한 시점 그대로 보관한다.
            # 나중에 화면에서 '그때 그 페이지'를 열어 검출 위치를 짚어주기 위함이다.
            if snapshot_dir is not None:
                try:
                    name = hashlib.sha1(page_key(url).encode("utf-8")).hexdigest()[:16] + ".html"
                    os.makedirs(snapshot_dir, exist_ok=True)
                    with open(os.path.join(snapshot_dir, name), "w",
                              encoding="utf-8", errors="replace") as fp:
                        fp.write(page.content())
                    snapshots[page_key(url)] = name
                except Exception:
                    pass

            # 크롤러 신원으로 한 번 더 조회해 응답이 달라지는지 본다.
            # 요청이 늘어나므로 켰을 때만, 정해진 페이지 수까지만 수행한다.
            if cloaking and cloaking_checked < cloaking_limit:
                cloaking_checked += 1
                try:
                    results.extend(cloaking_mod.check(ctx.request, url))
                except Exception:
                    pass

            # 3) 링크 수집
            try:
                tail = page.evaluate(PAGE_TAIL, [js_mod.SWITCH_LIMIT, [js_mod.PROBE_LIMIT, list(ses.probed)]])
                hrefs = tail["links"] + frame_links(page, page.frames[1:])
            except Exception:
                tail = {"sw": None, "cand": None}
                hrefs = frame_links(page)
            # 탭·'다음 페이지'로 같은 주소에서 바뀌는 화면도 훑는다 (같은 검출은 assemble 이 한 건으로 합친다).
            # 앞 화면의 링크를 모은 뒤에 바꾸고, 바꿨으면 눌러 보기(discover) 전에 페이지를 다시 연다.
            if tail["sw"] != [] and switch_views_and_walk(ses, url, results, iframe_urls, evidence_dir,
                                                          evid_map, hrefs, tail["sw"]):
                try:
                    ses.open(url)
                except Exception:
                    pass
            # 게시판 목록이 javascript:fn_view('1024') 나 onclick 으로만 이어지는 경우
            try:
                hrefs += js_mod.discover(page, ctx, guard, ses.probed, tail["cand"])
            except Exception:
                pass
            for h in hrefs:
                h, _ = urldefrag(urljoin(page.url or url, h))
                h = clean_url(h)
                if not scope.allows(h):
                    continue
                if h.lower().split("?")[0].endswith(SKIP_EXT):
                    continue
                # 확장자 없는 내려받기 주소(FileDown.do 등)를 페이지로 열지 않는다
                if attach_mod.DOWNLOAD_HINT.search(h):
                    continue
                hkey = page_key(h)
                if hkey not in seen and hkey not in queued:
                    queued.add(hkey)
                    (low_queue if low_priority(h) else queue).append(h)

            if (checkpoint and len(visited_pages) % CHECKPOINT_EVERY == 0
                    and time.perf_counter() - last_checkpoint >= CHECKPOINT_MIN_SEC):
                last_checkpoint = time.perf_counter()
                try:
                    checkpoint(assemble())
                except Exception:
                    pass

        # 4) 검색엔진 색인 목록 점검. 누리집 탐색으로 닿지 않는 주소들이다.
        if index_urls and not stopped and not out_of_time():
            indexer = index_mod.IndexChecker(prober, classify)
            try:
                results.extend(indexer.run(index_urls, entry_url))
            except Exception:
                pass

        # 5) 연계 링크 목적지 확인. 바깥 도메인마다 GET 한 번, 브라우저로 열지 않는다
        if linkcheck and not stopped and not out_of_time():
            try:
                results.extend(linkcheck.run(
                    should_stop=should_stop,
                    progress=(lambda h: progress(len(visited_pages), f"연계 링크 확인: {h}"))
                    if progress else None))
            except Exception:
                pass

        ses.close()

    return assemble()
