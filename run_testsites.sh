#!/bin/bash

# 훤히 시험 사이트 로컬 서버 실행 스크립트 (Mac/Linux용)
cd "$(dirname "$0")"

echo "훤히 시험 사이트 16개를 띄웁니다..."

# 각 testsite를 배경에서 실행
SITE=testsite PYTHONUNBUFFERED=1 python3 tools/serve.py 8765 > /tmp/hwonhi-8765.log 2>&1 &
echo "✓ testsite (포트 8765)"

SITE=testsite2 PYTHONUNBUFFERED=1 python3 tools/serve.py 8766 > /tmp/hwonhi-8766.log 2>&1 &
echo "✓ testsite2 (포트 8766)"

SITE=testsite3 PYTHONUNBUFFERED=1 python3 tools/serve.py 8767 > /tmp/hwonhi-8767.log 2>&1 &
echo "✓ testsite3 (포트 8767)"

SITE=testsite4 PYTHONUNBUFFERED=1 python3 tools/serve.py 8768 > /tmp/hwonhi-8768.log 2>&1 &
echo "✓ testsite4 (포트 8768)"

SITE=testsite5 PYTHONUNBUFFERED=1 python3 tools/serve.py 8769 > /tmp/hwonhi-8769.log 2>&1 &
echo "✓ testsite5 (포트 8769)"

SITE=testsite6 PYTHONUNBUFFERED=1 python3 tools/serve.py 8770 > /tmp/hwonhi-8770.log 2>&1 &
echo "✓ testsite6 (포트 8770)"

SITE=testsite7 PYTHONUNBUFFERED=1 python3 tools/serve.py 8771 > /tmp/hwonhi-8771.log 2>&1 &
echo "✓ testsite7 (포트 8771)"

SITE=testsite8 PYTHONUNBUFFERED=1 python3 tools/serve.py 8772 > /tmp/hwonhi-8772.log 2>&1 &
echo "✓ testsite8 (포트 8772)"

SITE=testsite9 PYTHONUNBUFFERED=1 python3 tools/serve.py 8773 > /tmp/hwonhi-8773.log 2>&1 &
echo "✓ testsite9 (포트 8773)"

SITE=testsite10 PYTHONUNBUFFERED=1 python3 tools/serve.py 8774 > /tmp/hwonhi-8774.log 2>&1 &
echo "✓ testsite10 (포트 8774)"

SITE=testsite11 PYTHONUNBUFFERED=1 python3 tools/serve.py 8775 > /tmp/hwonhi-8775.log 2>&1 &
echo "✓ testsite11 (포트 8775)"

SITE=testsite12 PYTHONUNBUFFERED=1 python3 tools/serve.py 8776 > /tmp/hwonhi-8776.log 2>&1 &
echo "✓ testsite12 (포트 8776)"

SITE=testsite13 PYTHONUNBUFFERED=1 python3 tools/serve.py 8777 > /tmp/hwonhi-8777.log 2>&1 &
echo "✓ testsite13 (포트 8777)"

SITE=testsite14 PYTHONUNBUFFERED=1 python3 tools/serve.py 8778 8779 8780 8781 8782 8783 8784 8785 > /tmp/hwonhi-8778.log 2>&1 &
echo "✓ testsite14 (포트 8778-8785)"

SITE=testsite15 PYTHONUNBUFFERED=1 python3 tools/serve.py 8786 > /tmp/hwonhi-8786.log 2>&1 &
echo "✓ testsite15 (포트 8786)"

SITE=testsite16 PYTHONUNBUFFERED=1 python3 tools/serve.py 8787 > /tmp/hwonhi-8787.log 2>&1 &
echo "✓ testsite16 (포트 8787)"

sleep 2

echo ""
echo "================================================================"
echo "  훤히 화면의 주소 입력란에 아래 주소 중 하나를 넣고 [탐지 시작]"
echo ""
echo "  기본 (주요 4종)       http://127.0.0.1:8765/board/list"
echo "  중간 난이도           http://127.0.0.1:8766/notice/index"
echo "  어려움 (iframe 중첩)  http://127.0.0.1:8767/portal/list"
echo "  어려움                http://127.0.0.1:8768/www/main"
echo "  첨부파일 (문서·zip)   http://127.0.0.1:8769/bbs/list"
echo "  검색결과 반사 점검    http://127.0.0.1:8770/main"
echo "  복합 (모두)           http://127.0.0.1:8771/issue/list"
echo "  복합                  http://127.0.0.1:8772/shop/list"
echo "  복합                  http://127.0.0.1:8773/gallery/main"
echo "  복합                  http://127.0.0.1:8774/menu/list"
echo "  복합                  http://127.0.0.1:8775/page/list"
echo "  복합                  http://127.0.0.1:8776/article/list"
echo "  복합                  http://127.0.0.1:8777/news/list"
echo "  복합                  http://127.0.0.1:8778/bbs/list"
echo "  복합                  http://127.0.0.1:8786/main"
echo "  복합                  http://127.0.0.1:8787/index"
echo ""
echo "  ⚠️ 주의: 실제 공공기관 누리집(go.kr 등)은 점검하지 마세요!"
echo "  ⚠️ 개발과 시험은 반드시 127.0.0.1의 시험 사이트에서만 합니다."
echo "================================================================"
echo ""
echo "모든 서버가 실행 중입니다. Ctrl+C를 누르면 종료됩니다."
echo ""

# 모든 백그라운드 프로세스가 계속 실행되도록 대기
wait
