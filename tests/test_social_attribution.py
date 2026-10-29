import importlib.util
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import unittest
spec=importlib.util.spec_from_file_location('social_tracking',Path(__file__).resolve().parents[1]/'scripts/publish_social.py')
social=importlib.util.module_from_spec(spec)
spec.loader.exec_module(social)

class AttributionTests(unittest.TestCase):
    def setUp(self):
        self.article={'id':'20261026-example','title':'Example','summary':'A short useful summary','source_url':'https://example.org/original'}
    def test_thread_url_identifies_article_and_preserves_canonical_preflight(self):
        url=social.tracked_article_url(self.article)
        self.assertEqual(parse_qs(urlparse(url).query)['utm_content'],[self.article['id']])
        self.assertEqual(social.article_url(self.article),'https://signal.amberlight.co.jp/articles/20261026-example/')
        text=social.threads_text(self.article)
        self.assertIn(social.article_url(self.article), text)
        self.assertNotIn('?utm_source=', text)
        self.assertTrue(text.endswith(self.article['source_url']))
        self.assertLessEqual(len(text),500)
    def test_custom_approved_copy_is_not_rewritten_and_can_include_tracking(self):
        original='My approved wording\n'+social.article_url(self.article)+'\n'+self.article['source_url']
        text=social.threads_text({**self.article,'social_threads_text':original})
        self.assertTrue(text.startswith('My approved wording\n'))
        self.assertEqual(text,original)
        self.assertTrue(text.endswith(self.article['source_url']))
        self.assertEqual(social.threads_text({**self.article,'social_threads_text':text}),text)
        tracked=original.replace(social.article_url(self.article),social.tracked_article_url(self.article))
        self.assertEqual(social.threads_text({**self.article,'social_threads_text':tracked}),tracked)

if __name__=='__main__':unittest.main()
