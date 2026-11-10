import copy
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree as ET
from scripts import build_site as site


class SubscriptionTests(unittest.TestCase):
    def test_follow_hub_has_real_existing_channels_and_usable_copy_fallback(self):
        page=site.follow_page((site.ROOT/'index.html').read_text())
        for url in ['https://www.threads.com/@work_signal_japan','https://www.instagram.com/work_signal_japan/','https://signal.amberlight.co.jp/feed.xml']:
            self.assertIn(url,page)
        self.assertIn('data-copy-rss-url=',page)
        self.assertIn('data-rss-feedback',page)
        self.assertIn('<link rel="canonical" href="https://signal.amberlight.co.jp/follow/">',page)
        self.assertNotIn('<form',page)
        self.assertNotIn('utm_',page)
        self.assertIn('data-follow-placement="follow_page"',page)

    def test_rss_keeps_actual_instant_and_omits_unknown_legacy_hour(self):
        feed=json.loads((site.ROOT/'data/articles.json').read_text())
        a=copy.deepcopy(feed[0]);a.update(id='earlier-z',published_at='2026-11-11',published_at_time='2026-11-10T15:10:00Z')
        b=dict(a,id='later-a',published_at_time='2026-11-11T01:00:00+09:00')
        old=dict(a,id='legacy',published_at='2026-11-10');old.pop('published_at_time')
        before=copy.deepcopy([a,b,old])
        with tempfile.TemporaryDirectory() as tmp:
            site.write_rss(Path(tmp),[a,b,old]);items=ET.parse(Path(tmp)/'feed.xml').findall('./channel/item')
        self.assertTrue(items[0].findtext('link').endswith('/later-a/'))
        self.assertEqual(parsedate_to_datetime(items[0].findtext('pubDate')),datetime(2026,11,10,16,tzinfo=timezone.utc))
        self.assertIsNone(items[-1].find('pubDate'))
        self.assertEqual([a,b,old],before)


if __name__=='__main__':unittest.main()
