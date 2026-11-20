import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode
from scripts import facebook_channel as fb
from scripts import publish_social as social
from scripts.check_social_channel_outcomes import evaluate
from scripts.social_queue import batch_ids, backlog_report
from scripts.reconcile_social_recovery import reconcile_facebook

NOW = datetime(2026, 11, 19, 0, 0, tzinfo=timezone.utc)
ARTICLE = dict(id='fresh-facebook', title='公式発表のタイトル', summary='重要な条件を照合した要約です。',
               source_url='https://example.org/official', social_publish=True, score=85,
               status='published', published_at='2026-11-19', published_at_time='2026-11-18T23:59:00Z',
               social_platforms=['facebook'])
CONFIG = dict(schema='work-signal-facebook-channel-v1', page_id=fb.PAGE_ID, graph_version='v27.0',
              new_articles_from='2026-11-18T23:00:00Z', activated_at='2026-11-18T23:30:00Z', excluded_existing_ids=['historical'])
URL = social.article_url(ARTICLE)
POST_ID = fb.PAGE_ID + '_123456'
LIVE = dict(id=POST_ID, **{'from': {'id': fb.PAGE_ID}}, is_published=True,
            message=fb.text(ARTICLE, URL), permalink_url='https://www.facebook.com/'+POST_ID,
            attachments={'data': [{'target': {'url': URL}}]})


class Ledger:
    def __init__(self, prior=None, claim_fails=False, progress_fails=False):
        self.rows = {ARTICLE['id']: copy.deepcopy(prior or {})}
        self.events = []
        self.claim_fails, self.progress_fails = claim_fails, progress_fails
    def read(self):
        return self.rows, 'sha'
    def record(self, aid, kind, status, **values):
        if status == 'attempting' and self.claim_fails:
            raise RuntimeError('lost ledger response')
        self.events.append(('ledger', status))
        self.rows.setdefault(aid, {})[kind] = dict(status=status, **values)
    def progress(self, aid, kind, stage, cid):
        self.events.append(('stage', stage))
        if self.progress_fails:
            raise RuntimeError('unknown stage write')


class FacebookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'.github').mkdir()
        (self.root/'.github/facebook-channel.json').write_text(json.dumps(CONFIG))
        p = patch.object(social, 'ROOT', self.root); p.start(); self.addCleanup(p.stop)
        self.creds = dict(SOCIAL_PUBLISH_ENABLED='true', FACEBOOK_PUBLISH_ENABLED='true',
                          FACEBOOK_PAGE_ACCESS_TOKEN='test-secret')

    def test_legacy_and_explicit_exclusions_do_not_acquire_facebook(self):
        self.assertEqual(social.requested_platforms({}), list(social.LEGACY_DEFAULT_PLATFORMS))
        self.assertEqual(social.requested_platforms(dict(social_platforms=['threads'])), ['threads'])
        self.assertIn('facebook', social.GithubLedger.platforms)

    def test_rollout_old_missing_naive_future_and_pre_activation_rejected(self):
        self.assertTrue(fb.eligible(ARTICLE, self.root, NOW))
        for changes in [dict(id='historical'), dict(published_at_time=None),
                        dict(published_at_time='2026-11-18T23:59:00'),
                        dict(published_at_time='2026-11-19T01:00:00Z'),
                        dict(published_at_time='2026-11-18T22:00:00Z'),
                        dict(published_at='2026-11-18')]:
            self.assertFalse(fb.eligible({**ARTICLE, **changes}, self.root, NOW))
        (self.root/'.github/facebook-channel.json').write_text(json.dumps({**CONFIG,'activated_at':None}))
        self.assertFalse(fb.eligible(ARTICLE, self.root, NOW))
        (self.root/'.github/facebook-channel.json').unlink()
        self.assertFalse(social.facebook_eligible(ARTICLE))

    def test_plain_canonical_message_and_link_no_utm(self):
        self.assertEqual(fb.text(ARTICLE, URL), ARTICLE['title']+'\n\n'+ARTICLE['summary']+'\n\n'+URL)
        self.assertTrue(fb.canonical_link(URL+'?fbclid=abc', URL))
        for url in [URL+'x', URL+'?utm_source=facebook', URL+'#other', URL.replace('https:', 'http:')]:
            self.assertFalse(fb.canonical_link(url, URL))
        with self.assertRaises(ValueError):
            fb.text({**ARTICLE, 'summary': 'https://example.org/?utm_source=x'}, URL)

    def test_verified_post_requires_page_body_permalink_and_attachment(self):
        self.assertEqual(fb.matches(ARTICLE, [LIVE], URL)[0]['permalink'], LIVE['permalink_url'])
        for change in [{'id':'other_123'}, {'from':{'id':'other'}}, {'is_published':False},
                       {'message':'different'}, {'permalink_url':'https://facebook.com.evil/post'},
                       {'attachments':{'data':[]}}]:
            self.assertFalse(fb.matches(ARTICLE, [{**LIVE, **change}], URL))

    def test_feed_card_can_move_url_out_of_message_and_use_facebook_shim(self):
        shim = 'https://l.facebook.com/l.php?' + urlencode({'u': URL+'?fbclid=abc', 'h': 'example'})
        observed = {**LIVE, 'message': ARTICLE['title']+'\n\n'+ARTICLE['summary'],
                    'attachments': {'data': [{'url': shim}]}}
        self.assertEqual(fb.matches(ARTICLE, [observed], URL)[0]['id'], POST_ID)
        for link in [shim.replace('l.facebook.com', 'l.facebook.com.invalid'),
                     shim + '&u=' + URL, shim.replace('/l.php', '/else'),
                     'https://l.facebook.com/l.php?' + urlencode({'u': URL+'?utm_source=test'})]:
            self.assertFalse(fb.matches(ARTICLE, [{**observed, 'attachments': {'data':[{'url':link}]}}], URL))
        with self.assertRaises(RuntimeError):
            fb.existing(lambda *a, **k: {'data':[{**observed, 'message':'conflict'}]}, ARTICLE, 'test', URL)

    def test_followup_reads_recorded_post_id_without_rearming_unknowns(self):
        receipt = dict(status='needs_review', stage='publish_response_received', container_id=POST_ID)
        unknown = dict(status='needs_review')
        unseen = {**ARTICLE, 'id':'pre-send-failure'}
        ledger = Ledger({'facebook':receipt})
        ledger.rows[unseen['id']] = {'facebook':unknown}
        def api(url, **kwargs):
            self.assertEqual(kwargs.get('method', 'GET'), 'GET')
            return {'id':fb.PAGE_ID,'name':'WORK-SIGNAL.jp'} if '/me?' in url else LIVE
        with (
            patch.object(social, 'request_json', side_effect=api) as request,
            patch('scripts.reconcile_social_recovery.save_verified') as save,
        ):
            reconcile_facebook(ledger, [ARTICLE, unseen], 'test')
        self.assertEqual(request.call_count, 2)
        self.assertEqual(save.call_count, 1)
        _, aid, platform, expected, replacement = save.call_args.args
        self.assertEqual((aid, platform, expected), (ARTICLE['id'], 'facebook', receipt))
        self.assertEqual(replacement['status'], 'published')
        self.assertEqual(replacement['remote_id'], POST_ID)
        self.assertEqual(ledger.rows[unseen['id']]['facebook'], unknown)

    def test_incomplete_pagination_or_conflicting_duplicate_withholds(self):
        def api(*args, **kwargs):
            return dict(data=[LIVE], paging={'next':'https://evil.test/?access_token=secret'})
        with self.assertRaises(RuntimeError): fb.history(api, 'test')
        with self.assertRaises(RuntimeError):
            fb.existing(lambda *a, **k: {'data':[{**LIVE, 'message':'manual different caption'}]}, ARTICLE, 'test', URL)
        with self.assertRaises(RuntimeError):
            fb.existing(lambda *a, **k: {'data':[LIVE, LIVE]}, ARTICLE, 'test', URL)

    def test_wrong_user_token_or_wrong_page_fails(self):
        for identity in ['personal-user', '99999', '61596301937684']:
            with self.assertRaises(RuntimeError):
                fb.verify_account(lambda *a, **k: {'id':identity,'name':'WORK-SIGNAL.jp'}, 'test')

    def execute(self, ledger, *, lose_response=False, live=True):
        calls = []
        def api(url, **kw):
            calls.append((url, kw))
            if '/me?' in url: return {'id':fb.PAGE_ID, 'name':'WORK-SIGNAL.jp'}
            if kw.get('method') == 'POST':
                self.assertEqual(ledger.events[-1], ('stage','publish_requested'))
                self.assertIn(('ledger','attempting'), ledger.events)
                self.assertEqual(kw['data']['link'], URL)
                self.assertNotIn('utm_', json.dumps(kw['data']))
                if lose_response: raise RuntimeError('lost Meta write response')
                return {'id':POST_ID}
            if '/published_posts?' in url:
                # Preflight empty; GET-only reconciliation can see the post after the write.
                posted = any(k.get('method') == 'POST' for _, k in calls)
                return {'data':[LIVE] if posted and live else []}
            return LIVE if live else {'id':POST_ID}
        with patch.object(social, 'request_json', side_effect=api), patch.object(social, 'verify_live'),\
             patch.object(social, 'facebook_eligible', return_value=True):
            result = social.run([ARTICLE], ledger, self.creds)
        return result, calls

    def test_full_delivery_is_claimed_then_posted_once_and_confirmed(self):
        ledger = Ledger()
        result, calls = self.execute(ledger)
        self.assertEqual(result, 0)
        self.assertEqual(sum(kw.get('method')=='POST' for _,kw in calls), 1)
        self.assertEqual(ledger.rows[ARTICLE['id']]['facebook']['remote_id'], POST_ID)
        self.assertEqual(ledger.rows[ARTICLE['id']]['facebook']['status'], 'published')

    def test_lost_response_recovers_read_only_no_second_post(self):
        ledger = Ledger()
        result, calls = self.execute(ledger, lose_response=True)
        self.assertEqual(result, 0)
        self.assertEqual(sum(kw.get('method')=='POST' for _,kw in calls), 1)
        self.assertEqual(ledger.rows[ARTICLE['id']]['facebook']['status'], 'published')

    def test_unknown_stays_review_and_second_run_never_resends(self):
        ledger = Ledger()
        result, calls = self.execute(ledger, lose_response=True, live=False)
        self.assertEqual(result, 1)
        self.assertEqual(ledger.rows[ARTICLE['id']]['facebook']['status'], 'needs_review')
        result, calls = self.execute(ledger)
        self.assertFalse(any(kw.get('method')=='POST' for _,kw in calls))
        self.assertEqual(result, 1)

    def test_missing_durable_claim_or_stage_prevents_meta_write(self):
        for ledger in [Ledger(claim_fails=True), Ledger(progress_fails=True)]:
            result, calls = self.execute(ledger)
            self.assertEqual(result, 1)
            self.assertFalse(any(kw.get('method')=='POST' for _,kw in calls))

    def test_disabled_facebook_does_not_block_threads(self):
        self.creds['FACEBOOK_PUBLISH_ENABLED']='false'
        self.creds.update(THREADS_ACCESS_TOKEN='test', THREADS_USER_ID='123')
        article={**ARTICLE,'social_platforms':['threads','facebook']}
        with patch.object(social,'facebook_eligible',return_value=True),\
             patch.object(social,'verify_account',return_value={}), patch.object(social,'verify_live'),\
             patch.object(social,'publish_threads',return_value='1') as send,\
             patch.object(social,'verify_threads_delivery',return_value={'id':'1'}),\
             patch.object(social,'request_json') as api:
            ledger=Ledger()
            self.assertEqual(social.run([article],ledger,self.creds),1)
            send.assert_called_once(); api.assert_not_called()
            self.assertEqual(ledger.rows[ARTICLE['id']]['threads']['status'],'published')
            self.assertNotIn('facebook',ledger.rows[ARTICLE['id']])

    def test_queue_and_outcomes_count_facebook_independently(self):
        with patch.object(social,'facebook_eligible',return_value=True):
            self.assertEqual(batch_ids([ARTICLE],{},clock=NOW),[ARTICLE['id']])
            self.assertEqual(batch_ids([ARTICLE],{ARTICLE['id']:{'facebook':{'status':'attempting'}}},clock=NOW),[])
            self.assertEqual(backlog_report([ARTICLE],{},NOW)['counts']['facebook']['ready'],1)
        report={'articles':[{'id':ARTICLE['id'],'platforms':{'facebook':'published'}}], 'failures':[]}
        self.assertFalse(evaluate(report,[ARTICLE],{})[0])
        ledger={ARTICLE['id']:{'facebook':{'status':'published','remote_id':POST_ID,'permalink':LIVE['permalink_url']}}}
        self.assertTrue(evaluate(report,[ARTICLE],ledger)[0])


if __name__ == '__main__': unittest.main()
