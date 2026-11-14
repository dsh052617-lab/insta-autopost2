"""카드뉴스 원고(JSON)를 1080x1350 JPEG 이미지들로 그린다."""
from __future__ import annotations

import glob
import re
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350
M = 96  # 좌우 여백
PAPER = (247, 246, 242)
INK = (22, 24, 29)
BODY = (52, 56, 64)
MUTED = (128, 132, 140)
WHITE = (255, 255, 255)


# ── 폰트 ────────────────────────────────────────────────────

def _find_ttc(weight: str) -> tuple[str, int]:
    patterns = [f"/usr/share/fonts/**/NotoSansCJK-{weight}.ttc",
                f"/usr/share/fonts/**/NotoSansCJKkr-{weight}.otf"]
    for pat in patterns:
        for path in glob.glob(pat, recursive=True):
            if path.endswith(".otf"):
                return path, 0
            for idx in range(10):
                try:
                    if "KR" in ImageFont.truetype(path, 10, index=idx).getname()[0]:
                        return path, idx
                except OSError:
                    break
    raise FileNotFoundError("한글 폰트(Noto Sans CJK)가 없어요. `sudo apt-get install fonts-noto-cjk`")


@lru_cache(maxsize=None)
def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path, idx = _find_ttc("Bold" if bold else "Regular")
    return ImageFont.truetype(path, size, index=idx)


# ── 텍스트 배치 ─────────────────────────────────────────────

def _text_w(text: str, f: ImageFont.FreeTypeFont) -> float:
    return f.getlength(text)


def wrap(text: str, f: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    """띄어쓰기 기준 줄바꿈. 한 단어가 너무 길면 글자 단위로 자른다. \\n은 강제 줄바꿈."""
    lines: list[str] = []
    for para in text.replace("\\n", "\n").split("\n"):
        cur = ""
        for word in para.split(" "):
            trial = f"{cur} {word}".strip()
            if _text_w(trial, f) <= max_w:
                cur = trial
                continue
            if cur:
                lines.append(cur)
            cur = ""
            for ch in word:
                if _text_w(cur + ch, f) > max_w:
                    lines.append(cur)
                    cur = ch
                else:
                    cur += ch
        lines.append(cur)
    # 마지막 줄에 1글자만 남는 '외톨이' 방지는 생략(가독성 영향 적음)
    return [ln for ln in lines if ln is not None]


def fit(text: str, max_w: int, max_h: int, start: int, minimum: int, bold: bool,
        leading: float) -> tuple[ImageFont.FreeTypeFont, list[str], int]:
    size = start
    while True:
        f = font(size, bold)
        lines = wrap(text, f, max_w)
        line_h = int(size * leading)
        if len(lines) * line_h <= max_h or size <= minimum:
            return f, lines, line_h
        size -= 2


def fit_lines(text: str, max_w: int, max_h: int, start: int, minimum: int, bold: bool,
              leading: float):
    """작성자가 넣은 줄바꿈(\\n)을 지키는 선에서 가장 큰 글자 크기를 찾는다."""
    wanted = len(text.replace("\\n", "\n").split("\n"))
    for size in range(start, minimum - 1, -2):
        f = font(size, bold)
        lines = wrap(text, f, max_w)
        if len(lines) == wanted and len(lines) * int(size * leading) <= max_h:
            return f, lines, int(size * leading)
    return fit(text, max_w, max_h, start, minimum, bold, leading)


def draw_lines(d: ImageDraw.ImageDraw, xy: tuple[int, int], lines: list[str],
               f: ImageFont.FreeTypeFont, line_h: int, fill) -> int:
    x, y = xy
    for ln in lines:
        d.text((x, y), ln, font=f, fill=fill)
        y += line_h
    return y


def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t: float):
    return tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3))


def header(d, project: str, category: str, color, sub_color, line_color):
    d.text((M, 96), project, font=font(30, True), fill=color)
    d.text((W - M, 96), category, font=font(28), fill=sub_color, anchor="ra")
    d.line((M, 150, W - M, 150), fill=line_color, width=2)


def footer(d, left: str, right: str, color, line_color):
    d.line((M, H - 128, W - M, H - 128), fill=line_color, width=2)
    d.text((M, H - 98), left, font=font(28, True), fill=color)
    d.text((W - M, H - 98), right, font=font(28), fill=color, anchor="ra")


# ── 카드 종류별 ──────────────────────────────────────────────

def rich_wrap(text: str, size: int, max_w: int) -> list[list[list[tuple[str, bool]]]]:
    """**강조** 표시가 있는 문장을 줄 → 단어 묶음 → (조각, 강조여부)로 나눈다.
    '**변동성**이'처럼 붙어 있는 조각은 한 단어로 묶어 띄어쓰기가 생기지 않게 한다."""
    groups: list[list[tuple[str, bool]]] = []
    for i, seg in enumerate(re.split(r"\*\*(.+?)\*\*", text)):
        for m in re.finditer(r"(\s*)(\S+)", seg):
            if groups and not m.group(1):
                groups[-1].append((m.group(2), i % 2 == 1))
            else:
                groups.append([(m.group(2), i % 2 == 1)])
        if seg and seg[-1].isspace():
            groups.append([])  # 다음 조각과 붙지 않도록 구분
    groups = [g for g in groups if g]
    space = font(size).getlength(" ")
    lines, cur, cur_w = [], [], 0.0
    for g in groups:
        gw = sum(font(size, b).getlength(t) for t, b in g)
        add = gw + (space if cur else 0)
        if cur and cur_w + add > max_w:
            lines.append(cur)
            cur, cur_w, add = [], 0.0, gw
        cur.append(g)
        cur_w += add
    if cur:
        lines.append(cur)
    return lines


def draw_rich(d, x: int, y: int, line, size: int, color, em_color):
    space = font(size).getlength(" ")
    for g in line:
        for t, b in g:
            f = font(size, b)
            d.text((x, y), t, font=f, fill=em_color if b else color)
            x += f.getlength(t)
        x += space


def cover(post: dict, ctx: dict) -> Image.Image:
    accent = ctx["accent"]
    img = Image.new("RGB", (W, H), accent)
    d = ImageDraw.Draw(img)
    soft = mix(accent, WHITE, 0.62)
    line = mix(accent, WHITE, 0.25)
    header(d, ctx["project"], ctx["date"], WHITE, soft, line)

    y = 360
    d.rectangle((M, y + 6, M + 6, y + 44), fill=WHITE)
    d.text((M + 24, y), post["cover_kicker"], font=font(36, True), fill=WHITE)
    f, lines, lh = fit_lines(post["cover_title"], W - 2 * M, 460, 104, 70, True, 1.3)
    y = draw_lines(d, (M, y + 110), lines, f, lh, WHITE)
    d.line((M, y + 40, M + 120, y + 40), fill=soft, width=4)
    sf, slines, slh = fit(post["cover_subtitle"], W - 2 * M, 140, 40, 32, False, 1.5)
    draw_lines(d, (M, y + 80), slines, sf, slh, mix(accent, WHITE, 0.85))
    if post.get("needs_disclaimer"):  # 특정 기업·투자 관련 글에만 표시
        note = "※ 특정 기업·상품에 대한 투자 권유가 아닌 정보 제공 목적의 글이에요"
        nf, nl, nlh = fit(note, W - 2 * M, 80, 26, 20, False, 1.5)
        draw_lines(d, (M, H - 175 - nlh * len(nl)), nl, nf, nlh, soft)
    footer(d, ctx["handle"], "넘겨서 보기  →", soft, line)
    return img


def body(slide: dict, idx: int, ctx: dict) -> Image.Image:
    accent = ctx["accent"]
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    rule = mix(PAPER, INK, 0.12)
    header(d, ctx["project"], ctx["category"], accent, MUTED, rule)

    terms = [t for t in slide.get("terms", []) if t.get("term")][:2]
    term_lh = 46
    terms_h = (len(terms) * term_lh + 56) if terms else 0
    top, bottom = 210, H - 170 - terms_h
    text_w = W - 2 * M - 50
    hf, hlines, hlh = fit(slide["heading"], W - 2 * M - 110, 200, 66, 50, True, 1.3)
    hl = (slide.get("highlight") or "").strip()
    if hl:
        bf, blines, blh = fit(hl, W - 2 * M - 72, 170, 110, 64, True, 1.18)
        hl_h = blh * len(blines) + 34 + 56
    else:
        hl_h = 40

    # 요점 글자 크기: 들어가는 가장 큰 크기
    points = slide["points"][:3]
    for size in range(56, 39, -2):
        wrapped = [rich_wrap(p, size, text_w) for p in points]
        lh = int(size * 1.5)
        pts_h = sum(len(w) * lh for w in wrapped) + (len(points) - 1) * 56
        if hlh * len(hlines) + 40 + hl_h + pts_h <= bottom - top:
            break
    y = top + 40  # 모든 카드에서 같은 위치에서 시작 (넘길 때 시선이 흔들리지 않게)

    d.text((M, y + 4), f"{idx:02d}", font=font(hf.size, True), fill=mix(accent, PAPER, 0.45))
    y = draw_lines(d, (M + 110, y), hlines, hf, hlh, INK) + 40
    if hl:
        box_w = max(bf.getlength(ln) for ln in blines) + 72
        d.rounded_rectangle((M, y, min(W - M, M + box_w), y + blh * len(blines) + 34), radius=18,
                            fill=mix(accent, PAPER, 0.88))
        draw_lines(d, (M + 36, y + 8), blines, bf, blh, accent)
        y += blh * len(blines) + 34 + 56
    else:
        y += 40

    for lines in wrapped:
        d.rectangle((M + 4, y + int(size * 0.55), M + 16, y + int(size * 0.55) + 12), fill=accent)
        for ln in lines:
            draw_rich(d, M + 50, y, ln, size, BODY, accent)
            y += lh
        y += 56

    if terms:  # 카드 하단 용어 풀이
        ty = H - 150 - len(terms) * term_lh
        d.line((M, ty - 26, W - M, ty - 26), fill=rule, width=2)
        for t in terms:
            tf = font(28, True)
            label = f"{t['term']}"
            d.text((M, ty), label, font=tf, fill=accent)
            x = M + tf.getlength(label) + 18
            mf, mlines, _ = fit(t.get("meaning", ""), int(W - M - x), term_lh, 28, 22, False, 1.3)
            d.text((x, ty + (28 - mf.size) // 2 + 1), mlines[0] if len(mlines) == 1 else " ".join(mlines),
                   font=mf, fill=MUTED)
            ty += term_lh

    footer(d, ctx["handle"], f"{ctx['page']} / {ctx['total']}", MUTED, rule)
    return img


def summary(post: dict, ctx: dict) -> Image.Image:
    """한 줄 정리 + 출처 (마지막 카드)."""
    accent = ctx["accent"]
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    rule = mix(PAPER, INK, 0.12)
    header(d, ctx["project"], ctx["category"], accent, MUTED, rule)

    d.text((M, 220), "한 줄 정리", font=font(60, True), fill=INK)
    y = 350
    for i, t in enumerate(post["takeaways"][:3], 1):
        d.ellipse((M, y, M + 60, y + 60), fill=accent)
        d.text((M + 30, y + 30), str(i), font=font(32, True), fill=WHITE, anchor="mm")
        f, lines, lh = fit(t.replace("**", ""), W - 2 * M - 96, 130, 44, 34, True, 1.45)
        draw_lines(d, (M + 96, y), lines, f, lh, INK)
        y += max(60, lh * len(lines)) + 48

    box_top = max(y + 30, 820)
    bg = mix(accent, PAPER, 0.93)
    d.rounded_rectangle((M - 24, box_top, W - M + 24, H - 160), radius=22, fill=bg)
    d.text((M + 8, box_top + 34), "출처", font=font(30, True), fill=accent)
    yy = box_top + 90
    for s in ctx["sources"][:3]:
        kind = "공식 발표" if s.get("tier") == "official" else "언론 보도"
        meta = " · ".join(x for x in (s["source"], kind, str(s.get("published") or "")[:10]) if x)
        d.text((M + 8, yy), meta, font=font(28, True), fill=INK)
        title, sf = s.get("title", ""), font(26)
        line = title
        while sf.getlength(line) > W - 2 * M - 30 and len(line) > 4:
            line = line[:-2]
        d.text((M + 8, yy + 40), line + ("…" if line != title else ""), font=sf, fill=MUTED)
        yy += 92
    footer(d, ctx["handle"], f"{ctx['page']} / {ctx['total']}", MUTED, rule)
    return img


def render_all(post: dict, cfg: dict, topic_key: str, out_dir: Path,
               date_text: str, sources: list[dict]) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    slides = post["slides"][:4]
    total = 1 + len(slides) + 1
    ctx = {
        "accent": hex_rgb(cfg["topics"][topic_key]["color"]),
        "handle": cfg["account"]["handle"],
        "project": cfg["account"].get("project", ""),
        "category": cfg["topics"][topic_key]["label"] + " 이슈",
        "date": date_text,
        "sources": sources,
        "total": total,
    }
    images = [cover(post, {**ctx, "page": 1})]
    for i, s in enumerate(slides, 1):
        images.append(body(s, i, {**ctx, "page": i + 1}))
    images.append(summary(post, {**ctx, "page": total}))

    paths = []
    for i, im in enumerate(images, 1):
        p = out_dir / f"{i:02d}.jpg"
        im.save(p, "JPEG", quality=92, optimize=True)
        paths.append(p)
    return paths
