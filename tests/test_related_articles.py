"""Regression cases for reader intent and safe related-link selection."""
import unittest
from scripts.related_articles import related_articles
from scripts.build_site import archive_page, ROOT

def article(identifier, title, **kw):
    return dict(id=identifier, title=title, summary='', category='SECURITY',
                status=kw.pop('status', 'published'), score=kw.pop('score', 90),
                published_at=kw.pop('published_at', '2026-10-01'),
                source_url=kw.pop('source_url', 'https://example.com/'), **kw)

class RelatedArticlesTests(unittest.TestCase):
    def test_generic_security_words_do_not_link_unrelated_products(self):
        first = article('alpha', 'Alphaに重大脆弱性、修正版と更新を確認')
        second = article('beta', 'Betaに重大脆弱性、修正版と更新を確認')
        self.assertEqual(related_articles(first, [first, second]), [])

    def test_same_product_followup_beats_newer_unrelated_story(self):
        first = article('old', 'undiciのHTTP通信を確認')
        follow = article('follow', 'undiciに追加修正', published_at='2026-10-02')
        unrelated = article('new', '別製品に重大脆弱性', published_at='2026-10-30')
        self.assertEqual([x['id'] for x in related_articles(first, [unrelated, first, follow])], ['follow'])

    def test_shared_cve_can_cross_categories(self):
        first = article('tech', 'BunのBrotli修正')
        first['summary'] = 'CVE-2026-111497の修正'
        second = article('guide', '圧縮ライブラリの基礎')
        second['category'] = '仕事'
        second['summary'] = 'CVE-2026-111497を点検'
        self.assertEqual([x['id'] for x in related_articles(first, [first, second])], ['guide'])

    def test_editorial_order_safe_targets_and_no_duplicates(self):
        first = article('a', '本文', related_article_ids=['missing', 'draft', 'low', 'a', 'c', 'c', 'b'])
        b, c = article('b', '基礎'), article('c', '続報', published_at='2026-10-02')
        draft, low = article('draft', '非公開', status='draft'), article('low', '低スコア', score=79)
        self.assertEqual([x['id'] for x in related_articles(first, [first, b, c, draft, low])], ['c', 'b'])

    def test_unscored_special_stories_keep_existing_publication_rules(self):
        first = article('normal', '管理職のマネジメント')
        special = article('special', '管理職の基礎', score=None, format='special_story')
        self.assertEqual([x['id'] for x in related_articles(first, [first, special])], ['special'])

    def test_editorial_links_provide_a_return_path(self):
        guide = article('guide', '事故情報の調べ方')
        news = article('news', 'サイバー攻撃の事例', related_article_ids=['guide'])
        self.assertEqual([x['id'] for x in related_articles(guide, [guide, news])], ['news'])

    def test_source_repository_matches_product_without_guessing_category(self):
        one = article('one', '仕様変更の解説', source_url='https://github.com/acme/tool/security/advisories/GHSA-abcd')
        two = article('two', '新バージョン', source_url='https://github.com/acme/tool/releases/tag/v2')
        self.assertEqual([x['id'] for x in related_articles(one, [one, two])], ['two'])

    def test_reference_urls_do_not_create_spurious_product_matches(self):
        first = article('a', 'Alphaの仕様', sections=[{'body': '参考 https://example.com/undici/bun/brotli'}])
        second = article('b', 'Bunの使い方')
        self.assertEqual(related_articles(first, [first, second]), [])

    def test_archive_analytics_reuses_existing_configuration_once(self):
        template = (ROOT / 'index.html').read_text()
        page = archive_page([article('a', 'テスト')], 1, template)
        self.assertEqual(page.count('googletagmanager.com/gtag/js?id=G-X4B5F6JJZH'), 1)
        self.assertEqual(page.count("gtag('config', 'G-X4B5F6JJZH'"), 1)
        self.assertIn("cookie_prefix: 'work_signal'", page)
        self.assertNotIn('adsbygoogle.js', page)

if __name__ == '__main__':
    unittest.main()
