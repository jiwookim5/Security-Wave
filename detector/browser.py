"""브라우저 실행 경로를 한곳에서 정한다.

Windows 10/11 에 기본 탑재된 Edge 로 탐지한다. 브라우저를 동봉하지 않아
배포본이 작고, 서명 없는 대용량 실행 파일이 늘어나지 않는다.
"""

# 판정에 그림은 쓰지 않는다. 요청을 가로채 막으면 요청마다 프로그램과 왕복이 생겨 느리므로
# 브라우저 설정으로 아예 받지 않는다 (CSS 바탕 그림 포함)
LAUNCH_ARGS = ["--disable-dev-shm-usage", "--disable-gpu", "--blink-settings=imagesEnabled=false"]
CHANNEL = "msedge"


def launch_browser(pw, headless=True):
    """(browser, 사용한 엔진 이름) 을 돌려준다."""
    try:
        return (pw.chromium.launch(channel=CHANNEL, headless=headless, args=LAUNCH_ARGS),
                f"설치된 브라우저({CHANNEL})")
    except Exception as exc:
        raise RuntimeError(
            "Microsoft Edge 를 실행하지 못했습니다. Edge 가 설치되어 있는지 확인해 주세요.\n"
            f"  원인 - {type(exc).__name__}: {exc}"
        ) from exc
