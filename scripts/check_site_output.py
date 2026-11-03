#!/usr/bin/env python3
"""Fail the Pages build if published articles or SECURITY WATCH output is incomplete.

This is a site-only verification gate. Social API posting checks belong to
social-publisher-ci.yml and must never prevent an approved article from
reaching the website.
"""
import json
import re
from html import escape
from pathlib import Path

from scripts.build_site import ROOT, published_articles, security_activity_sort_key, reading_minutes, reading_format, distinct_quick_take
from scripts.security_watch import security_feed

OUT = ROOT / "_site"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    articles = published_articles(load(ROOT / "data/articles.json"))
    emitted = load(OUT / "data/articles.json")
    expected_ids = [article["id"] for article in articles]
    actual_ids = [article["id"] for article in emitted]
    if actual_ids != expected_ids:
        raise RuntimeError("Published article feed differs from approved site output")
    missing = [aid for aid in expected_ids if not (OUT / "articles" / aid / "index.html").is_file()]
    if missing:
        raise RuntimeError("Missing generated article pages: " + ", ".join(missing[:10]))

    # The builder enriches approved articles with Git-history update times.
    # Compare SECURITY WATCH against the *effective published* article state;
    # otherwise the freshness gate can disagree with the site it verified.
    expected_security = security_feed(emitted, load(ROOT / "data/security-watch.json"))
    emitted_security = load(OUT / "data/security-watch.json")
    if emitted_security != expected_security:
        raise RuntimeError("SECURITY WATCH output differs from reviewed alert records")
    watch_html = (OUT / "security" / "index.html").read_text(encoding="utf-8")
    home_html = (OUT / "index.html").read_text(encoding="utf-8")
    if watch_html.count('class="sw-item"') != len(expected_security):
        raise RuntimeError("SECURITY WATCH entry count differs from generated page")
    if "SECURITY WATCH" not in home_html or 'href="/security/"' not in home_html:
        raise RuntimeError("SECURITY WATCH homepage link missing")
    article_ids = set(expected_ids)
    broken = [row["article_id"] for row in expected_security
              if row["article_id"] not in article_ids or
              ('href="/articles/' + row["article_id"] + '/"') not in watch_html]
    if broken:
        raise RuntimeError("SECURITY WATCH missing linked article pages: " + ", ".join(broken[:10]))
    lookup = {article["id"]: article for article in articles}
    wrongly_classified = [aid for aid in (row["article_id"] for row in expected_security)
                          if lookup[aid]["category"] != "SECURITY"]
    if wrongly_classified:
        raise RuntimeError("SECURITY WATCH articles must have category SECURITY: " + ", ".join(wrongly_classified[:10]))
    missing_headlines = [row["article_id"] for row in expected_security
                         if escape(row.get("headline") or lookup[row["article_id"]]["title"], quote=True) not in watch_html]
    if missing_headlines:
        raise RuntimeError("SECURITY WATCH article headlines not rendered: " + ", ".join(missing_headlines[:10]))
    # Check the *actual generated order* instead of trusting only the feed.
    # This catches a UI regression after SEO/template changes even if every
    # article link still exists and a normal build returns success.
    effective = {a["id"]: a for a in emitted}
    expected_order = sorted(expected_security, key=lambda row:
        security_activity_sort_key((
            effective[row["article_id"]].get("updated_at") or row["date"],
            row, effective[row["article_id"]]
        )), reverse=True)
    expected_order_ids = [row["article_id"] for row in expected_order]
    card_pattern = r'<a class="sw-item" href="/articles/([A-Za-z0-9_-]+)/">'
    archive_ids = re.findall(card_pattern, watch_html)
    home_ids = re.findall(card_pattern, home_html)
    if archive_ids != expected_order_ids:
        raise RuntimeError("SECURITY WATCH archive cards are not in publication/update order")
    if home_ids != expected_order_ids[:4]:
        raise RuntimeError("SECURITY WATCH top cards differ from archive order")
    if "新規公開・追記更新の新しい日時順" not in watch_html:
        raise RuntimeError("SECURITY WATCH sorting explanation is stale")
    if 'data-category="SECURITY"' not in home_html and "const categories=['すべて','AI','SECURITY'" not in home_html:
        raise RuntimeError("SECURITY category filter not available on the homepage")
    # The four highlighted SECURITY WATCH articles should not reappear in the
    # default LATEST cards (without JavaScript). Category/search still exposes them.
    featured_ids = set(home_ids)
    default_card_ids = set(re.findall(
        r'<a class="story-link" href="https://signal\.amberlight\.co\.jp/articles/([A-Za-z0-9_-]+)/"',
        home_html,
    ))
    if featured_ids & default_card_ids:
        raise RuntimeError("Featured SECURITY WATCH article repeated in LATEST: " +
                           ", ".join(sorted(featured_ids & default_card_ids)))

    listing = load(OUT / "data/index.json")
    indexed_minutes = {article["id"]: article.get("reading_minutes") for article in listing}
    indexed_formats = {article["id"]: article.get("reading_format") for article in listing}
    if set(indexed_minutes) != article_ids:
        raise RuntimeError("Search listing IDs differ from published articles")
    duplicate_suppressed = 0
    reading_counts = {'brief': 0, 'deep_dive': 0, 'management_guide': 0, 'special_story': 0}
    for article in articles:
        minutes = reading_minutes(article)
        mode = reading_format(article)
        reading_counts[mode] += 1
        if indexed_formats[article["id"]] != mode or effective[article["id"]].get('reading_format') != mode:
            raise RuntimeError("Reading format disagrees between static and index data: " + article["id"])
        if indexed_minutes[article["id"]] != minutes:
            raise RuntimeError("Reading time mismatch in listing: " + article["id"])
        generated = (OUT / "articles" / article["id"] / "index.html").read_text(encoding="utf-8")
        if (f'datetime="PT{minutes}M"' not in generated
                or f'aria-label="読了目安 {minutes}分"' not in generated):
            raise RuntimeError("Article reading time differs from card data: " + article["id"])
        if mode in ('brief', 'deep_dive'):
            label = "SIGNAL DEEP DIVE" if mode == 'deep_dive' else "SIGNAL BRIEF"
            if f'class="article-type">{label}</span>' not in generated:
                raise RuntimeError("Article reading format is mismatched: " + article["id"])
        if isinstance(article.get("sections"), list) and article["sections"] and article.get("quick_take"):
            expected_takeaway = distinct_quick_take(article) is not None
            has_takeaway = 'class="takeaways"' in generated
            if expected_takeaway != has_takeaway:
                raise RuntimeError("Repeated or distinct quick take rendered incorrectly: " + article["id"])
            if not expected_takeaway:
                duplicate_suppressed += 1
    print(f"SITE_OUTPUT_OK articles={len(articles)} security_alerts={len(expected_security)} suppressed_quick_takes={duplicate_suppressed} reading_formats={reading_counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
