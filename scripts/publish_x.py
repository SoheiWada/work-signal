#!/usr/bin/env python3
"""Independent official X publisher. Disabled until account, budget and baseline are set.

Never changes approval flags or retries uncertain writes. Uses the existing shared
ledger and workflow lock, with X-only history validation and completion reporting.
"""
import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

try:
    from . import publish_social as social
except ImportError:
    import publish_social as social

JST = timezone(timedelta(hours=9))
DAILY_LIMIT = 3
API = 'https://api.x.com/2'
KEYS = ('X_API_KEY', 'X_API_SECRET', 'X_ACCESS_TOKEN', 'X_ACCESS_TOKEN_SECRET')
SHA = re.compile(r'[0-9a-f]{40}')
REPORT = 'x-delivery-status.json'


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('Timezone-aware timestamp required')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timezone-aware timestamp required')
    return result


def x_state(existing):
    if not isinstance(existing, dict):
        raise RuntimeError('Invalid X publication history')
    if 'x' not in existing:
        return None
    state = existing['x']
    if not isinstance(state, dict) or state.get('status') not in social.STATUSES:
        raise RuntimeError('Unknown X publication state; manual review required')
    timestamp(state.get('updated_at'))
    if state['status'] == 'deferred':
        timestamp(state.get('next_attempt_at'))
    return state


class XGithubLedger(social.GithubLedger):
    # The Meta publisher keeps its existing channel validation and defaults.
    platforms = ('x',)

    def validate_history(self, existing):
        x_state(existing)


def x_selected(article):
    if 'social_platforms' in article:
        social.requested_platforms(article)  # Reject malformed existing media choices.
    flag = article.get('social_x_publish')
    if flag is not None and type(flag) is not bool:
        raise ValueError('social_x_publish must be boolean')
    if flag is not None:
        return flag
    # Preserve explicit existing media exclusions. A reviewed X opt-in can add X
    # without changing the legacy social_platforms enum used by Meta/editor.
    return 'social_platforms' not in article


def candidates(feed, baseline_feed, clock, scope=''):
    baseline_ids = {a['id'] for a in social.approved_articles(baseline_feed)}
    approved = social.approved_in_scope(feed, scope)
    chosen = []
    for article in approved:
        if article['id'] in baseline_ids or not x_selected(article):
            continue
        published = datetime.fromisoformat(article['published_at'])
        published_day = (published.astimezone(JST).date() if published.tzinfo else published.date())
        age = clock.astimezone(JST).date() - published_day
        if age < timedelta(0) or age > timedelta(days=2):
            continue
        if article.get('social_review_valid_until') and timestamp(article['social_review_valid_until']) <= clock:
            continue
        chosen.append(article)
    return sorted(chosen, key=lambda a: (
        {'CRITICAL': 0, 'HIGH': 1}.get(a.get('social_security_severity'), 2),
        -float(a.get('score') or 0), a['published_at'], a['id']))


def daily_attempts(rows, clock):
    if not isinstance(rows, dict):
        raise RuntimeError('Invalid X ledger')
    total = 0
    for history in rows.values():
        state = x_state(history)
        if state and state['status'] in ('attempting', 'published', 'needs_review'):
            total += timestamp(state['updated_at']).astimezone(JST).date() == clock.astimezone(JST).date()
    return total


def ready(state, clock):
    return state is None or (state['status'] == 'deferred'
                             and timestamp(state['next_attempt_at']) <= clock)


def x_copy(article):
    value = {key: article[key] for key in ('title', 'summary', 'source_url')}
    value.update(canonical_url=social.article_url(article),
                 tracked_url=social.article_url(article) + '?' + urlencode({
                     'utm_source': 'x', 'utm_medium': 'social',
                     'utm_campaign': 'work_signal', 'utm_content': article['id']}))
    for key in ('social_x_text', 'social_security_severity'):
        if key in article:
            value[key] = article[key]
    result = subprocess.run(['node', str(social.ROOT / 'scripts/x_text.mjs')],
                            input=json.dumps(value), capture_output=True, text=True,
                            timeout=20, check=False)
    if result.returncode:
        raise ValueError('X copy invalid or twitter-text dependency missing')
    rendered = json.loads(result.stdout)
    return rendered['text'], rendered['weighted_length']


def oauth_header(method, url, credentials, *, nonce=None, epoch=None):
    """OAuth 1.0a signature. JSON bodies are not form parameters."""
    if any(not credentials.get(key) for key in KEYS):
        raise ValueError('X OAuth credentials incomplete')
    parts = urlsplit(url)
    if parts.scheme != 'https' or parts.netloc != 'api.x.com' or parts.fragment:
        raise ValueError('Only the official X API is allowed')
    enc = lambda value: quote(str(value), safe='~-._')
    params = {
        'oauth_consumer_key': credentials['X_API_KEY'],
        'oauth_token': credentials['X_ACCESS_TOKEN'],
        'oauth_nonce': nonce or secrets.token_hex(16),
        'oauth_timestamp': str(int(time.time()) if epoch is None else epoch),
        'oauth_signature_method': 'HMAC-SHA1', 'oauth_version': '1.0',
    }
    pairs = [(enc(k), enc(v)) for k, v in list(params.items()) + parse_qsl(parts.query)]
    normalized = '&'.join(k + '=' + v for k, v in sorted(pairs))
    base_url = parts._replace(query='', fragment='').geturl()
    base = '&'.join((method.upper(), enc(base_url), enc(normalized)))
    key = enc(credentials['X_API_SECRET']) + '&' + enc(credentials['X_ACCESS_TOKEN_SECRET'])
    params['oauth_signature'] = base64.b64encode(
        hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()).decode()
    return 'OAuth ' + ', '.join(enc(k) + '="' + enc(v) + '"' for k, v in sorted(params.items()))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class XAPI:
    def __init__(self, credentials):
        self.credentials = credentials
        self.opener = build_opener(NoRedirect())

    def request(self, method, path, data=None):
        allowed = ((method == 'POST' and path == '/tweets')
                   or (method == 'GET' and re.fullmatch(r'/(?:users/me|tweets/[0-9]+)(?:\?[^\s]*)?', path)))
        if not allowed:
            raise ValueError('Unsupported X API operation')
        url = API + path
        headers = {'Authorization': oauth_header(method, url, self.credentials),
                   'Accept': 'application/json', 'Content-Type': 'application/json',
                   'User-Agent': 'WORK-SIGNAL-X/1.0'}
        payload = json.dumps(data, ensure_ascii=False).encode() if data is not None else None
        req = Request(url, method=method, data=payload, headers=headers)
        try:
            with self.opener.open(req, timeout=30) as response:
                result = json.loads(response.read(1000000))
        except HTTPError as exc:
            # No raw response body, authentication header or token in logs.
            exc.close()
            raise RuntimeError('X API HTTP ' + str(exc.code)) from None
        except (URLError, TimeoutError, ValueError):
            raise RuntimeError('X API transport/response error') from None
        if not isinstance(result, dict) or result.get('errors'):
            raise RuntimeError('X API response is incomplete')
        return result

    def identify_account(self):
        profile = self.request('GET', '/users/me').get('data', {})
        if (not isinstance(profile, dict)
                or not re.fullmatch(r'[0-9]+', str(profile.get('id', '')))
                or not re.fullmatch(r'[A-Za-z0-9_]{1,15}', str(profile.get('username', '')))):
            raise RuntimeError('X account response is incomplete')
        return profile

    def verify_account(self):
        expected_id = self.credentials.get('X_USER_ID', '')
        expected_name = self.credentials.get('X_USERNAME', '')
        if not re.fullmatch(r'[0-9]+', expected_id) or not re.fullmatch(r'[A-Za-z0-9_]{1,15}', expected_name):
            raise ValueError('Set X_USER_ID and X_USERNAME to the verified target account')
        profile = self.identify_account()
        if (str(profile.get('id')) != expected_id
                or str(profile.get('username', '')).lower() != expected_name.lower()):
            raise RuntimeError('Wrong X account; posting stopped')
        return profile

    def create(self, text):
        post = self.request('POST', '/tweets', {'text': text}).get('data', {})
        identifier = str(post.get('id', ''))
        if not re.fullmatch(r'[0-9]+', identifier):
            raise RuntimeError('X post result is ambiguous')
        return identifier

    def verify_post(self, identifier, expected_text):
        post = self.request('GET', '/tweets/' + identifier + '?tweet.fields=author_id,entities').get('data', {})
        text = post.get('text', '')
        for item in post.get('entities', {}).get('urls', []):
            if item.get('url') and item.get('expanded_url'):
                text = text.replace(item['url'], item['expanded_url'])
        import unicodedata
        if (str(post.get('id')) != identifier
                or str(post.get('author_id')) != self.credentials['X_USER_ID']
                or unicodedata.normalize('NFC', text) != unicodedata.normalize('NFC', expected_text)):
            raise RuntimeError('X post readback does not match the approved copy/account')
        return 'https://x.com/' + self.credentials['X_USERNAME'] + '/status/' + identifier


def report(articles, rows, errors=(), *, clock=None, disabled=False):
    clock = clock or datetime.now(timezone.utc)
    used = daily_attempts(rows, clock)
    details = []
    for article in articles:
        state = x_state(rows.get(article['id'], {}))
        status = state['status'] if state else ('waiting_daily_limit' if used >= DAILY_LIMIT else 'pending')
        details.append({'article_id': article['id'], 'status': status,
                        **({'permalink': state['permalink']} if state and state.get('permalink') else {})})
    result = {'checked_at': clock.isoformat(), 'platform': 'x', 'disabled': disabled,
              'daily_limit': DAILY_LIMIT, 'attempts_today_jst': used,
              'articles': details, 'errors': list(errors)}
    if os.environ.get('X_REPORT_ENABLED') == 'true':
        (social.ROOT / REPORT).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as output:
            output.write('\n## X delivery (independent of Meta)\n\n')
            output.write('Disabled; no X requests.\n' if disabled else 'JST daily attempt limit: 3.\n')
            output.write('\n| Article | State |\n|---|---|\n')
            for item in details:
                output.write('| ' + item['article_id'] + ' | ' + item['status'] + ' |\n')
            for error in errors:
                output.write('\n' + error + '\n')
    print('X_DELIVERY_SUMMARY', json.dumps(result, ensure_ascii=False))
    return result


def run(articles, baseline, ledger, credentials, *, clock=None, api=None):
    clock = clock or datetime.now(timezone.utc)
    if credentials.get('X_PUBLISH_ENABLED') != 'true' or credentials.get('SOCIAL_PUBLISH_ENABLED') != 'true':
        report([], {}, clock=clock, disabled=True)
        return 0
    chosen = candidates(articles, baseline, clock, credentials.get('X_SCOPE_ARTICLE_IDS', ''))
    rows, _ = ledger.read()
    # Validate all X history before computing the spend cap.
    used = daily_attempts(rows, clock)
    pending = [a for a in chosen if ready(x_state(rows.get(a['id'], {})), clock)]
    if not pending or used >= DAILY_LIMIT:
        report(chosen, rows, clock=clock)
        return int(any(x_state(rows.get(a['id'], {})) and
                       x_state(rows[a['id']])['status'] in ('attempting', 'needs_review') for a in chosen))
    if any(not credentials.get(key) for key in KEYS):
        report(chosen, rows, ['X OAuth credentials incomplete; no posts'], clock=clock)
        return 1
    api = api or XAPI(credentials)
    api.verify_account()  # Verified identity before any durable claim or POST.
    errors, attempted = [], 0
    for article in pending:
        rows, _ = ledger.read()
        if attempted >= DAILY_LIMIT or daily_attempts(rows, clock) >= DAILY_LIMIT:
            break
        if not ready(x_state(rows.get(article['id'], {})), clock):
            continue
        try:
            text, _ = x_copy(article)
            social.verify_live(social.article_url(article))
        except (ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            errors.append(article['id'] + ': X preflight ' +
                          (str(exc) if type(exc) in (ValueError, RuntimeError) else type(exc).__name__))
            continue
        claimed, remote = False, ''
        try:
            ledger.record(article['id'], 'x', 'attempting')
            claimed = True
            attempted += 1
            remote = api.create(text)  # Exactly one write; never automatic retry.
            ledger.progress(article['id'], 'x', 'post_created', remote)
            permalink = api.verify_post(remote, text)
            ledger.record(article['id'], 'x', 'published', remote_id=remote, permalink=permalink)
        except Exception as exc:
            if claimed:
                try:
                    ledger.record(article['id'], 'x', 'needs_review', remote_id=remote,
                                  reason='x_result_requires_manual_review')
                except Exception:
                    pass  # The original durable attempting claim still prevents resends.
            # Only known local errors are loggable; never echo an API payload.
            detail = str(exc) if type(exc) in (RuntimeError, ValueError) else type(exc).__name__
            errors.append(article['id'] + ': ' + detail)
            break  # Authentication/quota/uncertain results must not generate a burst.
    rows, _ = ledger.read()
    report(chosen, rows, errors, clock=clock)
    uncertain = any(x_state(rows.get(a['id'], {})) and
                    x_state(rows[a['id']])['status'] in ('attempting', 'needs_review') for a in chosen)
    return int(bool(errors) or uncertain)


def load_baseline(value):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise ValueError('X_PUBLISH_START_SHA must be the full activation baseline commit')
    subprocess.run(['git', 'merge-base', '--is-ancestor', value, 'HEAD'], cwd=social.ROOT,
                   check=True, capture_output=True)
    content = subprocess.check_output(['git', 'show', value + ':data/articles.json'],
                                      cwd=social.ROOT, text=True)
    result = json.loads(content)
    if not isinstance(result, list):
        raise ValueError('Invalid X approval baseline')
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--check', action='store_true', help='GET account only; no posting or ledger writes')
    parser.add_argument('--identify', action='store_true', help='GET connected username/ID for initial configuration only')
    args = parser.parse_args()
    credentials = dict(os.environ)
    try:
        if sum((args.live, args.check, args.identify)) > 1:
            raise ValueError('Choose only one X operation')
        if args.identify:
            profile = XAPI(credentials).identify_account()
            print('X_ACCOUNT_FOUND (compare with the intended WORK SIGNAL account)', profile['username'], profile['id'])
            return 0
        if args.check:
            profile = XAPI(credentials).verify_account()
            print('X_ACCOUNT_VERIFIED', profile['username'], profile['id'])
            return 0
        articles = json.loads((social.ROOT / 'data/articles.json').read_text())
        if not args.live:
            # Offline preview only. Existing articles shown here are not queued.
            previews = [{'article_id': a['id'], 'text': x_copy(a)[0]} for a in
                        social.approved_articles(articles)[:3]]
            print(json.dumps({'mode': 'offline_preview_not_a_queue', 'posts': previews}, ensure_ascii=False, indent=2))
            return 0
        if credentials.get('X_PUBLISH_ENABLED') != 'true' or credentials.get('SOCIAL_PUBLISH_ENABLED') != 'true':
            report([], {}, disabled=True)
            return 0
        baseline = load_baseline(credentials.get('X_PUBLISH_START_SHA', ''))
        ledger = XGithubLedger(credentials.get('GITHUB_REPOSITORY', ''), credentials.get('GITHUB_TOKEN', ''))
        return run(articles, baseline, ledger, credentials)
    except Exception as exc:
        detail = str(exc) if type(exc) in (ValueError, RuntimeError) else type(exc).__name__
        report([], {}, ['X stopped: ' + detail])
        return 1


if __name__ == '__main__':
    sys.exit(main())
