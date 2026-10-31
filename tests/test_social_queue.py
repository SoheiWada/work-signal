import unittest
from datetime import datetime, timezone, timedelta
from scripts.social_queue import batch_ids, continuation_ids, backlog_report, scheduler_health
from tests.test_scheduled_social import article
from scripts.reconcile_social_recovery import recovery_update

NOW = datetime(2026, 10, 31, 8, 0, tzinfo=timezone.utc)


class SocialQueueTests(unittest.TestCase):
    def test_canceled_events_are_recovered_from_articles_not_event_delta(self):
        feed = [article(str(i), pub="2026-10-31") for i in range(8)]
        batch = batch_ids(feed, {}, clock=NOW)
        self.assertEqual(len(batch), 5)
        after = {aid: {"threads": {"status": "published"}} for aid in batch}
        following = continuation_ids(feed, {}, after, batch, 0, NOW)
        self.assertEqual(len(following), 3)
        self.assertEqual(set(batch + following), {a["id"] for a in feed})

    def test_uncertain_done_expired_unapproved_and_old_never_rearm(self):
        feed = [article("pending"), article("unknown"), article("attempt"), article("done"),
                article("old", pub="2026-10-21"), article("draft", social_publish=False),
                article("expired", social_review_valid_until="2026-10-30T00:00:00Z")]
        rows = {aid: {"threads": {"status": state}} for aid, state in
                (("unknown", "needs_review"), ("attempt", "attempting"), ("done", "published"))}
        self.assertEqual(batch_ids(feed, rows, clock=NOW), ["pending"])

    def test_no_progress_or_depth_cap_cannot_loop(self):
        feed = [article("one")]
        self.assertEqual(continuation_ids(feed, {}, {}, ["one"], 0, NOW), [])
        for depth in (2, 100, -1):
            self.assertEqual(continuation_ids(feed, {}, {"one": {"threads": {"status": "published"}}},
                                              ["one"], depth, NOW), [])

    def test_scoped_manual_recovery_never_expands(self):
        self.assertEqual(batch_ids([article("one"), article("two")], {}, "one", NOW), ["one"])
        with self.assertRaises(ValueError):
            batch_ids([article("one")], {}, "unapproved", NOW)

    def test_reviewed_absence_can_recover_when_only_uncertain_work_remains(self):
        feed = [article("reviewed")]
        old = {"status": "needs_review"}
        rows = {"reviewed": {"threads": old}}
        self.assertEqual(batch_ids(feed, rows, clock=NOW), [])
        replacement = recovery_update(old, [], "new-owner-freshness-review", "threads")
        rows["reviewed"]["threads"] = replacement
        self.assertEqual(batch_ids(feed, rows), ["reviewed"])

    def test_global_report_exposes_missing_posts_outside_a_successful_batch(self):
        report = backlog_report([article("done"), article("missed"), article("unknown")], {
            "done": {"threads": {"status": "published"}},
            "unknown": {"threads": {"status": "needs_review"}}}, NOW)
        self.assertEqual(report["counts"]["threads"]["published"], 1)
        self.assertEqual(report["counts"]["threads"]["ready"], 1)
        self.assertEqual(report["counts"]["threads"]["needs_review"], 1)

    def test_feed_hold_does_not_hide_missing_threads_or_story(self):
        a = article("new", social_platforms=["threads", "instagram", "instagram_story"])
        report = backlog_report([a], {"other": {"instagram": {"status": "published",
                                 "action_block_hold": True}}}, NOW)
        self.assertEqual(report["counts"]["instagram"]["held"], 1)
        self.assertEqual(report["counts"]["threads"]["ready"], 1)
        self.assertEqual(report["counts"]["instagram_story"]["ready"], 1)

    def test_scheduler_gap_and_no_runs_are_detected(self):
        self.assertTrue(scheduler_health([], NOW)["stale"])
        for minutes, expected in ((30, False), (91, True), (360, True)):
            runs = [{"created_at": (NOW - timedelta(minutes=minutes)).isoformat()}]
            self.assertEqual(scheduler_health(runs, NOW)["stale"], expected)


if __name__ == "__main__":
    unittest.main()
