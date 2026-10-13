# 훤히 — 공공 누리집 숨은 불법광고 탐지 도구

공공 웹사이트에 숨겨진 불법광고(도박·성인·마약 등)를 찾아내는 Windows용 도구입니다.
'공공 웹사이트 불법광고 탐지 도구 개발 공모전' 출품작입니다.

**실행 파일만 필요하면** [Releases](https://github.com/CJ-AI-SecurityWave/hwonhi/releases)에서 `hwonhi.exe`를 받으세요. GitHub가 한글 파일 이름을 받지 않아 영문 이름으로 올라가 있으니, 받은 뒤 `훤히.exe`로 바꿔도 됩니다. Windows 전용입니다.

## 빠르게 시작하기

Windows 11, Python 3.12 이상, Microsoft Edge(기본 탑재)가 필요합니다.

```powershell
git clone https://github.com/CJ-AI-SecurityWave/hwonhi.git
cd hwonhi
python -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install playwright pypdf olefile pyinstaller pypdfium2
```

그림 속 글자 인식까지 쓰려면 `winrt-*` 패키지도 설치합니다. 자세한 내용은 [빌드 매뉴얼](docs/빌드_매뉴얼.md) 4장을 보세요.
`playwright install`은 하지 않아도 됩니다. 탐지에는 시스템에 설치된 Edge를 씁니다.

### 소스에서 실행

```powershell
.venv\Scripts\python detector\main.py
```

### 시험 사이트로 점검해 보기

`시험사이트 실행.bat`을 실행하면 시험 사이트 16개가 로컬에서 뜨고, 넣어 볼 주소 목록이 화면에 나옵니다.

> ⚠️ **실제 공공기관 누리집(go.kr 등)은 점검하지 마세요.** 허락 없이 크롤링하면 공격으로 보일 수 있습니다.
> 개발과 시험은 반드시 `127.0.0.1`의 시험 사이트에서만 합니다.

### 실행 파일 빌드

```powershell
powershell -ExecutionPolicy Bypass -File tools\build.ps1
```

결과물은 `dist\훤히\훤히.exe`입니다. 빌드한 실행 파일은 저장소에 커밋하지 않고 **GitHub Releases**에 올립니다.

## 폴더 구성

| 경로 | 내용 |
|---|---|
| `detector/` | 탐지 엔진과 화면(UI) |
| `tools/` | 시험 서버, 채점·회귀 점검, 빌드 스크립트 |
| `testsite*/` | 검증용 시험 사이트와 정답셋 |
| `docs/` | 사용설명서, 빌드 매뉴얼, 기획서, 제출 체크리스트 |

모듈별 설명은 [빌드 매뉴얼](docs/빌드_매뉴얼.md) 3장에 있습니다.

## 문서

- [사용설명서](docs/사용설명서.md)
- [빌드 매뉴얼](docs/빌드_매뉴얼.md)
- [제출 체크리스트](docs/제출_체크리스트.md)
- [함께 작업하는 방법](CONTRIBUTING.md)
