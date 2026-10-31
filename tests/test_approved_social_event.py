"""SEO changes grant no new approvals; wakeups can drain safe existing backlog."""
import unittest
from pathlib import Path
from scripts.approved_social_event import approvals, eligible
from scripts.publish_social import approved_in_scope


ROOT = Path(__file__).resolve().parents[1]


def article(aid="one", **kwargs):
    row = dict(id=aid, title="Reviewed", summary="A", source_url="https://example.org",
               published_at="2026-10-30", status="published", score=92, social_publish=True)
    row.update(kwargs)
    return row


class ApprovedSocialEventTests(unittest.TestCase):
    def test_only_explicit_new_approval_triggers(self):
        older = [article("existing")]
        newer = [article("existing", title="Edited for SEO"), article("new")]
        self.assertEqual(approvals(older, newer), ["new"])
        self.assertEqual(approvals(newer, [article("existing", summary="New copy"), article("new")]), [])

    def test_seo_and_security_display_changes_never_trigger(self):
        before = [article("old")]
        for updated in (article("old", card_image_alt="New alt"),
                        article("old", social_security_severity="HIGH"),
                        article("old", updated_at="2026-10-31T00:00:00+09:00")):
            self.assertEqual(approvals(before, [updated]), [])

    def test_unapproved_and_low_score_not_dispatched(self):
        baseline = []
        self.assertEqual(approvals(baseline, [article("draft", status="draft"),
                         article("unapproved", social_publish=False),
                         article("low", score=79)]), [])
        self.assertTrue(eligible(article("guide", format="management_guide", score=70)))

    def test_adding_platform_without_new_approval_is_not_repost(self):
        self.assertEqual(approvals([article("one", social_platforms=["threads"])],
                                   [article("one", social_platforms=["threads", "instagram"])]), [])

    def test_scoped_publisher_excludes_unrelated_old_pending(self):
        rows = [article("old"), article("fresh"), article("unapproved", social_publish=False)]
        self.assertEqual([a["id"] for a in approved_in_scope(rows, "fresh")], ["fresh"])
        self.assertEqual([a["id"] for a in approved_in_scope(rows)], ["old", "fresh"])
        for scope in ("old,old", "../escape", "unapproved", "unknown", ","):
            with self.subTest(scope=scope), self.assertRaises(ValueError):
                approved_in_scope(rows, scope)


    def test_canceled_intermediate_pages_commits_do_not_lose_approvals(self):
        """Baseline must be the last successful site deploy, not the last push."""
        successful_deploy = [article("already-published")]
        cancelled_a = [*successful_deploy, article("missing-early")]
        cancelled_b = [*cancelled_a, article("missing-middle")]
        final_deploy = [*cancelled_b, article("just-now")]
        # Old github.event.before -> final detects only "just-now".
        self.assertEqual(approvals(cancelled_b, final_deploy), ["just-now"])
        # Correct previous successful deployment -> all three in final.
        self.assertEqual(approvals(successful_deploy, final_deploy),
                         ["just-now", "missing-early", "missing-middle"])

    def test_delivery_wakeup_is_independent_of_ephemeral_push_delta(self):
        pages = (ROOT / ".github/workflows/pages.yml").read_text()
        social = (ROOT / ".github/workflows/social-publish.yml").read_text()
        self.assertIn('workflow_run:', social)
        self.assertIn('github.event.workflow_run.conclusion == \'success\'', social)
        self.assertIn('scripts/social_queue.py prepare', social)
        self.assertNotIn('BEFORE_SHA: ${{ github.event.before }}', pages)

    def test_site_and_social_triggers_are_separate(self):
        pages = (ROOT / ".github/workflows/pages.yml").read_text()
        social = (ROOT / ".github/workflows/social-publish.yml").read_text()
        self.assertIn("needs: build", pages)
        self.assertIn("group: pages-${{ github.ref }}", pages)
        self.assertNotIn("gh workflow run social-publish.yml", pages)
        self.assertIn('workflows: ["Build and deploy WORK SIGNAL"]', social)
        self.assertIn('github.event.workflow_run.head_repository.full_name == github.repository', social)
        self.assertIn('queue: max', social)
        self.assertIn("SOCIAL_SCOPE_ARTICLE_IDS:", social)
        self.assertIn("inputs.deployed_sha", social)
        self.assertIn("SOCIAL_PUBLISH_ENABLED", social)
        self.assertIn("cancel-in-progress: false", social)


if __name__ == "__main__":
    unittest.main()
