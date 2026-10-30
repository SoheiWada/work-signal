import copy
import json
import tempfile
import unittest
from pathlib import Path
from html.parser import HTMLParser
from scripts import build_site as site
from scripts.topic_catalog import TOPICS, active_topics, topic_articles, article_topics

class Document(HTMLParser):
    def __init__(self, source):
        super().__init__(); self.tags=[]; self.feed(source)
    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

class TopicPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.feed=site.published_articles(json.loads((site.ROOT/'data/articles.json').read_text()))
        cls.template=(site.ROOT/'index.html').read_text()

    def test_reading_paths_never_include_unpublished_or_low_score_articles(self):
        actual=next(a for a in self.feed if a['id']=='20261021-jp-incident-monitor-cyber-risk-management')
        draft=dict(actual,id='draft-incident',status='draft',title='PRIVATE DRAFT')
        low=dict(actual,id='low-incident',score=79,title='LOW SCORE')
        topic=next(t for t in TOPICS if t['id']=='security-practice')
        result=topic_articles(topic,[draft,low,actual])
        self.assertEqual([a['id'] for a in result],[actual['id']])

    def test_curated_foundation_survives_newer_articles_and_source_is_not_mutated(self):
        topic=TOPICS[0]
        original=copy.deepcopy(self.feed)
        selected=topic_articles(topic,self.feed)
        self.assertLessEqual(len(selected),12)
        self.assertEqual(selected[0]['id'],topic['steps'][0]['articles'][0])
        self.assertEqual(self.feed,original)
        self.assertEqual(len({a['id'] for a in selected}),len(selected))

    def test_guides_have_distinct_canonical_metadata_and_crawlable_articles(self):
        urls=set()
        for topic in active_topics(self.feed):
            page=site.topic_page(topic,self.feed,self.template)
            doc=Document(page)
            url=site.topic_url(topic);urls.add(url)
            self.assertEqual([a['href'] for t,a in doc.tags if t=='link' and a.get('rel')=='canonical'],[url])
            self.assertEqual(sum(t=='h1' for t,a in doc.tags),1)
            self.assertIn('name="description"',page)
            self.assertIn('"@type": "CollectionPage"',page)
            self.assertIn('"@type": "BreadcrumbList"',page)
            self.assertIn('og:site_name',page)
            self.assertIn('G-X4B5F6JJZH',page)
            self.assertNotIn('adsbygoogle.js',page)
            self.assertNotIn('utm_source',page)
            for article in topic_articles(topic,self.feed):
                self.assertIn('href="'+site.article_url(article)+'"',page)
        self.assertEqual(len(urls),len(active_topics(self.feed)))

    def test_topic_index_links_to_all_active_guides(self):
        page=site.topic_page(None,self.feed,self.template)
        for topic in active_topics(self.feed):
            self.assertIn('href="'+site.topic_url(topic)+'"',page)

    def test_article_topic_navigation_uses_the_existing_sidebar(self):
        article=next(a for a in self.feed if a['id']=='20261021-jp-incident-monitor-cyber-risk-management')
        page=site.article_page(article,(site.ROOT/'article.html').read_text(),topics=article_topics(article))
        self.assertIn('aria-label="関連テーマ"',page)
        self.assertIn('href="'+site.BASE+'topics/security-practice/"',page)
        self.assertIn('href="/#latest"',page)

if __name__=='__main__':
    unittest.main()
