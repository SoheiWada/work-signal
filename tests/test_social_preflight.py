import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from scripts import publish_social as social
from scripts.social_delivery_preflight import DeliveryPreflight
from scripts.audit_social_delivery import collect
from tests.test_delivery_reliability import MemoryLedger
from tests.test_scheduled_social import article

TODAY = datetime.now(timezone(timedelta(hours=9))).date().isoformat()


class SocialPreflightTests(unittest.TestCase):
    def setUp(self):
        self.a = article("preflight-test", pub=TODAY)
        self.credentials = {"SOCIAL_PUBLISH_ENABLED": "true", "SOCIAL_PREFLIGHT_HISTORY": "true",
                            "THREADS_ACCESS_TOKEN": "t", "THREADS_USER_ID": "1",
                            "INSTAGRAM_ACCESS_TOKEN": "i", "INSTAGRAM_USER_ID": "2"}
        self.preflight = DeliveryPreflight([self.a], {}, self.credentials,
                                           target_ids=[self.a["id"]])

    def test_existing_threads_is_recorded_without_any_publish(self):
        ledger = MemoryLedger()
        found = {"id": "123", "text": social.article_url(self.a), "permalink": "https://www.threads.com/t/test"}
        with (patch("scripts.social_delivery_preflight.collect", return_value=([found], True)),
              patch.object(social, "verify_account", return_value={}),
              patch.object(social, "verify_live"),
              patch.object(social, "publish_threads") as publish):
            self.assertEqual(social.run([self.a], ledger, self.credentials), 0)
        publish.assert_not_called()
        self.assertEqual(ledger.rows[self.a["id"]]["threads"]["remote_id"], "123")

    def test_incomplete_or_duplicate_history_prevents_claim_and_write(self):
        found = {"id": "123", "text": social.article_url(self.a)}
        for result in (([], False), ([found, {**found, "id": "456"}], True)):
            ledger = MemoryLedger()
            with (patch("scripts.social_delivery_preflight.collect", return_value=result),
                  patch.object(social, "verify_account", return_value={}),
                  patch.object(social, "verify_live"),
                  patch.object(social, "publish_threads") as publish):
                self.assertEqual(social.run([self.a], ledger, self.credentials), 1)
            publish.assert_not_called()
            self.assertEqual(ledger.rows, {})

    def test_verified_absence_allows_only_one_attempt(self):
        ledger = MemoryLedger()
        with (patch("scripts.social_delivery_preflight.collect", return_value=([], True)),
              patch.object(social, "verify_account", return_value={}),
              patch.object(social, "verify_live"),
              patch.object(social, "publish_threads", return_value="123") as publish,
              patch.object(social, "verify_threads_delivery", return_value={"id": "123"})):
            self.assertEqual(social.run([self.a], ledger, self.credentials), 0)
            self.assertEqual(social.run([self.a], ledger, self.credentials), 0)
        publish.assert_called_once()

    def test_story_uses_visual_positive_control_and_today_window(self):
        with (patch("scripts.social_delivery_preflight.collect", return_value=([], True)),
              patch("scripts.social_delivery_preflight.story_image_checks", return_value={
                  self.a["id"]: {"absence_verified": True, "matching_ids": []}})):
            self.assertIsNone(self.preflight.existing(self.a, "instagram_story"))
            with self.assertRaises(RuntimeError):
                self.preflight.existing({**self.a, "published_at": "2026-01-01"}, "instagram_story")
        with (patch("scripts.social_delivery_preflight.collect", return_value=([], True)),
              patch("scripts.social_delivery_preflight.story_image_checks", return_value={})):
            fresh = DeliveryPreflight([self.a], {}, self.credentials)
            with self.assertRaises(RuntimeError):
                fresh.existing(self.a, "instagram_story")

    def test_blank_story_caption_is_not_absence_evidence(self):
        with (patch("scripts.social_delivery_preflight.collect", return_value=([
                  {"id": "321", "caption": ""}], True)),
              patch("scripts.social_delivery_preflight.story_image_checks", return_value={
                  self.a["id"]: {"matching_ids": ["321"]}})):
            self.assertEqual(self.preflight.existing(self.a, "instagram_story")["id"], "321")

    def test_malformed_history_is_not_an_empty_complete_timeline(self):
        for response in ({}, {"data": {}}, {"data": [None]}, {"data": [{}]}):
            with patch.object(social, "request_json", return_value=response), self.assertRaises(RuntimeError):
                collect("https://graph.example", "user/media", "t", "id")


if __name__ == "__main__":
    unittest.main()
