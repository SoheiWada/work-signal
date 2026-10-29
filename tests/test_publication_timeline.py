"""Publication chronology must not invent timestamps for legacy articles."""
import unittest

from scripts.build_site import article_timeline, article_card, _clock_text


class TimelineTests(unittest.TestCase):
    def test_legacy_article_has_only_known_date(self):
        a = {"published_at": "2026-10-28"}
        html = article_timeline(a, compact=True)
        self.assertIn("公開 2026-10-28", html)
        self.assertNotIn("00:00", html)
        self.assertNotIn("更新 ", html)

    def test_recorded_publication_clock_uses_japan_time(self):
        a = {"published_at": "2026-10-29",
             "published_at_time": "2026-10-29T00:15:21Z"}
        html = article_timeline(a, compact=True)
        self.assertIn("公開登録 2026-10-29 09:15 JST", html)
        self.assertNotIn("更新 ", html)

    def test_substantive_update_keeps_original_publication(self):
        a = {"published_at": "2026-10-28"}
        html = article_timeline(a, "2026-10-29T02:34:12+00:00")
        self.assertIn("公開 2026-10-28", html)
        self.assertIn("更新 2026-10-29 11:34 JST", html)
        self.assertNotIn("公開登録 2026-10-29", html)

    def test_naive_or_date_mismatched_clock_is_not_shown(self):
        self.assertIsNone(_clock_text("2026-10-29T09:15:00"))
        html = article_timeline({"published_at": "2026-10-28",
                                 "published_at_time": "2026-10-29T09:15:00+09:00"})
        self.assertIn("公開 2026-10-28", html)
        self.assertNotIn("公開登録", html)

    def test_static_story_has_publication_date(self):
        a = {"id": "test-article", "title": "試験記事", "category": "AI",
             "published_at": "2026-10-29", "summary": "要約", "format": "deep_dive"}
        html = article_card(a)
        self.assertIn('class="story-timeline"', html)
        self.assertIn("公開 2026-10-29", html)


if __name__ == "__main__":
    unittest.main()
