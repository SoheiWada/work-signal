import tempfile
import unittest
from pathlib import Path

from scripts.build_site import ROOT, build


class MarketPublishingTests(unittest.TestCase):
    def test_pages_contains_only_public_market_assets_and_no_specimens_or_service(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'site'
            build(out, [])
            home = (out / 'index.html').read_text()
            self.assertIn('name="work-signal-market-endpoint" content=""', home)
            self.assertIn('name="work-signal-market-mode" content="free"', home)
            self.assertIn('<div class="orbit" aria-hidden="true"><div class="ring"></div><div class="signal">W<span style="color:#191918">.</span></div></div>', home)
            for asset in ('assets/js/hero-market.mjs', 'assets/js/market-model.mjs', 'assets/css/hero-market.css',
                          'assets/js/free-market-client.mjs', 'assets/js/free-market-feeds.mjs'):
                self.assertEqual((out / asset).read_bytes(), (ROOT / asset).read_bytes())
            for directory in ('services', 'tests', 'scripts', '.git', '.github', 'prototypes'):
                self.assertFalse((out / directory).exists())
            self.assertFalse(any('instruments.example' in str(p) for p in out.rglob('*')))
            public = home + '\n'.join(p.read_text() for p in (out / 'assets/js').glob('*.mjs'))
            self.assertNotIn('TWELVE_DATA_API_KEY', public)
            self.assertNotIn('68421.38', public)
            self.assertNotIn('/__quotes?', public)
