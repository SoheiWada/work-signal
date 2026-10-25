#!/usr/bin/env python3
"""Fail-closed official Meta social publisher for explicitly approved WORK SIGNAL articles.

Requires --live, SOCIAL_PUBLISH_ENABLED=true, and secrets for BOTH accounts.
Never retries an uncertain Meta write automatically: a durable GitHub ledger is
marked 'attempting' before any Meta publishing call.
"""
import argparse
import base64
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://signal.amberlight.co.jp/"
THREADS_API = "https://graph.threads.net/v1.0"
IG_API = "https://graph.instagram.com/v25.0"
LEDGER = ".github/social-post-ledger.json"
STATUSES = ("attempting", "published", "needs_review")
HANDLE = "work_signal_japan"


def article_url(article):
    identifier = article.get("id", "")
    if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,119}", identifier):
        raise ValueError("Invalid article ID")
    return BASE + "articles/" + identifier + "/"


def image_url(article):
    return BASE + "assets/instagram/" + article["id"] + ".jpg"


def story_image_url(article):
    return BASE + "assets/stories/" + article["id"] + ".jpg"


def approved_articles(feed):
    """Only an explicit boolean opt-in can authorize SNS delivery."""
    eligible = []
    for item in feed:
        if item.get("social_publish") is not True or item.get("status") != "published":
            continue
        score = item.get("score")
        published = item.get("format") in ("special_story", "management_guide") or (
            isinstance(score, (int, float)) and not isinstance(score, bool) and score >= 80)
        if not published:
            continue
        if not all(isinstance(item.get(key), str) and item[key].strip() for key in
                   ("title", "summary", "source_url")):
            raise ValueError("Approved article missing required fields")
        if not item["source_url"].startswith("https://"):
            raise ValueError("Invalid primary source URL")
        article_url(item)
        eligible.append(item)
    return eligible


def threads_text(article):
    source, url = article["source_url"], article_url(article)
    custom = article.get("social_threads_text")
    if custom is not None:
        if not isinstance(custom, str) or not custom.strip():
            raise ValueError("Invalid custom Threads text")
        value = custom.strip()
    else:
        end = "\n\n記事全文：\n" + url + "\n一次情報：\n" + source
        title = article["title"].strip()
        intro = "WORK SIGNALで、仕事や暮らしへの意味を読み解きました。"
        budget = 450 - len(title) - len(intro) - len(end) - 4
        if budget < 0:
            raise ValueError("Article URLs too long for Threads")
        summary = article["summary"].strip()
        if len(summary) > budget:
            summary = summary[:max(0, budget - 1)].rstrip() + "…"
        value = title + "\n\n" + summary + "\n" + intro + end
    if len(value) > 500 or url not in value or not value.endswith(source):
        raise ValueError("Threads text must be <=500 chars, include article URL and end in original source")
    return value


def instagram_text(article):
    custom = article.get("social_instagram_caption")
    if custom is not None:
        if not isinstance(custom, str) or not custom.strip():
            raise ValueError("Invalid custom Instagram caption")
        value = custom.strip()
    else:
        value = (article["title"].strip() + "\n\n" + article["summary"].strip()
                 + "\n\n詳しくはプロフィールのWORK SIGNALリンクから。\n#WORKSIGNAL #ニュース解説")
    if len(value) > 2200:
        raise ValueError("Instagram caption exceeds 2200 characters")
    return value


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def request_json(url, *, token="", data=None, method="GET"):
    if not url.startswith("https://"):
        raise ValueError("HTTPS required")
    headers = {"Accept": "application/json", "User-Agent": "WORK-SIGNAL-Social/1.0"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        payload = urlencode(data).encode("utf-8")
    else:
        payload = None
    req = Request(url, data=payload, method=method, headers=headers)
    try:
        with urlopen(req, timeout=30) as response:
            obj = json.loads(response.read(1_000_000))
    except HTTPError as exc:
        # Do not print tokens or request bodies in CI logs.
        raise RuntimeError("API HTTP " + str(exc.code)) from None
    except (URLError, TimeoutError, ValueError) as exc:
        raise RuntimeError("API transport/response error: " + type(exc).__name__) from None
    if not isinstance(obj, dict):
        raise RuntimeError("Unexpected API response type")
    return obj


class GithubLedger:
    """Optimistic SHA updates to a durable, non-deployed ledger in the repo."""
    def __init__(self, repo, token):
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo) or not token:
            raise ValueError("GitHub repository and token required")
        self.url = "https://api.github.com/repos/" + repo + "/contents/" + LEDGER
        self.token = token

    def read(self):
        try:
            value = request_json(self.url, token=self.token)
        except RuntimeError as exc:
            if str(exc) == "API HTTP 404":
                return {}, None
            raise
        rows = json.loads(base64.b64decode(value["content"].replace("\n", "")).decode())
        if not isinstance(rows, dict):
            raise RuntimeError("Ledger format is invalid")
        return rows, value["sha"]

    def record(self, identifier, platform, status, remote_id="", permalink=""):
        if platform not in ("threads", "instagram", "instagram_story") or status not in STATUSES:
            raise ValueError("Invalid ledger update")
        for attempt in range(4):
            rows, sha = self.read()
            per_article = rows.setdefault(identifier, {})
            previous = per_article.get(platform, {})
            prior = previous.get("status") if isinstance(previous, dict) else None
            if status == "attempting" and prior in STATUSES:
                raise RuntimeError("Already attempted; cannot automatically retry")
            if status != "attempting" and prior != "attempting":
                raise RuntimeError("Result without a prior claim")
            if prior == "published":
                raise RuntimeError("Already published")
            per_article[platform] = {
                "status": status, "updated_at": now(),
                **({"remote_id": remote_id} if remote_id else {}),
                **({"permalink": permalink} if permalink else {})
            }
            body = {
                "message": "Log social publication " + identifier + " " + platform,
                "content": base64.b64encode((json.dumps(rows, ensure_ascii=False, indent=2)
                                             + "\n").encode()).decode(),
                "branch": "main"
            }
            if sha:
                body["sha"] = sha
            req = Request(self.url, method="PUT",
                          data=json.dumps(body).encode(),
                          headers={"Accept": "application/vnd.github+json",
                                   "Content-Type": "application/json",
                                   "Authorization": "Bearer " + self.token,
                                   "User-Agent": "WORK-SIGNAL-Social/1.0"})
            try:
                with urlopen(req, timeout=30) as response:
                    if response.status not in (200, 201):
                        raise RuntimeError("Ledger update failed")
                return
            except HTTPError as exc:
                if exc.code in (409, 422) and attempt < 3:
                    continue
                raise RuntimeError("Ledger HTTP " + str(exc.code)) from None
        raise RuntimeError("Could not persist social claim")


def verify_live(url, *, jpg=False, attempts=7):
    for index in range(attempts):
        try:
            with urlopen(Request(url, headers={"User-Agent": "WORK-SIGNAL-Social/1.0"}),
                         timeout=20) as response:
                if response.status == 200:
                    if jpg and "jpeg" in response.headers.get("Content-Type", "").lower() \
                            and response.read(3) == b"\xff\xd8\xff":
                        return
                    if not jpg and ('<link rel="canonical" href="' + url + '">') in \
                            response.read(160_000).decode("utf-8", "replace"):
                        return
        except (URLError, HTTPError, TimeoutError):
            pass
        if index + 1 < attempts:
            time.sleep(5)
    raise RuntimeError("Published asset not visible: " + ("image" if jpg else "article"))


def verify_account(base, token, user_id, *, instagram=False):
    fields = "user_id,username,account_type" if instagram else "id,username"
    profile = request_json(base + "/me?" + urlencode({"fields": fields}), token=token)
    if str(profile.get("username", "")).lower() != HANDLE:
        raise RuntimeError("Wrong target account; social publishing stopped")
    found_id = str(profile.get("user_id") or profile.get("id") or "")
    if found_id and found_id != user_id:
        raise RuntimeError("Account ID mismatch")
    if instagram and profile.get("account_type") and profile["account_type"].upper() not in ("BUSINESS", "CREATOR"):
        raise RuntimeError("Instagram must be a professional account")
    return profile


def publish_threads(text, token, user_id):
    created = request_json(THREADS_API + "/" + user_id + "/threads",
                           method="POST", token=token, data={"media_type": "TEXT", "text": text})
    if not created.get("id"):
        raise RuntimeError("Threads container missing")
    time.sleep(15)
    posted = request_json(THREADS_API + "/" + user_id + "/threads_publish",
                          method="POST", token=token, data={"creation_id": created["id"]})
    if not posted.get("id"):
        raise RuntimeError("Threads publish result ambiguous")
    return str(posted["id"])


def publish_instagram(text, url, token, user_id):
    created = request_json(IG_API + "/" + user_id + "/media",
                           method="POST", token=token, data={"image_url": url, "caption": text})
    identifier = created.get("id")
    if not identifier:
        raise RuntimeError("Instagram container missing")
    for index in range(12):
        time.sleep(5)
        result = request_json(IG_API + "/" + str(identifier) + "?fields=status_code", token=token)
        if result.get("status_code") == "FINISHED":
            break
        if result.get("status_code") in ("ERROR", "EXPIRED"):
            raise RuntimeError("Instagram container failed")
    else:
        raise RuntimeError("Instagram container processing timeout")
    posted = request_json(IG_API + "/" + user_id + "/media_publish",
                          method="POST", token=token, data={"creation_id": identifier})
    if not posted.get("id"):
        raise RuntimeError("Instagram publish result ambiguous")
    return str(posted["id"])



def publish_instagram_story(url, token, user_id):
    """Publish one 9:16 JPEG as an ephemeral Instagram Story (Business only)."""
    created = request_json(IG_API + "/" + user_id + "/media",
                           method="POST", token=token,
                           data={"media_type": "STORIES", "image_url": url})
    creation_id = str(created.get("id", ""))
    if not creation_id.isdigit():
        raise RuntimeError("Instagram Story container missing")
    for _ in range(15):
        time.sleep(5)
        state = request_json(IG_API + "/" + creation_id + "?fields=status_code",
                             token=token).get("status_code")
        if state == "FINISHED":
            break
        if state in ("ERROR", "EXPIRED"):
            raise RuntimeError("Instagram Story container failed")
    else:
        raise RuntimeError("Instagram Story processing timeout")
    posted = request_json(IG_API + "/" + user_id + "/media_publish",
                          method="POST", token=token, data={"creation_id": creation_id})
    published_id = str(posted.get("id", ""))
    if not published_id.isdigit():
        raise RuntimeError("Instagram Story publish result ambiguous")
    return published_id


SOCIAL_PLATFORMS = ("threads", "instagram", "instagram_story")


def remaining_platforms(existing):
    """Do not automatically retry an attempted, published, or uncertain platform."""
    return [platform for platform in SOCIAL_PLATFORMS
            if existing.get(platform, {}).get("status") not in STATUSES]



def run(articles, ledger, credentials):
    pending = approved_articles(articles)
    if not pending:
        print("No explicitly approved social articles. No posts.")
        return 0
    if credentials.get("SOCIAL_PUBLISH_ENABLED") != "true":
        print("Social posting is disabled.")
        return 0
    keys = ("THREADS_ACCESS_TOKEN", "THREADS_USER_ID", "INSTAGRAM_ACCESS_TOKEN", "INSTAGRAM_USER_ID")
    if any(not credentials.get(k) for k in keys):
        print("Both Meta accounts must be connected before social posting.")
        return 0
    rows, _ = ledger.read()
    if not any(remaining_platforms(rows.get(item["id"], {})) for item in pending):
        print("All explicitly approved social articles are recorded; no posts.")
        return 0
    verify_account(THREADS_API, credentials["THREADS_ACCESS_TOKEN"], credentials["THREADS_USER_ID"])
    ig_profile = verify_account(IG_API, credentials["INSTAGRAM_ACCESS_TOKEN"],
                                credentials["INSTAGRAM_USER_ID"], instagram=True)
    failures, count = [], 0
    # Process oldest approved articles first. Deployed revision is pinned by workflow_run.
    for article in reversed(pending):
        identifier = article["id"]
        rows, _ = ledger.read()
        remaining = remaining_platforms(rows.get(identifier, {}))
        if not remaining:
            continue
        if count >= 5:
            print("5-article safety limit reached; remaining items queued.")
            break
        try:
            text = threads_text(article) if "threads" in remaining else ""
            ig_text = instagram_text(article) if "instagram" in remaining else ""
            if "instagram_story" in remaining and str(ig_profile.get("account_type", "")).upper() != "BUSINESS":
                raise ValueError("Instagram Stories require a business account")
            verify_live(article_url(article))
            if "instagram" in remaining:
                verify_live(image_url(article), jpg=True)
            if "instagram_story" in remaining:
                verify_live(story_image_url(article), jpg=True)
        except (ValueError, RuntimeError) as exc:
            failures.append(identifier + ": preflight " + str(exc))
            continue
        for kind in remaining:
            try:
                # Durable write BEFORE publishing, including ephemeral Stories.
                ledger.record(identifier, kind, "attempting")
                if kind == "threads":
                    remote = publish_threads(text, credentials["THREADS_ACCESS_TOKEN"],
                                             credentials["THREADS_USER_ID"])
                elif kind == "instagram":
                    remote = publish_instagram(ig_text, image_url(article),
                                               credentials["INSTAGRAM_ACCESS_TOKEN"],
                                               credentials["INSTAGRAM_USER_ID"])
                elif kind == "instagram_story":
                    remote = publish_instagram_story(story_image_url(article),
                                                      credentials["INSTAGRAM_ACCESS_TOKEN"],
                                                      credentials["INSTAGRAM_USER_ID"])
                else:
                    raise ValueError("Unsupported platform")
                ledger.record(identifier, kind, "published", remote_id=remote)
                print("PUBLISHED", identifier, kind, remote)
            except Exception as exc:
                # A network failure may occur AFTER Meta has published. Do not retry.
                try:
                    ledger.record(identifier, kind, "needs_review")
                except Exception:
                    print("IMPORTANT: ledger state requires manual inspection for", identifier, kind)
                failures.append(identifier + ": " + kind + " " + type(exc).__name__)
        count += 1
    if failures:
        for item in failures:
            print("NEEDS REVIEW", item, file=sys.stderr)
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    articles = json.loads((ROOT / "data/articles.json").read_text())
    approved = approved_articles(articles)
    if not approved:
        print("No explicitly approved social articles. No posts.")
        return 0
    if not args.live:
        for article in approved:
            print("DRY RUN", article["id"], threads_text(article), "\n", instagram_text(article))
        return 0
    if os.getenv("SOCIAL_PUBLISH_ENABLED") != "true":
        print("Disabled by SOCIAL_PUBLISH_ENABLED. No posts.")
        return 0
    required = ("THREADS_ACCESS_TOKEN", "THREADS_USER_ID", "INSTAGRAM_ACCESS_TOKEN", "INSTAGRAM_USER_ID")
    if any(not os.getenv(k) for k in required):
        print("Meta credentials incomplete. No posts.")
        return 0
    ledger = GithubLedger(os.getenv("GITHUB_REPOSITORY", ""), os.getenv("GITHUB_TOKEN", ""))
    return run(articles, ledger, dict(os.environ))


if __name__ == "__main__":
    sys.exit(main())
