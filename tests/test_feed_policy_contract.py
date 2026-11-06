import json
import unittest
from datetime import datetime
from pathlib import Path
from scripts.instagram_feed_pacing import feed_pacing_state


class SharedFeedPolicyTests(unittest.TestCase):
    def test_worker_and_python_share_boundary_cases(self):
        cases = json.loads((Path(__file__).parent / "fixtures/instagram-feed-policy.json").read_text())
        for case in cases:
            with self.subTest(case=case["name"]):
                before = json.dumps(case["rows"], sort_keys=True)
                actual = feed_pacing_state(case["rows"], datetime.fromisoformat(case["now"].replace("Z", "+00:00")))
                for key, expected in case["expected"].items():
                    value = actual[key]
                    if key.endswith("_at") or key == "restricted_until":
                        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
                        expected = datetime.fromisoformat(expected.replace("Z", "+00:00"))
                    self.assertEqual(value, expected, key)
                self.assertEqual(json.dumps(case["rows"], sort_keys=True), before)
