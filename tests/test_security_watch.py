"""Regression checks for SECURITY WATCH status provenance and update safety."""
import unittest

from scripts.security_watch import STALE_STATUS, security_feed


def story(updated_at=None, explicit=None):
    article = {
        "id": "existing-id", "title": "Verified advisory", "summary": "Reviewed summary",
        "published_at": "2026-10-22", "social_security_severity": "CRITICAL",
        "social_security_product": "PAN-OS / PHP",
    }
    if updated_at is not None:
        article["updated_at"] = updated_at
    if explicit is not None:
        article["security_watch"] = explicit
    return article


def legacy(reviewed_at=None):
    row = {
        "id": "original-alert", "article_id": "existing-id", "date": "2026-10-22",
        "product": "PHP", "severity": "HIGH", "summary": "Old text",
        "status": "修正版待ち（条件付き）",
    }
    if reviewed_at is not None:
        row["status_reviewed_at"] = reviewed_at
    return row


class SecurityWatchRemediationTests(unittest.TestCase):
    def test_original_status_is_kept_without_article_revision(self):
        item = security_feed([story()], [legacy()])[0]
        self.assertEqual(item["status"], "修正版待ち（条件付き）")
        self.assertEqual(item["severity"], "CRITICAL")
        self.assertEqual(item["product"], "PAN-OS / PHP")
        self.assertEqual(item["summary"], "Reviewed summary")

    def test_legacy_without_review_timestamp_does_not_survive_update(self):
        record = legacy()
        item = security_feed([story("2026-10-30T02:42:46.503Z")], [record])[0]
        self.assertEqual(item["status"], STALE_STATUS)
        self.assertEqual(record["status"], "修正版待ち（条件付き）")

    def test_status_reviewed_after_latest_article_update_remains_visible(self):
        item = security_feed([story("2026-10-30T02:42:46.503Z")],
                             [legacy("2026-10-30T03:19:51Z")])[0]
        self.assertEqual(item["status"], "修正版待ち（条件付き）")

    def test_later_article_revision_invalidates_previous_status(self):
        item = security_feed([story("2026-10-31T04:00:00Z")],
                             [legacy("2026-10-30T03:19:51Z")])[0]
        self.assertEqual(item["status"], STALE_STATUS)

    def test_invalid_status_timestamp_fails_closed(self):
        item = security_feed([story("2026-10-30T02:42:46Z")],
                             [legacy("yesterday")])[0]
        self.assertEqual(item["status"], STALE_STATUS)

    def test_explicit_metadata_fails_closed_after_update(self):
        article = story("2026-10-31T02:00:00Z", {
            "status": "修正版あり",
            "status_reviewed_at": "2026-10-30T12:00:00Z",
        })
        item = security_feed([article], [])[0]
        self.assertEqual(item["status"], STALE_STATUS)

    def test_legacy_duplicates_rejected(self):
        with self.assertRaises(ValueError):
            security_feed([story()], [legacy(), legacy()])


if __name__ == "__main__":
    unittest.main()
