import importlib.util
import json
import unittest
import tempfile
from urllib.error import HTTPError
from io import BytesIO
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


class PublisherErrorMetadataTests(unittest.TestCase):
    def test_preserve_restriction_text_and_redact_credentials(self):
        from scripts.publish_social import MetaAPIError
        msg = "We restrict certain activity to protect our community. Tell us if you think we made a mistake."
        result = MetaAPIError(400, {"code": 4, "error_subcode": 2207051,
            "message": msg, "error_user_msg": "Failed with token SECRET at https://example.com/?access_token=SECRET"},
            secrets=("SECRET",)).metadata()
        self.assertEqual(result["message"], msg)
        self.assertNotIn("SECRET", json.dumps(result))
        self.assertNotIn("example.com", json.dumps(result))

    def test_auth_failure_saves_report_and_makes_no_followup_calls(self):
        with tempfile.TemporaryDirectory() as root, patch.object(d, "ROOT", Path(root)), \
             patch.dict(d.os.environ, {"INSTAGRAM_ACCESS_TOKEN": "SECRET", "INSTAGRAM_USER_ID": "123"}), \
             patch.object(d, "urlopen") as open_url:
            open_url.side_effect = HTTPError("https://graph.instagram.com/v25.0/me", 401, "Unauthorized", {},
                BytesIO(json.dumps({"error": {"code": 190, "message": "Invalid OAuth access token: SECRET"}}).encode()))
            with patch("builtins.print"), self.assertRaises(SystemExit):
                d.main()
            result = json.loads((Path(root) / "instagram-health-diagnostic.json").read_text())
            self.assertFalse(result["account"]["verified"])
            self.assertEqual(result["calls"][0]["error"]["code"], 190)
            self.assertNotIn("SECRET", json.dumps(result))
            self.assertEqual(open_url.call_count, 1)

    def test_preserve_trace_without_raw_error_text(self):
        from scripts.publish_social import MetaAPIError
        result = MetaAPIError(403, {"code":4, "error_subcode":2207051, "type":"OAuthException",
            "fbtrace_id":"trace_12345", "is_transient":False, "message":"SECRET"}).metadata()
        self.assertEqual(result["fbtrace_id"], "trace_12345")
        self.assertFalse(result["is_transient"])
        self.assertNotIn("SECRET", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
