"""Local-only review server. Specimens and test pages never enter _site/."""
import argparse
import json
import re
import subprocess
import threading
import time
from datetime import datetime, timezone, timedelta
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]


class LiveCache:
    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        try:
            self.snapshot = json.loads(path.read_text())
        except (OSError, ValueError):
            self.snapshot = {}
        self.checked = 0

    def get(self):
        # One shared refresh per five minutes, also on failure. Never per visitor.
        with self.lock:
            if time.monotonic() - self.checked >= 300:
                self.checked = time.monotonic()
                try:
                    result = subprocess.run(['node', str(ROOT / 'scripts/fetch_market.mjs')],
                        input=json.dumps(self.snapshot.get('observations', [])), text=True,
                        capture_output=True, timeout=9, check=True, cwd=ROOT)
                    self.snapshot = json.loads(result.stdout)
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    temporary = self.path.with_suffix('.tmp')
                    temporary.write_text(json.dumps(self.snapshot))
                    temporary.replace(self.path)
                except (subprocess.SubprocessError, OSError, ValueError):
                    self.snapshot = dict(version=1, quotes=[], pendingIds=['nasdaq', 'sp500'],
                        observations=self.snapshot.get('observations', []))
            return {k: v for k, v in self.snapshot.items() if k != 'observations'}


class Preview(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path in ('/nba', '/nba-study'):
            self.send_response(302)
            self.send_header('Location', parsed.path + '/')
            self.end_headers()
            return
        if parsed.path.startswith(('/nba/', '/nba-study/')):
            study = parsed.path.startswith('/nba-study/')
            prefix = '/nba-study/' if study else '/nba/'
            asset = parsed.path.removeprefix(prefix) or 'index.html'
            allowed = {'index.html': 'text/html; charset=utf-8', 'style.css': 'text/css',
                'app.mjs': 'text/javascript', 'page.mjs': 'text/javascript', 'model.mjs': 'text/javascript',
                'court-motion.mjs': 'text/javascript',
                'fonts/Anton-Regular.ttf': 'font/ttf', 'fonts/OFL.txt': 'text/plain'}
            if study:
                allowed = {'index.html': 'text/html; charset=utf-8',
                    'app.mjs': 'text/javascript', 'data.mjs': 'text/javascript'}
            if asset not in allowed:
                return self.send('text/plain', b'Not found', 404)
            folder = ROOT / 'prototypes/nba-signal' if study else ROOT / 'nba'
            data = (folder / asset).read_bytes()
            if asset == 'index.html' and query.get('motion') == ['reduce']:
                # Development-only media emulation; no changes to the prototype assets.
                data = data.replace(b'<head>', b'''<head><style>*{animation:none!important;transition:none!important}</style><script>
                const originalMatchMedia=window.matchMedia.bind(window);
                window.matchMedia=q=>q.includes('prefers-reduced-motion')?{matches:true,addEventListener(){},removeEventListener(){}}:originalMatchMedia(q);
                </script>''')
            return self.send(allowed[asset], data)
        if parsed.path == '/__nba-review':
            return self.send('text/html; charset=utf-8', (ROOT / 'tests/nba/browser.html').read_bytes())
        if parsed.path == '/__review':
            return self.send('text/html; charset=utf-8', (ROOT / 'tests/market/browser.html').read_bytes())
        if parsed.path == '/__live-quotes':
            return self.send('application/json', json.dumps(self.server.live_cache.get()).encode())
        if parsed.path == '/__quotes':
            scenario = query.get('scenario', ['current'])[0]
            if scenario == 'failed':
                return self.send('application/json', b'{}', 503)
            now = datetime.now(timezone.utc)
            stamp = lambda delta: (now - timedelta(seconds=delta)).isoformat()
            prices = [('btc', 68421.38, 1.24), ('eth', 3521.74, -0.82), ('nasdaq', 18642.17, 0.43), ('sp500', 5842.36, 0.31), ('gold', 2648.90, -0.21), ('usdjpy', 149.82, 0.18)]
            quotes = [dict(id=i, price=p, changePercent=c, changeBasis='24h' if i in ('btc', 'eth') else 'previous_close', asOf=stamp(25), fetchedAt=stamp(0), marketState='open', timing='realtime', delaySeconds=0) for i,p,c in prices]
            if scenario == 'mixed':
                quotes[2].update(timing='delayed', delaySeconds=900, asOf=stamp(925))
                quotes[3].update(marketState='closed', asOf=stamp(2 * 86400))
            if scenario == 'stale':
                for q in quotes:
                    q.update(fetchedAt=stamp(600), asOf=stamp(600))
            if scenario == 'partial':
                quotes = quotes[:2]
            if scenario == 'reference':
                quotes = [q for q in quotes if q['id'] in ('btc', 'eth', 'gold', 'usdjpy')]
                for q in quotes:
                    q.update(provider='gold-api', changePercent=None, comparisonAt=None,
                        changeBasis='observed_24h', timing='reference', delaySeconds=None, marketState='unknown')
                quotes[-1].update(provider='frankfurter', timing='daily_reference', asOf=now.date().isoformat(),
                    changeBasis='previous_publication', changePercent=0.25,
                    comparisonAt=(now - timedelta(days=1)).date().isoformat())
            return self.send('application/json', json.dumps(dict(version=1, mode='specimen', quotes=quotes,
                pendingIds=['nasdaq', 'sp500'] if scenario == 'reference' else [])).encode())
        if parsed.path in ('/', '/index.html'):
            scenario = query.get('scenario', ['current'])[0]
            if scenario not in ('current', 'mixed', 'stale', 'failed', 'partial', 'reference'):
                scenario = 'current'
            source = (Path(self.directory) / 'index.html').read_text()
            source = re.sub(r'<!-- Google tag.*?</script>\s*<script>.*?</script>', '', source, flags=re.S)
            if query.get('market') in (['specimen'], ['live']):
                endpoint = '/__live-quotes' if query.get('market') == ['live'] else f'/__quotes?scenario={scenario}'
                source = source.replace('name="work-signal-market-endpoint" content=""', f'name="work-signal-market-endpoint" content="http://127.0.0.1:{self.server.server_port}{endpoint}"')
            elif query.get('market') == ['off']:
                source = source.replace('name="work-signal-market-mode" content="free"', 'name="work-signal-market-mode" content="off"')
            if query.get('motion') == ['reduce']:
                # Test-only media emulation for JS and CSS; the production files are untouched.
                source = source.replace('<head>', '''<head><style>*{animation:none!important;transition:none!important}</style><script>
                const originalMatchMedia=window.matchMedia.bind(window);
                window.matchMedia=q=>q.includes('prefers-reduced-motion')?{matches:true,addEventListener(){},removeEventListener(){}}:originalMatchMedia(q);
                </script>''')
            return self.send('text/html; charset=utf-8', source.encode())
        self.path = parsed.path
        return super().do_GET()

    def send(self, mime, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--cache', type=Path, default=ROOT / '.cache/market-live.json')
    args = parser.parse_args()
    if not (ROOT / '_site/index.html').exists():
        raise SystemExit('Run python3 scripts/build_site.py first.')
    server = ThreadingHTTPServer(('127.0.0.1', args.port), partial(Preview, directory=str(ROOT / '_site')))
    server.live_cache = LiveCache(args.cache)
    print(f'Local real data: http://127.0.0.1:{args.port}/?market=live', flush=True)
    print(f'Local design review: http://127.0.0.1:{args.port}/?market=specimen', flush=True)
    server.serve_forever()
