import copy
import html
import json
import re
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET
from PIL import Image

from scripts.topic_catalog import active_topics
from scripts.build_site import BASE, ROOT, build, article_card, archive_page, archive_url, ARCHIVE_PAGE_SIZE, HOME_PAGE_SIZE


class Document(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.tags = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class StaticPublishingTests(unittest.TestCase):
    def setUp(self):
        self.article = next(a for a in json.loads((ROOT / 'data/articles.json').read_text()) if a.get('what_happened'))

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
            # Deep dives render 'sections' instead of the legacy what_happened field.
            # Compare the published, visible paragraph text rather than raw HTML.
            class VisibleText(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.parts = []

                def handle_data(self, data):
                    self.parts.append(data)

            parser = VisibleText()
            parser.feed(page)
            visible = re.sub(r'\s+', ' ', ' '.join(parser.parts))
            sections = self.article.get('sections')
            expected_bodies = ([part['body'] for part in sections if part.get('body')]
                               if sections else [self.article['what_happened']])
            for body in expected_bodies:
                for paragraph in re.split(r'\n\s*\n', body):
                    normalized = re.sub(r'\s+', ' ', paragraph).strip()
                    if normalized:
                        self.assertIn(normalized, visible)
            self.assertNotIn('PRIVATE DRAFT', home)
            self.assertFalse((output / 'articles/unapproved').exists())
            self.assertFalse((output / 'assets/og/unapproved.png').exists())
            self.assertEqual(len(json.loads((output / 'data/articles.json').read_text())), 1)
            listing = json.loads((output / 'data/index.json').read_text())
            self.assertEqual(len(listing), 1)
            self.assertNotIn('sections', listing[0])
            self.assertNotIn('what_happened', listing[0])
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
            topics = active_topics([self.article])
            topic_urls = ([BASE + 'topics/'] + [BASE + 'topics/' + topic['id'] + '/' for topic in topics]) if topics else []
            self.assertEqual(urls, [BASE, BASE + 'about/', BASE + 'privacy/', BASE + 'contact/', BASE + 'security/', BASE + 'archive/'] + topic_urls + [BASE + path])
            self.assertIn(BASE + path, home)
            self.assertIn('href="/archive/"', home)
            self.assertIn('1 / 1 SIGNALS', home)
            self.assertIn('class="signals-navigation"', home)
            security = (output / 'security/index.html').read_text()
            security_doc = Document(security)
            self.assertEqual(sum(tag == 'h1' for tag, _ in security_doc.tags), 1)
            self.assertIn('<link rel="canonical" href="' + BASE + 'security/">', security)
            self.assertEqual(security.count("gtag('config', 'G-X4B5F6JJZH'"), 1)
            self.assertIn('href="/favicon-96.png"', security)
            self.assertNotIn('adsbygoogle.js', security)
            archive = (output / 'archive/index.html').read_text()
            self.assertIn(self.article['title'], archive)
            self.assertIn('href="' + BASE + 'archive/"', archive)
            self.assertIn('Sitemap: ' + BASE + 'sitemap.xml', (output / 'robots.txt').read_text())
            self.assertNotIn("fetch('./data/articles.json'", page)


    def test_article_hero_moves_score_into_intelligence_sidebar(self):
        from scripts.build_site import article_body

        rendered = article_body(self.article)
        hero = rendered.split('<div class="layout">', 1)[0]
        self.assertIn('class="hero article-hero"', hero)
        self.assertIn('class="article-kicker"', hero)
        self.assertIn('class="article-kicker-category"', hero)
        self.assertIn('class="article-meta-label">PUBLISHED</span>', hero)
        self.assertIn('class="readtime"', hero)
        self.assertNotIn('class="score"', hero)
        self.assertIn('<dt>SIGNAL SCORE</dt>', rendered)
        self.assertEqual(rendered.count('<h1>'), 1)

    def test_data_frequency_figure_is_source_checked_and_cohort_aware(self):
        from scripts.build_site import editorial_evidence_figure, article_body

        data = json.loads((ROOT / 'data/articles.json').read_text())
        article = next(a for a in data if
                       a['id'] == '20261102-ai-productivity-gains-unreported-management-survey')
        html = editorial_evidence_figure(article)
        self.assertIn('class="signal-evidence"', html)
        self.assertIn('95.2', html)
        self.assertIn('71.1', html)
        self.assertIn('n = 546', html)
        self.assertIn('n = 520', html)
        self.assertIn('母数', html)
        self.assertIn(article['source_url'], html)
        self.assertIn('style="width:95.2%"', html)
        self.assertIn('style="width:71.1%"', html)
        self.assertIn('https://', html)
        self.assertEqual(article_body(article).count('class="signal-evidence"'), 1)
        self.assertEqual(editorial_evidence_figure(self.article), '')

        altered = copy.deepcopy(article)
        altered['summary'] = '数値を伏せた文章'
        altered['sections'] = []
        with self.assertRaisesRegex(ValueError, 'Figure must cite figures'):
            editorial_evidence_figure(altered)

    def test_survey_heading_matches_primary_source_statistic(self):
        article = next(a for a in json.loads((ROOT / 'data/articles.json').read_text())
                       if a['id'] == '20261102-ai-productivity-gains-unreported-management-survey')
        self.assertTrue(article['sections'][0]['title'].startswith('95.2％'))
        self.assertIn('95.2％', article['summary'])
        self.assertIn('71.1％', article['summary'])

    def test_repeated_quick_take_is_not_rendered_twice(self):
        from scripts.build_site import article_body, distinct_quick_take

        article = copy.deepcopy(self.article)
        article['format'] = 'deep_dive'
        article['sections'] = [{'title': '検証したこと', 'body': '一次情報に基づく説明です。'}]
        article['summary'] = 'OpenAIが新しい技術を発表し、仕事の進め方に影響が出る可能性があります。'
        article['quick_take'] = article['summary']
        self.assertIsNone(distinct_quick_take(article))
        rendered = article_body(article)
        self.assertEqual(rendered.count(article['summary']), 1)
        self.assertNotIn('class="takeaways"', rendered)

        article['quick_take'] = 'OpenAIが新しい技術を発表し、仕事の進め方に影響が出る可能性があります。　'
        self.assertIsNone(distinct_quick_take(article))
        article['quick_take'] = '企業の担当者は導入前に権限管理と運用ルールを点検する必要があります。'
        self.assertEqual(distinct_quick_take(article), article['quick_take'])
        rendered = article_body(article)
        self.assertIn('class="takeaways"', rendered)
        self.assertEqual(rendered.count(article['quick_take']), 1)

    def test_reading_time_is_consistent_across_card_article_and_listing(self):
        from scripts.build_site import article_body, reading_minutes

        brief = copy.deepcopy(self.article)
        brief.pop('sections', None)
        brief['format'] = 'brief'
        brief['summary'] = 'ニュースの概要。'
        brief['what_happened'] = '詳細' * 350
        brief['why_it_matters'] = '重要性' * 120
        brief['impact'] = '仕事' * 100
        brief['caveats'] = '留保' * 100
        minutes = reading_minutes(brief)
        self.assertGreater(minutes, 1)
        for html in (article_card(brief), article_body(brief)):
            self.assertIn('datetime="PT' + str(minutes) + 'M"', html)
            self.assertIn('aria-label="読了目安 ' + str(minutes) + '分"', html)
            self.assertIn('class="readtime-number" aria-hidden="true">' + f'{minutes:02d}' + '</span>', html)
            self.assertIn('class="readtime-unit" aria-hidden="true">MIN</span>', html)

        deep = dict(brief, sections=[{'title': '背景', 'body': '背景の説明' * 180}], quick_take='概要の要点')
        deep_minutes = reading_minutes(deep)
        self.assertGreaterEqual(deep_minutes, 1)
        for html in (article_card(deep), article_body(deep)):
            self.assertIn('datetime="PT' + str(deep_minutes) + 'M"', html)

    def test_reading_format_uses_depth_not_legacy_deep_dive_badge(self):
        from scripts.build_site import reading_format

        story = copy.deepcopy(self.article)
        story['format'] = 'deep_dive'
        story['sections'] = [
            {'title': '確認事実', 'body': '公式の発表。' * 35},
            {'title': '修正方法', 'body': '更新を行う。' * 35},
        ]
        self.assertEqual(reading_format(story), 'brief')

        story['format'] = 'brief'
        story['sections'] = [
            {'title': f'独自の検証 {number}', 'body': '事実と背景を分析し、条件を比較する。' * 20}
            for number in range(4)
        ]
        self.assertEqual(reading_format(story), 'deep_dive')
        self.assertIn('SIGNAL DEEP DIVE', article_card(story))

        story['format'] = 'deep_dive'
        story['reading_format_override'] = 'brief'
        self.assertEqual(reading_format(story), 'brief')
        story['format'] = 'management_guide'
        self.assertEqual(reading_format(story), 'management_guide')

    def test_reading_format_editorial_override_requires_reason(self):
        from scripts.build_site import published_articles

        story = copy.deepcopy(self.article)
        story['reading_format_override'] = 'brief'
        with self.assertRaisesRegex(ValueError, 'Reading format override'):
            published_articles([story])
        story['reading_format_reason'] = '公式情報の事実整理を中心とした速報で、比較分析や背景考察は意図的に扱っていない。'
        self.assertEqual(len(published_articles([story])), 1)

    def test_formatted_reading_time_is_accessible_not_a_badge(self):
        from scripts.build_site import reading_time_markup

        story = copy.deepcopy(self.article)
        mark = reading_time_markup(story)
        self.assertIn('<time class="story-readtime" datetime="PT', mark)
        self.assertIn('readtime-number', mark)
        self.assertNotIn('約', mark)
        self.assertNotIn('rounded', mark)

    def test_home_search_and_security_deduplication_are_accessible(self):
        source = (ROOT / 'index.html').read_text()
        self.assertIn('role="search"', source)
        self.assertIn('type="search"', source)
        self.assertIn('id="signal-search-input"', source)
        self.assertIn('aria-controls="articles"', source)
        self.assertIn('featuredSecurityIds', source)
        self.assertIn('function matchingArticles(category,format,query)', source)
        self.assertIn('reading_minutes', source)
        self.assertNotIn('class="courtside-arrow" aria-hidden="true">→', source)

    def test_security_watch_activity_order_mixes_new_and_updated_by_instant(self):
        """Four user scenarios alternate new stories and updated older stories."""
        from scripts.build_site import security_activity_sort_key

        def row(aid, pub_date, pub_clock, changed=None):
            article = {'id': aid, 'published_at': pub_date,
                       'published_at_time': pub_clock}
            return (changed or pub_date,
                    {'article_id': aid, 'id': aid, 'date': pub_date}, article)

        # Actual order: 22:00 update, 21:59 new, 21:57 update, 21:56 new.
        first = row('first-updated', '2026-10-22',
                    '2026-10-22T10:00:00+09:00', '2026-10-30T22:00:00+09:00')
        second = row('second-new', '2026-10-30',
                     '2026-10-30T21:59:00+09:00')
        third = row('third-updated', '2026-10-20',
                    '2026-10-20T12:43:00+09:00', '2026-10-30T12:57:00Z')
        fourth = row('fourth-new', '2026-10-30',
                     '2026-10-30T21:56:00+09:00')
        items = [fourth, third, second, first]
        ordered = sorted(items, key=security_activity_sort_key, reverse=True)
        self.assertEqual([item[1]['article_id'] for item in ordered],
                         ['first-updated', 'second-new', 'third-updated', 'fourth-new'])
        # Reverse the first story's update and ensure the newer new stories win.
        changed_first = ('2026-10-23T10:01:00+09:00', first[1], first[2])
        ordered = sorted([fourth, third, second, changed_first],
                         key=security_activity_sort_key, reverse=True)
        self.assertEqual([item[1]['article_id'] for item in ordered],
                         ['second-new', 'third-updated', 'fourth-new', 'first-updated'])

    def test_security_watch_sort_handles_missing_clocks_and_timezone_offsets(self):
        from scripts.build_site import security_activity_sort_key
        jst_first = ('2026-10-30T21:59:00+09:00',
                     {'date': '2026-10-22', 'article_id': 'edited'},
                     {'published_at': '2026-10-22',
                      'first_registered_at': '2026-10-22T09:00:00+09:00'})
        utc_later = ('2026-10-30T13:00:00Z',
                     {'date': '2026-10-20', 'article_id': 'utc'},
                     {'published_at': '2026-10-20'})
        date_only = ('2026-10-30',
                     {'date': '2026-10-30', 'article_id': 'no-hour'}, None)
        self.assertEqual(
            [v[1]['article_id'] for v in
             sorted([date_only, jst_first, utc_later],
                    key=security_activity_sort_key, reverse=True)],
            ['utc', 'edited', 'no-hour'])

    def test_security_watch_archive_visual_order_follows_latest_activity(self):
        """Home and archive cards use the same latest editorial activity order."""
        def article(aid, published, registered, updated=None):
            item = copy.deepcopy(self.article)
            item.update(id=aid, title='Chronology test ' + aid, category='SECURITY',
                        published_at=published, published_at_time=registered,
                        social_security_severity='CRITICAL',
                        social_security_product='Test Product ' + aid)
            if updated:
                item['updated_at'] = updated
            else:
                item.pop('updated_at', None)
            return item

        first = article('activity-first', '2026-10-22',
                        '2026-10-22T10:00:00+09:00',
                        '2026-10-30T22:00:00+09:00')
        second = article('activity-second', '2026-10-30',
                         '2026-10-30T21:59:00+09:00')
        third = article('activity-third', '2026-10-20',
                        '2026-10-20T12:43:00+09:00',
                        '2026-10-30T21:57:00+09:00')
        fourth = article('activity-fourth', '2026-10-30',
                         '2026-10-30T21:56:00+09:00')
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'site'
            build(output, [fourth, third, second, first])
            archive = (output / 'security/index.html').read_text()
            home = (output / 'index.html').read_text()
            ids = ('activity-first', 'activity-second', 'activity-third',
                   'activity-fourth')
            # Use actual SECURITY WATCH card hrefs rather than incidental text.
            for page in (archive, home):
                found = [aid for aid in ids
                         if ('class="sw-item" href="/articles/' + aid + '/"') in page]
                if page is archive:
                    self.assertEqual(len(found), 4)
                offsets = [page.index('class="sw-item" href="/articles/' + aid + '/"')
                           for aid in found]
                self.assertEqual(offsets, sorted(offsets))
            self.assertIn('更新 2026-10-30 22:00 JST', archive)
            self.assertIn('公開登録 2026-10-22 10:00 JST', archive)
            self.assertIn('新規公開・追記更新の新しい日時順', archive)

    def test_security_watch_articles_return_to_archive_from_top_and_end(self):
        """SECURITY stories have a real archive route without losing ALL SIGNALS."""
        from scripts.build_site import article_page, security_watch_return
        template = (ROOT / 'article.html').read_text()
        security = copy.deepcopy(self.article)
        security['category'] = 'SECURITY'
        security['id'] = 'security-navigation-example'
        html = article_page(security, template)
        doc = Document(html)
        links = [attrs for tag, attrs in doc.tags if tag == 'a']
        security_links = [attrs for attrs in links if attrs.get('href') == '/security/']
        self.assertEqual(len(security_links), 2)
        self.assertTrue(all(attrs.get('aria-label') == 'SECURITY WATCHの記事一覧へ戻る'
                            for attrs in security_links))
        self.assertIn('security-watch-return--top', html)
        self.assertIn('security-watch-return--end', html)
        self.assertIn('SECURITY WATCH一覧へ戻る', html)
        self.assertIn('href="/#latest"', html)
        self.assertIn('class="article-return"', html)
        self.assertEqual(security_watch_return(security, 'top').count('href="/security/"'), 1)

        normal = copy.deepcopy(security)
        normal['category'] = 'AI'
        normal_html = article_page(normal, template)
        self.assertNotIn('security-watch-return', normal_html)
        self.assertNotIn('href="/security/"', normal_html)
        self.assertIn('href="/#latest"', normal_html)

    def test_legacy_and_preview_navigation_match_static_articles(self):
        for name in ('article.html', 'preview.html'):
            source = (ROOT / name).read_text()
            with self.subTest(name=name):
                self.assertIn("function securityWatchReturn(a,position)", source)
                self.assertIn("a.category==='SECURITY'", source)
                self.assertIn("link.href='/security/'", source)
                self.assertIn("grid.append(securityWatchReturn(a,'end'))", source)
                self.assertIn("hero.append(securityWatchReturn(a,'top'))", source)
                self.assertIn("returnLink.href='/#latest'", source)
        style = (ROOT / 'assets/css/signal-interactions.css').read_text()
        self.assertIn('.security-watch-return a:focus-visible', style)
        self.assertIn('min-height:48px', style)

    def test_security_watch_archive_card_contrast(self):
        # Archive cards have a pale surface; text must not inherit
        # the light foreground used by the surrounding dark shell.
        source = (ROOT / 'scripts/build_site.py').read_text()
        for rule in (
            '.sw-archive-page .sw-copy .sw-headline{color:#191918}',
            '.sw-archive-page .sw-copy .sw-product{color:#514a43}',
            '.sw-archive-page .sw-copy .sw-summary{color:#504a45}',
            '.sw-archive-page .sw-copy .sw-status{background:#ebe5dc;color:#40372d}',
        ):
            with self.subTest(rule=rule):
                self.assertIn(rule, source)
        self.assertNotIn('.sw-archive-page .sw-copy .sw-headline{color:#f5eee9}', source)

    def test_archive_page_size_and_numbered_links(self):
        articles = [dict(self.article, id=f'test-archive-{index:02d}', title=f'Archive story {index:02d}')
                    for index in range(ARCHIVE_PAGE_SIZE + 3)]
        home_template = (ROOT / 'index.html').read_text()
        first = archive_page(articles, 1, home_template)
        second = archive_page(articles, 2, home_template)
        self.assertEqual(first.count('<article class="story">'), ARCHIVE_PAGE_SIZE)
        self.assertEqual(second.count('<article class="story">'), 3)
        self.assertIn('href="' + archive_url(2) + '"', first)
        self.assertIn('href="' + archive_url(1) + '"', second)
        self.assertIn('aria-current="page"', second)
        self.assertIn('href="/#latest"', second)
        self.assertIn('https://www.instagram.com/work_signal_japan/', second)
        self.assertIn('https://www.threads.com/@work_signal_japan', second)
        self.assertEqual(HOME_PAGE_SIZE, 12)

    def test_instagram_jpeg_requires_explicit_social_approval(self):
        """Older published articles must never have scheduled social images."""
        article = dict(self.article, id='approved-instagram-test', social_publish=True)
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'site'
            build(output, [article])
            jpeg_path = output / 'assets/instagram/approved-instagram-test.jpg'
            self.assertTrue(jpeg_path.is_file())
            with Image.open(jpeg_path) as picture:
                self.assertEqual(picture.format, 'JPEG')
                self.assertEqual(picture.size, (1080, 1350))
            story_path = output / 'assets/stories/approved-instagram-test.jpg'
            self.assertTrue(story_path.is_file())
            with Image.open(story_path) as story_picture:
                self.assertEqual(story_picture.format, 'JPEG')
                self.assertEqual(story_picture.size, (1080, 1920))
            other = dict(self.article, id='unapproved-instagram-test')
            build(output, [other])
            self.assertFalse((output / 'assets/instagram/unapproved-instagram-test.jpg').exists())
            self.assertFalse((output / 'assets/stories/unapproved-instagram-test.jpg').exists())

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

    def test_editorial_section_paragraphs_split_on_blank_lines(self):
        from scripts.build_site import article_body

        article = copy.deepcopy(self.article)
        article['sections'] = [{
            'title': '本文の見出し',
            'body': '第一段落です。\\n\\n第二段落です。'.replace('\\n', '\n'),
        }]
        body = article_body(article)
        self.assertIn('<p>第一段落です。</p><p>第二段落です。</p>', body)

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

    def test_read_the_signal_is_the_only_card_navigation_target(self):
        """Large touch targets should not make the whole article card clickable."""
        source = (ROOT / 'index.html').read_text()
        css = (ROOT / 'assets/css/signal-interactions.css').read_text()
        card = article_card(self.article)
        self.assertIn('<span class="story-link-title">READ THE SIGNAL</span>', card)
        self.assertIn('class="story-link-wave"', card)
        self.assertIn('class="link-wave-live"', card)
        self.assertIn('aria-label="' + self.article['title'] + ' のシグナルを読む"', card)
        self.assertNotIn('記事を読む</span>', card)
        self.assertNotIn('onclick=', card)
        self.assertNotIn('href=', card.split('<a class="story-link"')[0])
        self.assertIn('@keyframes signal-transmit', css)
        self.assertIn('.story .story-link:focus-visible', css)
        self.assertIn('.story .story-link{', css)
        self.assertIn('.reading-guide{display:grid', source)
        self.assertIn('href="/assets/css/signal-interactions.css"', source)
        self.assertIn("'READ THE SIGNAL','story-link-title'", source)

    def test_article_end_is_a_shared_editorial_transmission_and_all_signals_return(self):
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
            self.assertIn('READ THE SIGNAL', home)
            self.assertIn('class="story-link-wave"', home)
            self.assertIn('id="article-end"', page)
            self.assertIn('aria-label="読了後のナビゲーション"', page)
            self.assertIn('SHARE THIS SIGNAL', page)
            self.assertIn('TRANSMISSION / AFTER THE SIGNAL', page)
            self.assertIn('ALL SIGNALS', page)
            self.assertIn('href="/#latest"', page)
            self.assertNotIn('ALL STORIES', page)
            self.assertNotIn('BACK TO THE TOP', page)
            self.assertTrue(any(attrs.get('href') == '/#latest'
                                and attrs.get('class') == 'article-return' for attrs in links))
            self.assertFalse(any(attrs.get('href') == '#page-top' for attrs in links))
            self.assertTrue(any(attrs.get('data-copy-article-url') == canonical
                                for attrs in buttons))
            follow_links = {attrs['data-social-follow']: attrs for attrs in links
                            if 'data-social-follow' in attrs}
            self.assertEqual(set(follow_links), {'threads', 'instagram', 'rss'})
            self.assertEqual(follow_links['threads']['href'], 'https://www.threads.com/@work_signal_japan')
            self.assertEqual(follow_links['instagram']['href'], 'https://www.instagram.com/work_signal_japan/')
            self.assertEqual(follow_links['rss']['href'], '/feed.xml')
            for attrs in follow_links.values():
                self.assertEqual(attrs['data-article-id'], self.article['id'])
            self.assertLess(page.index('FOLLOW THE SIGNAL'), page.index('SHARE THIS SIGNAL'))
            self.assertIn('href="/about/#editorial-policy"', page)
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
                    self.assertIn('\n' + canonical, params['text'][0])
                    self.assertTrue(params['text'][0].endswith(self.article['source_url']))

            self.assertIn('href="/assets/css/signal-interactions.css"', page)
            self.assertIn('src="/assets/js/article-actions.js"', page)
            dynamic = (output / 'article.html').read_text()
            self.assertFalse((output / 'preview.html').exists())
            self.assertFalse((output / 'data/drafts.json').exists())
            self.assertTrue((output / 'contact/index.html').is_file())
            self.assertIn('https://formspree.io/f/xoejzwye', (output / 'contact/index.html').read_text())
            self.assertNotIn('info@amberlight.co.jp', (output / 'contact/index.html').read_text())
            self.assertIn('href="/assets/css/signal-interactions.css"', dynamic)
            self.assertIn("returnLink.href='/#latest'", dynamic)
            self.assertIn("'SHARE THIS SIGNAL'", dynamic)
            shared_js = output / 'assets/js/article-actions.js'
            shared_css = output / 'assets/css/signal-interactions.css'
            self.assertTrue(shared_js.is_file())
            self.assertTrue(shared_css.is_file())
            self.assertIn("document.addEventListener('click'", shared_js.read_text())
            self.assertIn('@keyframes return-transmit', shared_css.read_text())
            self.assertIn('.article-share-list{', shared_css.read_text())
            self.assertIn('.article-return-name{', shared_css.read_text())
            self.assertIn('@media(prefers-reduced-motion:reduce)', shared_css.read_text())

    def test_transmission_is_consistent_with_existing_site_and_has_no_pseudo_card_navigation(self):
        index = (ROOT / 'index.html').read_text()
        article = (ROOT / 'article.html').read_text()
        preview = (ROOT / 'preview.html').read_text()
        for source in (article, preview):
            self.assertIn("section.id='article-end'", source)
            self.assertIn('ALL SIGNALS</a>', source)
            self.assertNotIn('ALL STORIES</a>', source)
            self.assertNotIn("returnLink.href='#page-top'", source)
            self.assertIn('href="/assets/css/signal-interactions.css"', source)
        self.assertIn('function signalMark(deep)', index)
        self.assertIn('.guide-pulse path{fill:none', index)
        self.assertIn('.reading-guide{display:grid', index)
        self.assertIn('@keyframes signal-draw', index)
        self.assertIn('.story-format .signal-mark', index)

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
