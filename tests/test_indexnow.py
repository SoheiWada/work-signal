import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

from scripts import build_site, indexnow


def article(identifier, **fields):
    return {'id': identifier, 'title': identifier, 'status': 'published',
            'published_at': '2026-11-20', 'reading_format': 'brief', **fields}


class IndexNowTests(unittest.TestCase):
    def test_only_new_or_substantively_changed_approved_articles_are_sent(self):
        old = article('old')
        unchanged = article('unchanged')
        removed = article('removed')
        previous = indexnow.article_snapshot([old, unchanged, removed])
        deployed = indexnow.article_snapshot([
            article('new'), {**old, 'summary': 'Updated content'},
            {**unchanged, 'score': 88, 'updated_at': '2026-11-21', 'social_publish': True},
            {**removed, 'status': 'draft'},
        ])
        self.assertEqual(indexnow.changed_urls(previous, deployed), [
            indexnow.BASE + 'articles/new/', indexnow.BASE + 'articles/old/',
        ])
        fetch = Mock()
        self.assertIsNone(indexnow.submit(previous, previous, '100-1', fetch))
        fetch.assert_not_called()

    def test_submit_waits_for_the_current_live_feed_and_key_and_checks_acceptance(self):
        feed = [article('approved')]
        snapshot = indexnow.article_snapshot(feed)
        live = (200, json.dumps(feed).encode())
        key = (200, indexnow.KEY.encode())
        fetch = Mock(side_effect=[live, key, (202, b'')])
        self.assertEqual(indexnow.submit({}, snapshot, '100-1', fetch), 202)
        fetch.assert_called_with('api.indexnow.org', 'POST', '/IndexNow', {
            'host': indexnow.HOST, 'key': indexnow.KEY,
            'keyLocation': indexnow.BASE + indexnow.KEY_FILE,
            'urlList': [indexnow.BASE + 'articles/approved/'],
        })
        for responses, reason, calls in [
            ([(200, b'[]')], 'feed is not live', 1),
            ([live, (404, b'')], 'key file is not live', 2),
            ([live, key, (429, b'')], 'HTTP 429', 3),
        ]:
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
                fetch = Mock(side_effect=responses)
                try:
                    indexnow.submit({}, snapshot, '100-1', fetch)
                finally:
                    self.assertEqual(fetch.call_count, calls)

    def test_llms_lists_only_a_bounded_selection_of_published_deep_dives_and_official_accounts(self):
        feed = [{**article(f'deep-{n}'), 'reading_format': 'deep_dive'} for n in range(6)]
        feed.append(article('brief'))
        with TemporaryDirectory() as directory:
            output = Path(directory)
            build_site.write_llms_txt(output, feed)
            guide = (output / 'llms.txt').read_text(encoding='utf-8')
        self.assertEqual(guide.count('/articles/'), 4)
        self.assertIn('/articles/deep-5/', guide)
        self.assertNotIn('/articles/brief/', guide)
        self.assertNotIn('/articles/deep-0/', guide)
        self.assertIn('about/#editorial-policy', guide)
        self.assertIn('profile.php?id=61596301937684', guide)
        self.assertNotIn('note.com/amber_light', guide)
