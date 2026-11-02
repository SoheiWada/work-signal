import json
import re
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError
from urllib.request import Request
from scripts import publish_social as social

class CredentialTransportTests(unittest.TestCase):
    def test_credentials_never_leave_fixed_api_hosts(self):
        for url in ("https://attacker.example/", "http://api.github.com/",
                    "https://api.github.com.attacker.example/", "https://user:password@api.github.com/",
                    "https://api.github.com:8443/"):
            with self.subTest(url=url), patch.object(social._CREDENTIAL_OPENER,"open") as send:
                with self.assertRaisesRegex(ValueError,"credential destination"):
                    social.urlopen(Request(url,headers={"Authorization":"Bearer private-token"}))
                send.assert_not_called()

    def test_redirect_does_not_forward_a_bearer_or_repeat_a_write(self):
        request=Request("https://graph.threads.net/v1.0/1/threads",
            method="POST",data=b"approved-text",headers={"Authorization":"Bearer private-token"})
        handler=social.NoCredentialRedirect()
        for code in (301,302,303,307,308):
            self.assertIsNone(handler.redirect_request(request,None,code,"redirect",{},
                                                      "https://attacker.example/collect"))
        failure=HTTPError(request.full_url,302,"redirect",{},BytesIO(b"private-token"))
        with patch.object(social._CREDENTIAL_OPENER,"open",side_effect=failure) as send, \
             patch.object(social,"_public_urlopen") as public:
            with self.assertRaises(social.MetaAPIError) as caught:
                social.request_json(request.full_url,token="private-token",method="POST",data={"text":"approved"})
            self.assertNotIn("private-token",str(caught.exception))
            self.assertEqual(send.call_count,1)
            public.assert_not_called()
            self.assertTrue(failure.closed)

    def test_normal_api_read_and_public_asset_transport_remain_available(self):
        with patch.object(social._CREDENTIAL_OPENER,"open") as api, \
             patch.object(social,"_public_urlopen") as public:
            social.urlopen(Request("https://api.github.com/repos/test/repo",
                                   headers={"Authorization":"Bearer test"}),timeout=20)
            api.assert_called_once()
            public.assert_not_called()
            social.urlopen(Request("https://signal.amberlight.co.jp/assets/test.jpg"))
            public.assert_called_once()

    def test_only_the_canonical_workflow_can_invoke_social_writers(self):
        root=Path(__file__).resolve().parents[1]
        writers=[]
        for path in (root/".github/workflows").glob("*.yml"):
            text=path.read_text()
            if re.search(r"(?m)^\s*(?:run:\s*)?python3?\s+scripts/(?:publish_(?:social|x)\.py\s+--live|publish_story_once\.py|recover_\S+\.py|publish_five_threads_\S+\.py|publish_nest_admin_\S+\.py)", text):
                writers.append(path.name)
        self.assertEqual(sorted(writers),["social-publish.yml"])
