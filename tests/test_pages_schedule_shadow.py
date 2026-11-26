import unittest
from datetime import datetime, timezone
from scripts.observe_pages_schedule import classify


class ScheduleShadowTests(unittest.TestCase):
    def test_classification(self):
        clock = datetime(2026, 11, 26, 12, tzinfo=timezone.utc)
        run = {'conclusion': 'success', 'head_branch': 'main',
               'run_started_at': '2026-11-26T10:00:00Z'}
        def article(day, format='brief'):
            return {'status': 'published', 'published_at': day, 'format': format}
        cases = [
            (None, [], [], 'baseline_unavailable'),
            (dict(run, conclusion='failure'), [], [], 'baseline_unavailable'),
            (run, ['data/articles.json'], [], 'source_changed'),
            (dict(run, run_started_at='2026-11-26T13:00:00Z'), [], [], 'clock_boundary'),
            (run, [], [article('2026-11-25')], 'news_window_active'),
            (run, [], [dict(article('2026-11-24'), published_at_time='2026-11-24T20:00:00+09:00')], 'news_window_active'),
            (run, [], [article('2026-11-27')], 'news_window_uncertain'),
            (run, [], [article('2026-11-20')], 'potentially_redundant'),
            (run, ['.github/social-post-ledger.json'], [article('2026-11-25', 'special_story')], 'potentially_redundant'),
        ]
        for baseline, paths, articles, expected in cases:
            with self.subTest(expected=expected, articles=articles):
                self.assertEqual(classify(baseline, paths, articles, clock), expected)
