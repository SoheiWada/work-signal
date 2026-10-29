import copy
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET
from PIL import Image
from scripts import build_site as site
from scripts.seo_metadata import modifications_from_snapshots, publications_from_snapshots, modification_date, article_modifications, latest_date

class SEOTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.feed=json.loads((site.ROOT/'data/articles.json').read_text())
        cls.template=(site.ROOT/'article.html').read_text()

    def test_modification_dates_ignore_reordering_scoring_and_unrelated_articles(self):
        a,b=copy.deepcopy([item for item in self.feed if item['published_at'] <= '2026-10-22'][:2])
        history=modifications_from_snapshots([
            ('2026-10-22T01:00:00Z',[a,b]),
            ('2026-10-22T02:00:00Z',[b,dict(a,score=a['score']-1)]),
            ('2026-10-22T03:00:00Z',[dict(b,summary=b['summary']+' 追記'),a])])
        self.assertEqual(history,{b['id']:'2026-10-22T12:00:00+09:00'})
        self.assertIsNone(modification_date(a,history))
        for invalid in ['2020-01-01','2026-10-22T12:00:00','invalid']:
            with self.assertRaises(ValueError): modification_date(dict(a,updated_at=invalid),{})
        self.assertEqual(latest_date(['2026-10-22T14:00:00+09:00','2026-10-22T06:00:00Z']),'2026-10-22T06:00:00Z')

    def test_first_git_registration_times_use_local_date_and_skip_backdates(self):
        snapshots = [
            ('2026-10-28T23:10:00Z', [
                {'id':'new-today','published_at':'2026-10-29','status':'published'},
                {'id':'old-backdated','published_at':'2026-10-27','status':'published'}
            ]),
            ('2026-10-29T02:11:00Z', [
                {'id':'new-today','published_at':'2026-10-29','status':'published'},
                {'id':'old-backdated','published_at':'2026-10-27','status':'published'}
            ])
        ]
        first = publications_from_snapshots(snapshots)
        self.assertEqual(first, {'new-today':'2026-10-29T08:10:00+09:00'})

    def test_category_only_reclassification_preserves_original_content_modification_time(self):
        security = next(item for item in self.feed if item['category'] == 'SECURITY')
        old = dict(security, category='仕事')
        history = modifications_from_snapshots([
            ('2026-10-28T01:00:00Z', [old]),
            ('2026-10-28T15:00:00Z', [security]),
        ])
        self.assertEqual(history, {})

    def test_all_published_articles_have_unique_canonical_and_complete_metadata(self):
        for article in site.published_articles(self.feed):
            with self.subTest(id=article['id']):
                page=site.article_page(article,self.template)
                self.assertEqual(page.count('<h1>'),1)
                self.assertIn('<link rel="canonical" href="'+site.article_url(article)+'">',page)
                self.assertIn('name="twitter:description" content="'+site.esc(article['summary']),page)
                self.assertNotIn('name="robots" content="noindex"',page)
                for section in article.get('sections',[]):
                    if section.get('title') and section.get('body'): self.assertIn('<h2>'+site.esc(section['title'])+'</h2>',page)
                schema=json.loads(re.search(r'application/ld\+json">(.*?)</script>',page).group(1))
                self.assertEqual(schema['datePublished'],article['published_at'])
                self.assertEqual(schema['publisher']['name'],'WORK SIGNAL')
                self.assertNotIn('dateModified',schema)
                self.assertNotIn('author',schema)
                related=site.related_articles(article,site.published_articles(self.feed))
                self.assertLessEqual(len(related),2)
                for item in related:
                    self.assertNotEqual(item['id'],article['id'])
                    self.assertEqual(item['category'],article['category'])

    def test_visible_schema_og_sitemap_dates_and_favicon_outputs_agree(self):
        article=next(item for item in self.feed if item['published_at'] <= '2026-10-22'); modified='2026-10-22T16:00:00+09:00'
        page=site.article_page(article,self.template,modified)
        self.assertIn('更新：<time datetime="'+modified+'">2026-10-22</time>',page)
        self.assertIn('"dateModified": "'+modified+'"',page)
        self.assertIn('property="article:modified_time" content="'+modified+'"',page)
        with tempfile.TemporaryDirectory() as temp,patch.object(site,'article_modifications',return_value={article['id']:modified}):
            output=Path(temp)/'site';site.build(output,[article])
            ns={'s':'http://www.sitemaps.org/schemas/sitemap/0.9'}
            dates={e.findtext('s:loc',namespaces=ns):e.findtext('s:lastmod',namespaces=ns) for e in ET.parse(output/'sitemap.xml').getroot().findall('s:url',ns)}
            self.assertEqual(dates[site.article_url(article)],modified)
            self.assertEqual(dates[site.BASE],modified)
            self.assertIsNone(dates[site.BASE+'about/'])
            for size in (96,192):
                with Image.open(output/('favicon-'+str(size)+'.png')) as image:
                    self.assertEqual(image.size,(size,size));self.assertEqual(image.format,'PNG')
            with Image.open(output/'favicon.ico') as image:
                self.assertTrue({(16,16),(32,32),(48,48),(96,96)}.issubset(image.ico.sizes()))

    def test_real_git_history_identifies_only_the_modified_article(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'data').mkdir()
            def git(*args,stamp='2026-10-22T01:00:00+00:00'):
                env=dict(os.environ,GIT_AUTHOR_NAME='SEO Test',GIT_AUTHOR_EMAIL='seo@example.invalid',GIT_COMMITTER_NAME='SEO Test',GIT_COMMITTER_EMAIL='seo@example.invalid',GIT_AUTHOR_DATE=stamp,GIT_COMMITTER_DATE=stamp)
                return subprocess.run(['git','-C',str(root),*args],check=True,capture_output=True,text=True,env=env)
            git('init');feed=copy.deepcopy([item for item in self.feed if item['published_at'] <= '2026-10-22'][:2]);(root/'data/articles.json').write_text(json.dumps(feed));git('add','data/articles.json');git('commit','-m','publish')
            feed[1]['summary']+=' 更新';(root/'data/articles.json').write_text(json.dumps(feed));git('add','data/articles.json');git('commit','-m','update second',stamp='2026-10-22T02:00:00+00:00')
            self.assertEqual(article_modifications(root),{feed[1]['id']:'2026-10-22T11:00:00+09:00'})
