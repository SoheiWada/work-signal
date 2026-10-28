"""Build crawlable GitHub Pages output from the approved article feed."""
import argparse
import html
import json
import re
import shutil
import math
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode, urlparse
from xml.etree import ElementTree as ET
from PIL import Image, ImageDraw, ImageFont
try:
    from .security_watch import security_feed as merged_security_feed
except ImportError:
    from security_watch import security_feed as merged_security_feed
try:
    from .social_asset_design import (
        security_style, security_share_card, security_story_card
    )
except ImportError:
    from social_asset_design import (
        security_style, security_share_card, security_story_card
    )
try:
    from .seo_metadata import article_modifications, modification_date, latest_date
except ImportError:
    from seo_metadata import article_modifications, modification_date, latest_date

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://signal.amberlight.co.jp/"
HOME_PAGE_SIZE = 12
ARCHIVE_PAGE_SIZE = 24
CATEGORIES = {"AI", "仕事", "マネジメント", "お金", "経済", "Crypto", "SECURITY"}
SECTIONS = [("何が起きた？", "what_happened"), ("なぜ重要？", "why_it_matters"),
            ("仕事や暮らしへの影響", "impact"), ("確認しておきたいこと", "caveats")]
CARD_SIZE = (1200, 630)


@lru_cache(maxsize=128)
def card_font(size, weight=700):
    font = ImageFont.truetype(str(ROOT / 'assets/fonts/NotoSansJP.ttf'), size)
    font.set_variation_by_axes([weight])
    return font


def wrap_title(text, font, width):
    lines = []
    for paragraph in text.split('\n'):
        line = ''
        for char in paragraph:
            if line and font.getlength(line + char) > width:
                carry = ''
                # Keep Japanese opening/closing punctuation with its surrounding text.
                if line[-1] in '「『（【〈《［(' or char in '、。，．！？：；」』）】〉》］!?.,:;)':
                    carry, line = line[-1], line[:-1]
                if line:
                    lines.append(line)
                line = carry + char
            else:
                line += char
        if line:
            lines.append(line)
    return lines


def fit_title(text, width=1072, height=290):
    for size in range(84, 27, -2):
        font = card_font(size, 800)
        lines = wrap_title(text, font, width)
        line_height = math.ceil(size * 1.3)
        if len(lines) * line_height <= height and all(font.getlength(line) <= width for line in lines):
            balanced_width = min(width, sum(font.getlength(part) for part in text.split('\n')) / max(1, len(lines)) + size)
            balanced = wrap_title(text, font, balanced_width)
            if len(balanced) <= len(lines):
                lines = balanced
            return font, lines, line_height
    raise ValueError('Article title is too long for a readable share image')


def share_card(output, article=None):
    paper, ink, orange = '#f2efe7', '#191918', '#fa4c24'
    image = Image.new('RGB', CARD_SIZE, paper)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1200, 8), fill=ink)
    brand = card_font(43, 800)
    brand_baseline = 39 - brand.getbbox('WORK', anchor='ls')[1]
    x = 64
    for text, color in [('WORK', ink), ('.', orange), ('SIGNAL', ink)]:
        draw.text((x, brand_baseline), text, font=brand, fill=color, anchor='ls')
        x += brand.getlength(text)
    draw.text((1136, 58), 'READ BEYOND THE HEADLINE', font=card_font(16), fill=ink, anchor='rt')
    draw.line((64, 109, 1136, 109), fill=ink, width=1)
    label = article['category'] if article else 'INDEPENDENT NEWS'
    label_font = card_font(19, 700)
    label_width = math.ceil(label_font.getlength(label)) + 32
    draw.rectangle((64, 139, 64 + label_width, 175), fill=orange)
    draw.text((80, 145), label, font=label_font, fill=ink, anchor='lt')
    if article:
        draw.text((88 + label_width, 146), article['published_at'], font=card_font(18), fill=ink, anchor='lt')
    title = article['title'] if article else 'ニュースは短く。\n意味は深く。'
    font, lines, line_height = fit_title(title)
    for i, line in enumerate(lines):
        draw.text((64, 211 + i * line_height), line, font=font,
                  fill=orange if not article and i == len(lines) - 1 else ink, anchor='lt')
    draw.line((64, 540, 1136, 540), fill='#c9c4ba', width=1)
    draw.text((64, 566), 'signal.amberlight.co.jp', font=card_font(19, 500), fill=ink, anchor='lt')
    for radius in [22, 14, 6]:
        draw.ellipse((1112 - radius, 582 - radius, 1112 + radius, 582 + radius), outline=orange, width=2)
    path = output / 'assets/og' / ((article['id'] if article else 'home') + '.png')
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, optimize=True)
    return path



def instagram_share_card(output, article):
    """Produce a portrait JPEG, suitable for Instagram's public image URL."""
    paper, ink, orange, muted = '#f2efe7', '#191918', '#fa4c24', '#68665f'
    width, height = 1080, 1350
    image = Image.new('RGB', (width, height), paper)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width, 11), fill=ink)
    x = 78
    brand = card_font(62, 800)
    for label, color in [('WORK', ink), ('.', orange), ('SIGNAL', ink)]:
        draw.text((x, 68), label, font=brand, fill=color, anchor='lt')
        x += brand.getlength(label)
    draw.text((78, 154), 'READ BEYOND THE HEADLINE', font=card_font(19, 700),
              fill=muted, anchor='lt')
    draw.line((78, 202, 1002, 202), fill='#c9c4ba', width=2)
    category = article['category']
    badge_font = card_font(28, 700)
    badge_width = min(460, int(badge_font.getlength(category)) + 40)
    draw.rectangle((78, 252, 78 + badge_width, 311), fill=orange)
    draw.text((98, 262), category, font=badge_font, fill=ink, anchor='lt')
    draw.text((1002, 264), article['published_at'], font=card_font(24, 600),
              fill=ink, anchor='rt')
    title = article['title']
    found = None
    for font_size in range(66, 27, -2):
        font = card_font(font_size, 800)
        lines = wrap_title(title, font, 920)
        leading = int(font_size * 1.42)
        if len(lines) * leading <= 580:
            found = (font, lines, leading)
            break
    if found is None:
        raise ValueError('Instagram share card title is too long: ' + article['id'])
    font, lines, leading = found
    for index, line in enumerate(lines):
        draw.text((78, 365 + leading * index), line, fill=ink, font=font, anchor='lt')
    wave_y = 985
    draw.line([(78, wave_y), (360, wave_y), (395, wave_y), (420, wave_y-45),
               (445, wave_y+50), (468, wave_y-75), (493, wave_y+55),
               (518, wave_y), (1002, wave_y)], fill=orange, width=5, joint='curve')
    excerpt = article['summary'].replace('\n', ' ').strip()
    excerpt_font = card_font(24, 500)
    excerpt_lines = wrap_title(excerpt, excerpt_font, 918)[:4]
    for index, line in enumerate(excerpt_lines):
        draw.text((78, 1042 + index * 40), line, font=excerpt_font, fill='#403e38', anchor='lt')
    draw.line((78, 1242, 1002, 1242), fill='#c9c4ba', width=2)
    draw.text((78, 1275), 'signal.amberlight.co.jp', font=card_font(23, 700),
              fill=ink, anchor='lt')
    draw.text((1002, 1275), 'WORK SIGNAL  /  OFFICIAL', font=card_font(16, 700),
              fill=muted, anchor='rt')
    path = output / 'assets' / 'instagram' / (article['id'] + '.jpg')
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format='JPEG', quality=92, optimize=True, progressive=True,
               subsampling=0)
    return path



def instagram_story_card(output, article):
    """Render a purpose-built 1080x1920 Story JPEG with generous UI safe areas."""
    width, height = 1080, 1920
    ink, paper, orange, quiet = '#171716', '#f4f0e8', '#fa4c24', '#bdbbb3'
    image = Image.new('RGB', (width, height), ink)
    draw = ImageDraw.Draw(image)

    # Restrained broadcast/signal treatment, distinct from the 4:5 feed card.
    draw.rectangle((0, 0, 1080, 13), fill=orange)
    for offset in range(0, 440, 24):
        draw.line((width - offset, 260, width, 260 + offset),
                  fill='#282827', width=2)

    brand_font = card_font(59, 800)
    x = 80
    for label, color in [('WORK', paper), ('.', orange), ('SIGNAL', paper)]:
        draw.text((x, 264), label, font=brand_font, fill=color, anchor='lt')
        x += brand_font.getlength(label)
    draw.text((82, 351), 'READ BEYOND THE HEADLINE',
              font=card_font(22, 700), fill=quiet, anchor='lt')
    draw.line((80, 412, 1000, 412), fill='#5a5954', width=2)

    draw.rectangle((80, 476, 94, 527), fill=orange)
    draw.text((114, 482), article['category'], font=card_font(31, 700),
              fill=orange, anchor='lt')
    draw.text((1000, 485), article['published_at'],
              font=card_font(23, 600), fill=quiet, anchor='rt')

    title = article['title'].replace('\\n', ' ').strip()
    fitted = None
    for size in range(79, 33, -2):
        font = card_font(size, 800)
        lines = wrap_title(title, font, 906)
        leading = round(size * 1.46)
        if len(lines) * leading <= 690 and all(font.getlength(line) <= 906 for line in lines):
            fitted = (font, lines, leading)
            break
    if fitted is None:
        raise ValueError('Instagram Story title too long: ' + article['id'])
    font, lines, leading = fitted
    for index, line in enumerate(lines):
        draw.text((80, 587 + index * leading), line,
                  font=font, fill=paper, anchor='lt')

    # Signal line / divider sits safely below variable-height headlines.
    wave_y = max(1235, 625 + len(lines) * leading + 76)
    if wave_y > 1330:
        raise ValueError('Instagram Story lacks space for signal footer')
    draw.line([(80, wave_y), (345, wave_y), (375, wave_y - 46),
               (406, wave_y + 56), (436, wave_y - 85),
               (468, wave_y + 48), (504, wave_y),
               (1000, wave_y)], fill=orange, width=5, joint='curve')

    summary_font = card_font(27, 500)
    summary = article['summary'].replace('\\n', ' ').strip()
    for index, line in enumerate(wrap_title(summary, summary_font, 912)[:3]):
        draw.text((80, wave_y + 72 + index * 44), line,
                  font=summary_font, fill=quiet, anchor='lt')

    # Leave lower controls of Instagram's Story viewer unobstructed.
    draw.rectangle((80, 1556, 1000, 1658), outline=orange, width=2)
    draw.text((106, 1585), '記事全文はプロフィールから',
              font=card_font(39, 700), fill=paper, anchor='lt')
    draw.text((80, 1700), 'signal.amberlight.co.jp',
              font=card_font(24, 600), fill=quiet, anchor='lt')

    path = output / 'assets' / 'stories' / (article['id'] + '.jpg')
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format='JPEG', quality=92, optimize=True,
               progressive=False, subsampling=0)
    return path


def image_metadata(url, alt):
    return ('<meta property="og:image" content="' + url + '">'
            + '<meta property="og:image:secure_url" content="' + url + '">'
            + '<meta property="og:image:type" content="image/png">'
            + '<meta property="og:image:width" content="1200">'
            + '<meta property="og:image:height" content="630">'
            + '<meta property="og:image:alt" content="' + esc(alt) + '">'
            + '<meta name="twitter:card" content="summary_large_image">'
            + '<meta name="twitter:image" content="' + url + '">'
            + '<meta name="twitter:image:alt" content="' + esc(alt) + '">')


def esc(value):
    return html.escape(str(value), quote=True)


def json_ld(value):
    # A feed value must never be able to terminate this script element.
    return '<script type="application/ld+json">' + json.dumps(
        value, ensure_ascii=False).replace("<", "\\u003c").replace(
            ">", "\\u003e").replace("&", "\\u0026") + '</script>'


def published_articles(data):
    if not isinstance(data, list):
        raise ValueError("Article feed must be a list")
    articles, seen = [], set()
    for article in data:
        if not isinstance(article, dict) or article.get("status") != "published":
            continue
        score = article.get("score")
        if not (article.get("format") in ("special_story", "management_guide") or (isinstance(score, (int, float)) and not isinstance(score, bool) and score >= 80)):
            continue
        if article.get("category") not in CATEGORIES:
            raise ValueError("Unknown category in published article")
        identifier = article.get("id", "")
        if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,119}", identifier):
            raise ValueError("Published article has an unsafe ID")
        if identifier in seen:
            raise ValueError("Duplicate published article ID: " + identifier)
        seen.add(identifier)
        for key in ["title", "summary", "published_at", "source_url"]:
            if not isinstance(article.get(key), str) or not article[key].strip():
                raise ValueError("Missing published article field: " + key)
        date.fromisoformat(article["published_at"])
        source = urlparse(article["source_url"])
        if source.scheme != "https" or not source.netloc:
            raise ValueError("Primary source must use HTTPS")
        articles.append(article)
    return articles


def favicon_links():
    return ('<link rel="icon" href="/favicon.svg" type="image/svg+xml" sizes="any">'
            '<link rel="icon" href="/favicon-96.png" type="image/png" sizes="96x96">'
            '<link rel="icon" href="/favicon-192.png" type="image/png" sizes="192x192">'
            '<link rel="shortcut icon" href="/favicon.ico" type="image/x-icon">'
            '<link rel="apple-touch-icon" href="/apple-touch-icon.png" sizes="180x180">')


def write_favicons(output):
    # Keep the existing W, orange dot and palette at stable URLs.
    scale = 8
    image = Image.new('RGBA', (64 * scale, 64 * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, 64 * scale - 1, 64 * scale - 1), radius=12 * scale, fill='#191918')
    draw.text((6 * scale, 45 * scale), 'W', font=card_font(43 * scale, 700), fill='#f2efe7', anchor='ls')
    draw.ellipse((50 * scale, 44 * scale, 60 * scale, 54 * scale), fill='#fa4c24')
    for size, filename in ((96, 'favicon-96.png'), (192, 'favicon-192.png'), (180, 'apple-touch-icon.png')):
        image.resize((size, size), Image.Resampling.LANCZOS).save(output / filename)
    image.save(output / 'favicon.ico', sizes=[(16, 16), (32, 32), (48, 48), (96, 96)])


def related_articles(article, articles):
    def tokens(item):
        title = item['title'].lower()
        terms = set(re.findall(r'[a-z][a-z0-9_-]{2,}', title))
        terms.update(title[i:i + 2] for i in range(len(title) - 1)
                     if all('一' <= char <= '龥' for char in title[i:i + 2]))
        return terms
    terms = tokens(article)
    ranked = [(len(terms & tokens(item)), item['published_at'], item['id'], item)
              for item in articles if item['id'] != article['id'] and item['category'] == article['category']]
    return [item for score, _, _, item in sorted(ranked, key=lambda value: value[:3], reverse=True) if score > 0][:2]


def article_url(article):
    return BASE + "articles/" + article["id"] + "/"


def threads_url(article=None, placement="post_01"):
    url = article_url(article) if article else BASE
    campaign = article["id"] if article else "profile"
    return url + "?" + urlencode({"utm_source": "threads", "utm_medium": "social",
                                  "utm_campaign": campaign, "utm_content": placement})


def story_icon(deep):
    """Compact, aspect-safe signal mark. Geometry matches the guide's signal vocabulary."""
    brief = "M0 13 H20.8 L23.8 13 L27.2 8 L30.2 18.4 L33.8 3.4 L37.8 22.2 L41.4 13 H96"
    deep_line = "M0 13 C15 13 21.6 7.2 33 9.6 S49 20.2 60.8 15.4 S78.6 9.6 96 13"
    echo = "M0 13 C16 13 24 23 35 19.8 S48 2.6 61 7 S78 18.4 96 13"
    line = deep_line if deep else brief
    rings = (
        '<circle class="signal-ring" cx="49" cy="13" r="10"/>'
        '<circle class="signal-ring" cx="49" cy="13" r="6"/>'
        '<path class="signal-echo" d="' + echo + '"/>'
        if deep else ''
    )
    return ('<svg class="signal-mark" viewBox="0 0 96 26" '
            'preserveAspectRatio="xMidYMid meet" aria-hidden="true" focusable="false">'
            + rings + '<path class="signal-base" d="' + line + '"/>'
            '<path class="signal-sweep" d="' + line + '"/></svg>')


def card_image_path(article):
    """Safe root-relative, site-owned image path or None."""
    image = article.get("card_image")
    if not isinstance(image, str) or not re.fullmatch(
            r"/assets/[A-Za-z0-9/_-]+\.(?:png|jpe?g|webp|avif)", image, re.I):
        return None
    return image


def article_card_image(article):
    """An optional article-owned visual; no generic cover competes with headlines."""
    image = card_image_path(article)
    if not image:
        return ""
    alt = article.get("card_image_alt")
    if not isinstance(alt, str):
        alt = ""
    return ('<figure class="story-figure"><img src="' + esc(image) + '" alt="'
            + esc(alt) + '" loading="lazy" decoding="async"></figure>')



def story_link(article):
    """A true touch target: the article card itself remains scrollable."""
    line = "M0 16 H30 L42 16 L49 10 L57 23 L65 4 L73 29 L81 16 H120"
    return (
        '<a class="story-link" href="' + article_url(article)
        + '" aria-label="' + esc(article["title"]) + ' のシグナルを読む">'
        '<span class="story-link-copy"><span class="story-link-title">READ THE SIGNAL</span></span>'
        '<span class="story-link-mark">'
        '<svg class="story-link-wave" viewBox="0 0 120 32" '
        'preserveAspectRatio="xMidYMid meet" aria-hidden="true">'
        '<path class="link-wave-track" d="' + line + '"/>'
        '<path class="link-wave-live" d="' + line + '"/>'
        '</svg></span></a>'
    )


def article_card(article):
    deep = article.get("format") == "deep_dive"
    form = "MANAGEMENT GUIDE · 独自解説" if article.get("format") == "management_guide" else ("SPECIAL STORY · 自社製品紹介" if article.get("format") == "special_story" else ("SIGNAL DEEP DIVE" if deep else "SIGNAL BRIEF"))
    minutes = "PRACTICAL GUIDE" if article.get("format") == "management_guide" else ("SPECIAL FEATURE" if article.get("format") == "special_story" else ("4–7 MIN" if deep else "1–2 MIN"))
    return ('<article class="story"><div class="story-head"><div class="story-top">'
            '<span class="story-category">' + esc(article["category"]) + '</span>'
            '<span class="story-format">' + story_icon(deep)
            + '<span class="story-format-label">' + form + '</span></span>'
            '</div><span class="story-readtime">' + minutes + '</span></div>'
            '<div class="story-content"><h3>' + esc(article["title"]) + '</h3>'
            + article_card_image(article) + '<p>' + esc(article["summary"])
            + '</p>' + story_link(article) + '</div></article>')



def management_cta(article):
    """Only management guides and the disclosed first-party service feature have a CTA."""
    if article.get("format") == "management_guide":
        note = article.get("note_url", "")
        intro = BASE + "articles/20261021-manager-relight-introduction/"
        note_label = "noteでさらに深く読む（有料記事）" if "management-stop-doing-work" in article.get("id", "") else "noteでさらに深く読む"
        return ('<section class="block" aria-label="記事の次の一歩"><h2>この記事を、次の一歩につなげる</h2>'
                '<p>この解説をさらに深く学びたい方へ。現場経験や実践方法をnoteで紹介しています。</p>'
                '<p><a href="' + esc(note) + '" target="_blank" rel="noopener noreferrer">' + note_label + ' ↗</a></p>'
                '<p><a href="https://note.com/amber_light/m/m9104f843fd06" target="_blank" rel="noopener noreferrer">マガジン「リーダーの灯」でまとめて読む ↗</a></p>'
                '<p>自分の状況について相談したい方へ。MANAGER reLIGHTはWORK SIGNALと同一運営元のサービスです。</p>'
                '<p><a href="' + esc(intro) + '">もっと相談したい｜MANAGER reLIGHTについて ↗</a></p></section>')
    if article.get("id") == "20261021-manager-relight-introduction":
        return ('<section class="block" aria-label="MANAGER reLIGHT"><h2>MANAGER reLIGHTを知る</h2>'
                '<p>無料のReflection、単発相談のSESSION、継続伴走のPARTNERをご案内しています。</p>'
                '<p><a href="https://relight.amberlight.co.jp/" target="_blank" rel="noopener noreferrer">公式サイトでサービスを確認する ↗</a></p>'
                '<p>このサービスはWORK SIGNALと同一運営元による提供です。</p></section>')
    return ""


URL_PATTERN = re.compile(r"https?://[^\s<>'\u3000]+")


def linked_text(value):
    """Escape article prose and link literal URLs safely."""
    source = str(value)
    result = []
    offset = 0
    for match in URL_PATTERN.finditer(source):
        result.append(esc(source[offset:match.start()]))
        raw = match.group(0)
        url = raw.rstrip('.,;:!?。、「」）)]')
        if url:
            safe = esc(url)
            result.append('<a class="inline-source-link" href="' + safe + '" target="_blank" rel="noopener noreferrer">' + safe + '</a>')
        result.append(esc(raw[len(url):]))
        offset = match.end()
    result.append(esc(source[offset:]))
    return ''.join(result)



def event_calendar(article, part):
    if article.get('id') != '20261021-bitcoin-ath-events' or part.get('title') != '2026年末までのBTC重要イベントカレンダー':
        return None
    lines = str(part.get('body', '')).splitlines()
    events = []
    for line in lines:
        if not line.startswith('【'):
            continue
        pieces = line.split('｜', 2)
        if len(pieces) != 3:
            continue
        prefix, name, impact = pieces
        priority = prefix[1:prefix.find('】')]
        when = prefix[prefix.find('】') + 1:]
        if priority not in ('最重要', '重要', '注目'):
            continue
        events.append((priority, when, name, impact))
    if len(events) != 10:
        return None
    styles = {'最重要': 'critical', '重要': 'important', '注目': 'watch'}
    cards = []
    for priority, when, name, impact in events:
        cards.append('<div class="btc-event btc-event--' + styles[priority] + '"><div class="btc-event-top"><strong class="btc-event-date">' + esc(when) + '</strong><span class="btc-priority">' + esc(priority) + '</span></div><div class="btc-event-name">' + esc(name) + '</div><div class="btc-event-impact">' + esc(impact) + '</div></div>')
    note = next((chunk.strip() for chunk in str(part['body']).split('\n\n') if chunk.strip() and not chunk.lstrip().startswith('【')), '')
    return '<div class="btc-calendar">' + ''.join(cards) + '</div><p class="btc-calendar-note">' + linked_text(note) + '</p>'


BTC_CALENDAR_CSS = """<style>
.btc-calendar{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:20px 0 22px}
.btc-event{min-width:0;border:1px solid #d8d2c6;border-left:4px solid #9a958b;border-radius:10px;background:#fffdf8;padding:16px 17px}
.btc-event--critical{border-left-color:#e14b2a;background:#fff4ed}
.btc-event--important{border-left-color:#b17b22;background:#fff9e9}
.btc-event--watch{border-left-color:#647e87;background:#f2f6f6}
.btc-event-top{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;margin-bottom:10px}
.btc-event-date{font-size:.89rem;font-weight:750;color:#242321}
.btc-priority{display:inline-block;flex-shrink:0;padding:4px 9px;border-radius:99px;font-size:.73rem;line-height:1.3;font-weight:800}
.btc-event--critical .btc-priority{color:#a82c12;background:#ffdfd1}
.btc-event--important .btc-priority{color:#7e530d;background:#f8e6b6}
.btc-event--watch .btc-priority{color:#345760;background:#dce9e9}
.btc-event-name{font-size:1.04rem;line-height:1.55;font-weight:800;overflow-wrap:anywhere}
.btc-event-impact{margin-top:7px;color:#55534e;font-size:.85rem;line-height:1.65;overflow-wrap:anywhere}
.btc-calendar-note{font-size:.84rem;line-height:1.85;overflow-wrap:anywhere}
@media(max-width:720px){.btc-calendar{grid-template-columns:minmax(0,1fr);gap:10px}.btc-event{padding:14px 15px}.btc-event-name{font-size:1rem}}
</style>"""


DSX_POD_DIAGRAM_CSS = """<style>
.dsx-figure{margin:1.6rem 0 2rem;border:1px solid #d9d4cb;border-radius:14px;background:#f2efe7;padding:clamp(12px,2vw,24px);color:#191918}
.dsx-figure *{box-sizing:border-box}.dsx-kicker{font-size:.7rem;letter-spacing:.14em;font-weight:800;color:#fa4c24}.dsx-figure h3{margin:.4rem 0 .4rem;font-size:clamp(1.1rem,2vw,1.5rem);line-height:1.4}.dsx-intro{font-size:.82rem;color:#54504a;margin:0 0 1rem}
.dsx-track{padding:1rem 0;border-top:1px solid #ccc5ba}.dsx-track-head{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:.8rem}.dsx-track-head strong{font-size:clamp(.84rem,2vw,1.05rem)}.dsx-time{font-weight:900;font-size:clamp(1rem,2.8vw,1.45rem);white-space:nowrap}.dsx-track--pod .dsx-time,.dsx-track--pod .dsx-track-head strong{color:#df4826}
.dsx-steps{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px}.dsx-step{position:relative;background:#fff;border-radius:10px;padding:10px 6px;border:1px solid #e4ded6;min-width:0;text-align:center}.dsx-step:not(:last-child):after{content:'→';position:absolute;z-index:2;right:-11px;top:50%;transform:translateY(-50%);font-weight:900;color:#fa4c24;background:#f2efe7;padding:0 2px}.dsx-step-head{display:flex;gap:4px;align-items:center;text-align:left;min-height:2.8em}.dsx-num{flex-shrink:0;display:inline-grid;place-items:center;width:22px;height:22px;border-radius:50%;background:#5d686d;color:white;font-size:.72rem;font-weight:900}.dsx-track--pod .dsx-num{background:#fa4c24}.dsx-step-label{font-size:clamp(.64rem,1.35vw,.79rem);font-weight:800;line-height:1.4}.dsx-step svg{width:100%;height:clamp(72px,12vw,115px);margin-top:5px;display:block}.dsx-step svg *{vector-effect:non-scaling-stroke}.dsx-footnote{border-top:1px solid #ccc5ba;padding-top:10px;margin:10px 0 0;font-size:.71rem;line-height:1.7;color:#55504a}
@media(max-width:650px){.dsx-steps{grid-template-columns:minmax(0,1fr);gap:18px}.dsx-step{display:grid;grid-template-columns:minmax(0,1fr) 120px;align-items:center;text-align:left;min-height:110px;padding:10px 14px}.dsx-step-head{min-height:0}.dsx-step svg{height:90px;max-width:120px;margin:0}.dsx-step:not(:last-child):after,.dsx-step:nth-child(2):after,.dsx-step:nth-child(3):after{content:'↓';left:50%;right:auto;top:auto;bottom:-20px;transform:translateX(-50%);padding:0 5px}.dsx-figure{padding:12px}}
</style>"""

def dsx_pod_diagram(article):
    if article.get('id') != '20261021-nvidia-dsx-pod-ai-datacenter-deployment':
        return ''
    def art(kind):
        if kind == 'site':
            return ('<rect x="13" y="57" width="102" height="27" rx="3" fill="#e5edf0" stroke="#627783" stroke-width="2"/>'
                    '<path d="M21 57V35L64 19L106 35V57" fill="#d8e4e9" stroke="#627783" stroke-width="2"/>'
                    '<path d="M64 19V2M64 2L45 57M64 2L83 57M50 19H78M42 35H86M35 49H93" stroke="#627783" stroke-width="2" fill="none"/>'
                    '<rect x="27" y="64" width="20" height="20" fill="#95a9b1"/><rect x="56" y="64" width="20" height="20" fill="#95a9b1"/>')
        if kind == 'truck':
            return ('<rect x="7" y="33" width="76" height="38" rx="3" fill="#c9d5db" stroke="#627783" stroke-width="2"/>'
                    '<path d="M83 45H102L117 59V71H83Z" fill="#e7edf0" stroke="#627783" stroke-width="2"/>'
                    '<path d="M90 49H100L109 58H90Z" fill="#8cb3c7"/>'
                    '<circle cx="29" cy="73" r="8" fill="#405666"/><circle cx="99" cy="73" r="8" fill="#405666"/>'
                    '<path d="M18 42H73M18 51H73M18 60H73" stroke="#91a6af" stroke-width="2"/>')
        if kind == 'wiring':
            return ('<rect x="12" y="12" width="42" height="70" rx="3" fill="#435d69"/><rect x="66" y="12" width="42" height="70" rx="3" fill="#435d69"/>'
                    + ''.join('<rect x="'+str(x)+'" y="'+str(y)+'" width="27" height="8" rx="1" fill="#92b6c3"/>' for x in (20,74) for y in (22,35,48,61))
                    + '<path d="M38 82C38 95 77 95 77 82M43 82C43 102 86 102 86 82" stroke="#fa4c24" stroke-width="3" fill="none"/>')
        if kind == 'server':
            return ('<rect x="16" y="12" width="25" height="72" rx="2" fill="#405765"/><rect x="47" y="12" width="25" height="72" rx="2" fill="#405765"/>'
                    '<rect x="78" y="12" width="25" height="72" rx="2" fill="#405765"/>'
                    + ''.join('<path d="M'+str(x)+' '+str(y)+'h13" stroke="#9fc6cf" stroke-width="3"/>' for x in (22,53,84) for y in (23,34,45,56,67))
                    + '<circle cx="99" cy="78" r="16" fill="#e5f3e8" stroke="#468b61" stroke-width="2"/><path d="M91 78l5 5 10-12" fill="none" stroke="#468b61" stroke-width="3"/>')
        if kind == 'factory':
            return ('<path d="M8 80V42L38 55V42L69 55V27H111V80Z" fill="#dce5e9" stroke="#627783" stroke-width="2"/>'
                    '<path d="M69 27V12H83V27" fill="#a8bac3" stroke="#627783" stroke-width="2"/>'
                    '<rect x="24" y="60" width="17" height="20" fill="#91aab6"/><rect x="51" y="60" width="17" height="20" fill="#91aab6"/>'
                    '<rect x="81" y="42" width="19" height="38" fill="#435d69"/>'
                    '<path d="M85 50h11M85 59h11M85 68h11" stroke="#a2c4cc" stroke-width="2"/>')
        if kind == 'testing':
            return ('<rect x="11" y="8" width="36" height="73" rx="2" fill="#435d69"/><rect x="52" y="8" width="36" height="73" rx="2" fill="#435d69"/>'
                    + ''.join('<path d="M'+str(x)+' '+str(y)+'h23" stroke="#a0c1c8" stroke-width="3"/>' for x in (17,58) for y in (20,33,46,59))
                    + '<rect x="76" y="47" width="40" height="29" rx="3" fill="#c9dce4" stroke="#627783" stroke-width="2"/>'
                    '<path d="M86 61l7 7 13-16" fill="none" stroke="#468b61" stroke-width="4"/>')
        if kind == 'container':
            return ('<rect x="7" y="24" width="78" height="45" rx="3" fill="#d8e3e8" stroke="#627783" stroke-width="2"/>'
                    + ''.join('<path d="M'+str(x)+' 28V66" stroke="#9db4bf" stroke-width="2"/>' for x in (19,31,43,55,67,79))
                    + '<path d="M85 42h18l13 16v11H85Z" fill="#e8eef0" stroke="#627783" stroke-width="2"/>'
                    '<circle cx="31" cy="72" r="7" fill="#405666"/><circle cx="100" cy="72" r="7" fill="#405666"/>')
        return ('<rect x="13" y="20" width="95" height="63" rx="4" fill="#d8e3e8" stroke="#627783" stroke-width="2"/>'
                '<rect x="28" y="27" width="25" height="49" fill="#435d69"/><rect x="60" y="27" width="25" height="49" fill="#435d69"/>'
                + ''.join('<path d="M'+str(x)+' '+str(y)+'h16" stroke="#a0c1c8" stroke-width="2"/>' for x in (32,64) for y in (35,45,55,65))
                + '<path d="M91 45h25M91 53h25" stroke="#fa4c24" stroke-width="3"/>')
    def step(num,label,kind):
        return ('<div class="dsx-step"><div class="dsx-step-head"><span class="dsx-num">'+str(num)+'</span>'
                '<span class="dsx-step-label">'+label+'</span></div>'
                '<svg viewBox="0 0 125 95" aria-hidden="true" focusable="false">'+art(kind)+'</svg></div>')
    traditional=[('電力・冷却などの準備','site'),('機器を個別搬入','truck'),('現地で配線・配管','wiring'),('統合検証・稼働','server')]
    pod=[('工場で組み立て','factory'),('工場で機能検証','testing'),('コンテナで輸送','container'),('現地接続・稼働','connected')]
    def track(name,time,steps,kind):
        return ('<div class="dsx-track dsx-track--'+kind+'"><div class="dsx-track-head"><strong>'+name+'</strong>'
                '<span class="dsx-time">'+time+'</span></div><div class="dsx-steps">'
                +''.join(step(i,label,icon) for i,(label,icon) in enumerate(steps,1))+'</div></div>')
    return ('<figure class="dsx-figure" aria-label="従来型とDSX PODの導入工程をイラストで比較">'
            '<div class="dsx-kicker">WORK SIGNAL / PROCESS COMPARISON</div>'
            '<h3>AIデータセンターの導入工程を比較</h3>'
            '<p class="dsx-intro">現地で組み立てるか、工場で検証してから運ぶか。</p>'
            +track('従来型｜現地で統合','約6カ月',traditional,'traditional')
            +track('DSX POD｜工場で事前統合','最短14日',pod,'pod')
            +'<figcaption class="dsx-footnote">※ NVIDIA公表値。電力・冷却・ネットワーク等の外部インフラが準備済みの設置場所での導入期間を比較。更地からの建設期間ではなく、最短値は全案件での実績を示すものではありません。DSX PODの工場作業と設置先の準備は並行可能です。出典：NVIDIA Newsroom（2026年10月21日）。</figcaption></figure>')

def article_body(article, modified_at=None, related=()):
    deep = article.get('format') == 'deep_dive'
    has_sections = isinstance(article.get('sections'), list) and bool(article['sections'])
    reading = max(1, math.ceil((len(article.get('summary', '')) + sum(len(str(part.get('body', ''))) for part in article.get('sections', []))) / 600))
    if has_sections:
        blocks = ''
        for i, part in enumerate(article['sections'], 1):
            if not isinstance(part, dict) or not part.get('title') or not part.get('body'):
                continue
            calendar = event_calendar(article, part)
            paragraphs = calendar if calendar is not None else ''.join('<p>' + linked_text(p) + '</p>' for p in re.split(r'\n\s*\n', str(part['body'])) if p.strip())
            if article.get('id') == '20261022-php2shell-critical-vulnerabilities' and part.get('title') == '図解｜何が起きるのか？':
                paragraphs += '<figure style="margin:24px 0"><img src="/assets/infographics/php2shell-explainer.svg" alt="PHPの脆弱性が攻撃者の通信からサーバーの不正操作につながる可能性を、4つのステップで示す図" loading="lazy" style="display:block;width:100%;height:auto;border-radius:12px"><figcaption style="font-size:0.85em;color:#666;margin-top:8px">仕組みを単純化した概念図。すべての環境で攻撃が成立するわけではありません。</figcaption></figure>'
            if part.get('title') == '図解｜従来型とDSX PODの導入工程を比較':
                paragraphs += dsx_pod_diagram(article)
            stats = ''.join('<div class="stat"><strong>' + esc(stat['value']) + '</strong><span>' + esc(stat.get('label', '')) + '</span></div>' for stat in part.get('stats', []) if isinstance(stat, dict) and stat.get('value'))
            blocks += '<section class="block" id="section-' + str(i) + '"><h2>' + esc(part['title']) + '</h2>' + paragraphs + stats + '</section>'
        if article.get('quick_take'):
            blocks = '<section class="takeaways"><h2>30秒でわかる / THE SIGNAL</h2><p>' + esc(article['quick_take']) + '</p></section>' + blocks
        toc = '<nav class="toc" aria-label="記事の目次"><div class="side-title">IN THIS STORY</div>' + ''.join('<a href="#section-' + str(i) + '">' + esc(part['title']) + '</a>' for i, part in enumerate(article['sections'], 1) if isinstance(part, dict) and part.get('title') and part.get('body')) + '</nav>'
    else:
        blocks = ''.join('<section class="block"><h2>' + title + '</h2><p>' + linked_text(article[key]) + '</p></section>' for title, key in SECTIONS if article.get(key))
        toc = ''
    format_label = 'MANAGEMENT GUIDE · 独自解説' if article.get('format') == 'management_guide' else ('SPECIAL STORY · 自社製品紹介' if article.get('format') == 'special_story' else ('SIGNAL DEEP DIVE' if deep else 'SIGNAL BRIEF'))
    return ('<section class="hero"><div class="eyebrow">/ ' + esc(article["category"])
             + (' / MANAGEMENT GUIDE' if article.get('format') == 'management_guide' else (' / SPECIAL STORY · 自社製品紹介' if article.get('format') == 'special_story' else (' / DEEP DIVE' if deep else ' / EDITORIAL BRIEFING'))) + '</div><h1>' + esc(article['title'])
            + '</h1><div class="meta">' + ('' if article.get('format') in ('special_story', 'management_guide') else '<span class="score">' + esc(article['score']) + ' / 100</span>') + '<span class="article-type">' + format_label + '</span><span>'
            + esc(article['category']) + '</span><time datetime="' + esc(article['published_at'])
            + '">' + esc(article['published_at']) + '</time>'
            + ('<span>更新：<time datetime="' + esc(modified_at) + '">' + esc(modified_at[:10]) + '</time></span>' if modified_at else '')
            + '<span class="readtime">約'
            + str(reading) + '分で読める</span></div></section><div class="layout"><article class="content">'
            + '<p class="lead">' + esc(article['summary']) + '</p>' + blocks
            + management_cta(article) + '</article><aside class="side"><div class="side-title">ARTICLE INTELLIGENCE</div>'
            + '<dl><dt>FORMAT</dt><dd>' + format_label + '</dd><dt>READ TIME</dt><dd>'
            + str(reading) + ' MIN</dd><dt>CATEGORY</dt><dd>' + esc(article['category'])
            + '</dd>' + ('' if article.get('format') in ('special_story', 'management_guide') else '<dt>SIGNAL SCORE</dt><dd>' + esc(article['score']) + ' / 100</dd>') + '<dt>PUBLISHED</dt><dd>' + esc(article['published_at'])
            + '</dd></dl>' + toc
            + ('<nav class="toc" aria-label="関連記事"><div class="side-title">RELATED SIGNALS</div>' + ''.join('<a href="' + article_url(item) + '">' + esc(item['title']) + '</a>' for item in related) + '</nav>' if related else '')
            + '<div class="source"><small>/ PRIMARY SOURCE</small><a href="'
            + esc(article['source_url']) + '" target="_blank" rel="noopener noreferrer">'
            + esc(article['source_url']) + '</a></div><p class="note">'
            + ('本記事はWORK SIGNALと同じ運営元による自社製品紹介・開発ストーリーです。独立した第三者レビューではありません。' if article.get('format') == 'special_story' else 'この記事は一次情報に基づく独自の要約・考察です。掲載内容は投資助言ではありません。')
            + '</p></aside></div>')


def article_end(article):
    """One editorial transmission rail, then a typographic return to all signals."""
    url = article_url(article)
    share_options = [
        ("X", "https://twitter.com/intent/tweet?" + urlencode({
            "text": article["title"], "url": url,
        })),
        ("Threads", "https://www.threads.net/intent/post?" + urlencode({
            "text": article["title"] + "\n" + url + "\n\n一次情報:\n" + article["source_url"],
        })),
        ("LINE", "https://social-plugins.line.me/lineit/share?" + urlencode({
            "url": url,
        })),
    ]
    share_links = ''.join(
        '<a class="article-share-button" href="' + esc(href)
        + '" target="_blank" rel="noopener noreferrer" aria-label="'
        + esc(name) + 'でこの記事を共有する（新しいタブ）">'
        + esc(name) + '</a>'
        for name, href in share_options
    )
    return (
        '<section class="article-end" id="article-end" aria-label="読了後のナビゲーション">'
        '<div class="article-end-label">TRANSMISSION / AFTER THE SIGNAL</div>'
        '<div class="article-end-intro"><h2>読んだ、その先へ。</h2>'
        '<p>気になった変化を共有して、次のシグナルへ。</p></div>'
        '<div class="article-end-grid">'
        '<div class="article-share"><p class="article-share-title">SHARE THIS SIGNAL</p>'
        '<nav class="article-share-list" aria-label="この記事を共有する">'
        + share_links
        + '<button type="button" class="article-share-button" data-copy-article-url="'
        + esc(url) + '">URLをコピー</button></nav>'
        '<span class="article-share-feedback" data-share-feedback="" '
        'role="status" aria-live="polite"></span></div>'
        '<a class="article-return" href="/#latest" aria-label="記事一覧のALL SIGNALSへ戻る">'
        '<span class="article-return-sub">BACK TO THE INDEX / FIND THE NEXT SIGNAL</span>'
        '<span class="article-return-label"><span class="article-return-name">ALL SIGNALS</span>'
        '<span class="article-return-signal">'
        '<svg class="article-return-svg" viewBox="0 0 200 56" '
        'preserveAspectRatio="xMidYMid meet" aria-hidden="true">'
        '<path class="return-line" d="M0 28 H42 C58 28 62 14 80 28 S112 42 130 28 H200"/>'
        '<path class="return-rise" d="M0 28 H42 C58 28 62 14 80 28 S112 42 130 28 H200"/>'
        '</svg></span></span></a></div></section>'
    )


def wage_widget_script(article, template):
    """Attach the wage-specific interactive widgets to generated, crawlable article pages."""
    if article.get('id') != '20261021-wage-raise-92-percent-real-wages':
        return ''
    match = re.search(r'function addWageWidgets\(content\)\{.*?\n\}\nfunction render\(a\)', template, re.S)
    if not match:
        raise ValueError('Wage widget implementation missing from article template')
    function_source = match.group().removesuffix('function render(a)')
    return ('<script>function el(tag,txt,cls){const n=document.createElement(tag);'
            'if(txt!==undefined)n.textContent=txt;if(cls)n.className=cls;return n}'
            + function_source
            + "addWageWidgets(document.querySelector('#article .content'));</script>")


def article_page(article, template, modified_at=None, related=()):
    url = article_url(article)
    image_url = BASE + 'assets/og/' + article['id'] + '.png'
    title = article["title"] + " — WORK SIGNAL"
    style = re.search(r'<style>.*?</style>', template, re.S).group()
    fonts = re.search(r'<link rel="preconnect".*?<style>', template, re.S).group().removesuffix('<style>')
    analytics = template.split('<!-- Google tag (gtag.js): WORK SIGNAL -->', 1)[1].split('</head>', 1)[0]
    schema = {"@context": "https://schema.org", "@type": ("Article" if article.get("format") in ("special_story", "management_guide") else "NewsArticle"), "headline": article["title"],
              "description": article["summary"], "datePublished": article["published_at"], "image": [image_url],
              "inLanguage": "ja", "mainEntityOfPage": {"@type": "WebPage", "@id": url},
              "publisher": {"@type": "Organization", "name": "WORK SIGNAL", "url": BASE, "sameAs": ["https://www.instagram.com/work_signal_japan/","https://www.threads.com/@work_signal_japan"]}}
    if modified_at:
        schema['dateModified'] = modified_at
    # Do not invent a person or organization byline that the feed does not provide.
    head = ('<!doctype html><html lang="ja"><head><meta charset="utf-8">'
            + '<meta name="viewport" content="width=device-width,initial-scale=1">'
            + '<meta name="theme-color" content="#f2efe7"><title>' + esc(title) + '</title>'
            + '<meta name="description" content="' + esc(article["summary"]) + '">'
            + '<link rel="canonical" href="' + url + '">' 
            + '<link rel="alternate" type="application/rss+xml" title="WORK SIGNAL RSS" href="/feed.xml">'
            + favicon_links()
            + '<meta property="og:type" content="article"><meta property="og:locale" content="ja_JP">'
            + '<meta property="og:site_name" content="WORK SIGNAL">'
            + '<meta property="og:title" content="' + esc(title) + '">'
            + '<meta property="og:description" content="' + esc(article["summary"]) + '">'
            + '<meta property="og:url" content="' + url + '">'
            + '<meta name="twitter:title" content="' + esc(title) + '">'
            + '<meta name="twitter:description" content="' + esc(article['summary']) + '">'
            + '<meta property="article:published_time" content="' + esc(article['published_at']) + '">'
            + ('<meta property="article:modified_time" content="' + esc(modified_at) + '">' if modified_at else '')
            + image_metadata(image_url, title)
            + '<meta name="robots" content="max-image-preview:large">'
            + json_ld(schema) + fonts + style + (BTC_CALENDAR_CSS if article.get('id') == '20261021-bitcoin-ath-events' else '') + (DSX_POD_DIAGRAM_CSS if article.get('id') == '20261021-nvidia-dsx-pod-ai-datacenter-deployment' else '')
            + '<link rel="stylesheet" href="/assets/css/signal-interactions.css">'
            + '<script defer src="/assets/js/article-actions.js"></script>' + analytics
            + '<script>measurePageView();</script></head>')
    body = ('<body><div class="top" id="page-top"></div><div class="shell"><header>'
            + '<a class="brand" href="/">WORK<span>.</span>SIGNAL</a>'
            + '<a class="back" href="/#latest">ALL SIGNALS</a></header>'
            + '<main id="article">' + article_body(article, modified_at, related) + article_end(article) + '</main></div>'
            + '<footer><div class="shell footer"><strong>WORK<span>.</span>SIGNAL</strong>'
            + '<small>NEWS IS SHORT. MEANING IS DEEP. · <a href="/about/">ABOUT</a> · <a href="/privacy/">PRIVACY POLICY</a> · <a href="/contact/">CONTACT</a> · <a href="/feed.xml">RSS</a></small>'
            + '<nav class="footer-social-links" aria-label="公式SNS"><a href="https://www.instagram.com/work_signal_japan/" target="_blank" rel="noopener noreferrer"><svg class="social-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><rect x="2.5" y="2.5" width="19" height="19" rx="5.5" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="12" cy="12" r="4.2" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="17.9" cy="6.4" r="1.1" fill="currentColor"/></svg><span>INSTAGRAM</span></a><a href="https://www.threads.com/@work_signal_japan" target="_blank" rel="noopener noreferrer"><svg class="social-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path fill="currentColor" d="M18.263 11.097c-.03-3.486-1.92-5.586-5.111-5.586-2.13 0-3.922.963-4.863 2.499l2.062 1.438c.535-.843 1.272-1.543 2.628-1.543 1.528 0 2.318.85 2.544 2.431a15 15 0 0 0-2.236-.173c-4.125 0-6.068 1.867-6.068 4.336s1.943 3.99 4.804 3.99c3.139 0 5.013-2.115 5.781-4.735.798.361 1.348 1.204 1.348 2.47 0 3.387-3.907 5.232-7.22 5.232-4.885 0-8.077-3.207-8.077-8.424 0-6.392 4.223-10.487 9.9-10.487 3.808 0 5.69 1.671 6.97 3.914l2.108-1.475C21.44 2.078 18.331 0 13.663 0 6.227 0 1.168 5.277 1.168 12.934c0 7 4.953 11.066 10.856 11.066 4.878 0 9.809-2.846 9.809-7.716 0-2.545-1.46-4.231-3.569-5.187m-6.33 4.855c-1.077 0-2.026-.512-2.026-1.453 0-1.483 1.822-1.934 3.606-1.934.678 0 1.34.045 1.927.173-.422 1.927-1.671 3.215-3.508 3.214Z"/></svg><span>THREADS</span></a></nav></div></footer>'
            + wage_widget_script(article, template) + '</body></html>')
    return head + body



def archive_url(page):
    return BASE + ('archive/' if page == 1 else f'archive/page/{page}/')


def archive_page(articles, page, home_html):
    """A crawlable, numbered archive; works with JavaScript disabled."""
    total_pages = max(1, math.ceil(len(articles) / ARCHIVE_PAGE_SIZE))
    if not (1 <= page <= total_pages):
        raise ValueError('Invalid archive page')
    start = (page - 1) * ARCHIVE_PAGE_SIZE
    subset = articles[start:start + ARCHIVE_PAGE_SIZE]
    url = archive_url(page)
    title = 'THE ARCHIVE — WORK SIGNAL' if page == 1 else f'THE ARCHIVE / {page} — WORK SIGNAL'
    description = 'WORK SIGNALで公開したAI・仕事・マネジメント・経済などのニュース解説を新しい順に読むアーカイブ。'
    style = re.search(r'<style>.*?</style>', home_html, re.S)
    fonts = re.search(r'<link rel="preconnect".*?<style>', home_html, re.S)
    footer = re.search(r'<div class="shell"><footer>.*?</footer></div>', home_html, re.S)
    if not style or not fonts or not footer:
        raise ValueError('Home design assets required for the archive are missing')
    footer_html = footer.group().replace('<span id="year"></span>', str(datetime.now(timezone.utc).year))
    archive_css = """<style>
.archive-section{padding:65px 0 95px}
.archive-section .section-heading h1{margin:8px 0 0;font:800 clamp(40px,6vw,78px)/1 var(--sans);letter-spacing:-.075em}
.archive-return{font:700 11px var(--sans);letter-spacing:.1em;text-decoration:none;border-bottom:1px solid var(--ink);padding:8px 0}
.archive-return:is(:hover,:focus-visible){color:var(--orange)}
.archive-intro{display:flex;align-items:baseline;justify-content:space-between;gap:15px;flex-wrap:wrap;padding:18px 0 33px;margin:0 0 23px;border-bottom:1px solid var(--line)}
.archive-intro p{font:500 12px/1.9 var(--jp);color:var(--muted);margin:0}
.archive-intro small{font:700 10px var(--sans);letter-spacing:.1em;color:var(--orange)}
.archive-pages{display:flex;align-items:center;justify-content:center;flex-wrap:wrap;gap:7px;margin-top:47px;padding:22px 0;border-top:1px solid var(--line)}
.archive-pages a,.archive-pages span{min-width:42px;min-height:44px;padding:10px 12px;display:inline-flex;align-items:center;justify-content:center;text-decoration:none;font:700 11px var(--sans);letter-spacing:.08em}
.archive-pages a{border:1px solid var(--line)}
.archive-pages a:is(:hover,:focus-visible){border-color:var(--orange);color:var(--orange)}
.archive-pages a:focus-visible,.archive-return:focus-visible{outline:2px solid var(--orange);outline-offset:3px}
.archive-pages [aria-current="page"]{background:var(--ink);color:var(--paper)}
.archive-pages .archive-gap{min-width:12px;color:var(--muted)}
@media(max-width:700px){.archive-section{padding:38px 0 65px}.archive-intro{padding-top:12px}.archive-return{font-size:9px}.archive-pages{gap:5px}.archive-pages a,.archive-pages span{min-width:37px;padding:9px 8px}}
</style>"""
    numbers = []
    previous_omitted = False
    for number in range(1, total_pages + 1):
        if total_pages > 7 and number not in (1, total_pages) and abs(number - page) > 2:
            if not previous_omitted:
                numbers.append('<span class="archive-gap" aria-hidden="true">…</span>')
            previous_omitted = True
            continue
        previous_omitted = False
        if number == page:
            numbers.append('<span aria-current="page">' + f'{number:02d}' + '</span>')
        else:
            numbers.append('<a href="' + archive_url(number) + '" aria-label="アーカイブ' + str(number) + 'ページ">' + f'{number:02d}' + '</a>')
    if page > 1:
        numbers.insert(0, '<a href="' + archive_url(page - 1) + '">PREVIOUS</a>')
    if page < total_pages:
        numbers.append('<a href="' + archive_url(page + 1) + '">NEXT</a>')
    canonical = '<link rel="canonical" href="' + url + '">'
    result = ('<!doctype html><html lang="ja"><head><meta charset="utf-8">'
              '<meta name="viewport" content="width=device-width,initial-scale=1">'
              '<meta name="theme-color" content="#f2efe7">'
              '<meta name="description" content="' + esc(description) + '">'
              '<title>' + esc(title) + '</title>' + canonical + favicon_links()
              + fonts.group().removesuffix('<style>') + style.group() + archive_css + '</head>'
              '<body><div class="topline"></div><div class="shell"><header class="masthead">'
              '<a class="brand" href="/" aria-label="WORK SIGNALホーム">WORK<span class="dot">.</span>SIGNAL<span class="sup">®</span></a>'
              '<a class="archive-return" href="/#latest">LATEST SIGNALS</a></header>'
              '<main><section class="section archive-section"><div class="section-heading">'
              '<div><div class="kicker">/ THE COMPLETE EDITION</div><h1>THE ARCHIVE<span style="color:var(--orange)">.</span></h1></div>'
              '<div class="section-aside">VERIFIED &amp; PUBLISHED<br>NEWEST FIRST</div></div>'
              '<div class="archive-intro"><p>' + esc(description) + '</p>'
              '<small>' + str(start + 1 if subset else 0) + '–' + str(start + len(subset))
              + ' / ' + str(len(articles)) + ' SIGNALS</small></div>'
              '<div class="grid">' + ''.join(article_card(item) for item in subset) + '</div>'
              '<nav class="archive-pages" aria-label="アーカイブのページ">' + ''.join(numbers) + '</nav>'
              '</section></main></div>' + footer_html + '</body></html>')
    return result


def write_rss(output, articles):
    """Generate an RSS 2.0 summary feed from approved published articles."""
    rss = ET.Element('rss', {'version': '2.0'})
    channel = ET.SubElement(rss, 'channel')
    for tag, value in (
        ('title', 'WORK SIGNAL'),
        ('link', BASE),
        ('description', 'AI・仕事・マネジメント・お金・経済・Cryptoのニュースを、一次情報と独自の視点から読み解く。'),
        ('language', 'ja'),
        ('generator', 'WORK SIGNAL static site builder'),
        ('ttl', '60'),
    ):
        ET.SubElement(channel, tag).text = value
    atom_ns = 'http://www.w3.org/2005/Atom'
    ET.register_namespace('atom', atom_ns)
    ET.SubElement(channel, '{' + atom_ns + '}link', {
        'href': BASE + 'feed.xml', 'rel': 'self', 'type': 'application/rss+xml'
    })
    for article in sorted(articles, key=lambda item: (item['published_at'], item['id']), reverse=True):
        item = ET.SubElement(channel, 'item')
        for tag, value in (
            ('title', article['title']),
            ('link', article_url(article)),
            ('guid', article_url(article)),
            ('description', article['summary']),
            ('category', article['category']),
        ):
            element = ET.SubElement(item, tag)
            element.text = value
            if tag == 'guid':
                element.set('isPermaLink', 'true')
        published = datetime.combine(date.fromisoformat(article['published_at']), datetime.min.time(), tzinfo=timezone.utc)
        ET.SubElement(item, 'pubDate').text = published.strftime('%a, %d %b %Y %H:%M:%S +0000')
    ET.ElementTree(rss).write(output / 'feed.xml', encoding='utf-8', xml_declaration=True)


def build(output, feed=None):
    if output.resolve() == ROOT.resolve() or ROOT.resolve().is_relative_to(output.resolve()):
        raise ValueError("Output must not overwrite the source repository")
    articles = published_articles(feed if feed is not None else json.loads((ROOT / 'data/articles.json').read_text()))
    history = article_modifications(ROOT)
    modified = {item['id']: modification_date(item, history) for item in articles}
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    share_card(output)
    # Shared behavior for article link copying on both static and dynamic pages.
    shared_actions = ROOT / 'assets/js/article-actions.js'
    output_actions = output / 'assets/js/article-actions.js'
    output_actions.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(shared_actions, output_actions)
    shared_style = ROOT / 'assets/css/signal-interactions.css'
    output_style = output / 'assets/css/signal-interactions.css'
    output_style.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(shared_style, output_style)
    # Explicit allowlist: no server source, test specimens or credentials enter Pages.
    for asset in ('assets/css/hero-market.css', 'assets/js/hero-market.mjs', 'assets/js/market-model.mjs',
                  'assets/js/free-market-client.mjs', 'assets/js/free-market-feeds.mjs'):
        destination = output / asset
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / asset, destination)
    # Approved NBA UI only. Local study scores and provider code stay out of Pages.
    for asset in ('index.html', 'app.mjs', 'page.mjs', 'model.mjs', 'court-motion.mjs',
                  'style.css', 'feed.mjs', 'data.json', 'fonts/Anton-Regular.ttf', 'fonts/OFL.txt'):
        destination = output / 'nba' / asset
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / 'nba' / asset, destination)
    index = (ROOT / 'index.html').read_text()
    # SECURITY WATCH: independent alert feed; article publication dates remain unchanged.
    security_feed = merged_security_feed(articles, json.loads((ROOT / 'data/security-watch.json').read_text()))
    (output / 'data').mkdir(exist_ok=True)
    (output / 'data/security-watch.json').write_text(json.dumps(security_feed, ensure_ascii=False, indent=2) + '\n')
    security_rows = []
    for alert in security_feed:
        article_id = alert.get('article_id')
        article = next((item for item in articles if item['id'] == article_id), None)
        update_date = (modified.get(article_id) if article else None) or alert['date']
        security_rows.append((update_date, alert, article))
    security_rows.sort(key=lambda row: (row[0], row[1]['date']), reverse=True)
    def security_card(row):
        updated, alert, article = row
        severity = esc(alert['severity'])
        product = esc(alert['product'])
        # Prefer the canonical article headline. A concise, editorially reviewed
        # security_headline can override it without changing the article title.
        raw_headline = (article.get('security_headline') or article['title']) if article else alert['product']
        headline = esc(raw_headline)
        summary = esc(article['summary'] if article else alert['summary'])
        status = alert.get('status', '')
        status_line = ('<span class="sw-status">' + esc(status) + '</span>') if status and status != '対応・影響条件は記事を参照' else ''
        href = '/articles/' + esc(article['id']) + '/' if article else '/security/'
        updated_label = '<span class="sw-updated">UPDATED</span>' if updated > alert['date'] else ''
        return ('<a class="sw-item" href="' + href + '"><span class="sw-level sw-' + severity.lower()
                + '">' + severity + '</span><span class="sw-copy">'
                + '<span class="sw-product">' + product + '</span>'
                + '<strong class="sw-headline">' + headline + '</strong>'
                + '<span class="sw-summary">' + summary + '</span>' + status_line
                + '</span><span class="sw-date">' + updated_label + esc(updated[:10]) + '</span></a>')
    security_home = '<section class="sw-section" aria-labelledby="sw-title"><div class="sw-heading"><div><span class="sw-kicker">/ VERIFIED SECURITY INTELLIGENCE</span><h2 id="sw-title">SECURITY WATCH<span>.</span></h2><div class="sw-pulse" aria-hidden="true"><svg viewBox="0 0 480 24" preserveAspectRatio="none" focusable="false"><path class="sw-baseline" d="M0 12 H480"/><path class="sw-wave sw-wave-echo" d="M0 12 H160 L169 12 L175 8 L182 17 L190 4 L198 20 L206 12 H310 L316 9 L322 15 L328 12 H480"/><path class="sw-wave sw-wave-main" d="M0 12 H160 L169 12 L175 8 L182 17 L190 4 L198 20 L206 12 H310 L316 9 L322 15 L328 12 H480"/><rect class="sw-tear" x="0" y="9" width="480" height="4"/></svg></div><p>主要Web技術の脆弱性と修正情報。重要な記事更新もここで確認できます。</p></div></div><div class="sw-items">' + ''.join(security_card(row) for row in security_rows[:4]) + '</div><a class="sw-more" href="/security/"><span class="sw-more-noise" aria-hidden="true"></span><span class="sw-more-label">MORE SECURITY SIGNALS</span></a></section>'
    security_styles = """<style>
.sw-archive-page{margin:0;min-height:100vh;background:radial-gradient(ellipse at 78% 0%,rgba(131,48,55,.30),transparent 52%),linear-gradient(145deg,#402225 0%,#261b20 46%,#17181d 100%);font-family:system-ui,sans-serif;color:#f5eee9}
.sw-archive-page::before{content:"";position:fixed;inset:0;pointer-events:none;opacity:.16;background:repeating-linear-gradient(0deg,transparent 0 5px,rgba(211,96,89,.13) 5px 6px,transparent 6px 12px)}
.sw-archive-main{position:relative;max-width:1050px;margin:auto;padding:24px}
.sw-back{margin:12px 0 24px}.sw-back a{color:#f4e8e2;text-decoration:underline;text-underline-offset:4px}
.sw-archive-page .sw-section{margin-top:0}
.sw-back{margin:2px 0 16px}
.sw-back a{position:relative;display:inline-flex;align-items:center;justify-content:center;isolation:isolate;overflow:hidden;min-height:44px;padding:5px 15px;border:1px solid rgba(190,116,105,.58);border-radius:4px;background:#282426;color:#f3e9e5;text-decoration:none;font:650 11px/1.2 ui-monospace,SFMono-Regular,monospace;letter-spacing:.09em}
.sw-back-label{position:relative;z-index:2}
.sw-back-label{display:flex;flex-direction:column;align-items:flex-start;justify-content:center;gap:3px;white-space:nowrap}
.sw-back-small{font:650 8px/1 ui-monospace,SFMono-Regular,monospace;letter-spacing:.11em;color:#cbb5b0}
.sw-back-brand{font:800 16px/1 system-ui,sans-serif;letter-spacing:-.095em;color:#f3e9e5}
.sw-back-dot{color:#d67b47}
.sw-back-reg{font-size:6px;vertical-align:top;letter-spacing:0;margin-left:3px}

.sw-back-noise{position:absolute;inset:0;z-index:0;pointer-events:none;background:repeating-linear-gradient(0deg,transparent 0 3px,rgba(228,103,80,.16) 3px 4px,transparent 4px 8px),linear-gradient(92deg,transparent 0 28%,rgba(201,65,57,.30) 32%,transparent 39% 65%,rgba(230,108,83,.24) 70%,transparent 76%);animation:sw-more-signal 8s steps(1,end) infinite}
.sw-back a::after{content:"";position:absolute;inset:0;pointer-events:none;background:linear-gradient(90deg,transparent 15%,rgba(236,99,87,.24) 20%,transparent 26% 67%,rgba(236,99,87,.17) 72%,transparent 77%);opacity:0;animation:sw-more-flash 8s steps(1,end) infinite}
.sw-back a:hover,.sw-back a:focus-visible{border-color:#d18b80;background:#34292a}
.sw-back a:focus-visible{outline:2px solid #e2aa8b;outline-offset:3px}
@media(max-width:620px){.sw-archive-page .sw-archive-heading{min-height:0;padding:20px 19px 16px;margin:-18px -16px 16px;gap:12px}.sw-archive-page .sw-archive-index{margin-bottom:15px}.sw-archive-page .sw-archive-heading h2{margin:12px 0 10px;font-size:clamp(42px,11vw,58px)}.sw-archive-page .sw-archive-monitor{position:absolute;right:14px;bottom:10px;top:auto;width:84px;height:32px;opacity:.42}.sw-archive-page .sw-archive-monitor svg{height:30px}.sw-archive-page .sw-archive-heading p{max-width:260px}.sw-archive-page .sw-section{margin-top:0}}
@media(prefers-reduced-motion:reduce){.sw-back-noise,.sw-back a::after{animation:none!important}.sw-back a::after{opacity:0!important}}

.sw-archive-heading{position:relative;isolation:isolate;overflow:hidden;min-height:148px;align-items:center;padding:24px 22px;margin:-26px -28px 20px;background:linear-gradient(110deg,#332125,#221c21 80%);border-radius:8px 8px 0 0}
.sw-archive-heading>div{position:relative;z-index:1}.sw-archive-heading .sw-kicker{color:#d49a91}.sw-archive-heading h2{color:#f7f2ec}.sw-archive-heading h2 span{color:#d25b4f}.sw-archive-heading p{color:#d1bcba}
.sw-archive-noise{position:absolute;inset:0;pointer-events:none;z-index:-1;background:repeating-linear-gradient(0deg,transparent 0 3px,rgba(220,85,77,.10) 3px 4px,transparent 4px 9px),linear-gradient(90deg,transparent 10%,rgba(211,75,67,.17) 32%,transparent 37% 62%,rgba(211,75,67,.14) 67%,transparent 74%);animation:sw-more-signal 8s steps(1,end) infinite}
.sw-archive-heading::after{content:"";position:absolute;inset:0;pointer-events:none;background:linear-gradient(90deg,transparent 20%,rgba(236,99,87,.24) 22%,transparent 24% 63%,rgba(236,99,87,.17) 64%,transparent 66%);opacity:0;animation:sw-more-flash 8s steps(1,end) infinite}
@media(max-width:620px){.sw-archive-main{padding:18px}.sw-archive-heading{margin:-18px -16px 18px;padding:26px 16px;min-height:124px}}
@media(prefers-reduced-motion:reduce){.sw-archive-noise,.sw-archive-heading::after{animation:none!important}.sw-archive-heading::after{opacity:0!important}}
.sw-archive-page .sw-section{border-color:#a69a94}
.sw-archive-heading{min-height:260px;display:flex;justify-content:space-between;gap:24px;padding:30px 34px;margin:-26px -28px 24px;background:#292824;border-bottom:1px solid #9b5550;border-radius:7px 7px 0 0}
.sw-archive-heading::before{content:"";position:absolute;inset:0;pointer-events:none;background:radial-gradient(ellipse at 78% 24%,rgba(142,51,51,.24),transparent 53%);z-index:0}
.sw-archive-heading .sw-archive-copy{position:relative;z-index:2;min-width:0}
.sw-archive-index{display:block;margin-bottom:26px;color:#c88b81;font:600 10px/1.2 ui-monospace,SFMono-Regular,monospace;letter-spacing:.18em}
.sw-archive-heading .sw-kicker{display:block;font-size:10px;letter-spacing:.20em}
.sw-archive-heading h2{font-size:clamp(44px,7.2vw,94px);line-height:.88;letter-spacing:-.075em;margin:16px 0 18px;font-weight:850}
.sw-archive-heading h2 span{color:#dc695b}
.sw-archive-heading p{font-size:12px;line-height:1.65}
.sw-archive-grid{position:absolute;inset:0;pointer-events:none;z-index:0;opacity:.17;background-image:linear-gradient(rgba(214,108,94,.25) 1px,transparent 1px),linear-gradient(90deg,rgba(214,108,94,.25) 1px,transparent 1px);background-size:42px 42px;mask-image:linear-gradient(90deg,transparent 18%,#000 100%)}
.sw-archive-noise{z-index:1;opacity:.55;background:repeating-linear-gradient(0deg,transparent 0 3px,rgba(228,103,80,.10) 3px 4px,transparent 4px 8px),linear-gradient(92deg,transparent 0 28%,rgba(201,65,57,.16) 32%,transparent 39% 65%,rgba(230,108,83,.15) 70%,transparent 76%);animation:sw-more-signal 8s steps(1,end) infinite}
.sw-archive-monitor{position:relative;z-index:2;align-self:stretch;width:33%;min-width:170px;display:flex;flex-direction:column;justify-content:center;gap:15px;border-left:1px solid rgba(225,158,146,.25);padding-left:24px;color:#b9a39f}
.sw-monitor-label,.sw-monitor-foot{font:600 9px/1.5 ui-monospace,SFMono-Regular,monospace;letter-spacing:.12em}
.sw-monitor-foot{opacity:.65}
.sw-archive-monitor svg{width:100%;height:92px;overflow:visible}.sw-monitor-axis{fill:none;stroke:#725b59;stroke-width:.5}.sw-monitor-trace{fill:none;stroke:#da6a60;stroke-width:1.4;vector-effect:non-scaling-stroke;animation:sw-distortion 8s steps(1,end) infinite}
@media(max-width:620px){.sw-archive-heading{min-height:238px;padding:22px 19px;margin:-18px -16px 18px}.sw-archive-index{margin-bottom:25px;font-size:8px}.sw-archive-heading .sw-kicker{font-size:9px}.sw-archive-heading h2{font-size:clamp(45px,12vw,68px)}.sw-archive-monitor{position:absolute;right:18px;top:24px;width:80px;min-width:0;height:52px;padding-left:8px;opacity:.55}.sw-monitor-label,.sw-monitor-foot{display:none}.sw-archive-monitor svg{height:42px}.sw-archive-heading p{max-width:290px}}
@media(prefers-reduced-motion:reduce){.sw-monitor-trace{animation:none!important}}
.sw-section{margin:34px 0 46px;padding:26px 28px;background:#f8f6f1;border:1px solid #dedbd3;border-radius:8px;color:#242424}
.sw-heading{display:flex;justify-content:space-between;align-items:end;gap:18px;margin-bottom:18px}
.sw-kicker{font-size:10px;letter-spacing:.16em;font-weight:700;color:#716f69}
.sw-heading h2{font-size:clamp(22px,3vw,34px);letter-spacing:-.045em;margin:5px 0}
.sw-heading h2 span{color:#d07a2c}.sw-heading p{font-size:12px;color:#65625d;margin:0}
.sw-heading>a{font-size:11px;font-weight:800;letter-spacing:.08em;color:inherit;text-decoration:none;white-space:nowrap}
.sw-pulse{height:22px;max-width:410px;margin:5px 0 9px;overflow:hidden;opacity:.9;isolation:isolate}.sw-pulse svg{display:block;width:100%;height:100%;overflow:hidden}.sw-baseline{fill:none;stroke:#b6b0a6;stroke-width:.7;opacity:.45}
.sw-wave{fill:none;stroke-linecap:round;stroke-linejoin:round}.sw-wave-main{stroke:#bb4446;stroke-width:1.7;animation:sw-distortion 8s steps(1,end) infinite both}.sw-wave-echo{stroke:#e38a85;stroke-width:1.1;opacity:0;animation:sw-ghost 8s steps(1,end) infinite both}.sw-tear{fill:#bb4446;opacity:0;animation:sw-tearing 8s steps(1,end) infinite both}
@keyframes sw-distortion{0%,12%,24%,38%,50%,65%,80%,100%{transform:translateX(0) skewX(0);opacity:1}14%{transform:translateX(11px) skewX(5deg)}16%{transform:translateX(-8px)}18%{transform:translateX(4px)}40%{transform:translateX(-14px) skewX(-7deg)}42%{transform:translateX(9px)}44%{transform:translateX(-3px)}67%{transform:translateX(10px);opacity:.3}69%{transform:translateX(-7px);opacity:.75}71%{transform:translateX(0);opacity:1}}
@keyframes sw-ghost{0%,12%,24%,38%,50%,65%,80%,100%{opacity:0;transform:translateX(0)}14%,40%,67%{opacity:.55;transform:translateX(13px)}18%,44%,71%{opacity:.3;transform:translateX(-8px)}}
@keyframes sw-tearing{0%,12%,24%,38%,50%,65%,80%,100%{opacity:0;transform:translateY(0)}14%,40%,67%{opacity:.2;transform:translateY(5px)}16%,42%,69%{opacity:.1;transform:translateY(-5px)}}
@media(prefers-reduced-motion:reduce){.sw-wave-main,.sw-wave-echo,.sw-tear{animation:none!important}.sw-wave-echo,.sw-tear{opacity:0}}
.sw-item{transition:background-color .2s ease,padding-left .2s ease}.sw-item:hover,.sw-item:focus-visible{background:rgba(177,124,66,.055);padding-left:5px}.sw-item:focus-visible{outline:2px solid #b17c42;outline-offset:2px}
@media(prefers-reduced-motion:reduce){.sw-wave{animation:none;stroke-dashoffset:0}.sw-item{transition:none}}
.sw-more{position:relative;display:flex;align-items:center;justify-content:center;min-height:54px;margin-top:20px;overflow:hidden;isolation:isolate;border:1px solid #b6aaa0;border-radius:3px;background:#292824;color:#f6f1e8;text-decoration:none;transition:border-color .2s,background-color .2s}
.sw-more-label{position:relative;z-index:2;font-size:11px;font-weight:800;letter-spacing:.17em;text-align:center}
.sw-more-noise{position:absolute;inset:0;z-index:0;pointer-events:none;opacity:.65;background:repeating-linear-gradient(0deg,transparent 0 3px,rgba(228,103,80,.10) 3px 4px,transparent 4px 8px),linear-gradient(92deg,transparent 0 28%,rgba(201,65,57,.16) 32%,transparent 39% 65%,rgba(230,108,83,.15) 70%,transparent 76%);animation:sw-more-signal 8s steps(1,end) infinite}
.sw-more::after{content:"";position:absolute;z-index:1;inset:0;pointer-events:none;background:linear-gradient(90deg,transparent 0 22%,rgba(220,88,74,.30) 23%,transparent 24% 61%,rgba(220,88,74,.22) 62%,transparent 63%);opacity:0;animation:sw-more-flash 8s steps(1,end) infinite}
@keyframes sw-more-signal{0%,12%,24%,38%,50%,65%,80%,100%{transform:translateX(0);opacity:.5}14%{transform:translateX(12px);opacity:.85}16%{transform:translateX(-8px);opacity:.8}40%{transform:translateX(-15px);opacity:.9}42%{transform:translateX(7px)}67%{transform:translateX(9px);opacity:.95}69%{transform:translateX(-6px)}}
@keyframes sw-more-flash{0%,12%,24%,38%,50%,65%,80%,100%{opacity:0}14%,40%,67%{opacity:.85}16%,42%,69%{opacity:.2}}
.sw-more:hover,.sw-more:focus-visible{border-color:#ba5a4d;background:#332b29}.sw-more:focus-visible{outline:2px solid #b17c42;outline-offset:3px}
@media(prefers-reduced-motion:reduce){.sw-more-noise,.sw-more::after{animation:none!important}.sw-more::after{opacity:0!important}}
.sw-items{border-top:1px solid #d9d6cf}.sw-item{display:flex;align-items:center;gap:18px;padding:15px 0;border-bottom:1px solid #d9d6cf;color:inherit;text-decoration:none}
.sw-level{min-width:80px;text-align:center;border:1px solid #aaa;padding:5px 7px;font-size:10px;font-weight:800;letter-spacing:.06em}
.sw-critical{background:#b92e32;border-color:#e65b5e;color:#fff;box-shadow:0 0 0 1px rgba(185,46,50,.08),0 0 12px rgba(185,46,50,.22)}.sw-high{background:#a96813;border-color:#e6a33d;color:#fff;box-shadow:inset 0 1px 0 rgba(255,221,154,.28)}
.sw-copy{display:flex;flex:1;flex-direction:column;gap:3px;min-width:0}.sw-copy strong{font-size:14px}.sw-copy>span{font-size:12px;color:#68645e}
.sw-date{font-size:11px;color:#78736c;white-space:nowrap;text-align:right}.sw-updated{display:block;color:#aa6220;font-size:9px;font-weight:800;letter-spacing:.08em}
@media(max-width:620px){.sw-section{padding:18px 16px;margin:20px 0 30px}.sw-heading{align-items:start;flex-direction:column}.sw-item{gap:9px}.sw-level{min-width:65px;font-size:9px}.sw-date{font-size:10px}.sw-copy>span{font-size:11px}}
/* Editorial-first security cards: urgency, consequence, action. */
.sw-item{display:grid;grid-template-columns:94px minmax(0,1fr) 88px;align-items:start;gap:14px;padding:19px 0}
.sw-level{min-width:0;justify-self:start;padding:8px 10px;margin-top:3px}
.sw-copy{display:flex;flex-direction:column;gap:7px;min-width:0}
.sw-copy .sw-product{font:750 10px/1.45 system-ui,sans-serif;letter-spacing:.07em;color:#645d57}
.sw-copy .sw-headline{font:800 clamp(15px,1.5vw,18px)/1.45 system-ui,sans-serif;color:#191918;letter-spacing:-.025em;overflow-wrap:anywhere}
.sw-copy .sw-summary{font:400 12px/1.62 system-ui,sans-serif;color:#68645e;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.sw-copy .sw-status{align-self:flex-start;padding:3px 8px;border-radius:2px;background:#ebe5dc;color:#51433a;font:700 10px/1.45 system-ui,sans-serif}
.sw-date{margin-top:7px;line-height:1.6}
.sw-archive-page .sw-copy .sw-headline{color:#f5eee9}
.sw-archive-page .sw-copy .sw-product{color:#cbb9b1}
.sw-archive-page .sw-copy .sw-summary{color:#d5c5be}
.sw-archive-page .sw-copy .sw-status{background:rgba(247,224,197,.12);color:#e5d2c4}
@media(max-width:620px){
  .sw-item{grid-template-columns:minmax(0,1fr) auto;column-gap:12px;row-gap:9px;padding:18px 0 20px}
  .sw-level{grid-column:1;grid-row:1;min-width:76px;justify-self:start;margin:0;padding:7px 11px}
  .sw-date{grid-column:2;grid-row:1;text-align:right;margin:0;padding-top:2px;font-size:10px}
  .sw-copy{grid-column:1/-1;grid-row:2;gap:6px}
  .sw-copy .sw-product{font-size:10px}
  .sw-copy .sw-headline{font-size:16px;line-height:1.48}
  .sw-copy .sw-summary{font-size:12px;line-height:1.6}
  .sw-copy .sw-status{font-size:10px}
}
</style>"""
    security_motion_script = """<script>
(function(){
  const pulse = document.querySelector('.sw-pulse');
  if (!pulse) return;
  const animations = () => pulse.querySelectorAll('.sw-wave-main, .sw-wave-echo, .sw-tear');
  const setPlayback = (running) => {
    animations().forEach(el => { el.style.animationPlayState = running ? 'running' : 'paused'; });
  };
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver(entries => {
      setPlayback(entries[0].isIntersecting && !document.hidden);
    }, {threshold: 0});
    observer.observe(pulse);
  }
  document.addEventListener('visibilitychange', () => {
    setPlayback(!document.hidden && pulse.getBoundingClientRect().bottom > 0 && pulse.getBoundingClientRect().top < innerHeight);
  });
  if (pulse.getBoundingClientRect().top >= innerHeight || pulse.getBoundingClientRect().bottom <= 0) setPlayback(false);
})();
</script>"""
    index = index.replace('</style>', '</style>' + security_styles, 1)
    index = index.replace('</body>', security_motion_script + '</body>', 1)
    index = index.replace('<div class="shell"><section class="section" id="latest">', '<div class="shell">' + security_home + '<section class="section" id="latest">', 1)
    security_page = ('<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        + '<title>SECURITY WATCH | WORK SIGNAL</title><meta name="description" content="主要Web技術の脆弱性・修正版・更新情報">'
        + security_styles + '</head><body class="sw-archive-page">'
        + '<main class="sw-archive-main"><p class="sw-back"><a href="/"><span class="sw-back-noise" aria-hidden="true"></span><span class="sw-back-label"><span class="sw-back-small">BACK TO</span><span class="sw-back-brand">WORK<span class="sw-back-dot">.</span>SIGNAL<span class="sw-back-reg">®</span></span></span></a></p>'
        + '<section class="sw-section sw-archive"><div class="sw-heading sw-archive-heading"><span class="sw-archive-noise" aria-hidden="true"></span><span class="sw-archive-grid" aria-hidden="true"></span><div class="sw-archive-copy"><span class="sw-archive-index" aria-hidden="true">WS / 01 — THREAT INTELLIGENCE</span><span class="sw-kicker">/ VERIFIED SECURITY INTELLIGENCE</span>'
        + '<h2>SECURITY<br>WATCH<span>.</span></h2><p>公式情報に基づく脆弱性アラート。更新日順に表示。</p></div><div class="sw-archive-monitor" aria-hidden="true"><span class="sw-monitor-label">SIGNAL / MONITORING</span><svg viewBox="0 0 260 100" preserveAspectRatio="none"><path class="sw-monitor-axis" d="M0 50H260M0 25H260M0 75H260"/><path class="sw-monitor-trace" d="M0 50H60L68 46L74 56L82 12L91 90L100 50H148L155 43L162 62L171 50H260"/></svg><span class="sw-monitor-foot">CONTINUOUS OBSERVATION · VERIFIED SOURCES</span></div></div><div class="sw-items">'
        + ''.join(security_card(row) for row in security_rows)
        + '</div></section></main></body></html>')
    security_dir = output / 'security'
    security_dir.mkdir(exist_ok=True)
    (security_dir / 'index.html').write_text(security_page)
    cards = ''.join(article_card(article) for article in articles[:HOME_PAGE_SIZE])
    if not cards:
        cards = '<div class="empty"><div><strong>THE SIGNAL IS COMING.</strong><p>公開準備中です。</p></div></div>'
    marker = '<div class="grid" id="articles"></div>'
    if marker not in index:
        raise ValueError("Home page article marker is missing")
    index = index.replace(marker, marker[:-6] + cards + '</div>', 1)
    progress_marker = '0 / 0 SIGNALS'
    if progress_marker not in index:
        raise ValueError('Home pagination progress marker is missing')
    index = index.replace(progress_marker, f'{min(len(articles), HOME_PAGE_SIZE)} / {len(articles)} SIGNALS', 1)
    (output / 'index.html').write_text(index)
    archive_urls = []
    for page in range(1, max(1, math.ceil(len(articles) / ARCHIVE_PAGE_SIZE)) + 1):
        relative = Path('archive') if page == 1 else Path('archive/page') / str(page)
        directory = output / relative
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'index.html').write_text(archive_page(articles, page, index))
        archive_urls.append(archive_url(page))
    template = (ROOT / 'article.html').read_text()
    (output / 'article.html').write_text(template)
    # Preview is not linked or indexed; it is accessible to anyone who knows the URL.
    # Editorial previews remain local; do not deploy draft content or preview UI.
    (output / 'data').mkdir(exist_ok=True)
    for page in ('about', 'privacy', 'contact'):
        destination = output / page
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / page / 'index.html', destination / 'index.html')
    (output / 'data/articles.json').write_text(json.dumps(articles, ensure_ascii=False, indent=2) + '\n')
    listing_fields = ('id', 'title', 'summary', 'category', 'format', 'score', 'status', 'source_url', 'card_image', 'card_image_alt')
    listing = [{key: article[key] for key in listing_fields if key in article} for article in articles]
    (output / 'data/index.json').write_text(json.dumps(listing, ensure_ascii=False, separators=(',', ':')) + '\n')
    infographic = ROOT / 'assets/infographics/php2shell-explainer.svg'
    if infographic.is_file():
        target = output / 'assets/infographics/php2shell-explainer.svg'
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(infographic, target)
    for article in articles:
        image_path = card_image_path(article)
        if image_path:
            source = ROOT / image_path.lstrip('/')
            if not source.is_file():
                raise ValueError('Missing article card image: ' + image_path)
            destination = output / image_path.lstrip('/')
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        share_card(output, article)
        if article.get('social_publish') is True:
            if security_style(article) is not None:
                security_share_card(output, article)
                security_story_card(output, article)
            else:
                instagram_share_card(output, article)
                instagram_story_card(output, article)
        folder = output / 'articles' / article['id']
        folder.mkdir(parents=True)
        (folder / 'index.html').write_text(article_page(article, template, modified[article['id']], related_articles(article, articles)))
    write_rss(output, articles)
    ns = 'http://www.sitemaps.org/schemas/sitemap/0.9'
    ET.register_namespace('', ns)
    sitemap = ET.Element('{' + ns + '}urlset')
    by_url = {article_url(item): item for item in articles}
    home_modified = latest_date([modified[item['id']] or item['published_at'] for item in articles])
    for url in [BASE, BASE + 'about/', BASE + 'privacy/', BASE + 'contact/'] + archive_urls + [article_url(article) for article in articles]:
        entry = ET.SubElement(sitemap, '{' + ns + '}url')
        ET.SubElement(entry, '{' + ns + '}loc').text = url
        item = by_url.get(url)
        lastmod = (modified[item['id']] or item['published_at']) if item else (home_modified if url == BASE or url in archive_urls else None)
        if lastmod:
            ET.SubElement(entry, '{' + ns + '}lastmod').text = lastmod
    ET.ElementTree(sitemap).write(output / 'sitemap.xml', encoding='utf-8', xml_declaration=True)
    (output / 'robots.txt').write_text('User-agent: *\nAllow: /\n\nSitemap: ' + BASE + 'sitemap.xml\n')
    (output / '.nojekyll').touch()
    (output / 'CNAME').write_text(BASE.removeprefix('https://').rstrip('/') + '\n')
    write_favicons(output)
    (output / 'favicon.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="12" fill="#191918"/><text x="6" y="45" fill="#f2efe7" font-family="sans-serif" font-size="43" font-weight="bold">W</text><circle cx="55" cy="49" r="5" fill="#fa4c24"/></svg>')
    (output / '404.html').write_text('<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex"><title>ページが見つかりません — WORK SIGNAL</title><h1>ページが見つかりません</h1><p><a href="/">WORK SIGNALのトップへ戻る</a></p></html>')
    return articles


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / '_site')
    args = parser.parse_args()
    for item in build(args.output):
        print(article_url(item))
        print('Threads: ' + threads_url(item))
