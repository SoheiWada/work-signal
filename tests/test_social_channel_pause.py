import copy
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from scripts import publish_social as social
from scripts.select_scheduled_social import scheduled_ids
from scripts.social_queue import backlog_report, delivery_health
from scripts.check_social_channel_outcomes import evaluate


class Ledger:
    def __init__(self, rows=None):
        self.rows = copy.deepcopy(rows or {})
        self.writes = []
    def read(self):
        return self.rows, "sha"
    def record(self, aid, kind, status, **metadata):
        self.writes.append((aid, kind, status))
        self.rows.setdefault(aid, {})[kind] = {"status": status, **metadata}


class ChannelPauseTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"SOCIAL_PAUSED_PLATFORMS":"instagram,instagram_story"})
        env.start()
        self.addCleanup(env.stop)
        self.article = {"id":"pause-test", "title":"Reviewed news", "summary":"Verified facts",
            "status":"published", "score":90, "social_publish":True,
            "source_url":"https://example.org/official",
            "published_at":datetime.now(timezone.utc).astimezone(
                social.timezone(social.timedelta(hours=9))).date().isoformat(),
            "social_platforms":["threads","instagram","instagram_story"]}
        self.credentials = {"SOCIAL_PUBLISH_ENABLED":"true",
            "THREADS_ACCESS_TOKEN":"t", "THREADS_USER_ID":"1"}

    def test_threads_publish_while_paused_instagram_gets_no_api_or_ledger_writes(self):
        ledger = Ledger()
        with (patch.object(social,"verify_account",return_value={}) as account,
              patch.object(social,"verify_live"),
              patch.object(social,"publish_threads",return_value="123"),
              patch.object(social,"verify_threads_delivery",return_value={"id":"123","permalink":"https://www.threads.com/t/test"}),
              patch.object(social,"publish_instagram") as feed,
              patch.object(social,"publish_instagram_story") as story,
              patch.object(social,"instagram_budget") as quota):
            self.assertEqual(social.run([self.article],ledger,self.credentials),0)
        feed.assert_not_called()
        story.assert_not_called()
        quota.assert_not_called()
        self.assertEqual(account.call_count,1)
        self.assertEqual({kind for _,kind,_ in ledger.writes},{"threads"})

    def test_published_threads_and_paused_stories_are_not_selected_again(self):
        rows = {self.article["id"]:{"threads":{"status":"published","remote_id":"123"}}}
        before = copy.deepcopy(rows)
        self.assertEqual(scheduled_ids([self.article],rows),[])
        ledger = Ledger(rows)
        with patch.object(social,"verify_account") as account:
            self.assertEqual(social.run([self.article],ledger,self.credentials),0)
        account.assert_not_called()
        self.assertEqual(ledger.rows,before)
        self.assertEqual(ledger.writes,[])

    def test_pause_is_visible_as_outstanding_and_never_as_published(self):
        rows = {self.article["id"]:{"threads":{"status":"published"}}}
        report = backlog_report([self.article],rows)
        self.assertEqual(report["counts"]["instagram_story"]["held"],1)
        self.assertEqual(report["counts"]["instagram_story"]["published"],0)
        self.assertEqual(delivery_health(report),"waiting")
        self.assertEqual(report["ready_article_ids"],[])
        self.assertTrue(all(x["hold_reason"]=="operator_pause" for x in report["outstanding"]))

    def test_only_documented_pause_is_accepted_by_channel_gate(self):
        rows = {self.article["id"]:{"threads":{"status":"published"}}}
        summary = {"articles":[{"id":self.article["id"],"platforms":{
            "threads":"published","instagram":"paused","instagram_story":"paused"}}],"failures":[]}
        ok, error, counts = evaluate(summary,[self.article],rows)
        self.assertTrue(ok,error)
        self.assertEqual(counts["operator_paused"],2)
        self.assertEqual(counts["instagram_story"],0)
        with patch.dict(os.environ,{"SOCIAL_PAUSED_PLATFORMS":""}):
            self.assertFalse(evaluate(summary,[self.article],rows)[0])

    def test_unknown_writes_and_threads_errors_are_not_hidden_by_pause(self):
        rows = {self.article["id"]:{"threads":{"status":"published"},
            "instagram_story":{"status":"needs_review","remote_id":"uncertain"}}}
        report = backlog_report([self.article],rows)
        self.assertEqual(report["counts"]["instagram_story"]["needs_review"],1)
        self.assertEqual(delivery_health(report),"needs_attention")
        for channel in ["threads","instagram_story"]:
            summary = {"articles":[{"id":self.article["id"],"platforms":{
                "threads":"published","instagram":"paused","instagram_story":"paused"}}],"failures":[]}
            summary["articles"][0]["platforms"][channel]="needs_review"
            self.assertFalse(evaluate(summary,[self.article],rows)[0])

    def test_unpause_retains_original_media_and_uncertain_ledger_protection(self):
        original = copy.deepcopy(self.article)
        self.assertEqual(social.delivery_platforms(self.article),["threads"])
        with patch.dict(os.environ,{"SOCIAL_PAUSED_PLATFORMS":""}):
            self.assertEqual(social.delivery_platforms(self.article),self.article["social_platforms"])
        self.assertEqual(self.article,original)
        self.assertNotIn("instagram_story",social.remaining_platforms({"instagram_story":{"status":"needs_review"}}))

    def test_invalid_pause_configuration_fails_closed(self):
        with patch.dict(os.environ,{"SOCIAL_PAUSED_PLATFORMS":"instagram,bogus"}):
            with self.assertRaises(RuntimeError):
                social.delivery_platforms(self.article)


if __name__ == "__main__":
    unittest.main()
