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
        today = datetime.now(timezone(timedelta(hours=9))).date().isoformat()
        feed = [article("reviewed", pub=today)]
        old = {"status": "needs_review"}
        rows = {"reviewed": {"threads": old}}
        self.assertEqual(batch_ids(feed, rows), [])
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



class SocialMonitorRecoveryTests(unittest.TestCase):
    def test_stale_schedule_is_not_a_delivery_failure_when_queue_is_complete(self):
        from scripts.social_queue import delivery_health
        report = backlog_report([article("done")], {"done": {"threads": {"status": "published"}}}, NOW)
        report["scheduler"] = scheduler_health([], NOW)
        self.assertTrue(report["scheduler"]["stale"])
        self.assertEqual(delivery_health(report), "complete")

    def test_hold_remains_incomplete_but_does_not_hide_other_channel_failure(self):
        from scripts.social_queue import delivery_health
        feed = [article("feed", social_platforms=["instagram"])]
        rows = {"old": {"instagram": {"status": "published", "action_block_hold": True}}}
        report = backlog_report(feed, rows, NOW)
        self.assertEqual(delivery_health(report), "waiting")
        self.assertEqual(report["counts"]["instagram"]["held"], 1)
        report = backlog_report(feed + [article("missed")], rows, NOW)
        self.assertEqual(delivery_health(report), "needs_attention")

    def test_invalid_history_is_reported_not_retried_or_silently_dropped(self):
        from scripts.social_queue import delivery_health
        for entry in (None, {"status": "bogus"}, {"status": "deferred"}):
            report = backlog_report([article("bad")], {"bad": {"threads": entry}}, NOW)
            self.assertEqual(report["counts"]["threads"]["review_required"], 1)
            self.assertEqual(report["ready_article_ids"], [])
            self.assertEqual(delivery_health(report), "needs_attention")

    def test_quota_resume_uses_the_same_clock_as_freshness_and_report(self):
        a = article("due")
        rows = {"due": {"threads": {"status": "deferred",
                                    "next_attempt_at": (NOW + timedelta(hours=1)).isoformat()}}}
        self.assertEqual(batch_ids([a], rows, clock=NOW), [])
        self.assertEqual(backlog_report([a], rows, NOW)["counts"]["threads"]["deferred"], 1)
        self.assertEqual(batch_ids([a], rows, clock=NOW + timedelta(hours=2)), ["due"])

    def test_recovery_is_bounded_and_never_wakes_an_active_publisher(self):
        from scripts.social_queue import recovery_decision
        run = {"created_at": (NOW - timedelta(hours=2)).isoformat(), "status": "completed"}
        self.assertTrue(recovery_decision(["missed"], [run], NOW)["dispatch"])
        self.assertFalse(recovery_decision([], [run], NOW)["dispatch"])
        for status in ("queued", "in_progress", "waiting"):
            self.assertFalse(recovery_decision(["missed"], [{**run, "status": status}], NOW)["dispatch"])
        self.assertEqual(recovery_decision(["missed"], [{**run, "created_at": NOW.isoformat()}], NOW)["state"],
                         "cooldown")

    def test_dispatch_uses_json_and_accepts_empty_204_without_meta_or_ledger_writes(self):
        import json
        from unittest.mock import patch, MagicMock
        from scripts.social_queue import dispatch_queue
        response = MagicMock()
        response.__enter__.return_value.status = 204
        with patch("scripts.social_queue.urlopen", return_value=response) as send:
            dispatch_queue("https://api.github.com/repos/SoheiWada/work-signal", "test-token")
        req = send.call_args.args[0]
        self.assertEqual(req.method, "POST")
        self.assertEqual(req.full_url, "https://api.github.com/repos/SoheiWada/work-signal/actions/workflows/social-publish.yml/dispatches")
        self.assertEqual(req.get_header("Content-type"), "application/json")
        self.assertEqual(json.loads(req.data), {"ref": "main", "inputs": {"wake_source": "monitor_recovery"}})

    def test_monitor_incident_reproduction_exits_zero_without_hiding_scheduler_warning(self):
        import json, tempfile
        from pathlib import Path
        from unittest.mock import patch
        from scripts import social_queue as q
        feed = [article("done")]
        rows = {"done": {"threads": {"status": "published"}}}
        run = {"created_at": (NOW - timedelta(minutes=10)).isoformat(),
               "status": "completed", "conclusion": "success"}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "data").mkdir()
            (root / "data/articles.json").write_text(json.dumps(feed))
            with patch.object(q.social, "ROOT", root), patch.object(q.social, "GithubLedger") as ledger, \
                 patch.object(q.social, "request_json", side_effect=[{"workflow_runs": [run]}, {"workflow_runs": []}]), \
                 patch.object(q, "dispatch_queue") as dispatch, patch.object(q, "write_report") as report, \
                 patch.object(q, "datetime", wraps=datetime) as clock, \
                 patch.dict("os.environ", {"GITHUB_REPOSITORY": "SoheiWada/work-signal", "GITHUB_TOKEN": "test"}), \
                 patch("sys.argv", ["social_queue.py", "monitor"]):
                clock.now.return_value = NOW
                ledger.return_value.read.return_value = (rows, "sha")
                self.assertEqual(q.main(), 0)
                state = report.call_args.args[0]
                self.assertEqual(state["delivery_health"], "complete")
                self.assertTrue(state["scheduler"]["stale"])
                self.assertEqual(state["publisher"]["state"], "recent")
                dispatch.assert_not_called()

    def test_monitor_wakes_real_pending_work_but_does_not_claim_delivery_complete(self):
        import json, tempfile
        from pathlib import Path
        from unittest.mock import patch
        from scripts import social_queue as q
        run = {"created_at": (NOW - timedelta(hours=2)).isoformat(), "status": "completed"}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "data").mkdir()
            (root / "data/articles.json").write_text(json.dumps([article("missed")]))
            with patch.object(q.social, "ROOT", root), patch.object(q.social, "GithubLedger") as ledger, \
                 patch.object(q.social, "request_json", return_value={"workflow_runs": [run]}), \
                 patch.object(q, "dispatch_queue") as dispatch, patch.object(q, "write_report") as report, \
                 patch.object(q, "datetime", wraps=datetime) as clock, \
                 patch.dict("os.environ", {"GITHUB_REPOSITORY": "SoheiWada/work-signal", "GITHUB_TOKEN": "test"}), \
                 patch("sys.argv", ["social_queue.py", "monitor"]):
                clock.now.return_value = NOW
                ledger.return_value.read.return_value = ({}, "sha")
                self.assertEqual(q.main(), 0)  # Monitor warns; publisher failures remain separate.
                self.assertEqual(report.call_args.args[0]["delivery_health"], "needs_attention")
                dispatch.assert_called_once()


class PipelineGraceTests(unittest.TestCase):
    def recent_report(self, age=120, recovery="cooldown"):
        feed = [article("ricoh", published_at_time=(NOW - timedelta(seconds=age)).isoformat()),
                article("xreal", published_at_time=(NOW - timedelta(seconds=age)).isoformat())]
        report = backlog_report(feed, {}, NOW)
        report["recovery"] = {"state": recovery}
        return report

    def test_two_new_articles_during_skipped_run_cooldown_are_processing_not_failed(self):
        from scripts.social_queue import delivery_health
        report = self.recent_report()
        self.assertEqual(delivery_health(report), "processing")
        self.assertEqual(report["counts"]["threads"]["ready"], 2)
        self.assertEqual(report["counts"]["threads"]["published"], 0)

    def test_new_runs_never_extend_the_fixed_article_deadline(self):
        from scripts.social_queue import delivery_health
        for recovery in ("cooldown", "publisher_active", "requested"):
            self.assertEqual(delivery_health(self.recent_report(899, recovery)), "processing")
            self.assertEqual(delivery_health(self.recent_report(900, recovery)), "needs_attention")

    def test_no_pipeline_or_unknown_future_timestamp_does_not_get_grace(self):
        from scripts.social_queue import delivery_health
        for recovery in ("idle", "failed", None):
            self.assertEqual(delivery_health(self.recent_report(recovery=recovery)), "needs_attention")
        self.assertEqual(delivery_health(self.recent_report(age=-1)), "needs_attention")

    def test_uncertain_result_always_alerts_even_with_an_active_pipeline(self):
        from scripts.social_queue import delivery_health
        report = self.recent_report(recovery="publisher_active")
        report["outstanding"][0]["state"] = "needs_review"
        self.assertEqual(delivery_health(report), "needs_attention")

    def test_sending_is_only_processing_while_the_actual_publisher_is_active(self):
        from scripts.social_queue import delivery_health
        report = self.recent_report(recovery="publisher_active")
        row = report["outstanding"][0]
        row["state"] = "attempting"
        row["attempt_updated_at"] = (NOW - timedelta(seconds=299)).isoformat()
        self.assertEqual(delivery_health(report), "processing")
        row["attempt_updated_at"] = (NOW - timedelta(seconds=300)).isoformat()
        self.assertEqual(delivery_health(report), "needs_attention")
        row["attempt_updated_at"] = NOW.isoformat()
        report["recovery"]["state"] = "cooldown"
        self.assertEqual(delivery_health(report), "needs_attention")

    def test_monitor_replays_the_incident_without_a_failure_or_false_published_claim(self):
        import json, tempfile
        from pathlib import Path
        from unittest.mock import patch
        from scripts import social_queue as q
        feed = [article("ricoh", published_at_time=(NOW - timedelta(minutes=2)).isoformat()),
                article("xreal", published_at_time=(NOW - timedelta(minutes=1)).isoformat())]
        run = {"created_at": (NOW - timedelta(seconds=13)).isoformat(),
               "status": "completed", "conclusion": "skipped"}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / "data").mkdir()
            (root / "data/articles.json").write_text(json.dumps(feed))
            with patch.object(q.social, "ROOT", root), patch.object(q.social, "GithubLedger") as ledger, \
                 patch.object(q.social, "request_json", return_value={"workflow_runs": [run]}), \
                 patch.object(q, "dispatch_queue") as dispatch, patch.object(q, "write_report") as report, \
                 patch.object(q, "datetime", wraps=datetime) as clock, \
                 patch.dict("os.environ", {"GITHUB_REPOSITORY": "SoheiWada/work-signal", "GITHUB_TOKEN": "test"}), \
                 patch("sys.argv", ["social_queue.py", "monitor"]):
                clock.now.return_value = NOW
                ledger.return_value.read.return_value = ({}, "sha")
                self.assertEqual(q.main(), 0)
                self.assertEqual(report.call_args.args[0]["delivery_health"], "processing")
                self.assertEqual(report.call_args.args[0]["counts"]["threads"]["ready"], 2)
                dispatch.assert_not_called()


if __name__ == "__main__":
    unittest.main()

