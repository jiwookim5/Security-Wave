# 기획서(서식4) 다시 만들기

제출본: `docs/기획서_훤히.docx` (A4, 9쪽). 그림은 `docs/기획서_그림/`.

| 파일 | 역할 |
|---|---|
| `make_doc.js` | 기획서 .docx 생성 (본문 내용이 이 파일 안에 있음) |
| `도식.html` | 그림 1(시스템 구조)·그림 2(사용자 흐름) 원본 |
| `render_figs.py` | `도식.html` 을 Edge 로 찍어 PNG 로 저장 |

```powershell
# 그림 1·2 다시 찍기 (.venv 필요)
.venv\Scripts\python docs\기획서_원본\render_figs.py docs\기획서_원본\도식.html docs\기획서_그림

# 기획서 생성 (Node.js 와 docx 패키지 필요: npm install docx@9)
node docs\기획서_원본\make_doc.js docs\기획서_그림 docs\기획서_훤히.docx
```

화면 캡처(그림 3~5)는 시험 사이트를 화면 모드로 점검해 1280×732(배율 1.5)로 찍은 것입니다.
- 그림 3: testsite4 사본을 점검한 뒤 첫 화면의 `::before` 광고 하나를 지우고 [조치 확인]을 누른 화면
- 그림 4: testsite 의 증거 보기 탭
- 그림 5: testsite6 에 `searchconsole_pages.csv` 를 색인 목록으로 넣어 점검한 화면

그림 1·2 를 다시 찍을 때 경로는 절대 경로로 줍니다(상대 경로면 `file URI` 오류).
신청자명·연락처는 제출 전에 Word 에서 직접 채웁니다.
