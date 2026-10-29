import json
import unittest
from unittest.mock import patch

from scripts.publish_social import (
    approved_articles, article_url, image_url, story_image_url, threads_text,
    instagram_text, GithubLedger, remaining_platforms, run, verify_account, main,
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

    def test_one_request_threads_text_publishing_has_explicit_canonical_link(self):
        from scripts.publish_social import publish_threads
        article = {**self.story, "social_publish": True}
        permalink = article_url(article)
        observed = []
        with patch("scripts.publish_social.request_json", return_value={"id": "18123456789000000"}) as api:
            posted = publish_threads(threads_text(article), "test-token", "12345",
                                     progress=lambda stage, value: observed.append((stage, value)),
                                     link_attachment=permalink)
        self.assertEqual(posted, "18123456789000000")
        api.assert_called_once()
        args, kwargs = api.call_args
        self.assertTrue(args[0].endswith("/12345/threads"))
        self.assertEqual(kwargs["method"], "POST")
        self.assertEqual(kwargs["data"]["link_attachment"], permalink)
        self.assertEqual(kwargs["data"]["auto_publish_text"], "true")
        self.assertEqual(kwargs["data"]["media_type"], "TEXT")
        self.assertEqual(observed, [("publish_requested", posted)])
        with self.assertRaises(ValueError):
            publish_threads("x", "test-token", "12345", link_attachment="https://other.example/test")

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
                  return_value={"username": "work_signal_japan", "user_id": "1784", "account_type": "BUSINESS"}),
            patch("scripts.publish_social.verify_live") as check_asset,
            patch("scripts.publish_social.instagram_budget", return_value=10),
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

    def test_unknown_or_malformed_history_never_becomes_a_new_post(self):
        for existing in (None, [], {"threads": None}, {"threads": {}},
                         {"threads": {"status": "unknown", "remote_id": "123"}}):
            with self.subTest(existing=existing), self.assertRaises(RuntimeError):
                remaining_platforms(existing)

    def test_missing_ledger_is_not_silently_reinitialized(self):
        with patch("scripts.publish_social.request_json", side_effect=RuntimeError("API HTTP 404")):
            with self.assertRaisesRegex(RuntimeError, "ledger missing"):
                GithubLedger("test/repo", "dummy-token").read()

    def test_unknown_history_cannot_be_overwritten_by_a_claim(self):
        ledger = GithubLedger("test/repo", "dummy-token")
        with patch.object(ledger, "read", return_value=({"id": {"threads": {"status": "unknown"}}}, "sha")), \
             patch("scripts.publish_social.urlopen") as write:
            with self.assertRaisesRegex(RuntimeError, "Unknown publication state"):
                ledger.record("id", "threads", "attempting")
            write.assert_not_called()

    def test_missing_credentials_fail_an_enabled_live_run_without_posts(self):
        article = {**self.story, "social_publish": True}
        with patch("scripts.publish_social.verify_account") as verify:
            self.assertEqual(run([article], None, {"SOCIAL_PUBLISH_ENABLED": "true"}), 1)
            verify.assert_not_called()

    def test_live_command_with_missing_credentials_returns_failure_before_ledger_access(self):
        with patch.dict("os.environ", {"SOCIAL_PUBLISH_ENABLED": "true"}, clear=True), \
             patch("sys.argv", ["publish_social.py", "--live"]), \
             patch("scripts.publish_social.Path.read_text", return_value=json.dumps([{**self.story, "social_publish": True}])), \
             patch("scripts.publish_social.GithubLedger") as ledger:
            self.assertEqual(main(), 1)
            ledger.assert_not_called()

    def test_missing_or_mismatched_account_id_is_rejected(self):
        for profile in ({"username": "work_signal_japan"},
                        {"username": "work_signal_japan", "id": "456"}):
            with patch("scripts.publish_social.request_json", return_value=profile):
                with self.assertRaisesRegex(RuntimeError, "Account ID mismatch"):
                    verify_account("https://graph.threads.net/v1.0", "dummy-token", "123")

    def test_safety_limit_reports_unprocessed_articles_without_exceeding_five(self):
        articles = [{**self.story, "id": "approved-" + str(i), "social_publish": True}
                    for i in range(6)]
        class Ledger:
            def __init__(self):
                self.rows = {}
            def read(self):
                return self.rows, "sha"
            def record(self, identifier, platform, status, **kwargs):
                self.rows.setdefault(identifier, {})[platform] = {"status": status}
        ledger = Ledger()
        credentials = {key: "123" for key in ("THREADS_ACCESS_TOKEN", "THREADS_USER_ID",
                       "INSTAGRAM_ACCESS_TOKEN", "INSTAGRAM_USER_ID")}
        credentials["SOCIAL_PUBLISH_ENABLED"] = "true"
        with patch("scripts.publish_social.verify_account", return_value={"account_type": "BUSINESS"}), \
             patch("scripts.publish_social.instagram_budget", return_value=50), \
             patch("scripts.publish_social.verify_live"), \
             patch("scripts.publish_social.publish_threads", return_value="1") as threads, \
             patch("scripts.publish_social.publish_instagram", return_value="2"), \
             patch("scripts.publish_social.publish_instagram_story", return_value="3"):
            self.assertEqual(run(articles, ledger, credentials), 1)
            self.assertEqual(threads.call_count, 5)
            self.assertEqual(len(ledger.rows), 5)


if __name__ == "__main__":
    unittest.main()

