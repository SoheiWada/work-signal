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
        self.assertIn('class="signal-mark"', card)
        self.assertIn('class="signal-base"', card)
        self.assertIn('class="signal-sweep"', card)
        self.assertIn('preserveAspectRatio="xMidYMid meet"', card)
        self.assertNotIn('guide-visual', card)

    def test_reading_index_has_global_layout_and_visible_wave_strokes(self):
        """Guard against dropping guide CSS when article card styles are redesigned."""
        source = (ROOT / 'index.html').read_text()
        stylesheet = source.split('<style>', 1)[1].split('</style>', 1)[0]
        base_styles = stylesheet.split('@media(max-width:1050px)', 1)[0]
        for required in (
            '.reading-guide{display:grid',
            '.guide-panels{display:grid',
            '.guide-item{appearance:none',
            '.guide-visual{grid-column:2',
            '.guide-pulse path{fill:none',
            '.guide-orbit{position:absolute',
            '@keyframes signal-draw',
            '@keyframes guide-spin',
        ):
            self.assertIn(required, base_styles)
        self.assertIn('id="reading-guide"', source)
        self.assertIn('data-format="brief"', source)
        self.assertIn('data-format="deep_dive"', source)
        self.assertIn('class="signal-mark"', article_card(self.article))
        self.assertNotIn('cloneNode(true)', source)

    def test_article_format_marks_are_isolated_from_large_guide_animation(self):
        source = (ROOT / 'index.html').read_text()
        self.assertIn('function signalMark(deep)', source)
        self.assertIn('.story-format .signal-mark', source)
        self.assertNotIn('cloneNode(true)', source)
        self.assertNotIn('.story-format .guide-pulse', source)
        self.assertIn('@keyframes signal-mini-trace', source)
        for format_name in (None, 'deep_dive'):
            article = copy.deepcopy(self.article)
            if format_name:
                article['format'] = format_name
            html = article_card(article)
            self.assertIn('<svg class="signal-mark"', html)
            self.assertIn('signal-base', html)
            self.assertIn('signal-sweep', html)
            self.assertNotIn('viewBox="0 0 480 130"', html)

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

    def test_story_call_to_action_is_explicit_and_has_wave_animation(self):
        source = (ROOT / 'index.html').read_text()
        card = article_card(self.article)
        self.assertIn('class="story-link-jp">記事を読む', card)
        self.assertIn('class="story-link-wave"', card)
        self.assertIn('class="link-wave-live"', card)
        self.assertIn('aria-label="' + self.article['title'] + ' の記事を読む"', card)
        self.assertIn('.story-link:is(:hover,:focus-visible,:active)', source)
        self.assertIn('@keyframes link-wave-trace', source)
        self.assertIn('.reading-guide{display:grid', source)
        # Touch scrolling remains native because the surrounding story is not clickable.
        self.assertNotIn('onclick=', card)

    def test_article_end_has_share_targets_top_link_and_shared_behavior(self):
        from urllib.parse import parse_qs, urlparse

        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'site'
            build(output, [self.article])
            canonical = BASE + 'articles/' + self.article['id'] + '/'
            page = (output / 'articles' / self.article['id'] / 'index.html').read_text()
            home = (output / 'index.html').read_text()
            doc = Document(page)
            links = [attrs for tag, attrs in doc.tags if tag == 'a']
            buttons = [attrs for tag, attrs in doc.tags if tag == 'button']
            self.assertIn('記事を読む', home)
            self.assertIn('class="story-link-wave"', home)
            self.assertIn('id="page-top"', page)
            self.assertIn('id="article-end"', page)
            self.assertIn('aria-label="読了後のナビゲーション"', page)
            self.assertIn('SHARE THE SIGNAL', page)
            self.assertIn('ページ上部へ戻る', page)
            self.assertIn('.article-end{', page)
            self.assertTrue(any(attrs.get('href') == '#page-top' for attrs in links))
            self.assertTrue(any(attrs.get('data-copy-article-url') == canonical
                                for attrs in buttons))
            outbound = [attrs for attrs in links
                        if attrs.get('class') == 'article-share-button']
            self.assertEqual(len(outbound), 3)
            for attrs in outbound:
                self.assertEqual(attrs.get('target'), '_blank')
                self.assertIn('noopener', attrs.get('rel', ''))
                params = parse_qs(urlparse(attrs['href']).query)
                if 'url' in params:
                    self.assertEqual(params['url'][0], canonical)
                else:
                    self.assertIn(canonical, params['text'][0])
            self.assertIn('src="/assets/js/article-actions.js"', page)
            self.assertIn('src="/assets/js/article-actions.js"', (output / 'article.html').read_text())
            self.assertIn('src="/assets/js/article-actions.js"', (output / 'preview.html').read_text())
            shared = output / 'assets/js/article-actions.js'
            self.assertTrue(shared.is_file())
            self.assertIn("document.addEventListener('click'", shared.read_text())
            # A draft may be previewed, but the client-only preview never promotes it.
            self.assertIn("articleEnd(a,true)", (output / 'preview.html').read_text())

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
