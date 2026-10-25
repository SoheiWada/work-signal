import unittest
from unittest.mock import patch

from scripts.publish_social import (
    approved_articles, article_url, image_url, story_image_url, threads_text,
    instagram_text, GithubLedger, remaining_platforms, run,
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


    def test_three_distinct_platforms_and_never_retry_ambiguous_results(self):
        self.assertEqual(remaining_platforms({}),
                         ["threads", "instagram", "instagram_story"])
        current = {
            "threads": {"status": "published"},
            "instagram": {"status": "needs_review"},
            "instagram_story": {"status": "attempting"},
        }
        self.assertEqual(remaining_platforms(current), [])
        self.assertEqual(remaining_platforms({
            "threads": {"status": "published"},
            "instagram": {"status": "published"},
        }), ["instagram_story"])
        self.assertTrue(story_image_url(self.story).endswith("/20261026-approved-test.jpg"))

    def test_only_unposted_story_runs_and_existing_posts_stay_untouched(self):
        class Ledger:
            def __init__(self, article_id):
                self.rows = {article_id: {
                    "threads": {"status": "published", "remote_id": "1"},
                    "instagram": {"status": "published", "remote_id": "2"},
                }}
                self.changes = []

            def read(self):
                return self.rows, "blob"

            def record(self, identifier, platform, status, remote_id="", permalink=""):
                self.changes.append((identifier, platform, status))
                self.rows.setdefault(identifier, {})[platform] = {
                    "status": status, "remote_id": remote_id,
                }

        article = {**self.story, "social_publish": True}
        ledger = Ledger(article["id"])
        credentials = {
            "SOCIAL_PUBLISH_ENABLED": "true",
            "THREADS_ACCESS_TOKEN": "threads-token",
            "THREADS_USER_ID": "123",
            "INSTAGRAM_ACCESS_TOKEN": "ig-token",
            "INSTAGRAM_USER_ID": "1784",
        }
        with (
            patch("scripts.publish_social.verify_account",
                  side_effect=[{"username": "work_signal_japan", "id": "123"},
                               {"username": "work_signal_japan",
                                "user_id": "1784", "account_type": "BUSINESS"}]),
            patch("scripts.publish_social.verify_live") as check_asset,
            patch("scripts.publish_social.publish_threads") as threads_post,
            patch("scripts.publish_social.publish_instagram") as feed_post,
            patch("scripts.publish_social.publish_instagram_story",
                  return_value="story-remote") as story_post,
        ):
            self.assertEqual(run([article], ledger, credentials), 0)
        threads_post.assert_not_called()
        feed_post.assert_not_called()
        story_post.assert_called_once_with(
            story_image_url(article), credentials["INSTAGRAM_ACCESS_TOKEN"],
            credentials["INSTAGRAM_USER_ID"])
        self.assertEqual(check_asset.call_count, 2)
        self.assertEqual([x[1:] for x in ledger.changes],
                         [("instagram_story", "attempting"),
                          ("instagram_story", "published")])
        self.assertEqual(ledger.rows[article["id"]]["threads"]["remote_id"], "1")
        self.assertEqual(ledger.rows[article["id"]]["instagram"]["remote_id"], "2")
        with patch("scripts.publish_social.verify_account") as verify:
            self.assertEqual(run([article], ledger, credentials), 0)
            verify.assert_not_called()

    def test_story_asset_not_sent_when_disabled(self):
        article = {**self.story, "social_publish": True}
        class NoNetworkLedger:
            def read(self):
                raise AssertionError("Disabled publishing must never touch GitHub ledger")
        credentials = {"SOCIAL_PUBLISH_ENABLED": "false"}
        self.assertEqual(run([article], NoNetworkLedger(), credentials), 0)


if __name__ == "__main__":
    unittest.main()
