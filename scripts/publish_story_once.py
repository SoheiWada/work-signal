#!/usr/bin/env python3
"""One-off Instagram Story validation for the previously approved NEC WORK SIGNAL article.

The workflow limits execution to a single site-deployment commit.
No Threads or Instagram feed publishing functions are called.
Each attempt is persisted BEFORE contacting a Meta publishing endpoint.
"""
import json
import os
import sys
import time

from scripts.publish_social import (
    IG_API, GithubLedger, approved_articles, article_url, request_json,
    story_image_url, verify_account, verify_live,
)

TARGET = "20261024-nec-ai-work-wellbeing-survey"
PLATFORM = "instagram_story"


def post_story(token, user_id, image_url):
    container = request_json(IG_API + "/" + user_id + "/media",
                             method="POST", token=token,
                             data={"media_type": "STORIES", "image_url": image_url})
    creation_id = str(container.get("id", ""))
    if not creation_id.isdigit():
        raise RuntimeError("Instagram Story container ID missing")
    # Await Meta processing; never publish until finished.
    for _ in range(15):
        time.sleep(5)
        status = request_json(IG_API + "/" + creation_id + "?fields=status_code",
                              token=token)
        current = status.get("status_code")
        if current == "FINISHED":
            break
        if current in ("ERROR", "EXPIRED"):
            raise RuntimeError("Instagram Story container failed: " + current)
    else:
        raise RuntimeError("Instagram Story container processing timeout")
    posted = request_json(IG_API + "/" + user_id + "/media_publish",
                          method="POST", token=token,
                          data={"creation_id": creation_id})
    remote_id = str(posted.get("id", ""))
    if not remote_id.isdigit():
        raise RuntimeError("Instagram Story publishing result ambiguous")
    return remote_id


def main():
    if os.getenv("STORY_ONE_SHOT_ENABLED") != "true":
        raise RuntimeError("This one-time Story publishing job is disabled")
    token, user_id = os.getenv("INSTAGRAM_ACCESS_TOKEN", ""), os.getenv("INSTAGRAM_USER_ID", "")
    if not token or not user_id:
        raise RuntimeError("Instagram Story credentials are missing")
    from pathlib import Path
    feed = json.loads((Path(__file__).resolve().parents[1] / "data/articles.json").read_text())
    matching = [article for article in feed if article.get("id") == TARGET]
    if len(matching) != 1 or matching[0] not in approved_articles(matching):
        raise RuntimeError("Story article is not uniquely approved")
    article = matching[0]
    ledger = GithubLedger(os.getenv("GITHUB_REPOSITORY", ""), os.getenv("GITHUB_TOKEN", ""))
    rows, _ = ledger.read()
    previous = rows.get(TARGET, {}).get(PLATFORM, {})
    if previous.get("status") == "published":
        print("Story already published; no duplicate posted.")
        return 0
    if previous.get("status") in ("attempting", "needs_review"):
        raise RuntimeError("Previous Story attempt must be manually checked; no retry")

    verify_account(IG_API, token, user_id, instagram=True)
    profile = request_json(IG_API + "/me?fields=account_type", token=token)
    if str(profile.get("account_type", "")).upper() != "BUSINESS":
        raise RuntimeError("Instagram Stories require the Business account in this integration")
    url = story_image_url(article)
    verify_live(article_url(article))
    verify_live(url, jpg=True)

    # Once marked 'attempting' we will NOT retry automatically, including on errors.
    ledger.record(TARGET, PLATFORM, "attempting")
    try:
        remote_id = post_story(token, user_id, url)
        ledger.record(TARGET, PLATFORM, "published", remote_id=remote_id)
        print("PUBLISHED Instagram Story", TARGET, "remote_id:", remote_id)
        return 0
    except Exception as exc:
        try:
            ledger.record(TARGET, PLATFORM, "needs_review")
        except Exception:
            print("IMPORTANT: Story ledger requires manual inspection", file=sys.stderr)
        print("NEEDS REVIEW Instagram Story", type(exc).__name__, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
