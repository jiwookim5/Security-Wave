"""불법광고 판별 사전.

은닉 기법이 쓰였다는 사실만으로는 위반이 아니다. 스킵내비게이션이나
스크린리더용 요약문도 화면에서 감춰지기 때문이다. 정확도 배점을 지키려면
'감춰졌다' + '광고다' 두 조건을 모두 만족할 때만 보고해야 한다.
"""

# 단독으로 나와도 광고로 볼 수 있는 표현 (도박·성매매 광고에서만 쓰는 은어와 '○○사이트' 꼴)
STRONG = [
    "먹튀", "안전놀이터", "메이저놀이터", "사설토토", "첫충", "입플", "꽁머니", "무료머니",
    "총판모집", "가입쿠폰", "가입코드", "라이브카지노", "온라인카지노",
    "토토사이트", "카지노사이트", "바카라사이트", "슬롯사이트", "홀덤사이트", "파워볼사이트",
    "bet365", "megabet",
    "조건만남", "출장안마", "오피스텔후기",
    # 성인 방송·음란물 (섹파: 성관계 상대 모집)
    "성인라방", "19라방", "섹파", "무료야동", "국산야동",
    # 출장 성매매 (출장안마와 같은 꼴)
    "출장마사지", "출장샵", "출장홈타이", "출장오피",
    # 영문 도박 광고
    "onlinecasino", "casinosite", "totosite",
]

# 도박 종목 이름. 광고에 늘 나오지만 정상 문서에도 나온다
# (동화 '창가의 토토', 카지노업 영업준칙, 바카라 게임규칙, 홀덤펍 단속 보도자료 등).
# 단독으로는 기준에 못 미치고, 다른 단서가 하나라도 붙어야 광고로 본다.
TOPIC = [
    "카지노", "바카라", "슬롯", "토토", "홀덤", "에볼루션", "배팅", "베팅", "환전", "파친코", "잭팟",
    "casino", "baccarat", "slot", "toto", "jackpot", "betting",
    "성인용품", "야동",
    # '음란'·'몸캠'은 신고·피해 주의 공고에도, '벗방'(노출 방송)은 국세청 탈세 적발 보도에도 나온다
    "음란", "성인방송", "몸캠", "벗방",
    # 성매매 업소 이름. 단속·적발 보도에도 나오므로 연락처·주소가 붙어야 광고로 본다
    # ('건마'는 '사건마다', '오피'는 '오피스'와 겹쳐 넣지 않는다.
    # '안마방'·'오피방'은 단속 보도에 여럿이 나란히 나와 점수가 겹치므로 넣지 않는다)
    "휴게텔", "키스방", "립카페", "룸싸롱", "풀싸롱", "셔츠룸",
    # 불법 사행성 게임(릴게임). '바다이야기 사태' 보도·단속 공고에도 나오므로 종목 이름으로 둔다
    # ('황금성'은 중국집 상호와 겹쳐 넣지 않는다)
    "바다이야기", "릴게임", "오션파라다이스",
    # 스포츠 도박 은어 (단폴: 한 경기만 거는 베팅)
    "단폴",
    # 성인물. '성인영상물 등급 분류' 안내에도 나온다
    "성인영상",
]

# 불법 거래를 가리키지만 정상 공고(예방 교육·피해 주의 안내)에도 나오는 표현.
# 단독으로는 기준에 못 미치고, 판매·연락처·금액 같은 유인 신호가 붙어야 광고로 본다.
# (2025년 보도된 공공 누리집 불법광고에 마약 거래·대포통장·돈세탁·고액 알바 광고가 섞여 있었다)
MEDIUM = [
    # 마약
    "필로폰", "대마초", "케타민", "엑스터시", "코카인", "물뽕", "빙두", "작대기", "아이스작대기",
    "떨액상", "대마젤리",
    # 통장·자금
    "대포통장", "통장매입", "통장임대", "통장삽니다", "법인통장", "돈세탁", "자금세탁",
    # 불법 대출
    "작업대출", "내구제", "무직자대출", "당일대출", "신불자대출",
    "법인장", "개인통장", "통장판매", "통장구매", "통장대여",
    # 마약 은어 (실제 공공 누리집 게시판 광고에서 확인)
    "떨액", "브액", "대마액상", "떨구매", "떨판매",
    # '대마' 단독은 삼베(안동포)·대마 재배 안내에도 나오므로 거래 표현과 붙은 꼴만 본다
    "대마판매", "대마구매", "대마구입", "대마사는곳", "대마파는곳", "대마구하는곳",
    # 불법 고수익 알바
    "고액알바", "꿀알바", "고수익알바", "당일지급알바", "재택부업", "단기고수익",
    # 불법 도박 유입 (스포츠 중계 미끼, 접속 주소 안내, 회원 DB 거래)
    "파워볼", "접속주소", "빠른주소", "보증업체", "구글검색",
    "토토디비", "토토db", "카지노디비", "카지노db", "디비팝니다", "db팝니다",
    # 대포폰·대포유심 (타인 명의 개통 휴대폰 거래. 달림폰·폰테크는 거래 은어)
    # ('선불유심'은 알뜰폰 안내에도 쓰이는 정상 용어라 넣지 않는다)
    "대포폰", "대포유심", "대포선불폰", "달림폰", "폰테크", "휴대폰개통대출",
    # 미등록 대부업 광고 표현
    "급전대출", "개인돈대출", "일수대출", "무서류대출", "무방문대출", "소액급전",
    # 발기부전 치료제 불법 판매 (식약처 단속·주의 안내에도 나오므로 판매·연락처가 붙어야 광고)
    "비아그라", "시알리스", "레비트라", "카마그라", "발기부전치료제", "viagra", "cialis", "levitra",
    # 먹는 낙태약 불법 판매 (식약처 단속 안내에도 나온다)
    "미프진", "낙태약",
    # 불법 흥신소 (개인정보 불법 수집·미행)
    "흥신소", "심부름센터", "사람찾기",
    # 휴대폰 소액결제·신용카드 현금화 (불법 대부. 금융감독원 주의 안내에도 나온다)
    "현금화", "카드깡", "상품권매입", "소액결제현금화", "상품권현금화",
    # 신분증·서류 위조
    "신분증위조", "위조신분증", "면허증위조", "졸업증명서위조",
    # 검색엔진 순위 조작 판매
    "백링크", "구글상위노출",
    # 성인 라이브 방송 유입. 지역 특산물 라이브커머스('복분자 라방 판매')에도 쓰여 종목 이름보다 약하게 둔다
    "라방",
    # 발기부전 치료제 (조루 치료제 포함)
    "프릴리지",
    # 불법 촬영물 판매
    "유출영상", "몰카영상", "도촬영상", "몰래카메라영상",
    # 불법 스포츠 중계 사이트 (도박 사이트로 끌어들이는 미끼). 방송사 편성 안내('KBS 스포츠중계')·행사 생중계
    # 안내('체육대회를 유튜브로 무료 실시간 중계합니다')와 겹치지 않게 해외 리그 이름을 붙인 꼴만 둔다
    "해외축구중계", "epl중계", "nba중계", "mlb중계",
]

# 단독으로는 약하고, 둘 이상 겹칠 때 광고로 보는 표현
WEAK = [
    "텔레그램", "상담", "지급", "쿠폰", "코드", "추천", "순위표", "바로가기",
    "가입", "체험", "이벤트", "검증", "주소", "총판", "모집", "보너스",
    "놀이터", "업체", "순위", "문의", "입금", "출금", "머니", "충전",
    "telegram", "vip", "promo", "event", "free",
    # 거래를 권하는 말 (MEDIUM 과 겹칠 때 의미가 생긴다)
    "팝니다", "삽니다", "매입", "직거래", "던지기", "비대면", "당일", "고수익", "선입금", "즉시",
    "해드립니다", "대행",
    # 불법 의약품·성인물·대출 광고에 붙는 말
    "비밀배송", "무삭제", "무직자", "신불자",
    "판매", "구매", "구입", "대여", "파는곳", "사는곳", "구하는곳", "구입방법", "구매방법",
    "무료", "실시간", "중계", "티비", "스포츠중계", "무료중계",
    # 도박 롤링(충전액 대비 배팅 조건)·투자 사기의 수익 약속
    "롤링", "수익보장", "원금보장",
    # 불법 투자 리딩방. 금융위 주의 안내·검거 보도에 훨씬 많이 나와 약하게 두고, 수익 약속·연락처와 겹쳐야 광고로 본다
    "리딩방",
    # '가입금'이 가입·입금으로 따로 세지 않게 한 낱말로 둔다
    "가입금",
]

# 예방 교육·피해 주의 공고에 쓰이는 말. 확정 표현이 없을 때 점수를 깎는다.
# ('대포통장 매입 제의를 받으면 신고하세요' 같은 안내문을 광고로 보지 않기 위함)
CAUTION = ["신고", "처벌", "예방", "주의", "피해", "사기", "금지", "범죄", "단속", "근절", "캠페인",
           "교육", "상담센터", "경찰", "불법", "도박문제", "중독",
           # 광고 문구를 따옴표로 인용해 경고하는 안내문 ('…라는 광고 문구에 속지 마세요')
           "속지", "광고문구",
           # 단속·수사 보도 ('가짜 비아그라 판매 성인용품점 적발', '코인 리딩방 일당 검거').
           # '차단'은 광고에도 '차단 걱정 없는 주소'로 쓰여 넣지 않는다
           *("적발", "검거", "기소", "구속", "덜미", "실태", "유혹", "미끼", "주의보", "수사", "송치", "혐의")]
# 위 가운데 보도체 낱말. 광고에는 거의 쓰이지 않는다
NEWS = ("적발", "검거", "기소", "구속", "덜미", "실태", "유혹", "미끼", "주의보", "수사", "송치", "혐의")


import re

from normalize import deleet_all

# 광고 문구에 반복적으로 따라붙는 유인 신호
# 텔레그램 표기 변형: 텔레·텔래·텔그·탤레·텔그램, '텔' 바로 뒤에 아이디 (텔richdb888, 텔@advjang)
# '텔레그램' 낱말만 있는 글(텔레그램 범죄 보도·주의 안내)은 연락처가 아니다. 뒤에 아이디가 붙어야 한다.
_CONTACT = re.compile(r"(@[a-z0-9_]{4,}|t\.me/|텔레(?!그램)|텔래|텔그|탤레|탤그|"
                      r"텔레그램\s*[@:]?\s*[a-z][a-z0-9_]{3,}|(?<!호)텔\s*[@:]?\s*[a-z][a-z0-9_]{3,}|"
                      r"카톡|010\d{7,8})")
_URLISH = re.compile(r"(https?://|www\.|\.com|\.net|bit\.ly|"
                     r"[a-z0-9-]+\.(kr|cc|vip|shop|top|xyz|bet|win|club|site|online|io|me|link))")
_PROMO = re.compile(r"(\d{1,3}%|\d+만원|\d+원)")
# 공공기관 주소는 광고가 끌어들이는 '외부 주소'가 아니다 (메뉴·안내문의 www.gov.kr 등)
_PUBLIC_HOST = re.compile(r"(https?://)?[a-z0-9.-]*\.(go\.kr|korea\.kr|mil\.kr|ac\.kr|re\.kr|gov)\b/?")

STRONG_W, TOPIC_W, TOPIC_MORE_W, MEDIUM_W, MEDIUM_MORE_W, WEAK_W, SIGNAL_W, THRESHOLD = 1.0, 0.7, 0.4, 0.6, 0.3, 0.3, 0.35, 1.0
CAUTION_W = 0.5
CAUTION_MAX = 3           # 안내문 표현이 여럿이면 셋까지 깎는다
# 외화 환전 문맥 (정규화된 글에서 찾으므로 띄어쓰기 없이 적는다)
FX_CONTEXT = ("외화", "환율", "외국환", "외국돈", "달러", "엔화", "유로", "위안", "해외여행", "여행자", "공항",
              "은행", "환전소")


def _maximal(words):
    """'순위'와 '순위표'처럼 겹치는 표현을 이중으로 세지 않는다."""
    return [w for w in words if not any(w != o and w in o for o in words)]


def match(normalized: str, obfuscated: bool = False, raw: str = "", strict: bool = False):
    """정규화된 문자열이 불법광고인지 가중치로 판정한다.

    접근성용 숨김 문구('추천 순위표 바로가기' 등)는 약한 단어만 여러 개 겹치므로
    단순 개수 기준으로는 오탐이 난다. 확정적 표현과 유인 신호에 무게를 둔다.

    raw 는 정규화 전 원문이다. 정규화가 . / - _ 를 지우므로 t.me/, www., .com 같은
    연락처·주소 신호는 원문에서 찾아야 한다.

    strict 는 화면에 그대로 보이는 글에 쓴다. 보이는 글은 숨긴 글보다 훨씬 많고
    도서 소개('창가의 토토')·규정 안내처럼 종목 이름이 섞인 정상 글이 흔하다.
    그래서 확정 표현이나 거래 은어가 있거나, 연락 수단·문자 위장이 붙은 경우만 인정한다.
    약한 단어 조합(이벤트·쿠폰·카톡 문의)이나 종목 이름만으로는 보고하지 않는다.
    """
    alts = deleet_all(normalized)     # t0t0 -> toto 처럼 숫자 치환을 되돌린 보조 표기

    def has(w):
        return w in normalized or any(w in a for a in alts)

    strong = _maximal([w for w in STRONG if has(w)])
    topic = _maximal([w for w in TOPIC if has(w)])
    topic = [w for w in topic if not any(w in s2 for s2 in strong)]
    # '환전'은 도박 머니 환전 말고 외화 환전(해외여행·은행 안내)에도 쓴다. 외화 문맥이고
    # 다른 도박 단서가 없으면 종목 이름으로 세지 않는다 ('당일 환전 보장 카지노'는 그대로 잡힌다)
    if topic == ["환전"] and not strong and any(w in normalized for w in FX_CONTEXT):
        topic = []
    medium = _maximal([w for w in MEDIUM if has(w)])
    medium = [w for w in medium if not any(w in s2 for s2 in strong + topic)]
    weak = _maximal([w for w in WEAK if has(w)])
    weak = [w for w in weak if not any(w in s2 for s2 in strong + topic + medium)]
    signals = []
    both = normalized + " " + (raw or "").lower()
    if _CONTACT.search(both):
        signals.append("연락처")
    if _URLISH.search(_PUBLIC_HOST.sub(" ", both)):
        signals.append("외부주소")
    if _PROMO.search(both):
        signals.append("금액·비율")
    if obfuscated:
        signals.append("문자 난독화")

    # 한 문구 안에서 겹치는 중간 표현(대포통장·통장매입)이 점수를 부풀리지 않게 둘째부터는 덜 센다
    score = (len(strong) * STRONG_W +
             (TOPIC_W + (len(topic) - 1) * TOPIC_MORE_W if topic else 0) +
             (MEDIUM_W + (len(medium) - 1) * MEDIUM_MORE_W if medium else 0) +
             len(weak) * WEAK_W + len(signals) * SIGNAL_W)
    # 예방·단속 안내문은 '토토사이트'처럼 확정 표현을 써도 연락처·주소를 달지 않는다.
    # 연락 수단이나 문자 위장이 붙은 글은 '사기 주의' 같은 말을 섞어도 광고로 본다.
    lure = any(x in signals for x in ("연락처", "외부주소", "문자 난독화"))
    if not lure:
        hits = sum(1 for c in CAUTION if c in normalized)
        score -= CAUTION_W * min(hits, CAUTION_MAX)
        # 확정 표현(먹튀·토토사이트 등)도 없이 거래 낱말만 겹친 글에 단속·주의 낱말이 섞였으면 보도·안내문이다
        # ('성인용품점 비아그라 판매는 불법'). 광고는 연락처·주소를 달거나 확정 표현을 쓴다.
        if hits and not strong:
            score = min(score, THRESHOLD - 0.05)
        # 단속·수사 보도는 확정 표현 하나쯤 인용해도('먹튀부터 시세조종까지… 리딩방 실태') 광고가 아니다
        if len(strong) <= 1 and any(w in normalized for w in NEWS):
            score = min(score, THRESHOLD - 0.05)
    # 약한 말만 겹친 글(숨긴 메뉴·탭·모달의 '회원가입 상담 이벤트 모집 문의')은 유인 신호가 없으면
    # 광고가 아니다. 숨긴 상자 안 글을 합쳐 판정하면 이런 글이 길게 이어져 약한 말이 쌓인다.
    if not (strong or topic or medium) and not lure:
        score = min(score, THRESHOLD - 0.05)
    # 화면에 보이는 글에서 종목 이름 하나를 자모로 풀어 쓴 것만으로는 광고가 아니다
    # ('한글 자모 조합 연습: ㅋㅏㅈㅣㄴㅗ'). 광고는 가입·지급·연락처처럼 권하는 말이 함께 붙는다.
    # 숨겨 둔 글은 그것만으로도 수상하므로 그대로 둔다.
    if strict and len(topic) == 1 and not (strong or medium or weak) and signals == ["문자 난독화"]:
        score = min(score, THRESHOLD - 0.05)
    is_ad = score >= THRESHOLD
    if strict and is_ad:
        contact = any(x in signals for x in ("연락처", "외부주소"))
        is_ad = bool(strong or medium or "문자 난독화" in signals or (topic and contact))
    return is_ad, strong + topic + medium + weak + signals



# ── 화면에서 관리하는 사용자 키워드 ──
# 담당자가 화면에서 단어를 더하거나 기본 단어를 끈 내역을 결과 폴더의 파일에 남기고,
# 실행할 때마다 기본 사전 위에 덧씌운다. 파일이 없거나 깨졌으면 기본 사전 그대로 동작한다.
USER_FILE = "keyword_state.json"

# (목록 이름, 화면 이름, 판정 방식 설명)
CATEGORIES = [
    ("STRONG", "확정 표현", "이 말만 있어도 광고로 봅니다. 광고에서만 쓰는 은어만 넣으십시오."),
    ("TOPIC", "종목·업종 이름", "보도·안내문에도 나오는 말이라 다른 단서(약한 말·연락처 등)가 하나 더 있어야 광고로 봅니다."),
    ("MEDIUM", "거래 표현", "예방 안내에도 쓰이는 말이라 판매·연락처·금액 같은 단서가 둘 이상 붙어야 광고로 봅니다."),
    ("WEAK", "약한 말", "단독으로는 광고가 아니고, 다른 표현과 겹칠 때 점수를 보탭니다."),
    ("CAUTION", "안내문 표현", "신고·예방 안내에 쓰는 말입니다. 연락처가 없는 글에서 광고 점수를 깎습니다."),
]
_CAT_IDS = [c[0] for c in CATEGORIES]
VERSION = 0                           # 사전을 고칠 때마다 올린다
_BUILTIN = {c: list(globals()[c]) for c in _CAT_IDS}


def _empty_state():
    return {"added": {c: [] for c in _CAT_IDS}, "off": {c: [] for c in _CAT_IDS}}


def clean_word(word: str) -> str:
    """매칭은 정규화된 글(띄어쓰기·구분자 제거, 소문자)에 대해 하므로 단어도 같은 꼴로 맞춘다."""
    from normalize import normalize
    return normalize(word or "").strip()


def apply_state(state):
    """기본 사전에서 꺼 둔 단어를 빼고 더한 단어를 붙여 판정 목록을 다시 만든다.

    목록 객체를 바꿔 끼우지 않고 내용만 고친다 (다른 모듈이 같은 목록을 들고 있어도 반영되게).
    """
    global VERSION
    VERSION += 1                      # 판정 결과를 기억해 둔 곳(findings.classify)이 새로 판정하게
    state = state or _empty_state()
    for c in _CAT_IDS:
        off = set(state.get("off", {}).get(c, []))
        added = [w for w in state.get("added", {}).get(c, []) if w not in _BUILTIN[c]]
        globals()[c][:] = [w for w in _BUILTIN[c] if w not in off] + added


def load_state(out_dir):
    import json, os
    try:
        with open(os.path.join(out_dir, USER_FILE), encoding="utf-8") as fp:
            state = json.load(fp)
        base = _empty_state()
        for part in ("added", "off"):
            for c in _CAT_IDS:
                base[part][c] = [str(w) for w in state.get(part, {}).get(c, []) if str(w)]
        apply_state(base)
        return base
    except Exception:
        apply_state(None)
        return _empty_state()


def save_state(out_dir, state):
    import os
    from fileio import write_json
    write_json(os.path.join(out_dir, USER_FILE), state, indent=1)
    apply_state(state)


def describe(state):
    """화면에 보여 줄 분류별 단어 목록."""
    rows = []
    for cid, name, desc in CATEGORIES:
        off = set(state["off"][cid])
        rows.append({
            "id": cid, "name": name, "desc": desc,
            "builtin": [{"word": w, "on": w not in off} for w in _BUILTIN[cid]],
            "added": list(state["added"][cid]),
        })
    return rows


def find_category(word):
    """이미 들어 있는 단어면 (분류, 기본 여부) 를 돌려준다."""
    for c in _CAT_IDS:
        if word in _BUILTIN[c]:
            return c, True
    return None, False
