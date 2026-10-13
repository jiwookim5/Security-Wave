"""난독화된 문자열을 사전 매칭이 가능한 형태로 되돌린다.

HOMOGLYPH / JAMO 탐지와 오탐 억제가 모두 이 모듈에 의존한다.
"""
import re
import unicodedata

CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
JONG = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"

ZERO_WIDTH = "​‌‍⁠﻿᠎"
SEPARATORS = ".·・_\\-*^~|/\\s"

# 키릴·그리스 문자를 시각적으로 같은 라틴 문자로 되돌린다.
CONFUSABLES = {
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x",
    "і": "i", "ј": "j", "ѕ": "s", "һ": "h", "ԁ": "d", "ɡ": "g", "ν": "v",
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O",
    "Р": "P", "С": "C", "Т": "T", "Х": "X", "Ѕ": "S", "І": "I", "Ј": "J",
    "α": "a", "ο": "o", "ρ": "p", "τ": "t", "υ": "u", "Ι": "I", "Ο": "O",
    # 소문자 라틴과 형태가 겹치는 키릴 자모를 추가로 되돌린다
    "ь": "b", "Ь": "b", "в": "b", "м": "m", "т": "t", "к": "k", "н": "h",
    "Β": "B", "Κ": "K", "Μ": "M", "Ν": "N", "Ρ": "P", "Τ": "T", "Υ": "Y",
    "Ε": "E", "Ζ": "Z", "Η": "H", "Χ": "X", "γ": "y", "ι": "i", "κ": "k",
}

# NFKC 가 풀지 못하는 장식 글자. 실제 불법광고 연락처에 쓰인다 (텔 🅞🅝❹❾❽❾, 텔레 sʙᴍᴛ3)
EXTRA_FOLD = {}
for _i in range(26):
    _c = chr(ord("a") + _i)
    EXTRA_FOLD[chr(0x1F150 + _i)] = _c      # 🅐 검은 원 문자
    EXTRA_FOLD[chr(0x1F170 + _i)] = _c      # 🅰 검은 네모 문자
    EXTRA_FOLD[chr(0x1F1E6 + _i)] = _c      # 🇦 지역 표시 문자
for _i in range(10):
    EXTRA_FOLD[chr(0x2776 + _i)] = str((_i + 1) % 10)   # ❶~❿
    EXTRA_FOLD[chr(0x2780 + _i)] = str((_i + 1) % 10)   # ➀~➉
    EXTRA_FOLD[chr(0x278A + _i)] = str((_i + 1) % 10)   # ➊~➓
EXTRA_FOLD["⓿"] = "0"
for _s, _c in zip("ᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡʏᴢ", "abcdefghijklmnopqrstuvwyz"):
    EXTRA_FOLD[_s] = _c                     # 작은 대문자

# 글자 사이에 끼워 넣는 이모지·기호(☑️ ⚡ ⥄ ≈ 등). 사전 매칭 전에 걷어낸다.
_SYMBOL_CATS = ("So", "Sk", "Sm", "Me")
_VARIATION = re.compile("[\ufe00-\ufe0f\U000e0000-\U000e007f]")


def _strip_symbols(t: str) -> str:
    t = _VARIATION.sub("", t)
    return "".join(ch for ch in t if unicodedata.category(ch) not in _SYMBOL_CATS
                   or unicodedata.normalize("NFKC", ch).isalnum())


_CYRILLIC = re.compile(r"[Ѐ-ӿ]")
_GREEK = re.compile(r"[Ͱ-Ͽ]")
_FULLWIDTH = re.compile(r"[！-｠￠-￦]")
# 호환 자모(U+3131~)와 조합용 자모(U+1100~) 양쪽을 모두 본다.
_COMPAT_JAMO = re.compile("[\\u3131-\\u318E\\u1100-\\u11FF]")
_LATIN = re.compile(r"[A-Za-z]")
# 자음 자모 옆에 'ㅣ' 대신 끼운 라틴 l·I (카ㅈl노 → 카지노). 생김새로 속이는 닮은꼴 위장이다
_JAMO_LATIN_I = re.compile(r"([ㄱ-ㅎ])[lI]")
_HANGUL = re.compile(r"[가-힣]")


def compose_jamo(text: str) -> str:
    """분해된 호환 자모열을 음절로 재결합한다. (ㅋㅏㅈㅣㄴㅗ -> 카지노)"""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        ci = CHO.find(c)
        if ci >= 0 and i + 1 < n:
            vi = JUNG.find(text[i + 1])
            if vi >= 0:
                ti, step = 0, 2
                if i + 2 < n:
                    cand = JONG.find(text[i + 2])
                    # 다음 글자가 또 중성이면 그 자음은 다음 음절의 초성이다
                    nxt_is_jung = i + 3 < n and JUNG.find(text[i + 3]) >= 0
                    if cand > 0 and not nxt_is_jung:
                        ti, step = cand, 3
                out.append(chr(0xAC00 + (ci * 21 + vi) * 28 + ti))
                i += step
                continue
        out.append(c)
        i += 1
    return "".join(out)


# 조합용 자모(U+1100 블록)를 호환 자모로 되돌리는 표.
# NFKC가 호환 자모를 초성 전용 코드로 바꿔버리면 종성을 붙일 수 없으므로,
# 재결합은 반드시 NFKC보다 먼저 수행한다.
_CONJOINING = {}
for _i, _c in enumerate(CHO):
    _CONJOINING[chr(0x1100 + _i)] = _c
for _i, _c in enumerate(JUNG):
    _CONJOINING[chr(0x1161 + _i)] = _c
_CONJOINING_BACK = dict(_CONJOINING)


def normalize(text: str) -> str:
    """사전 매칭 직전 단계까지 정규화한다."""
    t = "".join(ch for ch in text if ch not in ZERO_WIDTH)
    t = "".join(CONFUSABLES.get(ch, EXTRA_FOLD.get(ch, ch)) for ch in t)
    t = _strip_symbols(t)                         # ⓐ 같은 원문자는 NFKC 가 풀도록 남긴다
    t = re.sub(f"[{SEPARATORS}]+", "", t)         # 글자 사이 끼워넣은 구분자 제거
    t = "".join(_CONJOINING.get(ch, ch) for ch in t)
    t = _JAMO_LATIN_I.sub(r"\1ㅣ", t)
    t = compose_jamo(t)                           # NFKC보다 앞서야 한다
    t = unicodedata.normalize("NFKC", t)          # 전각/반각, 호환 문자 통일
    # NFKC가 전각 기호를 ASCII로 풀어놓으므로 구분자를 한 번 더 제거하고,
    # 결합되지 못한 자모는 호환 자모 표기로 되돌려 표기를 일관되게 유지한다.
    t = "".join(_CONJOINING_BACK.get(ch, ch) for ch in t)
    t = re.sub(f"[{SEPARATORS}]+", "", t)
    return t.lower()


def has_jamo_obfuscation(text: str) -> bool:
    """자모 분해 기법이 쓰였는가.

    'ㅋㅋㅋ', 'ㅇㅇ' 같은 통상적 표현과 구분하기 위해,
    재결합했을 때 실제로 한글 음절이 만들어지는 경우만 인정한다.
    """
    if not _COMPAT_JAMO.search(text):
        return False
    stripped = "".join(ch for ch in text if ch not in ZERO_WIDTH)
    # 조합용 자모(U+1100 블록)도 호환 자모로 맞춘 뒤에 재결합을 시도해야 한다.
    mapped = "".join(_CONJOINING.get(ch, ch) for ch in stripped)
    before = len(_HANGUL.findall(stripped))
    after = len(_HANGUL.findall(compose_jamo(mapped)))
    return after > before


def _is_disguised_letter(ch: str) -> bool:
    """ASCII 글자 한 자로 되돌아가는 비ASCII 글자인가.

    전각 라틴뿐 아니라 수학용 볼드(U+1D400~), 원문자 등 NFKC가 ASCII로
    되돌리는 글자를 한 번에 포착한다. '㈜'나 '½' 같은 기호는
    글자 범주가 아니므로 걸리지 않고, '㎏'·'℡'·'№'·'™' 처럼 여러 글자로 풀리는
    단위·약물 기호도 위장 글자가 아니다.
    """
    if ch in EXTRA_FOLD:
        return True
    cat = unicodedata.category(ch)
    # ⓐ 같은 원문자는 기호(So) 범주지만 NFKC 로 라틴 글자가 된다
    if ch.isascii() or not (cat.startswith("L") or cat == "So"):
        return False
    folded = unicodedata.normalize("NFKC", ch)
    return len(folded) == 1 and folded.isascii() and folded.isalnum()


# 문서에 단위로 흔히 쓰이는 글자 (500mℓ, 10µg). 라틴 글자로 풀리지만 위장으로 보지 않는다
_UNIT_LETTERS = set("ℓµ")
_SEP_RE = re.compile(f"[{SEPARATORS}{ZERO_WIDTH}－．＿／｜]+")


_FULLWIDTH_DIGIT = re.compile(r"[０-９]")


def _latinish(ch: str) -> bool:
    return ((ch.isascii() and ch.isalnum()) or ch in CONFUSABLES or _is_disguised_letter(ch)
            or bool(_FULLWIDTH_DIGIT.match(ch)))


def disguised_chars(text: str):
    """라틴 글자처럼 읽히는 낱말 안에 섞여 든 위장 글자들.

    닮은꼴 위장은 'саsinо', 'ｃａｓｉｎｏ', '텔 🅞🅝❹❾❽❾' 처럼 위장 글자가 다른 라틴(꼴) 글자와
    이어져 하나의 낱말로 읽혀야 의미가 있다. 날짜의 '～', '（주）', 단위 'μg', 목록 번호 'ⓐ'처럼
    홀로 쓰인 전각·특수 기호는 공공 문서에 흔하므로 세지 않는다.
    """
    t = _SEP_RE.sub("", text)
    out, run = [], []
    for ch in t + "\0":
        if _latinish(ch) and ch not in _UNIT_LETTERS:
            run.append(ch)
            continue
        fake = [c for c in run if not c.isascii()]
        lettered = any((EXTRA_FOLD.get(c) or unicodedata.normalize("NFKC", c)).isalpha() for c in run)
        # 전각 숫자만 이어진 경우는 연락처처럼 길 때만 위장으로 본다 ('２０２６년' 같은 표기는 제외)
        if fake and not lettered and len(fake) < 7:
            fake = []
        if len(run) >= 2 and fake:
            plain = [c for c in run if c.isascii() and c.isalpha()]
            # 키릴·그리스 글자만으로 된 낱말은 그 언어 글일 수 있다. ASCII 글자와 섞였거나
            # 전각·수학용·원문자처럼 그 자체로 위장용인 글자일 때만 위장으로 본다
            if plain or all(c not in CONFUSABLES for c in fake):
                out.extend(fake)
        run = []
    return out


def jamo_latin_i(text: str) -> bool:
    """자음 자모 옆에 'ㅣ' 대신 라틴 l·I 를 끼웠는가 (카ㅈl노)."""
    return bool(_JAMO_LATIN_I.search(_SEP_RE.sub("", text)))


def has_homoglyph(text: str) -> bool:
    """닮은꼴 글자 위장이 쓰였는가."""
    return bool(disguised_chars(text)) or jamo_latin_i(text)


def describe_homoglyph(text: str) -> str:
    """어떤 종류의 닮은꼴 글자가 몇 자 섞였는지 설명한다."""
    kinds = {}
    for ch in disguised_chars(text):
        if _FULLWIDTH.match(ch):
            kind = "전각 문자"
        elif _CYRILLIC.match(ch):
            kind = "키릴 문자"
        elif _GREEK.match(ch):
            kind = "그리스 문자"
        elif ch in EXTRA_FOLD:
            kind = "장식 문자"
        else:
            kind = "특수 라틴 변형"
        kinds[kind] = kinds.get(kind, 0) + 1
    if jamo_latin_i(text):
        kinds["'ㅣ' 대신 라틴 l"] = len(_JAMO_LATIN_I.findall(_SEP_RE.sub("", text)))
    if not kinds:
        return "닮은꼴 글자 혼용"
    return ", ".join(f"{k} {v}자" for k, v in kinds.items()) + " 혼용"


# 라틴 글자 자리에 끼워 넣는 숫자·기호 치환 (t0t0, c4sino, b3t ...).
# '1' 은 l 로도 i 로도 쓰인다 (be11y, cas1n0) 그래서 두 가지로 되돌려 본다.
_LEET = {"0": "o", "1": "l", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b", "@": "a", "$": "s"}
LEET = str.maketrans(_LEET)
LEET_I = str.maketrans(dict(_LEET, **{"1": "i"}))
# 라틴 글자가 섞인 낱말 안의 숫자만 바꾼다. 숫자만 이어진 전화번호(010-7070-...)가 'toto' 로
# 읽히지 않게 하기 위함이다.
_LEET_RUN = re.compile(r"[a-z0-9@$]+")
_HAS_LETTER = re.compile(r"[a-z]")


def _deleet_with(normalized: str, table) -> str:
    return _LEET_RUN.sub(lambda m: m.group(0).translate(table)
                         if _HAS_LETTER.search(m.group(0)) else m.group(0), normalized)


def deleet_all(normalized: str):
    """숫자 치환을 되돌린 보조 표기들 ('1' 을 l 로 본 것과 i 로 본 것).

    사전 매칭에만 쓴다. 표시용 문자열로는 쓰지 않는다.
    """
    return {_deleet_with(normalized, LEET), _deleet_with(normalized, LEET_I)}


def describe_jamo(text: str) -> str:
    """분해된 자모가 몇 자이고 무엇으로 재결합되는지 설명한다."""
    count = len(_COMPAT_JAMO.findall(text))
    return f"분해된 자모 {count}자를 재결합 → '{normalize(text)}'"
