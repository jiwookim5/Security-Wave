"""로컬 웹 UI 서버.

배포 대상이 기관 PC(폐쇄망 포함)이므로 표준 라이브러리만 사용한다.
탐지는 별도 스레드에서 돌리고, 화면은 상태를 주기적으로 물어본다.
"""
import base64
import csv
import hashlib
import io
import json
import os
import shutil
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import lexicon
import report
from fileio import write_json
from index_check import decode as decode_index, parse_urls
from findings import classify
from scan import DEFAULT_MAX_PAGES, scan
from recheck import recheck
from runtime import asset_path
from urls import normalize_entry, page_key
from ui import report_html
from ui import snapshot as snapshot_mod
from ui import native as native_ui
from ui.window import open_app_window

if getattr(sys, "frozen", False):
    # PyInstaller 로 묶이면 화면 파일이 임시 전개 폴더에 들어간다.
    HERE = os.path.join(sys._MEIPASS, "ui")
else:
    HERE = os.path.dirname(os.path.abspath(__file__))

STATE_FILE = "review_state.json"     # 조치 상태는 재탐지 후에도 남아야 한다
LAST_FILE = "last_result.json"       # 프로그램을 다시 켜도 지난 결과를 볼 수 있게 남긴다
GONE_SHOW = 200                      # 지난 점검과 비교해 사라진 항목을 이만큼까지 보여 준다


class Session:
    """한 번의 탐지 실행과 그 결과를 들고 있는다."""

    def __init__(self, out_dir):
        self.out_dir = out_dir
        self.lock = threading.Lock()
        self.running = False
        self.error = None
        self.entry_url = ""
        self.pages_done = 0
        self.current = ""
        self.started_at = 0.0
        self.ended_at = 0.0
        self.prev_result = None
        self.result = None
        self.stop_requested = False
        # 조치 확인 진행 상황
        self.rechecking = False
        self.recheck_done = self.recheck_total = 0
        self.review = self._load_review()
        self.tkeys = {}             # 지금 결과의 항목 키 -> 문구 키
        self.keywords = lexicon.load_state(out_dir)   # 화면에서 고친 탐지 키워드
        self.last_ping = 0.0        # 화면이 살아 있는지 확인하는 신호
        self.bye_at = 0.0           # 화면이 닫히며 보낸 신호 (새로고침이면 곧 ping 이 다시 온다)
        self._load_last()
        self._sync_review()

    # ---- 지난 결과 ----
    def _last_path(self):
        return os.path.join(self.out_dir, LAST_FILE)

    def _load_last(self):
        """지난 탐지 결과를 되살린다. 없거나 깨졌으면 결과 없이 시작한다."""
        try:
            with open(self._last_path(), encoding="utf-8") as fp:
                doc = json.load(fp)
            if not isinstance(doc.get("findings"), list):
                return
            self.result = doc
            self.entry_url = doc.get("entry_url", "")
        except Exception:
            self.result = None

    def _save_last(self, res):
        doc = dict(res)
        for k in ("started", "finished"):
            if hasattr(doc.get(k), "isoformat"):
                doc[k] = doc[k].isoformat(timespec="seconds")
        doc["entry_url"] = self.entry_url
        try:
            write_json(self._last_path(), doc)
        except Exception:
            pass

    def _history(self, prev, res):
        """같은 주소를 지난번에 점검했으면 무엇이 새로 생기고 무엇이 사라졌는지 견준다."""
        # 한쪽이라도 도중에 멈춘 점검이면 '사라짐'이 조치 때문인지 덜 봐서인지 알 수 없다
        if (not prev or prev.get("entry_url") != self.entry_url or prev.get("stopped")
                or res.get("stopped")):
            return None
        prev_rows = {finding_key(f): f for f in prev.get("findings", [])}
        now = {finding_key(f) for f in res["findings"]} | {text_key(f) for f in res["findings"]}
        # 이번에 열지 못한 페이지의 광고는 '사라짐'이 아니라 '확인 못 함'이다
        opened = {page_key(u) for u in res.get("pages", [])}
        gone = [{k: f.get(k) for k in ("url", "location", "technique", "extra_finding", "evidence_text")}
                for key, f in prev_rows.items()
                if key not in now and text_key(f) not in now and page_key(f["url"]) in opened]
        finished = prev.get("finished")
        return {
            "prev_finished": finished.isoformat(timespec="seconds")
            if hasattr(finished, "isoformat") else finished,
            "prev_count": len(prev_rows),
            "prev_keys": sorted(set(prev_rows) | {text_key(f) for f in prev_rows.values()}),
            "gone_count": len(gone),
            "gone": gone[:GONE_SHOW],
        }

    # ---- 조치 상태 ----
    def _review_path(self):
        return os.path.join(self.out_dir, STATE_FILE)

    def _load_review(self):
        try:
            with open(self._review_path(), encoding="utf-8") as fp:
                return json.load(fp)
        except Exception:
            return {}

    def save_review(self, key, patch):
        if "status" in patch:
            patch = dict(patch, carried=False)    # 담당자가 직접 정했으면 이어받은 표시는 뗀다
        self.save_reviews({key: patch})
        return self.review[key]

    def save_reviews(self, patches, drop=()):
        """여러 항목의 조치 상태를 한 번에 고치고 파일에 한 번만 쓴다."""
        with self.lock:
            for key, patch in patches.items():
                row = self.review.setdefault(key, {"status": "open", "memo": ""})
                if key in self.tkeys:
                    row.setdefault("tkey", self.tkeys[key])
                row.update(patch)
            for key in drop:
                self.review.pop(key, None)
            write_json(self._review_path(), self.review, indent=1)

    def _sync_review(self):
        """새 결과의 항목마다 지난 조치 상태를 찾아 붙인다.

        - 옛 키(문구 없이 위치만)로 저장한 기록은 새 키로 옮긴다 (한 번만)
        - 위치가 밀렸어도 같은 페이지·같은 문구를 오탐 처리했으면 오탐 처리를 이어 간다.
          '조치완료'는 잇지 않는다. 지운 광고가 다른 자리에 다시 올라온 것이기 때문이다.
        """
        if not self.result:
            self.tkeys = {}
            return
        findings = self.result.get("findings", [])
        self.tkeys = {finding_key(f): text_key(f) for f in findings}
        fp_by_text = {}
        for row in self.review.values():
            if row.get("status") == "fp" and row.get("tkey"):
                fp_by_text.setdefault(row["tkey"], row)
        patches, drop = {}, []
        for f in findings:
            key, tkey = finding_key(f), text_key(f)
            if key in self.review:
                if "tkey" not in self.review[key]:
                    patches[key] = {"tkey": tkey}
                continue
            old = self.review.get(legacy_key(f))
            if old is not None:
                patches[key] = dict(old, tkey=tkey)
                drop.append(legacy_key(f))
            elif tkey in fp_by_text:
                src = fp_by_text[tkey]
                patches[key] = {"status": "fp", "memo": src.get("memo", ""), "tkey": tkey,
                                "carried": True}
        if patches or drop:
            try:
                self.save_reviews(patches, drop)
            except OSError:
                pass

    # ---- 조치 확인 ----
    def start_recheck(self):
        """광고가 나왔던 페이지만 다시 열어 지워졌는지 확인한다. 미조치 항목만 본다."""
        if self.running or self.rechecking or not self.result:
            return False
        targets = [f for f in self.result["findings"]
                   if self.review.get(finding_key(f), {}).get("status", "open") == "open"]
        if not targets:
            return False
        self.rechecking, self.recheck_done, self.recheck_total = True, 0, 0
        self.error, self.stop_requested = None, False
        threading.Thread(target=self._run_recheck, args=(targets,), daemon=True).start()
        return True

    def _run_recheck(self, targets):
        def progress(n, total, url):
            self.recheck_done, self.recheck_total, self.current = n, total, url
        try:
            res = recheck(targets, politeness=self.result.get("politeness"), progress=progress,
                          should_stop=lambda: self.stop_requested)
            now = time.strftime("%Y-%m-%dT%H:%M:%S")
            patches = {}
            for i, outcome in res.items():
                patch = {"check": outcome, "checked_at": now}
                if outcome in ("gone", "deleted"):
                    patch["status"] = "done"
                patches[finding_key(targets[i])] = patch
            self.save_reviews(patches)
        except Exception as exc:
            self.error = f"조치 확인 실패: {type(exc).__name__}: {exc}"
        finally:
            self.rechecking = False
            self.stop_requested = False

    # ---- 탐지 키워드 ----
    def edit_keywords(self, body):
        """화면에서 보낸 키워드 추가·삭제·끄기를 반영한다. 실패하면 사람이 읽을 문장을 돌려준다."""
        if self.running:
            return "탐지 중에는 키워드를 바꿀 수 없습니다. 탐지가 끝난 뒤 바꾸십시오."
        action, cat = body.get("action"), body.get("cat")
        names = {c[0]: c[1] for c in lexicon.CATEGORIES}
        with self.lock:
            st = self.keywords
            if action == "reset":
                st = {"added": {c: [] for c in names}, "off": {c: [] for c in names}}
            else:
                if cat not in names:
                    return "분류를 고르십시오."
                word = lexicon.clean_word(body.get("word", ""))
                if action == "add":
                    if len(word) < 2:
                        return "두 글자 이상 넣으십시오. 한 글자는 정상 글에 너무 자주 나옵니다."
                    home, builtin = lexicon.find_category(word)
                    for c in names:
                        if word in st["added"][c]:
                            home, builtin = c, False
                    if home:
                        tail = " 꺼 두었다면 목록에서 다시 켜십시오." if builtin else ""
                        return f"'{word}'은(는) 이미 '{names[home]}'에 있습니다.{tail}"
                    st["added"][cat].append(word)
                elif action == "remove":
                    if word in st["added"][cat]:
                        st["added"][cat].remove(word)
                elif action == "toggle":
                    off = st["off"][cat]
                    if body.get("on"):
                        if word in off:
                            off.remove(word)
                    elif word not in off:
                        off.append(word)
                else:
                    return "알 수 없는 요청입니다."
            lexicon.save_state(self.out_dir, st)
            self.keywords = st
        return None

    # ---- 탐지 ----
    def start(self, url, max_pages, cloaking=False, attachments=True, search_reflect=True,
              index_urls=None, subdomains=False, polite=False, check_links=False, ocr_images=False):
        if self.running or self.rechecking:
            return False
        self.running, self.error, self.stop_requested = True, None, False
        prev = self.result
        if prev is not None:
            prev = dict(prev, entry_url=self.entry_url)
        self.entry_url, self.pages_done, self.current = url, 0, ""
        self.started_at = time.time()
        self.prev_result = prev
        # 결과를 새로 만들므로 지난 탐지의 증거 사진·페이지 사본은 계속 쌓이지 않게 지운다.
        # 한 페이지도 보기 전에 중지하면 지난 결과로 되돌리므로, 끝날 때까지는 옆에 치워 둔다.
        for sub in ("evidence", "snapshots"):
            path = os.path.join(self.out_dir, sub)
            shutil.rmtree(path + ".old", ignore_errors=True)
            if os.path.isdir(path):
                try:
                    os.replace(path, path + ".old")
                except OSError:
                    shutil.rmtree(path, ignore_errors=True)
        self.result = None
        threading.Thread(target=self._run,
                         args=(url, max_pages, cloaking, attachments, search_reflect, index_urls,
                               subdomains, polite, check_links, ocr_images),
                         daemon=True).start()
        return True

    def _run(self, url, max_pages, cloaking=False, attachments=True, search_reflect=True,
             index_urls=None, subdomains=False, polite=False, check_links=False, ocr_images=False):
        def progress(n, page_url):
            self.pages_done, self.current = n, page_url
        try:
            res = scan(url, max_pages=max_pages, progress=progress,
                       evidence_dir=os.path.join(self.out_dir, "evidence"),
                       snapshot_dir=os.path.join(self.out_dir, "snapshots"),
                       cloaking=cloaking, attachments=attachments,
                       search_reflect=search_reflect, index_urls=index_urls,
                       subdomains=subdomains, check_links=check_links, ocr_images=ocr_images,
                       # 실제 기관 누리집: 페이지 사이 간격을 두고 robots.txt 를 지킨다 (--polite 와 같음)
                       polite=polite,
                       should_stop=lambda: self.stop_requested,
                       # 도중에 프로그램이 꺼져도 그때까지 찾은 결과 파일이 남는다
                       checkpoint=lambda partial: report.write(url, partial, self.out_dir))
            if res.get("stopped") == "user" and not res["pages"] and self.prev_result:
                self._restore_prev()          # 아무것도 보기 전에 멈췄으면 지난 결과를 그대로 둔다
                return
            # 진입 주소부터 열리지 않은 경우(차단·장애)는 지난 결과로 덮지 않고 그대로 알린다
            try:
                report.write(url, res, self.out_dir)
            except OSError as exc:
                # 쓰기 금지 폴더 등에서 실행했다. 점검한 결과까지 버리지 않고 화면에 남기며 알린다
                res["save_error"] = (f"결과 파일을 쓰지 못했습니다({self.out_dir}): {exc.strerror or exc}. "
                                     "쓰기 가능한 폴더(바탕화면 등)로 프로그램을 옮겨 다시 점검하십시오.")
            res["history"] = self._history(self.prev_result, res)
            self._save_last(res)
            self.result = res
            self._sync_review()
        except Exception as exc:            # 화면에 그대로 보여주기 위해 붙잡아 둔다
            self.error = f"{type(exc).__name__}: {exc}"
            if self.prev_result:
                self._restore_prev()
        finally:
            for sub in ("evidence", "snapshots"):
                shutil.rmtree(os.path.join(self.out_dir, sub + ".old"), ignore_errors=True)
            self.ended_at = time.time()
            self.running = False

    def _restore_prev(self):
        for sub in ("evidence", "snapshots"):
            path = os.path.join(self.out_dir, sub)
            if os.path.isdir(path + ".old"):
                shutil.rmtree(path, ignore_errors=True)
                try:
                    os.replace(path + ".old", path)
                except OSError:
                    pass
        self.result = self.prev_result
        self.entry_url = self.prev_result.get("entry_url", "")
        self._sync_review()

    # ---- 화면에 넘길 형태 ----
    def _evidence_image(self, key):
        if not key or not self.result:
            return None
        row = self.result.get("evidence", {}).get(key) or {}
        return f"/api/evidence/{row['image']}" if row.get("image") else None

    def payload(self):
        if not self.result:
            return {"findings": [], "pages": [], "meta": None}
        rows = []
        hist = self.result.get("history") or None
        prev_keys = set(hist["prev_keys"]) if hist else None
        for i, f in enumerate(self.result["findings"], 1):
            key = finding_key(f)
            rev = self.review.get(key, {"status": "open", "memo": ""})
            rows.append({
                "id": f"f_{i:03d}", "key": key, "url": f["url"],
                "location": f["location"], "technique": f["technique"],
                "evidence_text": f["evidence_text"], "normalized": f["normalized"],
                "reason": f["reason"], "keywords": f["keywords"],
                "extra_finding": f.get("extra_finding"),
                "grade": f.get("grade"), "guide": f.get("guide"),
                "status": rev.get("status", "open"), "memo": rev.get("memo", ""),
                "check": rev.get("check"), "checked_at": rev.get("checked_at"),
                "is_new": prev_keys is not None and not prev_keys.intersection(
                    (key, text_key(f), legacy_key(f))),
                "carried": rev.get("carried", False),
                "evidence_key": f.get("evidence_key"),
                "evidence_image": self._evidence_image(f.get("evidence_key")),
                "outer_html": (self.result.get("evidence", {})
                               .get(f.get("evidence_key"), {}).get("html")),
            })
        return {
            "findings": rows,
            "pages": self.result["pages"],
            "meta": {
                "entry_url": self.entry_url,
                "elapsed_sec": round(self.result["elapsed"], 2),
                "page_count": len(self.result["pages"]),
                "out_dir": self.out_dir,
                "finished_at": (self.result["finished"].isoformat(timespec="seconds")
                                if hasattr(self.result.get("finished"), "isoformat")
                                else self.result.get("finished")),
                "stopped": self.result.get("stopped"),
                "save_error": self.result.get("save_error"),
                "coverage": self.result.get("coverage"),
                "coverage_lines": report.coverage_lines(self.result),
                "politeness": self.result.get("politeness"),
                "recheck": last_recheck(rows),
                "history": ({k: v for k, v in hist.items() if k != "prev_keys"} if hist else None),
            },
        }


def last_recheck(rows):
    """마지막 조치 확인의 시각과 결과별 건수 (저장된 항목별 기록에서 계산해 다시 켜도 남는다)."""
    at = max((r["checked_at"] for r in rows if r.get("checked_at")), default=None)
    if not at:
        return None
    counts = {}
    for r in rows:
        if r.get("checked_at") == at:
            counts[r["check"]] = counts.get(r["check"], 0) + 1
    return {"at": at, "counts": counts}


def _text_of(f):
    return " ".join((f.get("normalized") or f.get("evidence_text") or "").split())


def _hash(raw):
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def finding_key(f):
    """재탐지해도 같은 검출을 같은 항목으로 인식하기 위한 키.

    문구까지 넣는다. 오탐 처리한 자리에 진짜 광고가 새로 들어오면 다른 항목으로 다시 알려야 한다.
    """
    return _hash(f"{f['url']}|{f['location']}|{f['technique']}|{_text_of(f)}")


def text_key(f):
    """자리를 빼고 페이지·기법·문구로만 알아보는 키.

    게시판에 글이 더해져 순번(nth-of-type)이 밀리면 위치가 달라진다. 같은 페이지의 같은 문구면
    같은 검출로 보고 오탐 처리를 이어 간다 (recheck.still_there 와 같은 기준).
    """
    return _hash(f"{page_key(f['url'])}|{f['technique']}|{f.get('extra_finding') or ''}|{_text_of(f)}")


def legacy_key(f):
    """문구를 키에 넣기 전(2026-10-02 이전)에 저장한 조치 상태를 찾기 위한 옛 키."""
    return _hash(f"{f['url']}|{f['location']}|{f['technique']}")


class Handler(BaseHTTPRequestHandler):
    session: Session = None

    def _send(self, code, body, ctype="application/json; charset=utf-8", headers=None):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        s = self.session
        if u.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as fp:
                return self._send(200, fp.read(), "text/html; charset=utf-8")
        if u.path == "/favicon.ico":
            # 앱 창의 제목표시줄·작업표시줄 아이콘은 이 파일을 따라간다.
            icon = asset_path("훤히.ico")
            if icon:
                with open(icon, "rb") as fp:
                    return self._send(200, fp.read(), "image/x-icon")
            return self._send(204, b"", "image/x-icon")
        if u.path.startswith("/fonts/"):
            # 화면 글꼴(Pretendard, SIL OFL)을 동봉해 폐쇄망·글꼴 미설치 PC 에서도 같게 보이게 한다
            font = asset_path(os.path.join("fonts", os.path.basename(u.path)))
            if font and font.endswith(".woff2"):
                with open(font, "rb") as fp:
                    return self._send(200, fp.read(), "font/woff2")
            return self._send(404, b"", "text/plain")
        if u.path == "/api/status":
            return self._send(200, json.dumps({
                "running": s.running, "error": s.error,
                "pages_done": s.pages_done, "current": s.current,
                "elapsed": round((time.time() if s.running else s.ended_at) - s.started_at, 1)
                if s.started_at else 0,
                "has_result": s.result is not None,
                "stopping": s.running and s.stop_requested,
                "rechecking": s.rechecking, "recheck_done": s.recheck_done,
                "recheck_total": s.recheck_total,
            }, ensure_ascii=False))
        if u.path == "/api/ping":
            s.last_ping = time.time()
            return self._send(200, json.dumps({"ok": True}))
        if u.path == "/api/keywords":
            return self._send(200, json.dumps({"categories": lexicon.describe(s.keywords)},
                                              ensure_ascii=False))
        if u.path == "/api/result":
            return self._send(200, json.dumps(s.payload(), ensure_ascii=False))
        if u.path == "/api/page":
            qs = parse_qs(u.query)
            target = (qs.get("u") or [""])[0]
            sel = (qs.get("sel") or [None])[0]
            name = (s.result or {}).get("snapshots", {}).get(page_key(target)) if s.result else None
            path = os.path.join(s.out_dir, "snapshots", name) if name else None
            if not path or not os.path.exists(path):
                return self._send(404, "<p style='font:14px sans-serif;padding:20px'>"
                                       "저장된 페이지가 없습니다.</p>", "text/html; charset=utf-8")
            with open(path, encoding="utf-8", errors="replace") as fp:
                html = fp.read()
            page, csp = snapshot_mod.build(html, target, sel)
            return self._send(200, page, "text/html; charset=utf-8",
                              {"Content-Security-Policy": csp})
        if u.path.startswith("/api/evidence/"):
            name = os.path.basename(u.path)
            path = os.path.join(s.out_dir, "evidence", name)
            if not name.endswith(".png") or not os.path.exists(path):
                return self._send(404, json.dumps({"error": "not found"}))
            with open(path, "rb") as fp:
                return self._send(200, fp.read(), "image/png")
        if u.path == "/api/report.html":
            return self._send(200, report_html.build(s.payload(), s.review),
                              "text/html; charset=utf-8")
        if u.path == "/api/export.csv":
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(["번호", "페이지 URL", "위치(CSS 선택자)", "은닉 기법",
                        "판정 근거", "검출 원문", "정규화 결과", "매칭 표현", "조치 상태", "메모",
                        "지난 점검 대비", "조치 확인"])
            for r in s.payload()["findings"]:
                w.writerow([r["id"], r["url"], r["location"], r["technique"], r["reason"],
                            r["evidence_text"], r["normalized"], " ".join(r["keywords"]),
                            {"open": "미조치", "done": "조치완료", "fp": "오탐"}.get(r["status"], r["status"]),
                            r["memo"], "새로 생김" if r["is_new"] else "",
                            report_html.check_text(r)])
            # 엑셀에서 한글이 깨지지 않도록 BOM 을 붙인다 (result.json 과 달리 CSV 는 무관)
            return self._send(200, buf.getvalue().encode("utf-8-sig"),
                              "text/csv; charset=utf-8")
        return self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                raise ValueError("JSON 객체가 아닙니다")
        except Exception:
            return self._send(400, json.dumps({"error": "요청 형식이 올바르지 않습니다."},
                                              ensure_ascii=False))
        try:
            return self._post(urlparse(self.path), self.session, body)
        except Exception as exc:            # 잘못된 값 하나로 화면 요청이 응답 없이 끊기지 않게
            return self._send(400, json.dumps({"error": f"요청을 처리하지 못했습니다: {exc}"},
                                              ensure_ascii=False))

    def _post(self, u, s, body):
        if u.path == "/api/recheck":
            ok = s.start_recheck()
            return self._send(200 if ok else 409, json.dumps(
                {"ok": ok, "error": None if ok else "확인할 미조치 항목이 없거나 이미 진행 중입니다."},
                ensure_ascii=False))
        if u.path == "/api/stop":
            if s.running or s.rechecking:
                s.stop_requested = True
            return self._send(200, json.dumps({"ok": True}))
        if u.path == "/api/scan":
            url = normalize_entry(body.get("url") or "")
            if not url.startswith(("http://", "https://")):
                return self._send(400, json.dumps({"error": "URL은 http:// 또는 https:// 로 시작해야 합니다."},
                                                  ensure_ascii=False))
            # 화면에서 고른 Search Console CSV 는 글자 인코딩을 모르므로 원본 바이트(base64)로 받는다
            index_urls = None
            if body.get("index_csv"):
                index_urls = parse_urls(decode_index(base64.b64decode(body["index_csv"])))
            ok = s.start(url, int(body.get("max_pages") or DEFAULT_MAX_PAGES),
                         cloaking=bool(body.get("cloaking")),
                         attachments=bool(body.get("attachments", True)),
                         search_reflect=bool(body.get("search_reflect", True)),
                         index_urls=index_urls,
                         subdomains=bool(body.get("subdomains")),
                         polite=bool(body.get("polite")),
                         check_links=bool(body.get("check_links")),
                         ocr_images=bool(body.get("ocr_images")))
            return self._send(200 if ok else 409,
                              json.dumps({"ok": ok, "error": None if ok else "이미 탐지가 진행 중입니다."},
                                         ensure_ascii=False))
        if u.path == "/api/bye":
            s.bye_at = time.time()
            return self._send(200, json.dumps({"ok": True}))
        if u.path == "/api/quit":
            self._send(200, json.dumps({"ok": True}))
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if u.path == "/api/keywords":
            err = s.edit_keywords(body)
            if err:
                return self._send(400, json.dumps({"error": err}, ensure_ascii=False))
            return self._send(200, json.dumps({"categories": lexicon.describe(s.keywords),
                                               "word": lexicon.clean_word(body.get("word", ""))},
                                              ensure_ascii=False))
        if u.path == "/api/keywords/test":
            # 같은 문장이 숨긴 글일 때와 화면에 그대로 보이는 글일 때 판정이 다르므로 둘 다 보여 준다
            text = str(body.get("text") or "")[:2000]
            hidden, shown = classify(text), classify(text, strict=True)
            return self._send(200, json.dumps({
                "normalized": hidden["normalized"], "evidence": hidden["evidence"],
                "hidden": hidden["is_ad"], "visible": shown["is_ad"],
                "homoglyph": hidden["homoglyph"], "jamo": hidden["jamo"],
            }, ensure_ascii=False))
        if u.path == "/api/review":
            if not body.get("key"):
                return self._send(400, json.dumps({"error": "key 가 없습니다."}, ensure_ascii=False))
            row = s.save_review(str(body["key"]), {k: str(body[k]) for k in ("status", "memo") if k in body})
            return self._send(200, json.dumps(row, ensure_ascii=False))
        return self._send(404, json.dumps({"error": "not found"}))

    def log_message(self, *a):
        pass


def _watchdog(session, httpd, grace=180, bye_grace=3, wake_gap=10):
    """화면이 닫히면 프로세스를 정리한다.

    창을 닫으면 화면이 /api/bye 를 보낸다. 새로고침이면 몇 초 안에 ping 이 다시 오므로
    그때는 끝내지 않는다. 신호를 못 보내고 꺼진 경우(강제 종료 등)는 ping 이 끊긴 지
    grace 초 뒤에 끝낸다. 창을 닫았으면 탐지 중이라도 끝낸다(결과를 볼 화면이 없다).

    PC 가 절전에서 깨어나면 마지막 신호가 몇 분 전으로 보여, 화면이 신호를 다시 보내기도 전에
    꺼져 버린다('Failed to fetch'). 1초마다 도는 이 반복이 wake_gap 초 넘게 건너뛰었으면 절전으로 보고
    신호 대기를 새로 시작한다. 최소화한 창의 타이머가 늦춰지는 경우도 있어 grace 를 넉넉히 둔다.
    """
    prev = time.time()
    while True:
        time.sleep(1)
        now = time.time()
        if now - prev > wake_gap and session.last_ping:
            session.last_ping = max(session.last_ping, now)
        prev = now
        if session.bye_at and session.last_ping < session.bye_at and now - session.bye_at > bye_grace:
            httpd.shutdown()
            return
        if session.running:
            continue
        if session.last_ping and now - session.last_ping > grace:
            httpd.shutdown()
            return


class _Server(ThreadingHTTPServer):
    # Windows 에서는 주소 재사용을 켜 두면 다른 프로세스가 쓰는 포트에도 붙어 버린다.
    # 그러면 이전에 띄운 훤히(구버전일 수도 있다)의 화면이 열린다. 반드시 꺼 둔다.
    allow_reuse_address = False


def _bind(port, tries=20):
    """지정한 포트가 쓰이고 있으면 다음 빈 포트를 쓴다."""
    for p in range(port, port + tries):
        try:
            return _Server(("127.0.0.1", p), Handler)
        except OSError:
            continue
    return _Server(("127.0.0.1", 0), Handler)       # 운영체제가 고른 빈 포트


def serve(out_dir, port=8900, open_browser=True):
    Handler.session = Session(out_dir)
    httpd = _bind(port)
    port = httpd.server_address[1]
    url = f"http://127.0.0.1:{port}/"

    # 화면(창)은 주 스레드를 써야 하므로 서버를 뒤로 보낸다.
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()
    print(f"탐지 도구를 시작합니다: {url}")

    if not open_browser:
        try:
            server_thread.join()
        except KeyboardInterrupt:
            httpd.shutdown()
        return

    if native_ui.available():
        if native_ui.run(url, "훤히 — 공공 누리집 숨은 불법광고 탐지 도구"):
            httpd.shutdown()          # 창을 닫으면 프로그램도 끝난다
            return

    # 네이티브 창을 쓸 수 없는 환경에서는 브라우저 창으로 연다.
    threading.Timer(0.3, lambda: print("  화면 방식:", open_app_window(url))).start()
    threading.Thread(target=_watchdog, args=(Handler.session, httpd), daemon=True).start()
    try:
        server_thread.join()
    except KeyboardInterrupt:
        httpd.shutdown()
