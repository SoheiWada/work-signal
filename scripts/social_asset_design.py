"""WORK SIGNAL social-only visual language for explicitly tagged SECURITY WATCH articles.

This module never changes site cards, OG images, editorial metadata or SEO.
Classification is explicit: a reviewer must set social_security_severity=CRITICAL|HIGH.
"""
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONT_FILE = ROOT / "assets/fonts/NotoSansJP.ttf"
SEVERITIES = {
    "CRITICAL": {
        "background": "#15161B",
        "panel": "#1F2026",
        "ink": "#F7F5F2",
        "quiet": "#C0B6B7",
        "accent": "#EA5361",
        "glow": "#76252F",
        "tag": "#6B1D28",
        "tag_ink": "#FFE3E4",
        "wave": "#39212B",
    },
    "HIGH": {
        "background": "#1C222F",
        "panel": "#252D3C",
        "ink": "#F7F5F2",
        "quiet": "#C8C0B9",
        "accent": "#D6A46C",
        "glow": "#7E5A37",
        "tag": "#654A31",
        "tag_ink": "#FFE5C2",
        "wave": "#3E3A39",
    },
}


def security_style(article):
    """Return design tokens only when a reviewer explicitly specified a severity."""
    level = article.get("social_security_severity")
    if level is None:
        return None
    if level not in SEVERITIES:
        raise ValueError(
            "social_security_severity must be CRITICAL or HIGH: " + str(article.get("id", ""))
        )
    return SEVERITIES[level]


@lru_cache(maxsize=160)
def font(size, weight=700):
    face = ImageFont.truetype(str(FONT_FILE), size)
    face.set_variation_by_axes([weight])
    return face


def fit_one_line(draw, text, max_width, *, preferred_size, min_size=20, weight=800):
    """Never wrap severity labels: shrink the font to fit within the available width."""
    for size in range(preferred_size, min_size - 1, -2):
        face = font(size, weight)
        if draw.textlength(text, font=face) <= max_width:
            return face
    raise ValueError("Required one-line text cannot fit: " + text)


def wrap_words(text, face, max_width, max_lines):
    """Constrain Japanese headline without placing glyphs outside the image."""
    text = " ".join(str(text).split())
    lines, line = [], ""
    for char in text:
        if line and face.getlength(line + char) > max_width:
            lines.append(line)
            line = char
        else:
            line += char
    if line:
        lines.append(line)
    if len(lines) > max_lines:
        return None
    return lines


def fit_headline(text, width, max_lines, max_height, preferred_size):
    for size in range(preferred_size, 27, -2):
        face = font(size, 800)
        lines = wrap_words(text, face, width, max_lines)
        leading = round(size * 1.48)
        if lines is not None and len(lines) * leading <= max_height:
            return face, lines, leading
    raise ValueError("Security social headline too long for legible image")


def text_field(article, name, max_chars):
    text = article.get(name)
    if text is None:
        return ""
    if not isinstance(text, str) or len(text.strip()) > max_chars:
        raise ValueError("Invalid social security field: " + name)
    return " ".join(text.split())


def draw_signal(draw, *, width, height, style, top=0):
    # Quiet architectural grid and a single purposeful alert/signal trajectory.
    ink = style["wave"]
    for x in range(75, width - 60, 88):
        draw.line((x, top + 20, x, height - 70), fill=ink, width=1)
    for y in range(top + 35, height - 45, 88):
        draw.line((68, y, width - 68, y), fill=ink, width=1)
    mid = top + 132
    draw.line([(68, mid), (410, mid), (447, mid - 30),
               (487, mid + 35), (525, mid - 62), (566, mid + 29),
               (605, mid), (width - 68, mid)],
              fill=style["glow"], width=5, joint="curve")
    for x, y, r in ((width - 132, top + 100, 7), (width - 180, top + 136, 4)):
        draw.ellipse((x - r, y - r, x + r, y + r), fill=style["accent"])


def draw_brand(draw, style, *, left, y, right, label_size):
    name = font(label_size, 800)
    x = left
    for word, color in (("WORK", style["ink"]), (".", style["accent"]), ("SIGNAL", style["ink"])):
        draw.text((x, y), word, font=name, fill=color, anchor="lt")
        x += name.getlength(word)
    draw.text((right, y + 14), "SECURITY WATCH",
              font=font(21, 700), fill=style["accent"], anchor="rt")


def draw_severity(draw, article, *, style, left, top, right, preferred_size):
    severity = article["social_security_severity"]
    # The label is one atomic string. It MUST NEVER become CRITI / CAL.
    face = fit_one_line(draw, severity, right - left - 50,
                        preferred_size=preferred_size, min_size=54)
    draw.text((left, top), severity, font=face,
              fill=style["tag_ink"], anchor="lt")
    # Signal underline spans exactly the measured text, not the entire panel.
    length = int(draw.textlength(severity, font=face))
    draw.rectangle((left, top + face.size + 21, left + length, top + face.size + 28),
                   fill=style["accent"])
    return top + face.size + 60


def draw_article_info(draw, article, style, *, left, top, width):
    product = text_field(article, "social_security_product", 90)
    cve = text_field(article, "social_security_cve", 80)
    action = text_field(article, "social_security_action", 120)
    # Do not invent a CVE or remedial action; only display checked editorial fields.
    lines = []
    if product:
        lines.append(("対象", product))
    if cve:
        lines.append(("識別子", cve))
    if action:
        lines.append(("対処", action))
    if not lines:
        lines = [("確認", "対象と対処を記事本文で確認")]
    cursor = top
    for key, value in lines[:3]:
        draw.text((left, cursor), key, font=font(22, 700),
                  fill=style["accent"], anchor="lt")
        small = font(25, 600)
        candidate = wrap_words(value, small, width - 110, 2)
        if candidate is None:
            raise ValueError("Security metadata too long for social card")
        for i, line in enumerate(candidate):
            draw.text((left + 110, cursor + i * 36), line,
                      font=small, fill=style["ink"], anchor="lt")
        cursor += max(48, len(candidate) * 36 + 12)
    return cursor


def security_share_card(output, article):
    """Instagram feed: dark severity-aware 1080x1350 asset."""
    style = security_style(article)
    if style is None:
        raise ValueError("Security article must have explicitly checked severity")
    width, height = 1080, 1350
    image = Image.new("RGB", (width, height), style["background"])
    draw = ImageDraw.Draw(image)
    draw_signal(draw, width=width, height=height, style=style, top=280)
    draw.rectangle((0, 0, width, 11), fill=style["accent"])
    draw_brand(draw, style, left=78, y=62, right=1002, label_size=53)
    draw.line((78, 160, 1002, 160), fill=style["glow"], width=2)
    draw.text((78, 201), "THREAT INTELLIGENCE  /  WORK SIGNAL",
              font=font(21, 700), fill=style["quiet"], anchor="lt")
    draw_severity(draw, article, style=style, left=77, top=264,
                  right=1002, preferred_size=100)
    title_font, lines, leading = fit_headline(
        article["title"], width=915, max_lines=6,
        max_height=475, preferred_size=60)
    # Dark overlay preserves legibility over the technical background.
    draw.rectangle((64, 500, 1016, 957), fill=style["panel"])
    for index, line in enumerate(lines):
        draw.text((82, 550 + index * leading), line,
                  font=title_font, fill=style["ink"], anchor="lt")
    draw.line((78, 980, 1002, 980), fill=style["glow"], width=2)
    draw_article_info(draw, article, style, left=78, top=1010, width=924)
    draw.line((78, 1260, 1002, 1260), fill=style["glow"], width=2)
    draw.text((78, 1288), "signal.amberlight.co.jp",
              font=font(23, 600), fill=style["quiet"], anchor="lt")
    draw.text((1002, 1290), article["published_at"],
              font=font(20, 600), fill=style["quiet"], anchor="rt")
    path = output / "assets" / "instagram" / (article["id"] + ".jpg")
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="JPEG", quality=92, optimize=True,
               subsampling=0, progressive=True)
    return path


def security_story_card(output, article):
    """Instagram Story: dark severity-aware 1080x1920 JPEG with safe areas."""
    style = security_style(article)
    if style is None:
        raise ValueError("Security article must have explicitly checked severity")
    width, height = 1080, 1920
    image = Image.new("RGB", (width, height), style["background"])
    draw = ImageDraw.Draw(image)
    draw_signal(draw, width=width, height=height, style=style, top=420)
    draw.rectangle((0, 0, width, 13), fill=style["accent"])
    # Upper and lower blank areas are reserved for Instagram's UI chrome.
    draw_brand(draw, style, left=80, y=278, right=1000, label_size=51)
    draw.line((80, 394, 1000, 394), fill=style["glow"], width=2)
    draw.text((80, 459), "SECURITY ALERT  /  VERIFIED REPORT",
              font=font(22, 700), fill=style["quiet"], anchor="lt")
    draw_severity(draw, article, style=style, left=80, top=545,
                  right=1000, preferred_size=122)
    title_font, lines, leading = fit_headline(
        article["title"], width=908, max_lines=7,
        max_height=618, preferred_size=70)
    draw.rectangle((68, 803, 1012, 1370), fill=style["panel"])
    for index, line in enumerate(lines):
        draw.text((85, 849 + index * leading), line,
                  font=title_font, fill=style["ink"], anchor="lt")
    draw_article_info(draw, article, style, left=80, top=1400, width=920)
    draw.rectangle((80, 1680, 1000, 1778), outline=style["accent"], width=3)
    draw.text((108, 1702), "記事全文はプロフィールから",
              font=font(40, 700), fill=style["ink"], anchor="lt")
    path = output / "assets" / "stories" / (article["id"] + ".jpg")
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="JPEG", quality=92, optimize=True,
               subsampling=0, progressive=False)
    return path
