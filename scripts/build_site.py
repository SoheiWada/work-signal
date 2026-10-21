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

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://signal.amberlight.co.jp/"
CATEGORIES = {"AI", "仕事", "マネジメント", "お金", "経済", "Crypto"}
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
@media(max-width:650px){.dsx-steps{grid-template-columns:repeat(2,minmax(0,1fr))}.dsx-step svg{height:98px}.dsx-step:nth-child(2):after{content:'↓';right:50%;top:auto;bottom:-17px;transform:translateX(50%)}.dsx-step:nth-child(3):after{content:'→'}.dsx-figure{padding:12px}}
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

def article_body(article):
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
            + '">' + esc(article['published_at']) + '</time><span class="readtime">約'
            + str(reading) + '分で読める</span></div></section><div class="layout"><article class="content">'
            + '<p class="lead">' + esc(article['summary']) + '</p>' + blocks
            + management_cta(article) + '</article><aside class="side"><div class="side-title">ARTICLE INTELLIGENCE</div>'
            + '<dl><dt>FORMAT</dt><dd>' + format_label + '</dd><dt>READ TIME</dt><dd>'
            + str(reading) + ' MIN</dd><dt>CATEGORY</dt><dd>' + esc(article['category'])
            + '</dd>' + ('' if article.get('format') in ('special_story', 'management_guide') else '<dt>SIGNAL SCORE</dt><dd>' + esc(article['score']) + ' / 100</dd>') + '<dt>PUBLISHED</dt><dd>' + esc(article['published_at'])
            + '</dd></dl>' + toc + '<div class="source"><small>/ PRIMARY SOURCE</small><a href="'
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


def article_page(article, template):
    url = article_url(article)
    image_url = BASE + 'assets/og/' + article['id'] + '.png'
    title = article["title"] + " — WORK SIGNAL"
    style = re.search(r'<style>.*?</style>', template, re.S).group()
    fonts = re.search(r'<link rel="preconnect".*?<style>', template, re.S).group().removesuffix('<style>')
    analytics = template.split('<!-- Google tag (gtag.js): WORK SIGNAL -->', 1)[1].split('</head>', 1)[0]
    schema = {"@context": "https://schema.org", "@type": ("Article" if article.get("format") in ("special_story", "management_guide") else "NewsArticle"), "headline": article["title"],
              "description": article["summary"], "datePublished": article["published_at"], "image": [image_url],
              "inLanguage": "ja", "mainEntityOfPage": {"@type": "WebPage", "@id": url},
              "publisher": {"@type": "Organization", "name": "WORK SIGNAL", "url": BASE}}
    # Do not invent a person or organization byline that the feed does not provide.
    head = ('<!doctype html><html lang="ja"><head><meta charset="utf-8">'
            + '<meta name="viewport" content="width=device-width,initial-scale=1">'
            + '<meta name="theme-color" content="#f2efe7"><title>' + esc(title) + '</title>'
            + '<meta name="description" content="' + esc(article["summary"]) + '">'
            + '<link rel="canonical" href="' + url + '">' 
            + '<link rel="alternate" type="application/rss+xml" title="WORK SIGNAL RSS" href="/feed.xml">'
            + '<link rel="icon" href="/favicon.svg" type="image/svg+xml">'
            + '<meta property="og:type" content="article"><meta property="og:locale" content="ja_JP">'
            + '<meta property="og:site_name" content="WORK SIGNAL">'
            + '<meta property="og:title" content="' + esc(title) + '">'
            + '<meta property="og:description" content="' + esc(article["summary"]) + '">'
            + '<meta property="og:url" content="' + url + '">'
            + image_metadata(image_url, title)
            + '<meta name="robots" content="max-image-preview:large">'
            + json_ld(schema) + fonts + style + (BTC_CALENDAR_CSS if article.get('id') == '20261021-bitcoin-ath-events' else '') + (DSX_POD_DIAGRAM_CSS if article.get('id') == '20261021-nvidia-dsx-pod-ai-datacenter-deployment' else '')
            + '<link rel="stylesheet" href="/assets/css/signal-interactions.css">'
            + '<script defer src="/assets/js/article-actions.js"></script>' + analytics
            + '<script>measurePageView();</script></head>')
    body = ('<body><div class="top" id="page-top"></div><div class="shell"><header>'
            + '<a class="brand" href="/">WORK<span>.</span>SIGNAL</a>'
            + '<a class="back" href="/#latest">ALL SIGNALS</a></header>'
            + '<main id="article">' + article_body(article) + article_end(article) + '</main></div>'
            + '<footer><div class="shell footer"><strong>WORK<span>.</span>SIGNAL</strong>'
            + '<small>NEWS IS SHORT. MEANING IS DEEP. · <a href="/about/">ABOUT</a> · <a href="/privacy/">PRIVACY POLICY</a> · <a href="/contact/">CONTACT</a> · <a href="/feed.xml">RSS</a></small></div></footer>'
            + wage_widget_script(article, template) + '</body></html>')
    return head + body


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
    cards = ''.join(article_card(article) for article in articles)
    if not cards:
        cards = '<div class="empty"><div><strong>THE SIGNAL IS COMING.</strong><p>公開準備中です。</p></div></div>'
    marker = '<div class="grid" id="articles"></div>'
    if marker not in index:
        raise ValueError("Home page article marker is missing")
    index = index.replace(marker, marker[:-6] + cards + '</div>', 1)
    (output / 'index.html').write_text(index)
    template = (ROOT / 'article.html').read_text()
    (output / 'article.html').write_text(template)
    # Preview is not linked or indexed; it is accessible to anyone who knows the URL.
    # Editorial previews remain local; do not deploy draft content or preview UI.
    (output / 'data').mkdir()
    for page in ('about', 'privacy', 'contact'):
        destination = output / page
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / page / 'index.html', destination / 'index.html')
    (output / 'data/articles.json').write_text(json.dumps(articles, ensure_ascii=False, indent=2) + '\n')
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
        folder = output / 'articles' / article['id']
        folder.mkdir(parents=True)
        (folder / 'index.html').write_text(article_page(article, template))
    write_rss(output, articles)
    ns = 'http://www.sitemaps.org/schemas/sitemap/0.9'
    ET.register_namespace('', ns)
    sitemap = ET.Element('{' + ns + '}urlset')
    for url in [BASE, BASE + 'about/', BASE + 'privacy/', BASE + 'contact/'] + [article_url(article) for article in articles]:
        entry = ET.SubElement(sitemap, '{' + ns + '}url')
        ET.SubElement(entry, '{' + ns + '}loc').text = url
    ET.ElementTree(sitemap).write(output / 'sitemap.xml', encoding='utf-8', xml_declaration=True)
    (output / 'robots.txt').write_text('User-agent: *\nAllow: /\n\nSitemap: ' + BASE + 'sitemap.xml\n')
    (output / '.nojekyll').touch()
    (output / 'CNAME').write_text(BASE.removeprefix('https://').rstrip('/') + '\n')
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
