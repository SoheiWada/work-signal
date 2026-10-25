import unittest

from scripts.publish_social import (
    approved_articles, article_url, image_url, threads_text, instagram_text, GithubLedger,
)


class SocialPublisherTests(unittest.TestCase):
    def setUp(self):
        self.story = {
            "id": "20261026-approved-test",
            "title": "働く人のための新しい情報",
            "summary": "公式発表を読み解き、働く人への影響を分かりやすく解説します。",
            "category": "仕事",
            "format": "deep_dive",
            "score": 85,
            "source_url": "https://example.com/official",
            "status": "published",
        }

    def test_old_articles_never_post(self):
        self.assertEqual(approved_articles([self.story]), [])
        self.assertEqual(approved_articles([{**self.story, "social_publish": False}]), [])
        self.assertEqual(approved_articles([{**self.story, "social_publish": "true"}]), [])
        self.assertEqual(approved_articles([{**self.story, "social_publish": True, "status": "draft"}]), [])
        self.assertEqual(approved_articles([{**self.story, "social_publish": True, "score": 79}]), [])

    def test_explicit_approval_generates_safe_captions(self):
        approved = {**self.story, "social_publish": True}
        self.assertEqual(approved_articles([approved]), [approved])
        text = threads_text(approved)
        self.assertIn(article_url(approved), text)
        self.assertTrue(text.endswith(self.story["source_url"]))
        self.assertLessEqual(len(text), 500)
        self.assertIn("プロフィール", instagram_text(approved))
        self.assertTrue(image_url(approved).endswith(".jpg"))

    def test_manual_copy_requires_primary_source_at_end(self):
        article = {**self.story, "social_publish": True}
        copy = "公式発表を解説しました。\n" + article_url(article) + "\n" + article["source_url"]
        self.assertEqual(threads_text({**article, "social_threads_text": copy}), copy)
        with self.assertRaises(ValueError):
            threads_text({**article, "social_threads_text": "URLなしの文章"})
        with self.assertRaises(ValueError):
            instagram_text({**article, "social_instagram_caption": "x" * 2201})

    def test_unsafe_id_fails_closed(self):
        with self.assertRaises(ValueError):
            approved_articles([{**self.story, "social_publish": True, "id": "../unauthorized"}])

    def test_ledger_validates_arguments_before_any_network(self):
        ledger = GithubLedger("test/repo", "dummy-token")
        with self.assertRaises(ValueError):
            ledger.record("id", "youtube", "attempting")
        with self.assertRaises(ValueError):
            ledger.record("id", "threads", "retry")


if __name__ == "__main__":
    unittest.main()
