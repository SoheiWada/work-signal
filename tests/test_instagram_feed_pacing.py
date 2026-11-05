import copy
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from scripts.instagram_feed_pacing import feed_pacing_state, restriction_metadata, safe_pacing_deferral
from scripts import publish_social as social
from scripts.select_scheduled_social import scheduled_ids
from scripts.social_queue import backlog_report
from scripts.check_social_channel_outcomes import evaluate

NOW = datetime(2026, 11, 6, 1, 0, tzinfo=timezone.utc)


class DurableLedger:
    def __init__(self, rows=None):
        self.rows = copy.deepcopy(rows or {})
        self.writes = []
    def read(self):
        return self.rows, "test-sha"
    def record(self, aid, kind, status, **metadata):
        old = self.rows.setdefault(aid, {}).get(kind, {})
        preserved = {k:old[k] for k in ("feed_attempted_at","restricted_until") if k in old}
        self.rows[aid][kind] = {**preserved,"status":status,"updated_at":social.now(),**metadata}
        self.writes.append((aid,kind,status))


def article(aid):
    return {"id":aid,"title":"Reviewed news","summary":"Verified facts","score":90,
            "source_url":"https://example.org/official","status":"published","social_publish":True,
            "published_at":datetime.now(social.timezone(social.timedelta(hours=9))).date().isoformat(),
            "social_platforms":["threads","instagram","instagram_story"]}


class FeedPacingTests(unittest.TestCase):
    def test_empty_history_allows_one_feed(self):
        self.assertTrue(feed_pacing_state({},NOW)["allowed"])

    def test_one_feed_per_jst_day_and_24_hour_gap(self):
        last = NOW-timedelta(hours=23)
        rows={"old":{"instagram":{"status":"published","updated_at":last.isoformat()}}}
        gate=feed_pacing_state(rows,NOW)
        self.assertFalse(gate["allowed"])
        self.assertEqual(gate["reason"],"feed_pacing")
        self.assertEqual(datetime.fromisoformat(gate["next_attempt_at"]),last+timedelta(hours=24))
        self.assertTrue(feed_pacing_state(rows,last+timedelta(hours=24))["allowed"])

    def test_jst_midnight_does_not_reset_the_24_hour_interval(self):
        last=datetime(2026,11,5,14,59,tzinfo=timezone.utc)
        rows={"old":{"instagram":{"status":"published","updated_at":last.isoformat()}}}
        gate=feed_pacing_state(rows,last+timedelta(minutes=2))
        self.assertFalse(gate["allowed"])
        self.assertEqual(datetime.fromisoformat(gate["next_attempt_at"]),last+timedelta(hours=24))

    def test_manual_hold_survives_48_hours_and_old_records_get_stable_deadline(self):
        row={"status":"published","updated_at":NOW.isoformat(),"action_block_hold":True,
             "error":{"code":4,"subcode":2207051}}
        rows={"blocked":{"instagram":row}}
        before=feed_pacing_state(rows,NOW+timedelta(hours=1))
        after=feed_pacing_state(rows,NOW+timedelta(hours=49))
        self.assertFalse(before["allowed"]); self.assertFalse(after["allowed"])
        self.assertTrue(after["manual_release_required"])
        self.assertEqual(before["restricted_until"],after["restricted_until"])
        self.assertEqual(datetime.fromisoformat(after["restricted_until"]),NOW+timedelta(hours=48))

    def test_new_cooldown_cannot_be_shortened_by_clearing_only_the_hold(self):
        row={"status":"published","updated_at":NOW.isoformat(),"action_block_hold":True,
             "action_block_cleared_at":(NOW+timedelta(hours=1)).isoformat(),
             **restriction_metadata(NOW.isoformat())}
        self.assertFalse(feed_pacing_state({"a":{"instagram":row}},NOW+timedelta(hours=2))["allowed"])
        self.assertTrue(feed_pacing_state({"a":{"instagram":row}},NOW+timedelta(hours=49))["allowed"])

    def test_invalid_or_missing_history_times_fail_closed(self):
        for value in [None,"invalid","2026-11-06T01:00:00",(NOW+timedelta(hours=1)).isoformat()]:
            gate=feed_pacing_state({"a":{"instagram":{"status":"published","updated_at":value}}},NOW)
            self.assertFalse(gate["allowed"])
            self.assertTrue(gate["manual_release_required"])

    def test_attempt_time_is_preserved_across_late_live_reconciliation(self):
        row={"status":"published","feed_attempted_at":NOW.isoformat(),
             "updated_at":(NOW+timedelta(days=3)).isoformat()}
        self.assertTrue(feed_pacing_state({"a":{"instagram":row}},NOW+timedelta(days=4))["allowed"])

    def test_paced_deferral_does_not_hide_any_unknown_write(self):
        entry={"status":"deferred","reason":"instagram_feed_pacing",
               "next_attempt_at":(NOW+timedelta(days=1)).isoformat()}
        self.assertTrue(safe_pacing_deferral(entry,NOW))
        for changes in [{"status":"needs_review"},{"container_id":"unknown"},
                        {"stage":"publish_requested"},{"reason":"instagram_quota"}]:
            self.assertFalse(safe_pacing_deferral({**entry,**changes},NOW))

    def test_batch_and_next_run_cannot_burst_feed_but_other_channels_continue(self):
        feed=[article("one"),article("two")]
        ledger=DurableLedger()
        credentials={"SOCIAL_PUBLISH_ENABLED":"true","THREADS_ACCESS_TOKEN":"t","THREADS_USER_ID":"1",
                     "INSTAGRAM_ACCESS_TOKEN":"i","INSTAGRAM_USER_ID":"2"}
        with (patch.object(social,"verify_account",return_value={"account_type":"BUSINESS"}),
              patch.object(social,"verify_live"),patch.object(social,"instagram_budget",return_value=50),
              patch.object(social,"publish_threads",return_value="t"),
              patch.object(social,"verify_threads_delivery",return_value={"id":"t"}),
              patch.object(social,"publish_instagram",return_value="f") as publisher,
              patch.object(social,"publish_instagram_story",return_value="s") as stories,
              patch.object(social,"verify_instagram_delivery",return_value={"id":"visible"})):
            self.assertEqual(social.run(feed,ledger,credentials),0)
            self.assertEqual(social.run(feed,ledger,credentials),0)
        self.assertEqual(publisher.call_count,1)
        self.assertEqual(stories.call_count,2)
        self.assertTrue(all(ledger.rows[a["id"]]["threads"]["status"]=="published" for a in feed))
        deferred=[row["instagram"] for row in ledger.rows.values() if row["instagram"]["status"]=="deferred"]
        self.assertEqual(len(deferred),1)
        self.assertTrue(safe_pacing_deferral(deferred[0]))

    def test_error_with_live_post_keeps_published_and_sets_48h_manual_hold(self):
        item=article("ambiguous")
        ledger=DurableLedger()
        credentials={"SOCIAL_PUBLISH_ENABLED":"true","INSTAGRAM_ACCESS_TOKEN":"i","INSTAGRAM_USER_ID":"2"}
        item["social_platforms"]=["instagram"]
        observed = datetime.now(timezone.utc).isoformat(timespec="seconds")
        def blocked(*args,**kwargs):
            kwargs["progress"]("publish_requested","container")
            raise social.MetaAPIError(403,{"code":4,"error_subcode":2207051})
        with (patch.object(social,"now",return_value=observed),
              patch.object(social,"verify_account",return_value={"account_type":"BUSINESS"}),
              patch.object(social,"verify_live"),patch.object(social,"instagram_budget",return_value=50),
              patch.object(social,"publish_instagram",side_effect=blocked) as publisher,
              patch.object(social,"verify_instagram_delivery",return_value={"id":"real","permalink":"https://www.instagram.com/p/real/"})):
            self.assertEqual(social.run([item],ledger,credentials),0)
        row=ledger.rows[item["id"]]["instagram"]
        self.assertEqual(row["status"],"published")
        self.assertEqual(row["remote_id"],"real")
        self.assertEqual(row["error"]["subcode"],2207051)
        self.assertEqual(datetime.fromisoformat(row["restricted_until"])-datetime.fromisoformat(row["updated_at"]),timedelta(hours=48))
        self.assertTrue(feed_pacing_state(ledger.rows)["manual_release_required"])
        self.assertEqual(publisher.call_count,1)

    def test_existing_active_hold_never_attempts_even_after_deadline(self):
        rows={"old":{"instagram":{"status":"published","updated_at":"2026-01-01T00:00:00Z",
                                   "action_block_hold":True,"remote_id":"old"}}}
        item=article("held"); item["social_platforms"]=["instagram"]
        ledger=DurableLedger(rows)
        with (patch.object(social,"verify_account") as account,
              patch.object(social,"publish_instagram") as publisher):
            social.run([item],ledger,{"SOCIAL_PUBLISH_ENABLED":"true","INSTAGRAM_ACCESS_TOKEN":"i","INSTAGRAM_USER_ID":"2"})
        publisher.assert_not_called(); account.assert_not_called()
        self.assertNotIn(item["id"],ledger.rows)

    def test_selector_monitor_and_channel_gate_report_pacing_as_not_posted(self):
        when=datetime.now(timezone.utc)
        item=article("next")
        rows={"old":{"instagram":{"status":"published","updated_at":when.isoformat()}},
              "next":{"threads":{"status":"published"},"instagram_story":{"status":"published"},
                      "instagram":{"status":"deferred","reason":"instagram_feed_pacing",
                         "next_attempt_at":(when+timedelta(days=1)).isoformat()}}}
        self.assertEqual(scheduled_ids([item],rows),[])
        report=backlog_report([item],rows)
        self.assertEqual(report["counts"]["instagram"]["deferred"],1)
        summary={"articles":[{"id":"next","platforms":{"threads":"published","instagram_story":"published","instagram":"deferred"}}],"failures":[]}
        ok,error,counts=evaluate(summary,[item],rows)
        self.assertTrue(ok,error)
        self.assertEqual(counts["feed_paced"],1)
        self.assertEqual(counts["feed_published"],0)

    def test_malformed_feed_history_is_a_monitor_review_case(self):
        item=article("next"); item["social_platforms"]=["instagram"]
        rows={"old":{"instagram":{"status":"published","updated_at":"invalid"}}}
        report=backlog_report([item],rows)
        self.assertEqual(report["counts"]["instagram"]["review_required"],1)
        self.assertEqual(report["counts"]["instagram"]["held"],0)

    def test_unselected_feed_deferral_cannot_mask_a_missing_thread(self):
        item=article("thread-only"); item["social_platforms"]=["threads"]
        rows={"thread-only":{"instagram":{"status":"deferred","reason":"instagram_feed_pacing",
                 "next_attempt_at":(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()}}}
        ledger=DurableLedger(rows)
        with patch.object(social,"verify_account",side_effect=RuntimeError("unavailable")):
            result=social.run([item],ledger,{"SOCIAL_PUBLISH_ENABLED":"true",
                    "THREADS_ACCESS_TOKEN":"t","THREADS_USER_ID":"1"})
        self.assertEqual(result,1)


if __name__=="__main__":
    unittest.main()
