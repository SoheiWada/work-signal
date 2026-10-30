import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from scripts.select_scheduled_social import scheduled_ids


NOW = datetime(2026, 10, 30, 15, 0, tzinfo=timezone.utc)


def article(aid, pub="2026-10-30", **changes):
    item = {"id": aid, "title": "Reviewed", "summary": "Summary", "source_url": "https://example.org",
            "published_at": pub, "status": "published", "score": 93,
            "social_publish": True, "social_platforms": ["threads"]}
    item.update(changes)
    return item


class ScheduledSocialTests(unittest.TestCase):
    def test_recent_missing_threads_is_selected(self):
        self.assertEqual(scheduled_ids([article("new")], {}, NOW), ["new"])

    def test_old_unknown_or_expired_items_are_not_retried(self):
        feed = [article("old", pub="2026-10-21"), article("new"),
                article("review", social_review_valid_until="2026-10-29T00:00:00Z")]
        ledger = {"new": {"threads": {"status": "needs_review"}}}
        self.assertEqual(scheduled_ids(feed, ledger, NOW), [])

    def test_inprogress_and_published_do_not_repost(self):
        rows = {
            "attempting": {"threads": {"status": "attempting"}},
            "done": {"threads": {"status": "published"}},
        }
        feed = [article("attempting"), article("done")]
        self.assertEqual(scheduled_ids(feed, rows, NOW), [])

    def test_instagram_protective_hold_prevents_new_instagram_writes(self):
        feed = [article("new", social_platforms=["threads", "instagram"])]
        rows = {"other": {"instagram": {"status": "needs_review", "error": {
            "code": 4, "subcode": 2207051}}}}
        self.assertEqual(scheduled_ids(feed, rows, NOW), ["new"])
        feed[0]["social_platforms"] = ["instagram"]
        self.assertEqual(scheduled_ids(feed, rows, NOW), [])

    def test_future_or_uncertain_dates_are_held(self):
        self.assertEqual(scheduled_ids([article("future", pub="2026-11-01"),
                                        article("broken", pub="not-date")], {}, NOW), [])

    def test_scheduled_workflow_skips_when_no_safe_candidate(self):
        from pathlib import Path
        source = (Path(__file__).resolve().parents[1] /
                  ".github/workflows/social-publish.yml").read_text()
        self.assertIn("steps.scheduled.outputs.ready == 'true'", source)
        self.assertIn("scripts/select_scheduled_social.py", source)
        self.assertIn("cancel-in-progress: false", source)


if __name__ == "__main__":
    unittest.main()
