import copy
import unittest
from unittest.mock import patch
from scripts import publish_social as p
from scripts.security_watch import security_feed
from scripts.verify_deployed_revision import safe_drift
from scripts.reconcile_social_recovery import may_retry_story, save_verified
from datetime import datetime, timezone


class MemoryLedger:
    def __init__(self, rows=None):
        self.rows = copy.deepcopy(rows or {})
    def read(self):
        return self.rows, "sha"
    def record(self, aid, kind, status, **metadata):
        self.rows.setdefault(aid, {})[kind] = {"status": status, **metadata}


class DeliveryReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.article = {"id": "fresh-test", "title": "Reviewed news", "summary": "Reviewed facts",
                        "status": "published", "score": 90, "social_publish": True,
                        "source_url": "https://example.com/official", "published_at": "2026-10-28"}
        self.credentials = {"SOCIAL_PUBLISH_ENABLED": "true", "THREADS_ACCESS_TOKEN": "t", "THREADS_USER_ID": "1",
                            "INSTAGRAM_ACCESS_TOKEN": "i", "INSTAGRAM_USER_ID": "2"}

    def test_threads_only_ignores_missing_instagram_credentials(self):
        a = {**self.article, "social_platforms": ["threads"]}
        c = {k: v for k, v in self.credentials.items() if not k.startswith("INSTAGRAM")}
        with patch.object(p, "verify_account", return_value={}) as account, patch.object(p, "verify_live"), \
             patch.object(p, "publish_threads", return_value="123"), patch.object(p, "instagram_budget") as quota:
            self.assertEqual(p.run([a], MemoryLedger(), c), 0)
        self.assertEqual(account.call_count, 1)
        quota.assert_not_called()

    def test_instagram_failure_does_not_stop_threads(self):
        with patch.object(p, "verify_account", side_effect=[{}, RuntimeError("Instagram authentication unavailable")]), \
             patch.object(p, "verify_live"), patch.object(p, "publish_threads", return_value="123") as publish:
            ledger = MemoryLedger()
            self.assertEqual(p.run([self.article], ledger, self.credentials), 1)
            self.assertEqual(ledger.rows["fresh-test"]["threads"]["status"], "published")
            publish.assert_called_once()

    def test_existing_review_is_reported_as_incomplete_without_retry(self):
        a = {**self.article, "social_platforms": ["threads"]}
        with patch.object(p, "verify_account") as account, patch.object(p, "publish_threads") as publish:
            self.assertEqual(p.run([a], MemoryLedger({a["id"]: {"threads": {"status": "needs_review"}}}), self.credentials), 1)
        account.assert_not_called()
        publish.assert_not_called()

    def test_expired_review_does_not_invalidate_completed_posts(self):
        a = {**self.article, "social_platforms": ["threads"], "social_review_valid_until": "2000-01-01T00:00:00+00:00"}
        ledger = MemoryLedger({a["id"]: {"threads": {"status": "published", "remote_id": "1"}}})
        with patch.object(p, "verify_account") as account:
            self.assertEqual(p.run([a], ledger, self.credentials), 0)
        account.assert_not_called()

    def test_quota_reserves_each_instagram_medium_and_keeps_threads_moving(self):
        ledger = MemoryLedger()
        with patch.object(p, "verify_account", return_value={"account_type": "BUSINESS"}), patch.object(p, "verify_live"), \
             patch.object(p, "instagram_budget", return_value=1), patch.object(p, "publish_threads", return_value="11"), \
             patch.object(p, "publish_instagram", return_value="22") as feed, patch.object(p, "publish_instagram_story") as story:
            self.assertEqual(p.run([self.article], ledger, self.credentials), 1)
        feed.assert_called_once()
        story.assert_not_called()
        self.assertEqual(ledger.rows["fresh-test"]["instagram_story"]["status"], "deferred")

    def test_action_block_stops_all_further_instagram_writes_in_the_run(self):
        ledger = MemoryLedger()
        error = p.MetaAPIError(403, {"code": 4, "error_subcode": 2207051})
        with patch.object(p, "verify_account", return_value={"account_type": "BUSINESS"}), patch.object(p, "verify_live"), \
             patch.object(p, "instagram_budget", return_value=10), patch.object(p, "publish_threads", return_value="11"), \
             patch.object(p, "publish_instagram", side_effect=error) as feed, patch.object(p, "publish_instagram_story") as story:
            self.assertEqual(p.run([self.article, {**self.article, "id": "second"}], ledger, self.credentials), 1)
        self.assertEqual(feed.call_count, 1)
        story.assert_not_called()
        self.assertEqual(ledger.rows["fresh-test"]["threads"]["status"], "published")

    def test_existing_action_block_keeps_instagram_paused_but_allows_threads(self):
        ledger = MemoryLedger({"old": {"instagram": {"status": "needs_review", "error": {"code": 4, "subcode": 2207051}}}})
        with patch.object(p, "verify_account", return_value={}) as account, patch.object(p, "verify_live"), \
             patch.object(p, "publish_threads", return_value="11"), patch.object(p, "publish_instagram") as feed, \
             patch.object(p, "instagram_budget") as budget:
            self.assertEqual(p.run([self.article], ledger, self.credentials), 1)
        self.assertEqual(account.call_count, 1)
        budget.assert_not_called()
        feed.assert_not_called()

    def test_2207042_is_deferred_but_ambiguous_publish_is_never_retried(self):
        for error, expected in ((p.MetaAPIError(400, {"code": 9, "error_subcode": 2207042}), "deferred"),
                                (RuntimeError("API transport timeout"), "needs_review")):
            with self.subTest(expected=expected), patch.object(p, "verify_account", return_value={"account_type": "BUSINESS"}), \
                 patch.object(p, "verify_live"), patch.object(p, "instagram_budget", return_value=10), \
                 patch.object(p, "publish_instagram", side_effect=error):
                a = {**self.article, "social_platforms": ["instagram"]}
                ledger = MemoryLedger()
                self.assertEqual(p.run([a], ledger, self.credentials), 1)
                self.assertEqual(ledger.rows[a["id"]]["instagram"]["status"], expected)
                self.assertNotIn("instagram", p.remaining_platforms(ledger.rows[a["id"]]))

    def test_only_due_deferred_work_is_eligible(self):
        for date, included in (("2000-01-01T00:00:00+00:00", True), ("2099-01-01T00:00:00+00:00", False)):
            self.assertEqual("instagram" in p.remaining_platforms({"instagram": {"status": "deferred", "next_attempt_at": date}}), included)
        with self.assertRaises(RuntimeError):
            p.remaining_platforms({"instagram": {"status": "deferred"}})

    def test_only_ledger_changes_can_drift_from_deployed_revision(self):
        self.assertTrue(safe_drift([".github/social-post-ledger.json"]))
        self.assertFalse(safe_drift(["data/articles.json"]))
        self.assertFalse(safe_drift(["scripts/publish_social.py"]))

    def test_reviewed_security_article_registers_itself_once(self):
        a = {**self.article, "social_security_severity": "HIGH", "social_security_product": "Reviewed product"}
        result = security_feed([a], [])
        self.assertEqual(result[0]["article_id"], a["id"])
        self.assertEqual(len(security_feed([a], result)), 1)
        with self.assertRaises(ValueError):
            security_feed([{**a, "social_security_product": ""}], [])

    def test_security_exclusion_requires_reason(self):
        a = {**self.article, "security_watch": False}
        with self.assertRaises(ValueError):
            security_feed([a], [])
        self.assertEqual(security_feed([{**a, "security_watch_exclusion_reason": "Duplicate coverage"}], []), [])

    def test_story_recovery_requires_recent_attempt_and_verified_image_absence(self):
        current = datetime(2026, 10, 28, 0, 0, tzinfo=timezone.utc)
        proof = {"absence_verified": True, "matching_ids": []}
        self.assertTrue(may_retry_story({"updated_at": "2026-10-27T23:00:00+00:00"}, proof, current))
        self.assertFalse(may_retry_story({"updated_at": "2026-10-26T23:00:00+00:00"}, proof, current))
        self.assertFalse(may_retry_story({"updated_at": "2026-10-27T23:00:00+00:00"}, {}, current))
        self.assertFalse(may_retry_story({"updated_at": "2026-10-28T01:00:00+00:00"}, proof, current))

    def test_reconciliation_cannot_overwrite_published_or_changed_history(self):
        ledger = MemoryLedger({"a": {"threads": {"status": "published", "remote_id": "1"}}})
        with self.assertRaises(RuntimeError):
            save_verified(ledger, "a", "threads", {"status": "needs_review"}, {"status": "deferred"})


if __name__ == "__main__":
    unittest.main()
