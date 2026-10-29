import unittest
from scripts.check_social_channel_outcomes import evaluate, KNOWN_FEED_HOLD_MESSAGES


class ChannelOutcomeTests(unittest.TestCase):
    def setUp(self):
        self.feed = [{
            "id":"sample","title":"A verified story","summary":"Original verified summary",
            "source_url":"https://example.org/official","score":90,"format":"deep_dive",
            "status":"published","social_publish":True,
            "social_platforms":["threads","instagram","instagram_story"]
        }]
        self.rows = {"sentinel":{"instagram":{"status":"published","action_block_hold":True}}}
        self.report = {"articles":[{
            "id":"sample","platforms":{"threads":"published","instagram_story":"published",
                                       "instagram":"pending"}
        }], "failures":list(KNOWN_FEED_HOLD_MESSAGES)}

    def test_known_instagram_hold_is_separately_reported_without_hiding_it(self):
        ok, error, counts = evaluate(self.report,self.feed,self.rows)
        self.assertTrue(ok,error)
        self.assertEqual(counts["threads"],1)
        self.assertEqual(counts["instagram_story"],1)
        self.assertEqual(counts["feed_held"],1)
        self.assertEqual(counts["feed_published"],0)

    def test_pending_threads_cannot_be_masked_by_known_instagram_hold(self):
        self.report["articles"][0]["platforms"]["threads"]="needs_review"
        ok, error, _ = evaluate(self.report,self.feed,self.rows)
        self.assertFalse(ok)
        self.assertIn("threads",error)

    def test_pending_story_cannot_be_masked_by_known_instagram_hold(self):
        self.report["articles"][0]["platforms"]["instagram_story"]="pending"
        ok, error, _ = evaluate(self.report,self.feed,self.rows)
        self.assertFalse(ok)
        self.assertIn("instagram_story",error)

    def test_feed_pending_without_actual_action_block_is_failure(self):
        ok, error, _ = evaluate(self.report,self.feed,{})
        self.assertFalse(ok)
        self.assertIn("Instagram feed incomplete",error)

    def test_unexpected_failure_remains_red(self):
        self.report["failures"].append("threads Graph API error code=190")
        ok, error, _ = evaluate(self.report,self.feed,self.rows)
        self.assertFalse(ok)
        self.assertIn("Unexpected publication failure",error)

    def test_feed_marked_review_cannot_be_hidden_without_its_own_block(self):
        self.report["articles"][0]["platforms"]["instagram"]="needs_review"
        ok, error, _ = evaluate(self.report,self.feed,self.rows)
        self.assertFalse(ok)
        self.assertIn("Instagram feed incomplete",error)

    def test_missing_delivery_report_article_is_failure(self):
        self.report["articles"]=[]
        ok, error, _ = evaluate(self.report,self.feed,self.rows)
        self.assertFalse(ok)
        self.assertIn("Missing delivery evidence",error)


if __name__ == "__main__":
    unittest.main()
