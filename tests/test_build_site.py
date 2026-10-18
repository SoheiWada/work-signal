import copy
import json
import re
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET
from PIL import Image

from scripts.build_site import BASE, ROOT, build, article_card


class Document(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.tags = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class StaticPublishingTests(unittest.TestCase):
    def setUp(self):
        self.article = json.loads((ROOT / 'data/articles.json').read_text())[0]

    def test_public_output_is_crawlable_and_does_not_publish_drafts(self):
        draft = dict(self.article, id='unapproved', status='draft', title='PRIVATE DRAFT')
        low_score = dict(self.article, id='below-threshold', score=79)
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'site'
            build(output, [self.article, draft, low_score])
            home = (output / 'index.html').read_text()
            path = 'articles/' + self.article['id'] + '/'
            page = (output / path / 'index.html').read_text()
            self.assertIn(self.article['title'], home)
            self.assertIn(self.article['what_happened'], page)
            self.assertNotIn('PRIVATE DRAFT', home)
            self.assertFalse((output / 'articles/unapproved').exists())
            self.assertFalse((output / 'assets/og/unapproved.png').exists())
            self.assertEqual(len(json.loads((output / 'data/articles.json').read_text())), 1)
            doc = Document(page)
            canonicals = [attrs['href'] for tag, attrs in doc.tags
                          if tag == 'link' and attrs.get('rel') == 'canonical']
            self.assertEqual(canonicals, [BASE + path])
            meta = {attrs.get('property', attrs.get('name')): attrs.get('content')
                    for tag, attrs in doc.tags if tag == 'meta'}
            image_url = meta['og:image']
            image_path = output / image_url.removeprefix(BASE)
            with Image.open(image_path) as image:
                self.assertEqual(image.format, 'PNG')
                self.assertEqual(image.size, (int(meta['og:image:width']), int(meta['og:image:height'])))
                self.assertEqual(image.size, (1200, 630))
            schema = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', page, re.S).group(1))
            self.assertEqual(schema['image'], [image_url])
            self.assertEqual(meta['twitter:card'], 'summary_large_image')
            self.assertTrue((output / 'assets/og/home.png').is_file())
            sitemap = ET.parse(output / 'sitemap.xml')
            urls = [node.text for node in sitemap.iter('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')]
            self.assertEqual(urls, [BASE, BASE + path])
            self.assertIn(BASE + path, home)
            self.assertIn('Sitemap: ' + BASE + 'sitemap.xml', (output / 'robots.txt').read_text())
            self.assertNotIn("fetch('./data/articles.json'", page)

    def test_editorial_cards_put_article_first_and_support_optional_assets(self):
        article = copy.deepcopy(self.article)
        article['format'] = 'deep_dive'
        article['card_image'] = '/assets/cards/feature.webp'
        article['card_image_alt'] = 'Independent editorial illustration'
        card = article_card(article)
        self.assertIn('SIGNAL DEEP DIVE', card)
        self.assertIn('story-format', card)
        self.assertIn('class="story-figure"', card)
        self.assertIn('alt="Independent editorial illustration"', card)
        self.assertLess(card.index('<h3>'), card.index('<figure'))
        self.assertNotIn('story-masthead', card)
        self.assertNotIn('story-score', card)
        self.assertIn(article['title'], card)
        self.assertIn('class="guide-pulse"', card)

    def test_missing_article_visual_fails_build_instead_of_broken_image(self):
        article = copy.deepcopy(self.article)
        article['card_image'] = '/assets/cards/nonexistent_work_signal_card_image_123.webp'
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, 'Missing article card image'):
                build(Path(temp) / 'site', [article])

    def test_unsafe_card_image_is_ignored(self):
        article = copy.deepcopy(self.article)
        article['card_image'] = 'https://outside.example/tracker.png'
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'site'
            build(output, [article])
            home = (output / 'index.html').read_text()
            self.assertNotIn('outside.example', home)
            self.assertNotIn('class="story-figure"', home)

    def test_feed_text_cannot_inject_markup_or_terminate_structured_data(self):
        article = copy.deepcopy(self.article)
        article['title'] = 'A </script><script src="https://invalid.example/attack.js">'
        article['summary'] = '<img src=x onerror=alert(1)> & "quoted"'
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'site'
            build(output, [article])
            page = (output / 'articles' / article['id'] / 'index.html').read_text()
            doc = Document(page)
            self.assertFalse(any(tag == 'img' for tag, attrs in doc.tags))
            self.assertFalse(any(attrs.get('src') == 'https://invalid.example/attack.js'
                                 for tag, attrs in doc.tags))
            self.assertIn('\\u003c/script\\u003e', page)
            self.assertIn('&lt;img', page)

    def test_unsafe_or_duplicate_published_ids_fail_before_output_is_replaced(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'site'
            output.mkdir()
            sentinel = output / 'existing.txt'
            sentinel.write_text('keep')
            for feed in [[dict(self.article, id='../escape')], [self.article, self.article]]:
                with self.assertRaises(ValueError):
                    build(output, feed)
                self.assertEqual(sentinel.read_text(), 'keep')


if __name__ == '__main__':
    unittest.main()
