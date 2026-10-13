"""주소 다루기: 방문·보고할 주소 다듬기, 같은 페이지 비교 키, 함정 주소, 점검 범위(어느 누리집까지 볼지)."""
import re
from functools import lru_cache
from urllib.parse import parse_qsl, quote, urldefrag, urlencode, urlparse, urlunparse


SKIP_EXT = (".pdf", ".hwp", ".zip", ".jpg", ".jpeg", ".png", ".gif", ".xls",
            ".xlsx", ".doc", ".docx", ".ppt", ".pptx", ".hwpx", ".mp4")


# 페이지 내용과 무관한 세션·유입 추적 파라미터. 남겨 두면 같은 글을 여러 번 방문해 페이지 예산이 샌다.
_NOISE_PARAM = re.compile(r"^(utm_\w+|jsessionid|phpsessid|aspsessionid\w*|gclid|fbclid)$", re.I)


# 달력·정렬·검색 조건처럼 값만 바꿔 끝없이 만들어지는 주소. 페이지 예산을 먹어 게시글에 닿기 전에
# 탐색이 끝나지 않도록, 다른 주소를 다 본 뒤에 남은 예산으로만 본다.
_TRAP_PARAM = re.compile(r"^(year|month|day|date|ym|yyyymm|yyyy|mm|dd|cal\w*|sort\w*|order\w*|"
                         r"search\w*|keyword|query|q|print\w*)$", re.I)


def low_priority(url: str) -> bool:
    return any(_TRAP_PARAM.match(k) and v.strip()
               for k, v in parse_qsl(urlparse(url).query, keep_blank_values=True))


# 파라미터 값의 글자 인코딩은 누리집마다 다르다 (옛 게시판은 EUC-KR: ?cate=%B0%A1 은 '가').
# UTF-8 로 풀면 UTF-8 이 아닌 바이트가 모두 '�' 로 바뀌어, 서로 다른 분류·검색 페이지가 같은 주소가 되거나
# 다시 쓴 주소가 망가진다. 바이트 하나를 글자 하나로 그대로 옮기는 latin-1 로 풀고 다시 묶는다.
_ASCII_SAFE = "".join(chr(i) for i in range(33, 127))


def _split_query(query, **kw):
    # 퍼센트 인코딩 없이 들어온 한글 등은 UTF-8 로 인코딩해 둔다 (전에 쓰던 방식과 같은 결과)
    return parse_qsl(quote(query, safe=_ASCII_SAFE), encoding="latin-1", **kw)


def _join_query(pairs):
    return urlencode(pairs, encoding="latin-1")


def clean_url(url: str) -> str:
    """방문·보고할 주소에서 세션 주소(;jsessionid=)와 추적 파라미터를 뗀다. 나머지 순서는 그대로 둔다."""
    p = urlparse(url)
    if not p.params and not _NOISE_PARAM.search(p.query or "") and "utm_" not in p.query.lower():
        return url
    q = [(k, v) for k, v in _split_query(p.query, keep_blank_values=True) if not _NOISE_PARAM.match(k)]
    return urlunparse(p._replace(params="", query=_join_query(q)))


def normalize_entry(url: str) -> str:
    """사람이 넣은 진입 주소를 다듬는다. 'www.기관.go.kr/board' 처럼 http:// 를 빼고 넣어도 연다.

    https 만 받는 누리집도 보통 http 를 https 로 넘겨 주므로 http 를 붙인다 (채점도 http·https 를 가리지 않는다).
    """
    url = (url or "").strip()
    if not url or re.match(r"^[a-z][a-z0-9+.-]*://", url, re.I):
        return url
    return "http://" + url.lstrip("/")


@lru_cache(maxsize=65536)      # 공통 메뉴 주소처럼 같은 주소를 거듭 비교한다
def page_key(url: str) -> str:
    """같은 페이지인지 가리는 비교용 키.

    끝 슬래시·fragment·세션 주소·추적 파라미터·빈 값은 무시하고, 파라미터 순서는 정렬한다
    (요강 채점도 순서만 다른 주소를 같은 페이지로 본다). 파라미터 값이 다르면 다른 페이지다.
    """
    u, _ = urldefrag(url)
    p = urlparse(u)
    path = p.path.rstrip("/") or "/"
    q = sorted((k, v) for k, v in _split_query(p.query) if not _NOISE_PARAM.match(k))
    return f"{p.netloc.lower()}{path}?{_join_query(q)}"


# 기관 도메인에서 '누리집 이름' 앞에 붙는 2단계 국가 도메인 (예: seoul.go.kr 의 go.kr)
_KR_SECOND = ("go.kr", "or.kr", "ac.kr", "re.kr", "co.kr", "ne.kr", "pe.kr", "mil.kr",
              "hs.kr", "ms.kr", "es.kr", "sc.kr", "kg.kr")
_IPV4 = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


def _host(netloc):
    return (urlparse("//" + netloc).hostname or "").lower()


def _strip_www(host):
    return host[4:] if host.startswith("www.") else host


def site_base(host):
    """서브도메인을 뗀 기관 도메인. www.seoul.go.kr·bbs.seoul.go.kr → seoul.go.kr"""
    if not host or _IPV4.match(host) or ":" in host or "." not in host:
        return host                      # IP 주소·localhost 는 서브도메인 개념이 없다
    labels = host.split(".")
    keep = 3 if any(host.endswith("." + k) for k in _KR_SECOND) else 2
    return ".".join(labels[-keep:])


class SiteScope:
    """어느 주소까지를 '점검 대상 누리집'으로 볼지 정한다.

    기본: 진입 주소와 같은 호스트·포트. www 유무는 같은 누리집으로 보고,
          진입 주소가 다른 호스트로 넘겨지면(리다이렉트) 넘겨진 곳도 같은 누리집으로 본다.
    subdomains: 같은 기관 도메인의 서브도메인·다른 포트까지 (bbs.기관.go.kr, 기관.go.kr:8080).
    같은 서버에 올라간 다른 기관 누리집(가상 호스트)은 점검 권한 밖이므로 따라가지 않는다.
    """

    def __init__(self, entry_url, subdomains=False):
        self.subdomains = subdomains
        self.hosts = set()
        self.bases = set()
        self.add(entry_url)

    def add(self, url):
        p = urlparse(url)
        self.hosts.add((_strip_www(_host(p.netloc)), p.port))
        self.bases.add(site_base(_strip_www(_host(p.netloc))))

    def allows(self, url):
        p = urlparse(url)
        host = _strip_www(_host(p.netloc))
        if (host, p.port) in self.hosts:
            return True
        return self.subdomains and site_base(host) in self.bases
