import unittest

from scripts.check_article_ids import REPOSITORY, deployed_sha, missing_ids


class ArticleIdGuardTests(unittest.TestCase):
    def test_updates_new_publications_and_retained_withdrawals_keep_ids(self):
        old = [{'id': 'first', 'status': 'published'}, {'id': 'second', 'status': 'published'}]
        new = [{'id': 'first', 'title': 'Revised'}, {'id': 'second', 'status': 'withdrawn'},
               {'id': 'third', 'status': 'published'}]
        self.assertEqual(missing_ids(old, new), [])
        self.assertEqual(missing_ids(old, [{'id': 'first'}, {'id': 'second-revised'}]), ['second'])

    def test_baseline_is_the_successful_main_and_malformed_ids_are_rejected(self):
        run = {'head_branch': 'main', 'conclusion': 'success', 'head_sha': 'a' * 40,
               'head_repository': {'full_name': REPOSITORY}}
        self.assertEqual(deployed_sha({'workflow_runs': [run]}), 'a' * 40)
        with self.assertRaises(ValueError):
            deployed_sha({'workflow_runs': [{**run, 'conclusion': 'failure'}]})
        with self.assertRaises(ValueError):
            missing_ids([{'id': 'first'}], [{'id': 'first'}, {'id': 'first'}])
