"""Audit every generated article, or the currently published sitemap.

No Google or Meta credentials are used. --live measures crawlable responses;
it does not claim to inspect Google's index or real-user Core Web Vitals.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from xml.etree import ElementTree as ET

from scripts.build_site import BASE, ROOT


class Document(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.tags, self.text, self.schemas = [], [], []
        self.current = None
        self.buffer = ''
        self.hidden = 0
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags.append((tag, attrs))
        if tag in ('script', 'style'):
            self.hidden += 1
        if tag == 'script' and attrs.get('type') == 'application/ld+json':
            self.current, self.buffer = 'json', ''

    def handle_endtag(self, tag):
        if tag == 'script' and self.current == 'json':
            self.schemas.append(json.loads(self.buffer))
            self.current = None
        if tag in ('script', 'style'):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, text):
        if self.current == 'json':
            self.buffer += text
        if not self.hidden:
            self.text.append(text)

    def attr(self, tag, key, value, attr):
        return [attrs.get(attr, '') for t, attrs in self.tags
                if t == tag and attrs.get(key) == value]


def remote(url):
    req = Request(url, headers={'User-Agent': 'WORK-SIGNAL-SEO-Audit/1.0'})
    try:
        with urlopen(req, timeout=25) as response:
            return url, response.status, response.read().decode('utf-8'), dict(response.headers)
    except HTTPError as error:
        return url, error.code, error.read().decode('utf-8'), dict(error.headers)


def audit(pages, sitemap_urls):
    errors, warnings, metadata = [], [], []
    related_map = {}
    article_urls = {url for url in sitemap_urls if '/articles/' in url}
    for url, status, source, headers in pages:
        if status != 200:
            errors.append([url, 'HTTP ' + str(status)])
            continue
        if not url.endswith('/') or '/articles/' not in url:
            continue
        try:
            doc = Document(source)
            canonical = doc.attr('link', 'rel', 'canonical', 'href')
            description = doc.attr('meta', 'name', 'description', 'content')
            schemas = [s for s in doc.schemas if s.get('@type') in ('Article', 'NewsArticle')]
            h1s = sum(tag == 'h1' for tag, _ in doc.tags)
            if canonical != [url]:
                errors.append([url, 'canonical'])
            if len(description) != 1 or not description[0].strip():
                errors.append([url, 'description'])
            if h1s != 1:
                errors.append([url, 'H1 count ' + str(h1s)])
            if any('noindex' in value.lower() for value in
                   doc.attr('meta', 'name', 'robots', 'content')):
                errors.append([url, 'noindex'])
            if 'noindex' in headers.get('X-Robots-Tag', '').lower():
                errors.append([url, 'X-Robots-Tag noindex'])
            if len(schemas) != 1:
                errors.append([url, 'Article schema'])
                continue
            schema = schemas[0]
            for key in ('headline', 'description', 'datePublished', 'publisher', 'mainEntityOfPage'):
                if not schema.get(key):
                    errors.append([url, 'missing ' + key])
            if schema.get('mainEntityOfPage', {}).get('@id') != url:
                errors.append([url, 'schema canonical mismatch'])
            if schema.get('description') != (description or [''])[0]:
                errors.append([url, 'schema description mismatch'])
            if schema.get('dateModified'):
                def clock(value):
                    return datetime.fromisoformat(value.replace('Z', '+00:00')).replace(tzinfo=None)
                if clock(schema['dateModified']) < clock(schema['datePublished']):
                    errors.append([url, 'dateModified before datePublished'])
            for key, tagkey in (('og:title', 'property'), ('og:description', 'property'),
                                ('og:image', 'property'), ('twitter:card', 'name')):
                if not doc.attr('meta', tagkey, key, 'content'):
                    errors.append([url, 'missing ' + key])
            if len(''.join(doc.text).strip()) < 300:
                errors.append([url, 'insufficient static body'])
            for tag, attrs in doc.tags:
                if tag != 'a':
                    continue
                target = urlsplit(urljoin(url, attrs.get('href', '')))
                if target.netloc == urlsplit(BASE).netloc and target.path.startswith('/articles/'):
                    normalized = target._replace(query='', fragment='').geturl()
                    if normalized not in article_urls:
                        errors.append([url, 'unknown internal article ' + normalized])
            if 'G-X4B5F6JJZH' not in source:
                warnings.append([url, 'GA4 tag absent'])
            related = re.search(r'<nav class="toc" aria-label="関連記事">(.*?)</nav>', source, re.S)
            related_map[url] = re.findall(r'<a href="([^"]+)">', related.group(1)) if related else []
            metadata.append((url, schema.get('headline', ''), (description or [''])[0]))
        except (ValueError, TypeError, KeyError) as error:
            errors.append([url, 'parse: ' + str(error)])
    for position, label in ((1, 'title'), (2, 'description')):
        counts = Counter(row[position] for row in metadata)
        for value, count in counts.items():
            if count > 1:
                errors.append([label, 'duplicate (' + str(count) + '): ' + value])
    return {'articles': len(metadata), 'sitemap_urls': len(sitemap_urls),
            'articles_with_related': sum(bool(links) for links in related_map.values()),
            'related_link_count': sum(len(links) for links in related_map.values()),
            'related_examples': {url: links for url, links in related_map.items()
                                 if any(term in url for term in ('jp-incident-monitor', 'bun-144', 'undici-content', 'express-body-parser', 'storybook-dev'))},
            'errors': errors, 'warnings': warnings}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true')
    args = parser.parse_args()
    out = ROOT / '_site'
    if args.live:
        _, _, xml, _ = remote(BASE + 'sitemap.xml')
        urls = [node.text for node in ET.fromstring(xml).iter('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')]
        with ThreadPoolExecutor(max_workers=6) as executor:
            pages = list(executor.map(remote, urls))
        report = audit(pages, urls)
        report['mode'] = 'live'
        report['missing_archive_ga4'] = [url for url, status, source, headers in pages
                                         if '/archive/' in url and 'G-X4B5F6JJZH' not in source]
        _, status, security, _ = remote(BASE + 'security/')
        report['security_hub'] = {'status': status, 'canonical': 'rel="canonical"' in security,
                                  'ga4': 'G-X4B5F6JJZH' in security, 'h1': '<h1' in security}
        _, status, _, _ = remote(BASE + 'seo-audit-nonexistent-20261030/')
        report['missing_url_status'] = status
        if status != 404:
            report['errors'].append(['404 handling', str(status)])
    else:
        urls = [node.text for node in ET.parse(out / 'sitemap.xml').iter('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')]
        pages = [(url, 200, (out / url.removeprefix(BASE) / 'index.html').read_text(), {})
                 for url in urls]
        report = audit(pages, urls)
        report['mode'] = 'generated'
        emitted = json.loads((out / 'data/articles.json').read_text())
        if report['articles'] != len(emitted):
            report['errors'].append(['coverage', 'article count mismatch'])
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report['errors']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
