"""Shadow-only observation; never authorizes skipping a Pages deployment."""
import json
import subprocess
from datetime import datetime, timezone

try:
    from .discovery_sitemaps import news_publication
except ImportError:
    from discovery_sitemaps import news_publication


def classify(run, paths, articles, clock):
    if not run or run.get('conclusion') != 'success' or run.get('head_branch') != 'main':
        return 'baseline_unavailable'
    if any(path != '.github/social-post-ledger.json' for path in paths):
        return 'source_changed'
    start = datetime.fromisoformat(run['run_started_at'].replace('Z', '+00:00'))
    if start > clock or start.year != clock.year:
        return 'clock_boundary'
    for article in articles:
        if article.get('status') != 'published':
            continue
        if article.get('format') in ('management_guide', 'special_story'):
            continue
        if news_publication(article, start) or news_publication(article, clock):
            return 'news_window_active'
        # Future publication dates or an expiry within the previous build
        # interval are conservatively treated as requiring a build.
        if article.get('published_at', '') >= (start.astimezone(timezone.utc).date()).isoformat():
            return 'news_window_uncertain'
    return 'potentially_redundant'


def main():
    runs = json.loads(subprocess.check_output([
        'gh', 'api', 'repos/SoheiWada/work-signal/actions/workflows/pages.yml/runs?branch=main&status=success&per_page=1'
    ]))['workflow_runs']
    run = runs[0] if runs else None
    paths = []
    if run:
        jobs = json.loads(subprocess.check_output([
            'gh', 'api', f"repos/SoheiWada/work-signal/actions/runs/{int(run['id'])}/jobs?per_page=100"
        ]))['jobs']
        if not any(j['name'] == 'deploy' and j['conclusion'] == 'success' for j in jobs):
            run = None
    if run:
        sha = run['head_sha']
        subprocess.run(['git', 'merge-base', '--is-ancestor', sha, 'HEAD'], check=True)
        paths = subprocess.check_output(['git', 'diff', '--name-only', sha, 'HEAD'], text=True).splitlines()
    with open('data/articles.json', encoding='utf-8') as f:
        articles = json.load(f)
    print('PAGES_SCHEDULE_SHADOW', json.dumps({
        'state': classify(run, paths, articles, datetime.now(timezone.utc)),
        'baseline': run['head_sha'] if run else None,
        'deployment_skipped': False
    }))


if __name__ == '__main__':
    main()
