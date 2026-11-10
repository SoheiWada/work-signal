"""Discovery files from approved articles only; never invent publication times."""
from datetime import date, datetime, timedelta, timezone
from xml.etree import ElementTree as ET

BASE = 'https://signal.amberlight.co.jp/'
SM = 'http://www.sitemaps.org/schemas/sitemap/0.9'
NEWS = 'http://www.google.com/schemas/sitemap-news/0.9'
IMAGE = 'http://www.google.com/schemas/sitemap-image/1.1'
JST = timezone(timedelta(hours=9))


def news_publication(article, clock):
    value = article.get('published_at_time')
    if value:
        try:
            moment = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if moment.tzinfo is None or moment.astimezone(JST).date().isoformat() != article['published_at']:
                return None
            return value if timedelta(0) <= clock-moment <= timedelta(hours=48) else None
        except (ValueError, TypeError):
            return None
    # Date precision is valid in news sitemaps. Use the conservative start of
    # the reported day for expiry, never output a manufactured hour.
    try:
        day = date.fromisoformat(article['published_at'])
        start = datetime.combine(day, datetime.min.time(), JST)
        return day.isoformat() if clock-timedelta(hours=48) <= start <= clock else None
    except (ValueError, TypeError):
        return None


def write_discovery_sitemaps(output, articles, clock=None):
    clock = clock or datetime.now(timezone.utc)
    ET.register_namespace('', SM)
    ET.register_namespace('news', NEWS)
    ET.register_namespace('image', IMAGE)
    news, images = ET.Element('{'+SM+'}urlset'), ET.Element('{'+SM+'}urlset')
    selected = sorted((a for a in articles if a.get('status') == 'published'),
                      key=lambda a: (a.get('published_at_time') or a['published_at'], a['id']), reverse=True)
    count = 0
    for article in selected:
        url = BASE+'articles/'+article['id']+'/'
        entry = ET.SubElement(images, '{'+SM+'}url')
        ET.SubElement(entry, '{'+SM+'}loc').text = url
        image = ET.SubElement(entry, '{'+IMAGE+'}image')
        ET.SubElement(image, '{'+IMAGE+'}loc').text = BASE+'assets/og/'+article['id']+'.png'
        published = news_publication(article, clock)
        if not published or article.get('format') in ('management_guide', 'special_story') or count >= 1000:
            continue
        entry = ET.SubElement(news, '{'+SM+'}url')
        ET.SubElement(entry, '{'+SM+'}loc').text = url
        item = ET.SubElement(entry, '{'+NEWS+'}news')
        publication = ET.SubElement(item, '{'+NEWS+'}publication')
        ET.SubElement(publication, '{'+NEWS+'}name').text = 'WORK SIGNAL'
        ET.SubElement(publication, '{'+NEWS+'}language').text = 'ja'
        ET.SubElement(item, '{'+NEWS+'}publication_date').text = published
        ET.SubElement(item, '{'+NEWS+'}title').text = article['title']
        count += 1
    ET.ElementTree(news).write(output/'news-sitemap.xml', encoding='utf-8', xml_declaration=True)
    ET.ElementTree(images).write(output/'image-sitemap.xml', encoding='utf-8', xml_declaration=True)
