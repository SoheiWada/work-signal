"""The local live bridge must share cache and keep private history off the wire."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.preview_market import LiveCache


class LivePreviewTests(unittest.TestCase):
    def test_cache_is_shared_for_five_minutes_and_history_stays_internal(self):
        with tempfile.TemporaryDirectory() as directory:
            state = dict(version=1, quotes=[dict(id='btc', price=100)], observations=[dict(id='btc', price=90)])
            cache = LiveCache(Path(directory) / 'live.json')
            with patch('scripts.preview_market.time.monotonic', side_effect=[1000, 1000, 1100, 1301, 1301]), patch('scripts.preview_market.subprocess.run', return_value=subprocess.CompletedProcess([], 0, json.dumps(state))) as runner:
                first = cache.get()
                second = cache.get()
                self.assertEqual(first, second)
                self.assertNotIn('observations', first)
                self.assertEqual(runner.call_count, 1)
                cache.get()
                self.assertEqual(runner.call_count, 2)
                self.assertEqual(json.loads(runner.call_args.kwargs['input']), state['observations'])
                self.assertEqual(json.loads(cache.path.read_text()), state)

    def test_failure_is_backed_off_and_never_relabels_old_prices(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'live.json'
            old = dict(version=1, quotes=[dict(id='btc', price=100, fetchedAt='old')], observations=[dict(id='btc', price=90)])
            path.write_text(json.dumps(old))
            cache = LiveCache(path)
            with patch('scripts.preview_market.time.monotonic', side_effect=[1000, 1000, 1100]), patch('scripts.preview_market.subprocess.run', side_effect=subprocess.TimeoutExpired('node', 9)) as runner:
                self.assertEqual(cache.get()['quotes'], [])
                self.assertEqual(cache.get()['quotes'], [])
                self.assertEqual(runner.call_count, 1)
                self.assertEqual(cache.snapshot['observations'], old['observations'])
                self.assertEqual(json.loads(path.read_text()), old)
