"""The integrated page must never ship the design study's invented NBA results."""
import re
import tempfile
import unittest
from pathlib import Path

from scripts.build_site import ROOT, build


class NbaPublishingTests(unittest.TestCase):
    def test_public_page_has_closed_dependencies_and_no_study_data(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'site'
            build(out, [])
            nba = out / 'nba'
            expected = {'index.html', 'app.mjs', 'page.mjs', 'model.mjs',
                        'court-motion.mjs', 'style.css',
                        'fonts/Anton-Regular.ttf', 'fonts/OFL.txt'}
            self.assertEqual({str(p.relative_to(nba)) for p in nba.rglob('*') if p.is_file()}, expected)
            for name in expected:
                self.assertEqual((nba / name).read_bytes(), (ROOT / 'nba' / name).read_bytes())
            for module in nba.glob('*.mjs'):
                for dependency in re.findall(r"from ['\"]([^'\"]+)['\"]", module.read_text()):
                    self.assertTrue(dependency.startswith('./'), dependency)
                    self.assertTrue((module.parent / dependency).is_file(), dependency)
            public = '\n'.join(p.read_text() for p in nba.iterdir() if p.suffix in ('.html', '.mjs', '.css'))
            for fixture in ('Boston Celtics', 'BOS', '118対', './data.mjs', 'prototypes/', 'nba-study/'):
                self.assertNotIn(fixture, public)
            self.assertIn('試合データは現在未接続です。', public)
            self.assertIn('noindex,nofollow', (nba / 'index.html').read_text())
            self.assertNotIn('/nba/', (out / 'index.html').read_text())
            self.assertNotIn('/nba/', (out / 'sitemap.xml').read_text())
            self.assertFalse((out / 'nba-study').exists())
            self.assertFalse((out / 'prototypes').exists())
