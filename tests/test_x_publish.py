"""X account, authorization, spend cap, ledger and readback tests. No network."""
import copy
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from scripts import publish_x as x
from scripts import publish_social as social

CLOCK = datetime(2026, 10, 31, 3, tzinfo=timezone.utc)
CREDS = dict(SOCIAL_PUBLISH_ENABLED='true', X_PUBLISH_ENABLED='true',
             X_API_KEY='key', X_API_SECRET='secret', X_ACCESS_TOKEN='token',
             X_ACCESS_TOKEN_SECRET='token-secret', X_USERNAME='example_news', X_USER_ID='123')


def article(aid='new', **kwargs):
    value = dict(id=aid, title='確認された更新のポイント', summary='一次情報で影響条件を確認しました。',
                 source_url='https://example.org/official', published_at='2026-10-31',
                 status='published', score=90, social_publish=True)
    return {**value, **kwargs}


class MemoryLedger:
    def __init__(self, rows=None):
        self.rows = copy.deepcopy(rows or {})
        self.changes = []

    def read(self):
        return copy.deepcopy(self.rows), 'sha'

    def record(self, aid, platform, status, **kwargs):
        self.changes.append((aid, platform, status))
        self.rows.setdefault(aid, {})[platform] = dict(status=status, updated_at=CLOCK.isoformat(), **kwargs)

    def progress(self, aid, platform, stage, identifier):
        self.rows[aid][platform].update(stage=stage, container_id=identifier)


class XPublisherTests(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)
        self.live = patch.object(social, 'verify_live')
        self.live.start()
        self.addCleanup(self.live.stop)
        self.api = Mock()
        self.api.create.return_value = '456'
        self.api.verify_post.return_value = 'https://x.com/example_news/status/456'

    def run_x(self, feed, ledger=None, baseline=None, credentials=None):
        ledger = ledger or MemoryLedger()
        return x.run(feed, baseline or [], ledger, credentials or CREDS, clock=CLOCK, api=self.api)

    def test_existing_approvals_and_seo_edits_are_never_queued(self):
        before = [article('old')]
        feed = [article('old', title='SEO改稿'), article('new'),
                article('draft', status='draft'), article('no', social_publish=False), article('low', score=79)]
        self.assertEqual([a['id'] for a in x.candidates(feed, before, CLOCK)], ['new'])
        self.assertEqual(x.candidates(feed, feed, CLOCK), [])

    def test_explicit_media_restrictions_and_optional_x_optin(self):
        self.assertEqual(x.candidates([article(social_platforms=['threads'])], [], CLOCK), [])
        selected = article(social_platforms=['threads'], social_x_publish=True)
        self.assertEqual(x.candidates([selected], [], CLOCK), [selected])
        self.assertEqual(x.candidates([article(social_x_publish=False)], [], CLOCK), [])
        with self.assertRaises(ValueError):
            x.candidates([article(social_x_publish='true')], [], CLOCK)

    def test_stale_future_and_expired_articles_are_not_delivered(self):
        feed = [article('old', published_at='2026-10-27'), article('future', published_at='2026-11-01'),
                article('expired', social_review_valid_until='2026-10-31T02:59:00Z')]
        self.assertEqual(x.candidates(feed, [], CLOCK), [])

    def test_scoped_approval_does_not_publish_unrelated_pending_articles(self):
        feed = [article('one'), article('two')]
        self.assertEqual([a['id'] for a in x.candidates(feed, [], CLOCK, 'two')], ['two'])
        with self.assertRaises(ValueError):
            x.candidates(feed, [], CLOCK, 'missing')

    def test_either_off_switch_prevents_every_api_and_ledger_call(self):
        for name in ('X_PUBLISH_ENABLED', 'SOCIAL_PUBLISH_ENABLED'):
            ledger = Mock()
            self.assertEqual(self.run_x([article()], ledger, credentials={**CREDS, name: 'false'}), 0)
            ledger.read.assert_not_called()
        self.api.verify_account.assert_not_called()
        self.api.create.assert_not_called()

    def test_published_x_is_not_reposted_when_other_media_are_pending(self):
        ledger = MemoryLedger({'new': {'x': {'status': 'published', 'updated_at': CLOCK.isoformat()}}})
        self.assertEqual(self.run_x([article()], ledger), 0)
        self.api.verify_account.assert_not_called()
        self.api.create.assert_not_called()

    def test_uncertain_or_unknown_state_never_becomes_new_post(self):
        for status in ('attempting', 'needs_review'):
            ledger = MemoryLedger({'new': {'x': dict(status=status, updated_at=CLOCK.isoformat())}})
            self.assertEqual(self.run_x([article()], ledger), 1)
        for state in (None, {}, {'status': 'unknown'}, {'status': 'published'}):
            with self.assertRaises((RuntimeError, ValueError)):
                self.run_x([article()], MemoryLedger({'new': {'x': state}}))
        self.api.create.assert_not_called()

    def test_verified_delivery_keeps_other_channels_untouched(self):
        meta = {'threads': {'status': 'published', 'remote_id': '1'},
                'instagram': {'status': 'needs_review', 'error': {'code': 4, 'subcode': 2207051}}}
        ledger = MemoryLedger({'new': meta})
        self.assertEqual(self.run_x([article()], ledger), 0)
        self.assertEqual(ledger.rows['new']['threads'], meta['threads'])
        self.assertEqual(ledger.rows['new']['instagram'], meta['instagram'])
        self.assertEqual(ledger.rows['new']['x']['status'], 'published')
        self.assertEqual([status for _, _, status in ledger.changes], ['attempting', 'published'])
        self.api.verify_account.assert_called_once()
        self.api.verify_post.assert_called_once()
        self.assertIn('utm_source=x', self.api.create.call_args.args[0])

    def test_lost_response_is_held_and_rerun_never_sends_again(self):
        ledger = MemoryLedger()
        self.api.create.side_effect = RuntimeError('X API transport/response error')
        self.assertEqual(self.run_x([article()], ledger), 1)
        self.assertEqual(ledger.rows['new']['x']['status'], 'needs_review')
        self.assertEqual(self.run_x([article()], ledger), 1)
        self.api.create.assert_called_once()

    def test_failed_claim_and_wrong_account_cannot_send(self):
        ledger = MemoryLedger()
        ledger.record = Mock(side_effect=RuntimeError('Ledger HTTP 409'))
        self.assertEqual(self.run_x([article()], ledger), 1)
        self.api.create.assert_not_called()
        self.api.verify_account.side_effect = RuntimeError('Wrong X account; posting stopped')
        ledger = MemoryLedger()
        self.assertEqual(self.run_x([article()], ledger), 1)
        self.assertEqual(ledger.changes, [])

    def test_daily_limit_counts_uncertain_attempts_and_stops_at_three(self):
        ledger = MemoryLedger()
        feed = [article(str(i)) for i in range(6)]
        self.assertEqual(self.run_x(feed, ledger), 0)
        self.assertEqual(self.api.create.call_count, 3)
        self.assertEqual(self.run_x(feed, ledger), 0)
        self.assertEqual(self.api.create.call_count, 3)
        for row in ledger.rows.values():
            row['x']['status'] = 'needs_review'
        self.assertEqual(x.daily_attempts(ledger.rows, CLOCK), 3)

    def test_jst_day_boundary_is_used_not_utc_calendar_day(self):
        history = {'one': {'x': {'status': 'published', 'updated_at': '2026-10-30T15:00:00Z'}},
                   'two': {'x': {'status': 'needs_review', 'updated_at': '2026-10-30T14:59:59Z'}}}
        self.assertEqual(x.daily_attempts(history, CLOCK), 1)

    def test_missing_credentials_fail_before_any_x_request(self):
        self.assertEqual(self.run_x([article()], credentials={**CREDS, 'X_API_KEY': ''}), 1)
        self.api.verify_account.assert_not_called()
        self.api.create.assert_not_called()

    def test_shared_ledger_x_write_preserves_meta_and_rejects_unknown_x_history(self):
        ledger = x.XGithubLedger('owner/repo', 'github-token')
        meta = {'threads': {'status': 'published', 'remote_id': '1'}}
        response = Mock()
        response.__enter__ = Mock(return_value=Mock(status=200))
        response.__exit__ = Mock(return_value=False)
        with patch.object(ledger, 'read', return_value=({'new': copy.deepcopy(meta)}, 'sha')), \
                patch.object(social, 'urlopen', return_value=response) as write:
            ledger.record('new', 'x', 'attempting')
        request = write.call_args.args[0]
        stored = json.loads(__import__('base64').b64decode(json.loads(request.data)['content']))
        self.assertEqual(stored['new']['threads'], meta['threads'])
        self.assertEqual(stored['new']['x']['status'], 'attempting')
        with patch.object(ledger, 'read', return_value=({'new': {'x': {}}}, 'sha')), \
                patch.object(social, 'urlopen') as write:
            with self.assertRaises(RuntimeError):
                ledger.record('new', 'x', 'attempting')
            write.assert_not_called()

    def test_x_history_never_changes_meta_remaining_channels(self):
        self.assertEqual(social.remaining_platforms({'x': {'status': 'needs_review'}}),
                         ['threads', 'instagram', 'instagram_story'])

    def test_baseline_requires_real_ancestor_commit_not_arbitrary_ref(self):
        with self.assertRaises(ValueError):
            x.load_baseline('main')
        with patch.object(x.subprocess, 'run', side_effect=__import__('subprocess').CalledProcessError(1, 'git')):
            with self.assertRaises(__import__('subprocess').CalledProcessError):
                x.load_baseline('a' * 40)

    def test_setup_identification_never_posts_or_touches_ledger_or_article_data(self):
        with patch.object(sys, 'argv', ['publish_x.py', '--identify']), \
                patch.object(x, 'XAPI') as api, patch.object(x, 'XGithubLedger') as ledger, \
                patch.object(x, 'load_baseline') as baseline:
            api.return_value.identify_account.return_value = {'username': 'work_signal_jp', 'id': '123'}
            self.assertEqual(x.main(), 0)
            api.return_value.create.assert_not_called()
            ledger.assert_not_called()
            baseline.assert_not_called()

    def test_invalid_copy_does_not_claim_or_block_other_valid_x_articles(self):
        feed = [article('bad', score=95, social_x_text='URLなし'), article('good')]
        ledger = MemoryLedger()
        self.assertEqual(self.run_x(feed, ledger), 1)
        self.assertNotIn('bad', ledger.rows)
        self.assertEqual(ledger.rows['good']['x']['status'], 'published')
        self.api.create.assert_called_once()

    def test_invalid_copy_does_not_spend_on_repeated_profile_checks(self):
        ledger = MemoryLedger()
        self.assertEqual(self.run_x([article(social_x_text='URLなし')], ledger), 1)
        self.assertEqual(ledger.changes, [])
        self.api.verify_account.assert_not_called()
        self.api.create.assert_not_called()


class XAPITests(unittest.TestCase):
    def test_unconfigured_identity_and_nonpublishing_methods_never_call_api(self):
        api = x.XAPI({**CREDS, 'X_USER_ID': ''})
        with patch.object(api, 'request') as request:
            with self.assertRaises(ValueError):
                api.verify_account()
            request.assert_not_called()
        with patch.object(api.opener, 'open') as request:
            for method, path in [('DELETE', '/tweets/123'), ('POST', '/users/me'), ('GET', '/tweets')]:
                with self.assertRaises(ValueError):
                    api.request(method, path)
            request.assert_not_called()
    def test_account_identity_and_readback_require_matching_author_and_expanded_copy(self):
        api = x.XAPI(CREDS)
        with patch.object(api, 'request', return_value={'data': {'id': '123', 'username': 'EXAMPLE_NEWS'}}):
            self.assertEqual(api.verify_account()['id'], '123')
        with patch.object(api, 'request', return_value={'data': {'id': '999', 'username': 'example_news'}}):
            with self.assertRaises(RuntimeError):
                api.verify_account()
        post = {'data': {'id': '456', 'author_id': '123', 'text': 'Read https://t.co/test',
                         'entities': {'urls': [{'url': 'https://t.co/test', 'expanded_url': 'https://example.org/'}]}}}
        with patch.object(api, 'request', return_value=post):
            self.assertEqual(api.verify_post('456', 'Read https://example.org/'),
                             'https://x.com/example_news/status/456')
            with self.assertRaises(RuntimeError):
                api.verify_post('456', 'Different text')
            post['data']['author_id'] = '999'
            with self.assertRaises(RuntimeError):
                api.verify_post('456', 'Read https://example.org/')

    def test_api_error_never_exposes_raw_body_and_write_is_not_retried(self):
        api = x.XAPI(CREDS)
        error = HTTPError(x.API + '/tweets', 402, 'private-token', {}, io.BytesIO(b'private payload'))
        with patch.object(api.opener, 'open', side_effect=error) as call:
            with self.assertRaisesRegex(RuntimeError, '^X API HTTP 402$'):
                api.create('Approved text')
            call.assert_called_once()
        with patch.object(api, 'request', return_value={'data': {}}):
            with self.assertRaisesRegex(RuntimeError, 'ambiguous'):
                api.create('Approved text')

    def test_oauth_is_deterministic_and_only_signs_the_official_https_api(self):
        header = x.oauth_header('GET', x.API + '/users/me?user.fields=id%2Cusername', CREDS,
                                nonce='known-nonce', epoch=1700000000)
        self.assertEqual(header, x.oauth_header('GET', x.API + '/users/me?user.fields=id%2Cusername', CREDS,
                                              nonce='known-nonce', epoch=1700000000))
        self.assertIn('oauth_signature_method="HMAC-SHA1"', header)
        self.assertNotIn('token-secret', header)
        self.assertNotEqual(header, x.oauth_header('GET', x.API + '/users/me', CREDS,
                                                 nonce='known-nonce', epoch=1700000000))
        with self.assertRaises(ValueError):
            x.oauth_header('POST', 'https://other.example/2/tweets', CREDS)


if __name__ == '__main__':
    unittest.main()
