# 함께 작업하는 방법

## 꼭 지킬 것

- **실제 공공기관 누리집은 점검하지 않습니다.** 시험은 로컬 시험 사이트(`시험사이트 실행.bat`, `tools/serve.py`, `testsite/scenario_suite.py`)에서만 합니다.
- `main`에 바로 push하지 않습니다. 브랜치를 따서 작업하고 PR로 합칩니다.
- 실행 파일(`.exe`), 빌드 결과(`build/`, `dist/`), 점검 결과(`out/`, `result*.json`, `evidence/`), 압축 파일은 커밋하지 않습니다. `.gitignore`에 들어 있습니다.

## 작업 순서

```powershell
git switch main
git pull
git switch -c 작업-이름          # 예: fix/jamo-false-positive, feat/hwpx-hidden
# ... 수정 ...
git add <파일>
git commit -m "무엇을 왜 바꿨는지 한 줄로"
git push -u origin 작업-이름
```

GitHub에서 PR을 열고, 다른 팀원 1명이 확인한 뒤 합칩니다.

## PR 올리기 전에 확인할 것

탐지 로직(`detector/`)이나 판정 사전(`lexicon.py`)을 바꿨다면 회귀 점검을 돌려 기존 시험 사이트 결과가 나빠지지 않았는지 확인합니다.

```powershell
# 처음 한 번: main에서 기준 결과 만들기 (_regress/baseline.json, 커밋되지 않음)
.venv\Scripts\python tools\regress.py --save-baseline

# 작업 브랜치에서: 기준과 비교
.venv\Scripts\python tools\regress.py
```

PR 설명에 회귀 점검 결과(점수 변화, 새로 생긴 오탐·미탐)를 적어 주세요.

## 커밋 메시지

이 저장소는 커밋 메시지를 한국어로, 바뀐 동작이 드러나게 씁니다.

- 좋은 예: `탐지 사전: 외화 환전 안내를 도박 '환전'으로 잡지 않기`
- 나쁜 예: `fix`, `수정`

## 실행 파일 배포

제출하거나 공유할 실행 파일은 `tools\build.ps1`로 빌드한 뒤 GitHub **Releases**에 올립니다.
태그는 날짜로 붙입니다(예: `v2026.10.10`).
