"""Notify IndexNow of new or substantively changed, deployed article URLs."""
import argparse
from hashlib import sha256
from http.client import HTTPSConnection
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from time import sleep
from urllib.parse import urlsplit

try:
    from .seo_metadata import editorial_content
    from .site_identity import BASE
except ImportError:
    from seo_metadata import editorial_content
    from site_identity import BASE

KEY = 'e24940f2691bf99d6c2bc6ab770827a3'
KEY_FILE = KEY + '.txt'
HOST = urlsplit(BASE).netloc
# Initial approved article snapshot, matched to the live feed before rollout.
BOOTSTRAP_REVISION = '7e0a8d0b2b39f7ccbb42b4ec8c951a3babe79ae1'


class LiveDeploymentPending(ValueError):
    """The Pages artifact is deployed but the public edge has an older copy."""


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + '\n', encoding='utf-8')


def article_snapshot(feed):
    if not isinstance(feed, list):
        raise ValueError('Invalid article feed')
    snapshot = {}
    for item in feed:
        if not isinstance(item, dict):
            raise ValueError('Invalid article record')
        if item.get('status') != 'published':
            continue
        identifier = item.get('id', '')
        if not isinstance(identifier, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,119}', identifier) or identifier in snapshot:
            raise ValueError('Invalid or duplicate article ID')
        content = editorial_content(item)
        for field in ('category', 'published_at', 'published_at_time', 'reading_format_override'):
            if field in item:
                content[field] = item[field]
        fingerprint = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        snapshot[identifier] = sha256(fingerprint.encode('utf-8')).hexdigest()
    return snapshot


def changed_urls(previous, deployed):
    return [BASE + f'articles/{identifier}/' for identifier, digest in sorted(deployed.items())
            if previous.get(identifier) != digest]


def request(host, method, path, payload=None):
    # Fixed HTTPS endpoints, bounded reads and no redirect following.
    connection = HTTPSConnection(host, timeout=8)
    try:
        body = json.dumps(payload).encode('utf-8') if payload is not None else None
        headers = {'User-Agent': 'WORK-SIGNAL-IndexNow/1.0', 'Cache-Control': 'no-cache'}
        if body is not None:
            headers['Content-Type'] = 'application/json; charset=utf-8'
        connection.request(method, path, body=body, headers=headers)
        with connection.getresponse() as response:
            if method == 'POST' or response.status != 200:
                return response.status, b''
            body = response.read(8 * 1024 * 1024 + 1)
            if len(body) > 8 * 1024 * 1024:
                raise ValueError('Public response exceeded size limit')
            return response.status, body
    finally:
        connection.close()


def submit(previous, deployed, deployment_id, fetch=request):
    urls = changed_urls(previous, deployed)
    if not urls:
        return None
    if not re.fullmatch(r'[0-9]+-[0-9]+', deployment_id):
        raise ValueError('Invalid deployment identifier')
    query = '?indexnow_deploy=' + deployment_id
    status, body = fetch(HOST, 'GET', '/data/articles.json' + query)
    if status != 200 or article_snapshot(json.loads(body)) != deployed:
        raise LiveDeploymentPending('The newly built article feed is not live yet')
    status, body = fetch(HOST, 'GET', '/' + KEY_FILE + query)
    if status != 200 or body.strip() != KEY.encode('utf-8'):
        raise LiveDeploymentPending('The IndexNow key file is not live yet')
    status, _ = fetch('api.indexnow.org', 'POST', '/IndexNow',
                      {'host': HOST, 'key': KEY, 'keyLocation': BASE + KEY_FILE, 'urlList': urls})
    if status not in (200, 202):
        raise ValueError(f'IndexNow returned HTTP {status}')
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('feed', type=Path, help='Approved feed from the successful Pages build')
    parser.add_argument('state', type=Path, help='Last successfully submitted article snapshot')
    parser.add_argument('deployment_id', help='GitHub run ID and attempt')
    args = parser.parse_args()
    try:
        if args.state.exists():
            previous = read_json(args.state)
        else:
            baseline = subprocess.check_output(
                ['git', 'show', BOOTSTRAP_REVISION + ':data/articles.json'])
            previous = article_snapshot(json.loads(baseline))
        deployed = article_snapshot(read_json(args.feed))
        # Retry propagation checks only. A POST with an unknown outcome is left
        # for the next successful deployment against the same saved baseline.
        for delay in (2, 5):
            try:
                status = submit(previous, deployed, args.deployment_id)
                break
            except LiveDeploymentPending:
                sleep(delay)
        else:
            status = submit(previous, deployed, args.deployment_id)
        if status is None:
            print('IndexNow: no new or changed articles')
            return
        write_json(args.state, deployed)
        if output := os.environ.get('GITHUB_OUTPUT'):
            with Path(output).open('a', encoding='utf-8') as stream:
                stream.write('updated=true\n')
        print(f'IndexNow: {len(changed_urls(previous, deployed))} URL(s), HTTP {status}')
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f'::warning::IndexNow notification pending: {error}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
