import copy
import json
import re
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET
from scripts import build_site as site
from scripts.related_articles import category_followups
from scripts.discovery_sitemaps import write_discovery_sitemaps, news_publication, SM, NEWS, IMAGE


class DiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.articles = site.published_articles(json.loads((site.ROOT/'data/articles.json').read_text()))
        cls.template = (site.ROOT/'article.html').read_text()

    def test_every_article_has_four_distinct_reading_targets_and_consistent_breadcrumbs(self):
        original = copy.deepcopy(self.articles)
        for article in self.articles:
            related = site.related_articles(article, self.articles)
            rest = category_followups(article, self.articles, related)
            ids = [a['id'] for a in [*related, *rest]]
            self.assertEqual(len(ids), 4, article['id'])
            self.assertEqual(len(set(ids)), 4)
            self.assertNotIn(article['id'], ids)
            page = site.article_page(article, self.template, related=related,
                                     topics=site.article_topics(article), followups=rest)
            rail = re.search(r'<nav class="article-reading-rail".*?</nav>', page).group()
            for item in [*related, *rest]:
                self.assertIn(site.article_url(item), rail)
            self.assertIn('href="/topics/"', rail)
            schemas = [json.loads(x) for x in re.findall(r'application/ld\+json">(.*?)</script>', page)]
            article_schema = next(x for x in schemas if x['@type'] in ('Article', 'NewsArticle'))
            breadcrumb = next(x for x in schemas if x['@type'] == 'BreadcrumbList')
            self.assertEqual(breadcrumb['itemListElement'][-1]['item'], site.article_url(article))
            self.assertEqual(article_schema['author']['name'], 'WORK SIGNAL編集部')
            self.assertIn('WORK SIGNAL編集部</a>', page)
        self.assertEqual(self.articles, original)

    def test_category_fallback_is_labeled_and_excludes_drafts_low_scores_and_self(self):
        a = self.articles[0]
        bad = [dict(a, id='draft', status='draft'), dict(a, id='low', score=79),
               dict(a, id='other', category='Crypto')]
        self.assertEqual(category_followups(a, [a, *bad]), [])
        page = site.reading_rail(a, (), [dict(a, id='follow')])
        self.assertIn(a['category']+'の新着', page)
        self.assertNotIn('<h3>関連記事', page)

    def test_security_facts_use_only_approved_fields_and_escape_text(self):
        a = {'category':'SECURITY', 'social_security_product':'Product < 2',
             'social_security_severity':'HIGH', 'social_security_action':'2.0へ更新 & 再起動'}
        facts = site.security_key_facts(a)
        self.assertIn('Product &lt; 2', facts)
        self.assertIn('2.0へ更新 &amp; 再起動', facts)
        self.assertNotIn('CVSS', facts)
        self.assertEqual(site.security_key_facts(dict(a, security_watch=False)), '')
        self.assertEqual(site.security_key_facts({'category':'AI'}), '')

    def test_news_expiry_future_times_precision_and_image_discovery(self):
        clock = datetime(2026,11,11,3,tzinfo=timezone.utc)
        base = dict(self.articles[0], published_at='2026-11-10',
                    published_at_time='2026-11-10T12:00:00Z', format='brief', title='確認 & 留保 < 条件')
        items = [base, dict(base,id='expired',published_at='2026-11-08',published_at_time='2026-11-08T12:00:00Z'),
                 dict(base,id='future',published_at='2026-11-12',published_at_time='2026-11-12T12:00:00Z'),
                 dict(base,id='draft',status='draft'), dict(base,id='guide',format='management_guide')]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_discovery_sitemaps(root, items, clock)
            news = ET.parse(root/'news-sitemap.xml')
            dates = news.findall('.//{'+NEWS+'}publication_date')
            self.assertEqual([x.text for x in dates], ['2026-11-10T12:00:00Z'])
            self.assertEqual(news.find('.//{'+NEWS+'}title').text, base['title'])
            images = ET.parse(root/'image-sitemap.xml')
            self.assertEqual(len(images.findall('.//{'+IMAGE+'}image')), 4)
            # Rebuild without new articles expires the old entry.
            write_discovery_sitemaps(root, [base], datetime(2026,11,13,3,tzinfo=timezone.utc))
            self.assertEqual(ET.parse(root/'news-sitemap.xml').findall('{'+SM+'}url'), [])
        date_only = dict(base,published_at_time=None)
        self.assertEqual(news_publication(date_only, clock), '2026-11-10')
        self.assertIsNone(news_publication(dict(base,published_at_time='2026-11-10T12:00:00'), clock))
        self.assertIsNone(news_publication(dict(base,published_at_time='2026-11-09T12:00:00Z'), clock))


if __name__ == '__main__':
    unittest.main()
