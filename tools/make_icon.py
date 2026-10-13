"""프로그램 아이콘을 생성한다.

빨간 바탕에 흰 돋보기, 렌즈 안에 검은 줄과 붉은 줄 — 숨은 것을 찾아 짚는다는 뜻이다.
화면(흰 바탕·검정 글자·빨강 강조)과 같은 세 가지 색만 쓴다.

작업표시줄에서는 16~32px 로 보인다. 큰 그림 하나를 줄이면 가는 선이 뭉개지므로
크기마다 따로 그린다(4배로 그린 뒤 축소). 24px 이하는 형태를 더 단순하게 한다.
"""
import os

from PIL import Image, ImageDraw, ImageFilter

TOP = (228, 26, 36)                # 바탕 위쪽
BOTTOM = (184, 14, 22)             # 바탕 아래쪽
WHITE = (255, 255, 255, 255)
LENS = (243, 243, 243, 255)        # 렌즈 안쪽. 흰 테두리와 구분되도록 아주 옅은 회색
BLACK = (17, 17, 17, 255)
RED = (215, 20, 30, 255)

SIZES = [16, 24, 32, 48, 64, 128, 256]
SS = 4                              # 계단 현상을 줄이기 위한 확대 배율


def render(size):
    n = size * SS
    small = size <= 24
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))

    # 바탕: 위에서 아래로 옅게 어두워지는 둥근 사각형
    grad = Image.new("RGB", (1, n))
    for y in range(n):
        t = y / (n - 1)
        grad.putpixel((0, y), tuple(int(a + (b - a) * t) for a, b in zip(TOP, BOTTOM)))
    grad = grad.resize((n, n))
    mask = Image.new("L", (n, n), 0)
    margin = 0 if small else int(n * 0.03)
    ImageDraw.Draw(mask).rounded_rectangle(
        [margin, margin, n - 1 - margin, n - 1 - margin],
        radius=int(n * (0.20 if small else 0.22)), fill=255)
    img.paste(grad, (0, 0), mask)

    # 돋보기 도형은 따로 그려 그림자를 깔 수 있게 한다
    glass = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(glass)
    cx, cy = int(n * 0.43), int(n * 0.42)
    radius = int(n * (0.27 if small else 0.25))
    ring = int(n * (0.10 if small else 0.068))
    hw = int(n * (0.14 if small else 0.10))

    # 손잡이: 둥근 끝을 가진 굵은 막대
    x0, y0 = cx + int(radius * 0.70), cy + int(radius * 0.70)
    x1, y1 = int(n * 0.80), int(n * 0.80)
    d.line([(x0, y0), (x1, y1)], fill=WHITE, width=hw)
    d.ellipse([x1 - hw // 2, y1 - hw // 2, x1 + hw // 2, y1 + hw // 2], fill=WHITE)

    # 렌즈: 흰 테두리 + 옅은 안쪽
    d.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=WHITE)
    inner = radius - ring
    d.ellipse([cx - inner, cy - inner, cx + inner, cy + inner], fill=LENS)

    # 렌즈 안: 찾아낸 숨은 문구. 작은 크기에서는 붉은 줄 하나만 남긴다.
    if small:
        bars = [(RED, 1.25, 0.0)]
        line_h = int(n * 0.10)
    else:
        bars = [(BLACK, 0.95, -0.55), (RED, 1.25, 0.55)]
        line_h = int(n * 0.058)
    for color, wscale, offset in bars:
        w = int(inner * wscale)
        y = cy + int(offset * line_h * 1.9) - line_h // 2
        d.rounded_rectangle([cx - w // 2, y, cx + w // 2, y + line_h],
                            radius=line_h // 2, fill=color)

    # 그림자: 큰 크기에서만. 작은 크기에서는 번져 보인다.
    if not small:
        alpha = glass.split()[3].point(lambda a: int(a * 0.28))
        shadow = Image.new("RGBA", (n, n), (70, 0, 5, 0))
        shadow.putalpha(alpha)
        shadow = shadow.filter(ImageFilter.GaussianBlur(n * 0.018))
        img.alpha_composite(shadow, (0, int(n * 0.016)))

    img.alpha_composite(glass)
    return img.resize((size, size), Image.LANCZOS)


def main():
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
    os.makedirs(out_dir, exist_ok=True)
    images = [render(s) for s in SIZES]
    ico = os.path.join(out_dir, "훤히.ico")
    images[-1].save(ico, format="ICO", sizes=[(s, s) for s in SIZES],
                    append_images=images[:-1])
    images[-1].save(os.path.join(out_dir, "icon_preview.png"))
    print("생성:", ico, "/", ", ".join(f"{s}px" for s in SIZES))


if __name__ == "__main__":
    main()
