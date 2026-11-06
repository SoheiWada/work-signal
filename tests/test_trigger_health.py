import unittest
from datetime import datetime, timedelta, timezone
from scripts.social_queue import trigger_health, scheduler_health


class TriggerHealthTests(unittest.TestCase):
    def test_external_clock_covers_schedule_gap_without_claiming_delivery(self):
        clock = datetime(2026, 11, 6, 1, tzinfo=timezone.utc)
        run = {"created_at": (clock-timedelta(minutes=10)).isoformat(),
               "event": "repository_dispatch", "conclusion": "success",
               "display_title": "SNS delivery health · repository_dispatch"}
        self.assertEqual(trigger_health([], [], [run], clock)["state"], "external_clock_covering_delay")
        for changed in ({"conclusion":"failure"}, {"conclusion":None}, {"event":"workflow_dispatch"},
                        {"created_at":(clock-timedelta(minutes=46)).isoformat()},
                        {"created_at":(clock+timedelta(hours=1)).isoformat()}):
            with self.subTest(changed=changed):
                self.assertEqual(trigger_health([], [], [{**run, **changed}], clock)["state"], "trigger_attention_required")

    def test_missing_naive_invalid_and_future_timestamps_are_not_health(self):
        clock = datetime(2026, 11, 6, 1, tzinfo=timezone.utc)
        for stamp in (None, "bad", "2026-11-06T01:00:00", "2026-11-07T01:00:00Z"):
            self.assertTrue(scheduler_health([{"created_at":stamp}], clock)["stale"])
