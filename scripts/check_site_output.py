#!/usr/bin/env python3
"""Fail the Pages build if published articles or SECURITY WATCH output is incomplete.

This is a site-only verification gate. Social API posting checks belong to
social-publisher-ci.yml and must never prevent an approved article from
reaching the website.
"""
import json
from pathlib import Path

from scripts.build_site import ROOT, published_articles
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

    expected_security = security_feed(articles, load(ROOT / "data/security-watch.json"))
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
    print(f"SITE_OUTPUT_OK articles={len(articles)} security_alerts={len(expected_security)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
