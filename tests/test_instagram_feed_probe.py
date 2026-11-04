import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch
from scripts import publish_social as p


class Ledger:
    def __init__(self, rows=None):
        self.rows = copy.deepcopy(rows or {})
        self.calls = []

    def read(self):
        return copy.deepcopy(self.rows), "sha"

    def record(self, aid, kind, status, **metadata):
        self.calls.append((aid, kind, status))
        self.rows.setdefault(aid, {}).setdefault(kind, {}).update(
            status=status, updated_at=p.now(), **metadata)

    def progress(self, aid, kind, stage, cid):
        self.rows[aid][kind].update(stage=stage, container_id=cid)


class FeedProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.clock = datetime.now(timezone.utc)
        self.article = {"id": "probe-article", "status": "published", "social_publish": True,
            "score": 88, "title": "Reviewed article title", "summary": "Reviewed source facts",
            "source_url": "https://example.com/official", "social_platforms": ["threads"]}
        self.caption = "Individually reviewed caption. " + p.article_url(self.article)
        self.plan = {"request_id": "probe-request", "article_id": self.article["id"],
            "reviewed_at": (self.clock-timedelta(minutes=1)).isoformat(),
            "valid_until": (self.clock+timedelta(hours=1)).isoformat(),
            "authorization": "Owner approved one feed recovery test in this conversation.",
            "max_publish_calls": 1, "caption": self.caption, "source_url": self.article["source_url"]}
        self.credentials = {"INSTAGRAM_ACCESS_TOKEN": "SECRET", "INSTAGRAM_USER_ID": "123"}
        self.ledger = Ledger({"old": {"instagram": {"status": "published", "action_block_hold": True}}})
        self.live = {"id": "456", "caption": self.caption,
                     "timestamp": self.clock.isoformat(), "permalink": "https://www.instagram.com/p/test/"}
        for name, value in (("ROOT", Path(self.temp.name)),):
            patcher = patch.object(p, name, value); patcher.start(); self.addCleanup(patcher.stop)
        self.mocks = {}
        for name in ("verify_account", "instagram_budget", "verify_live", "publish_instagram"):
            patcher = patch.object(p, name); self.mocks[name] = patcher.start(); self.addCleanup(patcher.stop)
        self.mocks["instagram_budget"].return_value = 99
        self.mocks["publish_instagram"].return_value = "456"
        patcher = patch("scripts.audit_social_delivery.collect")
        self.collect = patcher.start(); self.addCleanup(patcher.stop)
        self.collect.side_effect = [([], True), ([self.live], True)]
        patcher = patch.object(p.time, "sleep"); patcher.start(); self.addCleanup(patcher.stop)
        patcher = patch("builtins.print"); patcher.start(); self.addCleanup(patcher.stop)

    def run_probe(self):
        return p.instagram_feed_probe([self.article], self.ledger, self.credentials, self.plan, self.clock)

    def result(self):
        return json.loads((Path(self.temp.name)/"instagram-feed-probe-result.json").read_text())

    def test_success_is_one_call_with_live_confirmation_and_preserves_other_holds(self):
        self.assertEqual(self.run_probe(), 0)
        self.mocks["publish_instagram"].assert_called_once()
        self.assertEqual(self.ledger.rows["probe-article"]["instagram"]["status"], "published")
        self.assertTrue(self.ledger.rows["old"]["instagram"]["action_block_hold"])
        self.assertEqual(self.result()["permalink"], self.live["permalink"])

    def test_protective_error_stops_and_rerunning_never_retries(self):
        self.mocks["publish_instagram"].side_effect = p.MetaAPIError(403,
            {"code": 4, "error_subcode": 2207051, "fbtrace_id": "trace_12345", "is_transient": False})
        self.collect.side_effect = None; self.collect.return_value = ([], True)
        self.assertEqual(self.run_probe(), 1)
        entry = self.ledger.rows["probe-article"]["instagram"]
        self.assertEqual(entry["status"], "needs_review")
        self.assertTrue(entry["action_block_hold"])
        self.assertEqual(entry["error"]["subcode"], 2207051)
        self.assertEqual(self.run_probe(), 0)
        self.mocks["publish_instagram"].assert_called_once()

    def test_error_with_actual_post_is_recorded_published_without_resending(self):
        self.mocks["publish_instagram"].side_effect = p.MetaAPIError(400, {"code":4, "error_subcode":2207051})
        self.assertEqual(self.run_probe(), 0)
        self.assertTrue(self.ledger.rows["probe-article"]["instagram"]["action_block_hold"])
        self.assertEqual(self.result()["state"], "published")
        self.mocks["publish_instagram"].assert_called_once()

    def test_lost_response_remains_uncertain(self):
        self.mocks["publish_instagram"].side_effect = RuntimeError("Lost response")
        self.collect.side_effect = None; self.collect.return_value = ([], True)
        self.assertEqual(self.run_probe(), 1)
        self.assertEqual(self.ledger.rows["probe-article"]["instagram"]["status"], "needs_review")

    def test_incomplete_history_never_claims_or_posts(self):
        self.collect.side_effect = None; self.collect.return_value = ([], False)
        self.assertEqual(self.run_probe(), 1)
        self.assertFalse(self.ledger.calls)
        self.mocks["publish_instagram"].assert_not_called()

    def test_existing_live_post_never_posts(self):
        self.collect.side_effect = None; self.collect.return_value = ([self.live], True)
        self.assertEqual(self.run_probe(), 1)
        self.assertFalse(self.ledger.calls)
        self.mocks["publish_instagram"].assert_not_called()

    def test_account_mismatch_or_quota_zero_never_posts(self):
        self.mocks["verify_account"].side_effect = RuntimeError("Wrong account")
        self.assertEqual(self.run_probe(), 1)
        self.mocks["verify_account"].side_effect = None
        self.mocks["instagram_budget"].return_value = 0
        self.assertEqual(self.run_probe(), 1)
        self.assertFalse(self.ledger.calls)
        self.mocks["publish_instagram"].assert_not_called()

    def test_recent_feed_keeps_quiet_period(self):
        self.collect.side_effect = None
        self.collect.return_value = ([{**self.live, "caption": "Unrelated post"}], True)
        self.assertEqual(self.run_probe(), 1)
        self.assertFalse(self.ledger.calls)
        self.mocks["publish_instagram"].assert_not_called()

    def test_expired_review_or_existing_uncertain_target_never_posts(self):
        self.plan["valid_until"] = (self.clock-timedelta(seconds=1)).isoformat()
        self.assertEqual(self.run_probe(), 0)
        self.assertEqual(self.result()["state"], "expired")
        self.plan["valid_until"] = (self.clock+timedelta(hours=1)).isoformat()
        self.ledger.rows["probe-article"] = {"instagram": {"status": "needs_review"}}
        self.assertEqual(self.run_probe(), 0)
        self.assertFalse(self.ledger.calls)
        self.mocks["publish_instagram"].assert_not_called()

    def test_request_cannot_authorize_multiple_articles_or_early_second_probe(self):
        self.ledger.rows["other"] = {"instagram": {"status": "needs_review",
            "probe_request_id": "earlier-request", "updated_at": self.clock.isoformat()}}
        self.assertEqual(self.run_probe(), 1)
        self.assertFalse(self.ledger.calls)
        self.mocks["publish_instagram"].assert_not_called()


if __name__ == "__main__":
    unittest.main()
