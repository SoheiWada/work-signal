import unittest
from datetime import datetime, timezone, timedelta
from io import BytesIO
from unittest.mock import patch
from PIL import Image, ImageDraw
from scripts.audit_social_delivery import story_image_checks
from scripts.social_delivery_preflight import DeliveryPreflight
from scripts import publish_social as social


class StoryVisualIdentityTests(unittest.TestCase):
    def setUp(self):
        today = datetime.now(timezone(timedelta(hours=9))).date().isoformat()
        self.articles = [{"id": aid, "published_at": today} for aid in ("one", "two", "target")]
        self.images = {}
        # Same card, differing only in a small title region, like adjacent CVEs.
        for i, a in enumerate(self.articles):
            image = Image.new("RGB", (1080, 1920), (25, 25, 25))
            ImageDraw.Draw(image).rectangle((220 + i * 100, 900, 295 + i * 100, 940), fill="white")
            data = BytesIO(); image.save(data, "PNG")
            self.images[a["id"]] = data.getvalue()
        self.rows = {aid: {"instagram_story": {"status": "published", "remote_id": aid}}
                     for aid in ("one", "two")}
        self.stories = [{"id": aid, "media_url": "https://s.cdninstagram.com/" + aid}
                        for aid in ("one", "two")]

    def checks(self, stories=None, rows=None):
        def open_image(request, **kwargs):
            return BytesIO(self.images[request.full_url.rsplit("/", 1)[-1]])
        with (patch.object(social, "story_image_url", side_effect=lambda a: "https://signal.amberlight.co.jp/" + a["id"]),
              patch("scripts.audit_social_delivery.urlopen", side_effect=open_image)):
            return story_image_checks(self.articles, self.rows if rows is None else rows,
                                      self.stories if stories is None else stories, target_ids=["target"])

    def test_known_distinct_cve_cards_do_not_block_a_new_unclaimed_story(self):
        proof = self.checks()
        row = proof["target"]
        self.assertEqual(set(row["known_other_ids"]), {"one", "two"})
        self.assertEqual(row["matching_ids"], [])
        self.assertTrue(row["absence_verified"])
        with (patch("scripts.social_delivery_preflight.collect", return_value=(self.stories, True)),
              patch("scripts.social_delivery_preflight.story_image_checks", return_value=proof)):
            preflight = DeliveryPreflight(self.articles, self.rows, {"INSTAGRAM_USER_ID": "u", "INSTAGRAM_ACCESS_TOKEN": "t"})
            self.assertIsNone(preflight.existing(self.articles[-1], "instagram_story"))

    def test_unrecorded_actual_target_remains_a_match_and_is_never_resent(self):
        stories = self.stories + [{"id": "actual", "media_url": "https://s.cdninstagram.com/target"}]
        row = self.checks(stories)["target"]
        self.assertEqual(row["matching_ids"], ["actual"])
        self.assertFalse(row["absence_verified"])

    def test_unknown_similar_card_remains_ambiguous(self):
        row = self.checks(rows={"one": self.rows["one"]})["target"]
        self.assertIn("two", row["matching_ids"])
        self.assertFalse(row["absence_verified"])

    def test_uncertain_duplicate_and_identical_bindings_cannot_prove_absence(self):
        for status in ("attempting", "needs_review"):
            rows = {"one": self.rows["one"], "two": {"instagram_story": {"status": status, "remote_id": "two"}}}
            self.assertFalse(self.checks(rows=rows)["target"]["absence_verified"])
        rows = {**self.rows, "target": {"instagram_story": {"status": "published", "remote_id": "two"}}}
        self.assertFalse(self.checks(rows=rows)["target"]["absence_verified"])
        self.images["target"] = self.images["two"]
        self.assertFalse(self.checks()["target"]["absence_verified"])

    def test_incorrect_or_missing_positive_control_cannot_authorize_absence(self):
        self.assertFalse(self.checks(rows={})["target"]["absence_verified"])
        self.images["one"] = self.images["two"]
        # One wrong binding cannot remove the unknown matching image.
        self.assertFalse(self.checks(rows={"one": self.rows["one"]})["target"]["absence_verified"])


if __name__ == "__main__":
    unittest.main()
