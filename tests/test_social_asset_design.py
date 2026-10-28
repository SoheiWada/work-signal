"""Social-only SECURITY WATCH design tests; site, OG and older articles stay untouched."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

from scripts.build_site import build
from scripts.social_asset_design import (
    fit_one_line, font, fit_metadata_lines, wrap_words,
    security_style, security_share_card, security_story_card,
)


class SecurityAssetDesignTests(unittest.TestCase):
    def setUp(self):
        import json
        from scripts.build_site import ROOT
        articles = json.loads((ROOT / "data/articles.json").read_text(encoding="utf-8"))
        self.article = dict(next(a for a in articles
                                 if a["id"] == "20261024-asvereinbase-wordpress-auth-bypass"))
        self.article.update({
            "id": "20261026-security-card-design-check",
            "title": "認証不要の重大な脆弱性。対象製品への更新と侵害確認が必要",
            "summary": "影響範囲を確認し、修正版への更新とアクセス履歴の調査を推奨。",
            "social_publish": True,
            "social_security_product": "対象ソフトウェア",
            "social_security_cve": "CVE-2026-12345",
            "social_security_action": "修正版へ更新し侵害の痕跡を確認",
        })

    def test_explicit_tag_only_and_invalid_value_fails_closed(self):
        self.assertIsNone(security_style(self.article))
        self.assertIsNotNone(security_style({
            **self.article, "social_security_severity": "CRITICAL"
        }))
        self.assertIsNotNone(security_style({
            **self.article, "social_security_severity": "HIGH"
        }))
        for invalid in ("critical", "MEDIUM", "UNKNOWN", ""):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    security_style({**self.article, "social_security_severity": invalid})

    def test_critical_never_wraps_and_fits_within_image(self):
        image = Image.new("RGB", (1080, 1350))
        draw = ImageDraw.Draw(image)
        for level in ("CRITICAL", "HIGH"):
            face = fit_one_line(draw, level, 875, preferred_size=122, min_size=54)
            self.assertLessEqual(draw.textlength(level, font=face), 875)
            self.assertGreaterEqual(face.size, 54)
            # CRITICAL is drawn as one atomic string, not broken into CRITI / CAL.
            self.assertNotIn("\n", level)

    def test_feed_and_story_have_expected_distinct_dark_themes(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            critical = {**self.article, "social_security_severity": "CRITICAL"}
            high = {**self.article, "social_security_severity": "HIGH",
                    "id": "20261026-security-high-design-check"}
            for article, bg in ((critical, (21, 22, 27)), (high, (28, 34, 47))):
                feed_path = security_share_card(output, article)
                story_path = security_story_card(output, article)
                with Image.open(feed_path) as feed:
                    self.assertEqual(feed.size, (1080, 1350))
                    self.assertEqual(feed.format, "JPEG")
                    for left, top in ((20, 120), (1060, 1110)):
                        color = feed.getpixel((left, top))
                        self.assertTrue(all(abs(a-b) < 4 for a, b in zip(color, bg)))
                with Image.open(story_path) as story:
                    self.assertEqual(story.size, (1080, 1920))
                    self.assertEqual(story.format, "JPEG")

    def test_long_mitigation_is_visibly_shortened_only_on_image(self):
        full = ("Better Auth 1.7.7へ更新し、関連プラグインも揃えて更新。"
                "既存Magic Link・進行中のOAuthフローを再発行 / "
                "Better Auth 1.7.7へ更新し、OAuth Proxyの参加環境・"
                "同一stateを扱うノードを同時更新。")
        face = font(25, 600)
        clipped = fit_metadata_lines(full, face, 814, 2)
        self.assertLessEqual(len(clipped), 2)
        self.assertTrue(clipped[-1].endswith("…詳細は記事本文"))
        self.assertTrue("".join(clipped).startswith("Better Auth 1.7.7へ更新"))
        self.assertIsNone(wrap_words(full, face, 814, 2))
        self.assertEqual(fit_metadata_lines("最新版へ更新", face, 814, 2), ["最新版へ更新"])

    def test_long_security_actions_in_real_published_articles_do_not_break_assets(self):
        import json
        from scripts.build_site import ROOT
        articles = json.loads((ROOT / "data/articles.json").read_text(encoding="utf-8"))
        identifiers = (
            "20261028-fastify-express-absolute-form-middleware-bypass",
            "20261028-better-auth-magic-link-oauth-account-takeover",
        )
        by_id = {article["id"]: article for article in articles}
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            for identifier in identifiers:
                article = by_id[identifier]
                original_action = article["social_security_action"]
                self.assertGreater(len(original_action), 120)
                feed = security_share_card(output, article)
                story = security_story_card(output, article)
                self.assertTrue(feed.is_file())
                self.assertTrue(story.is_file())
                self.assertEqual(article["social_security_action"], original_action)

    def test_build_routes_only_explicit_severity_and_keeps_standard_unchanged(self):
        from scripts.build_site import instagram_share_card, instagram_story_card

        # Confirm routing without rebuilding the entire public site.
        article = {**self.article, "social_security_severity": "CRITICAL"}
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            with patch("scripts.build_site.instagram_share_card",
                       wraps=instagram_share_card) as normal_feed, \
                 patch("scripts.build_site.instagram_story_card",
                       wraps=instagram_story_card) as normal_story:
                from scripts.build_site import security_share_card as guarded_feed
                from scripts.build_site import security_story_card as guarded_story
                with patch("scripts.build_site.security_share_card",
                           wraps=guarded_feed) as critical_feed, \
                     patch("scripts.build_site.security_story_card",
                           wraps=guarded_story) as critical_story:
                    # Restrict site generation to two articles and avoid unrelated writes.
                    from scripts.build_site import build
                    build(output, [article])
                    normal_feed.assert_not_called()
                    normal_story.assert_not_called()
                    critical_feed.assert_called_once()
                    critical_story.assert_called_once()


if __name__ == "__main__":
    unittest.main()
