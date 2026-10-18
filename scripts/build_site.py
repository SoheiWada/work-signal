"""Build crawlable GitHub Pages output from the approved article feed."""
import argparse
import html
import json
import re
import shutil
import math
from datetime import date
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
        if not isinstance(score, (int, float)) or isinstance(score, bool) or score < 80:
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
    """Reuse the reading index signal as subtle article-format identification."""
    if deep:
        return ('<span class="guide-visual" aria-hidden="true"><span class="guide-orbit"></span>'
                '<svg class="guide-pulse" viewBox="0 0 480 130" preserveAspectRatio="none">'
                '<path class="echo-two" d="M0 65 C90 65 98 8 155 20 S225 125 270 102 S350 23 480 65"/>'
                '<path class="echo" d="M0 65 C80 65 120 115 175 99 S240 13 305 35 S390 92 480 65"/>'
                '<path d="M0 65 C75 65 108 36 165 48 S245 101 304 77 S393 48 480 65"/>'
                '</svg></span>')
    return ('<span class="guide-visual" aria-hidden="true">'
            '<svg class="guide-pulse" viewBox="0 0 480 130" preserveAspectRatio="none">'
            '<path d="M0 65 H104 L119 65 L136 40 L151 92 L169 17 L189 111 L207 65 H480"/>'
            '</svg></span>')


def article_card_image(article):
    """An optional article-owned visual; no generic cover competes with headlines."""
    image = article.get("card_image")
    if not isinstance(image, str) or not re.fullmatch(
            r"/assets/[A-Za-z0-9/_-]+\\.(?:png|jpe?g|webp|avif)", image, re.I):
        return ""
    alt = article.get("card_image_alt")
    if not isinstance(alt, str):
        alt = ""
    return ('<figure class="story-figure"><img src="' + esc(image) + '" alt="'
            + esc(alt) + '" loading="lazy" decoding="async"></figure>')


def article_card(article):
    deep = article.get("format") == "deep_dive"
    form = "SIGNAL DEEP DIVE" if deep else "SIGNAL BRIEF"
    minutes = "4–7 MIN" if deep else "1–2 MIN"
    return ('<article class="story"><div class="story-head"><div class="story-top">'
            '<span class="story-category">' + esc(article["category"]) + '</span>'
            '<span class="story-format">' + story_icon(deep)
            + '<span class="story-format-label">' + form + '</span></span>'
            '</div><span class="story-readtime">' + minutes + '</span></div>'
            '<div class="story-content"><h3>' + esc(article["title"]) + '</h3>'
            + article_card_image(article) + '<p>' + esc(article["summary"])
            + '</p><a class="story-link" href="' + article_url(article)
            + '"><span>READ THE STORY</span></a></div></article>')



def article_body(article):
    deep = article.get('format') == 'deep_dive' and isinstance(article.get('sections'), list) and bool(article['sections'])
    reading = max(1, math.ceil((len(article.get('summary', '')) + sum(len(str(part.get('body', ''))) for part in article.get('sections', []))) / 600))
    if deep:
        blocks = ''
        for i, part in enumerate(article['sections'], 1):
            if not isinstance(part, dict) or not part.get('title') or not part.get('body'):
                continue
            paragraphs = ''.join('<p>' + esc(p) + '</p>' for p in re.split(r'\\n\\s*\\n', str(part['body'])) if p.strip())
            stats = ''.join('<div class="stat"><strong>' + esc(stat['value']) + '</strong><span>' + esc(stat.get('label', '')) + '</span></div>' for stat in part.get('stats', []) if isinstance(stat, dict) and stat.get('value'))
            blocks += '<section class="block" id="section-' + str(i) + '"><h2>' + esc(part['title']) + '</h2>' + paragraphs + stats + '</section>'
        if article.get('quick_take'):
            blocks = '<section class="takeaways"><h2>30秒でわかる / THE SIGNAL</h2><p>' + esc(article['quick_take']) + '</p></section>' + blocks
        toc = '<nav class="toc" aria-label="記事の目次"><div class="side-title">IN THIS STORY</div>' + ''.join('<a href="#section-' + str(i) + '">' + esc(part['title']) + '</a>' for i, part in enumerate(article['sections'], 1) if isinstance(part, dict) and part.get('title') and part.get('body')) + '</nav>'
    else:
        blocks = ''.join('<section class="block"><h2>' + title + '</h2><p>' + esc(article[key]) + '</p></section>' for title, key in SECTIONS if article.get(key))
        toc = ''
    format_label = 'SIGNAL DEEP DIVE' if deep else 'SIGNAL BRIEF'
    return ('<section class="hero"><div class="eyebrow">/ ' + esc(article["category"])
            + (' / DEEP DIVE' if deep else ' / EDITORIAL BRIEFING') + '</div><h1>' + esc(article['title'])
            + '</h1><div class="meta"><span class="score">' + esc(article['score'])
            + ' / 100</span><span class="article-type">' + format_label + '</span><span>'
            + esc(article['category']) + '</span><time datetime="' + esc(article['published_at'])
            + '">' + esc(article['published_at']) + '</time><span class="readtime">約'
            + str(reading) + '分で読める</span></div></section><div class="layout"><article class="content">'
            + '<p class="lead">' + esc(article['summary']) + '</p>' + blocks
            + '</article><aside class="side"><div class="side-title">ARTICLE INTELLIGENCE</div>'
            + '<dl><dt>FORMAT</dt><dd>' + format_label + '</dd><dt>READ TIME</dt><dd>'
            + str(reading) + ' MIN</dd><dt>CATEGORY</dt><dd>' + esc(article['category'])
            + '</dd><dt>SIGNAL SCORE</dt><dd>' + esc(article['score'])
            + ' / 100</dd><dt>PUBLISHED</dt><dd>' + esc(article['published_at'])
            + '</dd></dl>' + toc + '<div class="source"><small>/ PRIMARY SOURCE</small><a href="'
            + esc(article['source_url']) + '" target="_blank" rel="noopener noreferrer">'
            + esc(article['source_url']) + '</a></div><p class="note">'
            + 'この記事は一次情報に基づく独自の要約・考察です。掲載内容は投資助言ではありません。'
            + '</p></aside></div>')


def article_page(article, template):
    url = article_url(article)
    image_url = BASE + 'assets/og/' + article['id'] + '.png'
    title = article["title"] + " — WORK SIGNAL"
    style = re.search(r'<style>.*?</style>', template, re.S).group()
    fonts = re.search(r'<link rel="preconnect".*?<style>', template, re.S).group().removesuffix('<style>')
    analytics = template.split('<!-- Google tag (gtag.js): WORK SIGNAL -->', 1)[1].split('</head>', 1)[0]
    schema = {"@context": "https://schema.org", "@type": "NewsArticle", "headline": article["title"],
              "description": article["summary"], "datePublished": article["published_at"], "image": [image_url],
              "inLanguage": "ja", "mainEntityOfPage": {"@type": "WebPage", "@id": url},
              "publisher": {"@type": "Organization", "name": "WORK SIGNAL", "url": BASE}}
    # Do not invent a person or organization byline that the feed does not provide.
    head = ('<!doctype html><html lang="ja"><head><meta charset="utf-8">'
            + '<meta name="viewport" content="width=device-width,initial-scale=1">'
            + '<meta name="theme-color" content="#f2efe7"><title>' + esc(title) + '</title>'
            + '<meta name="description" content="' + esc(article["summary"]) + '">'
            + '<link rel="canonical" href="' + url + '">'
            + '<link rel="icon" href="/favicon.svg" type="image/svg+xml">'
            + '<meta property="og:type" content="article"><meta property="og:locale" content="ja_JP">'
            + '<meta property="og:site_name" content="WORK SIGNAL">'
            + '<meta property="og:title" content="' + esc(title) + '">'
            + '<meta property="og:description" content="' + esc(article["summary"]) + '">'
            + '<meta property="og:url" content="' + url + '">'
            + image_metadata(image_url, title)
            + '<meta name="robots" content="max-image-preview:large">'
            + json_ld(schema) + fonts + style + analytics
            + '<script>measurePageView();</script></head>')
    body = ('<body><div class="top"></div><div class="shell"><header>'
            + '<a class="brand" href="/">WORK<span>.</span>SIGNAL</a>'
            + '<a class="back" href="/#latest">← ALL STORIES</a></header>'
            + '<main id="article">' + article_body(article) + '</main></div>'
            + '<footer><div class="shell footer"><strong>WORK<span>.</span>SIGNAL</strong>'
            + '<small>NEWS IS SHORT. MEANING IS DEEP.</small></div></footer></body></html>')
    return head + body


def build(output, feed=None):
    if output.resolve() == ROOT.resolve() or ROOT.resolve().is_relative_to(output.resolve()):
        raise ValueError("Output must not overwrite the source repository")
    articles = published_articles(feed if feed is not None else json.loads((ROOT / 'data/articles.json').read_text()))
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    share_card(output)
    index = (ROOT / 'index.html').read_text()
    cards = ''.join(article_card(article) for article in articles)
    if not cards:
        cards = '<div class="empty"><div><strong>THE SIGNAL IS COMING.</strong><p>公開準備中です。</p></div></div>'
    marker = '<div class="grid" id="articles" aria-live="polite"></div>'
    if marker not in index:
        raise ValueError("Home page article marker is missing")
    index = index.replace(marker, marker[:-6] + cards + '</div>', 1)
    (output / 'index.html').write_text(index)
    template = (ROOT / 'article.html').read_text()
    (output / 'article.html').write_text(template)
    # Preview is not linked or indexed; it is accessible to anyone who knows the URL.
    (output / 'preview.html').write_text((ROOT / 'preview.html').read_text())
    (output / 'data').mkdir()
    (output / 'data/drafts.json').write_text((ROOT / 'data/drafts.json').read_text())
    (output / 'data/articles.json').write_text(json.dumps(articles, ensure_ascii=False, indent=2) + '\n')
    for article in articles:
        share_card(output, article)
        folder = output / 'articles' / article['id']
        folder.mkdir(parents=True)
        (folder / 'index.html').write_text(article_page(article, template))
    ns = 'http://www.sitemaps.org/schemas/sitemap/0.9'
    ET.register_namespace('', ns)
    sitemap = ET.Element('{' + ns + '}urlset')
    for url in [BASE] + [article_url(article) for article in articles]:
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
