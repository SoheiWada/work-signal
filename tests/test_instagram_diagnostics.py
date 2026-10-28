import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import diagnose_instagram as d


class DiagnosticsTests(unittest.TestCase):
    def test_headers_discard_identifiers_and_unrecognised_payloads(self):
        headers = {"x-app-usage": '{"call_count":2,"token":"SECRET"}',
                   "x-business-use-case-usage": '{"private-account-id":[{"call_count":3,"total_time":1,"url":"SECRET"}]}',
                   "retry-after": "60", "x-fb-request-id": "safe_trace_123", "set-cookie": "SECRET"}
        out = json.dumps(d.safe_headers(headers))
        self.assertNotIn("SECRET", out)
        self.assertNotIn("private-account-id", out)
        self.assertIn("call_count", out)

    def test_error_does_not_disclose_raw_message_or_token(self):
        out = d.safe_error({"code":4,"error_subcode":2207051,"is_transient":False,"type":"OAuthException",
                            "message":"Spam protective block; token SECRET", "error_user_msg":"SECRET"})
        self.assertNotIn("SECRET", json.dumps(out))
        self.assertIn("spam_or_protective", out["message_categories"])
        self.assertEqual(out["error_subcode"], 2207051)

    def test_reader_only_sends_get_with_bearer_header(self):
        with patch.object(d, "urlopen") as open_url:
            response = open_url.return_value.__enter__.return_value
            response.status, response.headers = 200, {}
            response.read.return_value = b'{"data":[]}'
            d.Reader("SECRET").get("me/permissions", "permissions")
            req = open_url.call_args.args[0]
            self.assertEqual(req.get_method(), "GET")
            self.assertNotIn("SECRET", req.full_url)
            self.assertIsNone(req.data)

    def test_reader_rejects_foreign_hosts_and_write_endpoints(self):
        for path in ("https://evil.example/", "123/media_publish", "123/media?x=1\nInjected: x"):
            with self.subTest(path=path), patch.object(d, "urlopen") as open_url:
                with self.assertRaises(ValueError):
                    d.Reader("SECRET").get(path, "invalid")
                open_url.assert_not_called()


if __name__ == "__main__":
    unittest.main()
