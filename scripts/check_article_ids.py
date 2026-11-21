"""Protect the IDs in the most recent successful WORK SIGNAL Pages deployment."""

import json
import os
from pathlib import Path
import re
import subprocess
from urllib.request import HTTPRedirectHandler, Request, build_opener

REPOSITORY = 'SoheiWada/work-signal'
RUNS = ('https://api.github.com/repos/' + REPOSITORY
        + '/actions/workflows/pages.yml/runs?branch=main&status=success&per_page=1')
HEAD = re.compile(r'[0-9a-f]{40}')
ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,119}')
FEED = 'data/articles.json'


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def deployed_sha(payload):
    runs = payload.get('workflow_runs', [])
    if not runs:
        raise ValueError('No successful Pages baseline was found.')
    run = runs[0]
    sha = run.get('head_sha', '')
    if (run.get('head_branch') != 'main' or run.get('conclusion') != 'success'
            or (run.get('head_repository') or {}).get('full_name') != REPOSITORY
            or not HEAD.fullmatch(sha)):
        raise ValueError('Successful Pages baseline could not be verified.')
    return sha


def article_ids(records):
    if not isinstance(records, list) or not records:
        raise ValueError('Article baseline or candidate is empty.')
    ids = set()
    for record in records:
        identifier = record.get('id') if isinstance(record, dict) else None
        if not isinstance(identifier, str) or not ID.fullmatch(identifier) or identifier in ids:
            raise ValueError('Article data contains a malformed or duplicate ID.')
        ids.add(identifier)
    return ids


def missing_ids(deployed, current):
    return sorted(article_ids(deployed) - article_ids(current))


def main():
    if os.environ['GITHUB_REPOSITORY'] != REPOSITORY:
        raise ValueError('Unexpected deployment repository.')
    token = os.environ['GITHUB_TOKEN']
    request = Request(RUNS, headers={'Authorization': 'Bearer ' + token,
                                      'Accept': 'application/vnd.github+json',
                                      'User-Agent': 'work-signal-article-id-guard'})
    with build_opener(NoRedirects()).open(request, timeout=20) as response:
        baseline = deployed_sha(json.load(response))
    subprocess.run(['git', 'merge-base', '--is-ancestor', baseline, 'HEAD'], check=True)
    deployed = json.loads(subprocess.check_output(['git', 'show', f'{baseline}:{FEED}']))
    missing = missing_ids(deployed, json.loads(Path(FEED).read_text(encoding='utf-8')))
    if missing:
        raise SystemExit('Published article IDs disappeared. Retain the original IDs or '
                         'prepare an explicit migration: ' + ', '.join(missing))
    print(f'Article IDs preserved against successful Pages baseline {baseline}.')


if __name__ == '__main__':
    main()
