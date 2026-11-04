import unittest
from unittest.mock import patch
from scripts import publish_social as p
from scripts.audit_social_delivery import collect as real_collect
from tests.test_instagram_feed_probe import Ledger


class InstagramDeliveryConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.a = {"id": "reviewed-feed", "title": "Reviewed news title", "summary": "Verified facts",
                  "status": "published", "score": 90, "social_publish": True,
                  "source_url": "https://example.com/official", "social_platforms": ["instagram"]}
        self.credentials = {"SOCIAL_PUBLISH_ENABLED": "true", "INSTAGRAM_ACCESS_TOKEN": "test-token",
                            "INSTAGRAM_USER_ID": "123"}
        self.live = {"id": "456", "caption": p.instagram_text(self.a),
                     "media_product_type": "FEED", "permalink": "https://www.instagram.com/p/verified/"}
        self.ledger = Ledger()
        self.elapsed = 0
        for name, value in (("verify_account", {"account_type": "BUSINESS"}),
                            ("verify_live", None), ("instagram_budget", 99)):
            patcher = patch.object(p, name, return_value=value)
            patcher.start(); self.addCleanup(patcher.stop)
        patcher = patch.object(p.time, "sleep", side_effect=self.tick)
        patcher.start(); self.addCleanup(patcher.stop)
        patcher = patch("scripts.audit_social_delivery.collect", return_value=([self.live], True))
        self.history = patcher.start(); self.addCleanup(patcher.stop)
        patcher = patch.object(p, "publish_instagram", side_effect=self.publish)
        self.send = patcher.start(); self.addCleanup(patcher.stop)
        patcher = patch("builtins.print"); patcher.start(); self.addCleanup(patcher.stop)
        self.error = None

    def tick(self, seconds):
        self.elapsed += seconds

    def publish(self, *args, **kwargs):
        kwargs["progress"]("container_created", "789")
        kwargs["progress"]("publish_requested", "789")
        if self.error:
            raise self.error
        return "456"

    def run_delivery(self):
        return p.run([self.a], self.ledger, self.credentials)

    def test_403_with_actual_post_is_published_and_hold_survives(self):
        self.error = p.MetaAPIError(403, {"code":4, "error_subcode":2207051,
            "fbtrace_id":"trace_12345", "is_transient":False})
        self.assertEqual(self.run_delivery(), 0)
        entry = self.ledger.rows[self.a["id"]]["instagram"]
        self.assertEqual(entry["status"], "published")
        self.assertEqual(entry["remote_id"], "456")
        self.assertEqual(entry["error"]["subcode"], 2207051)
        self.assertTrue(p.active_instagram_action_block(entry))
        self.assertEqual(self.run_delivery(), 0)
        self.send.assert_called_once()

    def test_success_id_missing_from_history_is_not_published(self):
        self.history.return_value = ([], True)
        self.assertEqual(self.run_delivery(), 1)
        self.assertEqual(self.ledger.rows[self.a["id"]]["instagram"]["status"], "needs_review")
        self.assertEqual(self.run_delivery(), 1)
        self.send.assert_called_once()

    def test_success_id_mismatch_is_not_substituted(self):
        self.history.return_value = ([{**self.live, "id": "999"}], True)
        self.assertEqual(self.run_delivery(), 1)
        self.assertEqual(self.ledger.rows[self.a["id"]]["instagram"]["status"], "needs_review")

    def test_title_only_candidate_never_confirms_a_post(self):
        self.history.return_value = ([{**self.live, "caption": self.a["title"] + " / a different article"}], True)
        self.assertEqual(self.run_delivery(), 1)
        self.assertEqual(self.ledger.rows[self.a["id"]]["instagram"]["status"], "needs_review")

    def test_delayed_appearance_after_60_seconds_never_resends(self):
        self.error = RuntimeError("Publish response lost")
        self.history.side_effect = lambda *a, **kw: ([self.live] if self.elapsed >= 60 else [], True)
        self.assertEqual(self.run_delivery(), 0)
        self.assertGreaterEqual(self.elapsed, 60)
        self.assertLessEqual(self.elapsed, 120)
        self.send.assert_called_once()

    def test_incomplete_or_duplicate_history_remains_uncertain(self):
        for result in (([self.live], False), ([self.live, {**self.live, "id":"999"}], True)):
            with self.subTest(result=result):
                self.ledger = Ledger()
                self.history.return_value = result
                self.assertEqual(self.run_delivery(), 1)
                self.assertEqual(self.ledger.rows[self.a["id"]]["instagram"]["status"], "needs_review")

    def test_failure_before_publish_boundary_does_not_confirm_unrelated_history(self):
        self.send.side_effect = RuntimeError("Container create failed")
        self.assertEqual(self.run_delivery(), 1)
        self.history.assert_not_called()
        self.assertEqual(self.ledger.rows[self.a["id"]]["instagram"]["status"], "needs_review")

    def test_process_exit_after_claim_is_never_rearmed(self):
        self.send.side_effect = SystemExit("Simulated runner termination")
        with self.assertRaises(SystemExit):
            self.run_delivery()
        self.assertEqual(self.ledger.rows[self.a["id"]]["instagram"]["status"], "attempting")
        self.assertEqual(self.run_delivery(), 1)
        self.send.assert_called_once()

    def test_story_success_uses_exact_id_not_empty_caption(self):
        self.a["social_platforms"] = ["instagram_story"]
        self.history.return_value = ([{"id":"999", "caption":"", "media_product_type":"STORY"}], True)
        with patch.object(p, "publish_instagram_story", return_value="456") as send:
            self.assertEqual(self.run_delivery(), 1)
        self.assertEqual(self.ledger.rows[self.a["id"]]["instagram_story"]["status"], "needs_review")
        send.assert_called_once()

    def test_story_success_requires_its_returned_id_in_owned_stories(self):
        self.a["social_platforms"] = ["instagram_story"]
        self.history.return_value = ([{"id":"456", "caption":""}], True)
        with patch.object(p, "publish_instagram_story", return_value="456") as send:
            self.assertEqual(self.run_delivery(), 0)
        self.assertEqual(self.ledger.rows[self.a["id"]]["instagram_story"]["status"], "published")
        self.assertTrue(self.history.call_args.args[1].endswith("/stories"))
        send.assert_called_once()

    def test_protective_error_confirmed_as_published_still_blocks_the_next_feed(self):
        self.error = p.MetaAPIError(400, {"code":4, "error_subcode":2207051})
        other = {**self.a, "id":"other-feed"}
        # Oldest-first ordering makes the original article the first write.
        self.assertEqual(p.run([other, self.a], self.ledger, self.credentials), 1)
        self.send.assert_called_once()
        self.assertNotIn(other["id"], self.ledger.rows)

    def test_unknown_publication_reserves_quota_before_the_next_medium(self):
        self.a["social_platforms"] = ["instagram", "instagram_story"]
        self.error = RuntimeError("Publish response lost")
        self.history.return_value = ([], True)
        with patch.object(p, "instagram_budget", return_value=1), \
             patch.object(p, "publish_instagram_story") as send:
            self.assertEqual(self.run_delivery(), 1)
        send.assert_not_called()
        self.assertEqual(self.ledger.rows[self.a["id"]]["instagram_story"]["status"], "deferred")

    def test_confirmation_is_get_only(self):
        # Exercise the real paginated reader, with a transport mock that rejects writes.
        def get_only(url, **kwargs):
            self.assertEqual(kwargs.get("method", "GET"), "GET")
            self.assertIsNone(kwargs.get("data"))
            return {"data":[self.live]}
        with patch("scripts.audit_social_delivery.collect", wraps=real_collect), \
             patch.object(p, "request_json", side_effect=get_only) as api:
            found = p.verify_instagram_delivery(self.a, "test-token", "123", expected_id="456")
        self.assertEqual(found["id"], "456")
        api.assert_called_once()


class InstagramMatchIdentityTests(unittest.TestCase):
    def setUp(self):
        self.a = {"id":"exact-article", "title":"Shared title", "summary":"Facts"}

    def test_article_url_must_match_the_complete_path(self):
        url = p.article_url(self.a)
        for caption in (url + "different/", url.replace("signal.amberlight.co.jp", "signal.amberlight.co.jp.evil.example")):
            self.assertEqual(p.instagram_feed_matches(self.a, [{"id":"1", "caption":caption}]), [])
        self.assertEqual(p.instagram_feed_matches(self.a, [{"id":"2", "caption":url + "?utm_source=instagram"}])[0]["id"], "2")

    def test_title_alone_is_not_identity(self):
        self.assertEqual(p.instagram_feed_matches(self.a, [{"id":"1", "caption":"Shared title / another post"}]), [])


if __name__ == "__main__":
    unittest.main()
