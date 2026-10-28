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
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://signal.amberlight.co.jp/"
THREADS_API = "https://graph.threads.net/v1.0"
IG_API = "https://graph.instagram.com/v25.0"
LEDGER = ".github/social-post-ledger.json"
STATUSES = ("attempting", "published", "needs_review", "deferred")
HANDLE = "work_signal_japan"


def article_url(article):
    identifier = article.get("id", "")
    if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,119}", identifier):
        raise ValueError("Invalid article ID")
    return BASE + "articles/" + identifier + "/"


def image_url(article):
    return BASE + "assets/instagram/" + article["id"] + ".jpg"


def tracked_article_url(article):
    """Attribution only: retain the canonical page and original source URL."""
    return article_url(article) + "?" + urlencode({
        "utm_source": "threads", "utm_medium": "social",
        "utm_campaign": "work_signal", "utm_content": article["id"]
    })


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
    source, url = article["source_url"], tracked_article_url(article)
    custom = article.get("social_threads_text")
    if custom is not None:
        if not isinstance(custom, str) or not custom.strip():
            raise ValueError("Invalid custom Threads text")
        # Preserve explicitly approved custom copy, including its URLs.
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
    required_url = article_url(article) if custom is not None else url
    if len(value) > 500 or required_url not in value or not value.endswith(source):
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


class MetaAPIError(RuntimeError):
    """Only allowlisted structured fields; never persist raw messages or tokens."""
    def __init__(self, http_status, error):
        self.http_status = http_status
        self.code = error.get("code")
        self.subcode = error.get("error_subcode")
        self.error_type = str(error.get("type", "?"))[:80]
        super().__init__(f"API HTTP {http_status} code={self.code} subcode={self.subcode} type={self.error_type}")

    def metadata(self):
        return {"http_status": self.http_status, "code": self.code,
                "subcode": self.subcode, "type": self.error_type}


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
        err = {}
        try:
            err = json.loads(exc.read(8192)).get("error", {})
        except (ValueError, TypeError, AttributeError):
            pass
        raise MetaAPIError(exc.code, err if isinstance(err, dict) else {}) from None
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
                raise RuntimeError("Publication ledger missing; manual recovery required") from None
            raise
        rows = json.loads(base64.b64decode(value["content"].replace("\n", "")).decode())
        if not isinstance(rows, dict):
            raise RuntimeError("Ledger format is invalid")
        return rows, value["sha"]

    def record(self, identifier, platform, status, remote_id="", permalink="", **metadata):
        if platform not in ("threads", "instagram", "instagram_story") or status not in STATUSES:
            raise ValueError("Invalid ledger update")
        for attempt in range(4):
            rows, sha = self.read()
            per_article = rows.setdefault(identifier, {})
            remaining_platforms(per_article)  # Reject malformed or unknown history before overwriting it.
            previous = per_article.get(platform, {})
            prior = previous.get("status") if isinstance(previous, dict) else None
            if status == "attempting" and prior in ("attempting", "published", "needs_review"):
                raise RuntimeError("Already attempted; cannot automatically retry")
            if status not in ("attempting", "deferred") and prior != "attempting":
                raise RuntimeError("Result without a prior claim")
            if prior == "published":
                raise RuntimeError("Already published")
            if status == "deferred" and prior == "needs_review":
                raise RuntimeError("Uncertain results require explicit reconciliation")
            allowed = {"reason", "next_attempt_at", "error", "stage", "container_id"}
            if set(metadata) - allowed:
                raise ValueError("Unsupported ledger metadata")
            per_article[platform] = {
                "status": status, "updated_at": now(),
                **{key: previous[key] for key in ("recovery_review_id", "reconciled_at") if key in previous},
                **({key: previous[key] for key in ("stage", "container_id") if key in previous}
                   if status != "attempting" else {}),
                **({"remote_id": remote_id} if remote_id else {}),
                **({"permalink": permalink} if permalink else {}),
                **metadata,
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

    def progress(self, identifier, platform, stage, container_id):
        """Persist the container and publish boundary while preserving the claim."""
        for attempt in range(4):
            rows, sha = self.read()
            entry = rows.get(identifier, {}).get(platform, {})
            if entry.get("status") != "attempting":
                raise RuntimeError("No active publication claim")
            entry.update(stage=stage, container_id=str(container_id), updated_at=now())
            body = {"message": "Record social publishing stage " + identifier + " " + platform,
                    "content": base64.b64encode((json.dumps(rows, ensure_ascii=False, indent=2) + "\n").encode()).decode(),
                    "sha": sha, "branch": "main"}
            req = Request(self.url, method="PUT", data=json.dumps(body).encode(),
                          headers={"Authorization": "Bearer " + self.token,
                                   "Accept": "application/vnd.github+json", "Content-Type": "application/json"})
            try:
                with urlopen(req, timeout=30):
                    return
            except HTTPError as exc:
                if exc.code in (409, 422) and attempt < 3:
                    continue
                raise RuntimeError("Ledger stage HTTP " + str(exc.code)) from None


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
    if not user_id.isdigit() or found_id != user_id:
        raise RuntimeError("Account ID mismatch")
    if instagram and profile.get("account_type") and profile["account_type"].upper() not in ("BUSINESS", "CREATOR"):
        raise RuntimeError("Instagram must be a professional account")
    return profile


def publish_threads(text, token, user_id, progress=None):
    # Stage labels and HTTP status are safe to log; never log token, text, URLs or API bodies.
    try:
        created = request_json(THREADS_API + "/" + user_id + "/threads",
                               method="POST", token=token, data={"media_type": "TEXT", "text": text})
    except RuntimeError as exc:
        raise RuntimeError("Threads create-container: " + str(exc)) from None
    if not created.get("id"):
        raise RuntimeError("Threads create-container: missing container ID")
    if progress:
        progress("container_created", created["id"])
    # Meta containers are asynchronous. Publish only after the official FINISHED state.
    # A failed/unknown status is not proof that publishing is safe to retry.
    status = None
    for attempt in range(5):
        try:
            info = request_json(
                THREADS_API + "/" + str(created["id"]) + "?fields=status,error_message",
                token=token)
        except RuntimeError as exc:
            raise RuntimeError("Threads container-status: " + str(exc)) from None
        status = info.get("status")
        if status == "FINISHED":
            break
        if status in ("ERROR", "EXPIRED", "PUBLISHED"):
            raise RuntimeError("Threads container-status: " + status)
        if status != "IN_PROGRESS":
            raise RuntimeError("Threads container-status: unknown status")
        if attempt < 4:
            time.sleep(60)
    if status != "FINISHED":
        raise RuntimeError("Threads container-status: not ready after 5 checks")
    if progress:
        progress("publish_requested", created["id"])
    try:
        posted = request_json(THREADS_API + "/" + user_id + "/threads_publish",
                              method="POST", token=token, data={"creation_id": created["id"]})
    except RuntimeError as exc:
        raise RuntimeError("Threads publish-container: " + str(exc)) from None
    if not posted.get("id"):
        raise RuntimeError("Threads publish-container: ambiguous response")
    return str(posted["id"])


def publish_instagram(text, url, token, user_id, progress=None):
    created = request_json(IG_API + "/" + user_id + "/media",
                           method="POST", token=token, data={"image_url": url, "caption": text})
    identifier = created.get("id")
    if not identifier:
        raise RuntimeError("Instagram container missing")
    if progress:
        progress("container_created", identifier)
    for index in range(12):
        time.sleep(5)
        result = request_json(IG_API + "/" + str(identifier) + "?fields=status_code", token=token)
        if result.get("status_code") == "FINISHED":
            break
        if result.get("status_code") in ("ERROR", "EXPIRED"):
            raise RuntimeError("Instagram container failed")
    else:
        raise RuntimeError("Instagram container processing timeout")
    if progress:
        progress("publish_requested", identifier)
    posted = request_json(IG_API + "/" + user_id + "/media_publish",
                          method="POST", token=token, data={"creation_id": identifier})
    if not posted.get("id"):
        raise RuntimeError("Instagram publish result ambiguous")
    return str(posted["id"])



def publish_instagram_story(url, token, user_id, progress=None):
    """Publish one 9:16 JPEG as an ephemeral Instagram Story (Business only)."""
    created = request_json(IG_API + "/" + user_id + "/media",
                           method="POST", token=token,
                           data={"media_type": "STORIES", "image_url": url})
    creation_id = str(created.get("id", ""))
    if not creation_id.isdigit():
        raise RuntimeError("Instagram Story container missing")
    if progress:
        progress("container_created", creation_id)
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
    if progress:
        progress("publish_requested", creation_id)
    posted = request_json(IG_API + "/" + user_id + "/media_publish",
                          method="POST", token=token, data={"creation_id": creation_id})
    published_id = str(posted.get("id", ""))
    if not published_id.isdigit():
        raise RuntimeError("Instagram Story publish result ambiguous")
    return published_id


SOCIAL_PLATFORMS = ("threads", "instagram", "instagram_story")


def requested_platforms(article):
    selected = article.get("social_platforms", list(SOCIAL_PLATFORMS))
    if not isinstance(selected, list) or not selected or any(p not in SOCIAL_PLATFORMS for p in selected) or len(set(selected)) != len(selected):
        raise ValueError("Invalid explicit social platform selection")
    return selected


def remaining_platforms(existing):
    """Do not automatically retry an attempted, published, or uncertain platform."""
    if not isinstance(existing, dict):
        raise RuntimeError("Invalid publication history; manual review required")
    for platform in SOCIAL_PLATFORMS:
        if platform in existing:
            entry = existing[platform]
            if not isinstance(entry, dict) or entry.get("status") not in STATUSES:
                raise RuntimeError("Unknown publication state; manual review required")
    pending = []
    for platform in SOCIAL_PLATFORMS:
        entry = existing.get(platform)
        if entry is None:
            pending.append(platform)
        elif entry.get("status") == "deferred":
            try:
                resume = datetime.fromisoformat(entry["next_attempt_at"])
                if resume.tzinfo is None:
                    raise ValueError("Timezone required")
            except (KeyError, ValueError, TypeError):
                raise RuntimeError("Invalid deferred publication state") from None
            if resume <= datetime.now(timezone.utc):
                pending.append(platform)
    return pending




def instagram_budget(credentials):
    response = request_json(IG_API + "/" + credentials["INSTAGRAM_USER_ID"]
                            + "/content_publishing_limit?fields=config,quota_usage",
                            token=credentials["INSTAGRAM_ACCESS_TOKEN"])
    row = (response.get("data") or [{}])[0]
    usage, total = row.get("quota_usage"), (row.get("config") or {}).get("quota_total")
    if type(usage) is not int or type(total) is not int or usage < 0 or total <= 0:
        raise RuntimeError("Instagram publishing quota unreadable")
    # Observed 2207042 at 50/100. This ceiling is an operational guard, not a Meta specification.
    ceiling = min(50, total)
    print("INSTAGRAM_BUDGET", usage, "/", total, "operational ceiling", ceiling)
    return max(0, ceiling - usage)


def delivery_report(articles, rows, failures=()):
    pending, review, published = 0, 0, 0
    table = ["| Article | Threads | Feed | Story |", "|---|---|---|---|"]
    details = []
    for article in articles:
        state = rows.get(article["id"], {})
        selected = requested_platforms(article)
        statuses = {}
        for kind in SOCIAL_PLATFORMS:
            status = state.get(kind, {}).get("status", "pending" if kind in selected else "not requested")
            statuses[kind] = status
            if kind not in selected:
                continue
            published += status == "published"
            review += status in ("attempting", "needs_review")
            pending += status in ("pending", "deferred")
        table.append("| " + article["id"] + " | " + " | ".join(statuses.values()) + " |")
        details.append({"id": article["id"], "platforms": statuses})
    summary = {"checked_at": now(), "published": published, "pending": pending,
               "needs_review": review, "failures": list(failures), "articles": details}
    print("DELIVERY_SUMMARY", json.dumps({k: v for k, v in summary.items() if k != "articles"}))
    if os.getenv("SOCIAL_REPORT_ENABLED") == "true":
        (ROOT / "social-delivery-status.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    if os.getenv("SOCIAL_REPORT_ENABLED") == "true" and os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as report:
            report.write("\n## WORK SIGNAL delivery\n\n" + f"Published: {published}; pending: {pending}; needs review: {review}\n\n" + "\n".join(table) + "\n")
    return pending + review


def run(articles, ledger, credentials):
    approved = approved_articles(articles)
    if not approved or credentials.get("SOCIAL_PUBLISH_ENABLED") != "true":
        print("Social posting disabled or no explicitly approved articles. No posts.")
        return 0
    if not any(credentials.get(token) and credentials.get(uid) for token, uid in (
        ("THREADS_ACCESS_TOKEN", "THREADS_USER_ID"), ("INSTAGRAM_ACCESS_TOKEN", "INSTAGRAM_USER_ID"))):
        print("No requested Meta account is connected.", file=sys.stderr)
        return 1
    rows, _ = ledger.read()
    work = {a["id"]: [p for p in remaining_platforms(rows.get(a["id"], {}))
                       if p in requested_platforms(a)] for a in approved}
    needed = set(p for kinds in work.values() for p in kinds)
    failures, profiles = [], {}
    for group, kinds, base, token_key, user_key in (
        ("threads", {"threads"}, THREADS_API, "THREADS_ACCESS_TOKEN", "THREADS_USER_ID"),
        ("instagram", {"instagram", "instagram_story"}, IG_API, "INSTAGRAM_ACCESS_TOKEN", "INSTAGRAM_USER_ID"),
    ):
        if not needed & kinds:
            continue
        try:
            if not credentials.get(token_key) or not credentials.get(user_key):
                raise RuntimeError(group + " credentials incomplete")
            profiles[group] = verify_account(base, credentials[token_key], credentials[user_key], instagram=group == "instagram")
        except RuntimeError as exc:
            failures.append(str(exc))
    budget = 0
    if "instagram" in profiles:
        try:
            budget = instagram_budget(credentials)
        except RuntimeError as exc:
            failures.append(str(exc))
    # SECURITY WATCH first; within each group preserve oldest-first delivery.
    ordered = sorted(enumerate(approved), key=lambda pair: (0 if pair[1].get("social_security_severity") else 1, -pair[0]))
    processed = {"threads": set(), "instagram": set()}
    for _, article in ordered:
        identifier = article["id"]
        if article.get("social_review_valid_until"):
            limit = datetime.fromisoformat(article["social_review_valid_until"])
            if limit.tzinfo is None or limit <= datetime.now(timezone.utc):
                failures.append(identifier + ": freshness review expired; delivery held")
                continue
        rows, _ = ledger.read()
        remaining = [p for p in remaining_platforms(rows.get(identifier, {})) if p in requested_platforms(article)]
        if not remaining:
            continue
        for kind in remaining:
            group = "threads" if kind == "threads" else "instagram"
            if group not in profiles:
                continue
            if identifier not in processed[group] and len(processed[group]) >= 5:
                message = group + " 5-article batch limit reached; scheduled continuation pending"
                if message not in failures:
                    failures.append(message)
                continue
            if kind != "threads" and budget <= 0:
                ledger.record(identifier, kind, "deferred", reason="instagram_quota",
                              next_attempt_at=(datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(timespec="seconds"))
                continue
            try:
                verify_live(article_url(article))
                if kind == "threads":
                    text = threads_text(article)
                elif kind == "instagram":
                    text = instagram_text(article)
                    verify_live(image_url(article), jpg=True)
                else:
                    if str(profiles[group].get("account_type", "")).upper() != "BUSINESS":
                        raise ValueError("Instagram Stories require a business account")
                    verify_live(story_image_url(article), jpg=True)
            except (ValueError, RuntimeError) as exc:
                failures.append(identifier + ": " + kind + " preflight " + str(exc))
                continue
            claimed = False
            try:
                processed[group].add(identifier)
                ledger.record(identifier, kind, "attempting")
                claimed = True
                options = {}
                if hasattr(ledger, "progress"):
                    options["progress"] = lambda stage, cid: ledger.progress(identifier, kind, stage, cid)
                if kind == "threads":
                    remote = publish_threads(text, credentials["THREADS_ACCESS_TOKEN"], credentials["THREADS_USER_ID"], **options)
                elif kind == "instagram":
                    remote = publish_instagram(text, image_url(article), credentials["INSTAGRAM_ACCESS_TOKEN"], credentials["INSTAGRAM_USER_ID"], **options)
                else:
                    remote = publish_instagram_story(story_image_url(article), credentials["INSTAGRAM_ACCESS_TOKEN"], credentials["INSTAGRAM_USER_ID"], **options)
                ledger.record(identifier, kind, "published", remote_id=remote)
                if kind != "threads":
                    budget -= 1
                print("PUBLISHED", identifier, kind, remote)
            except Exception as exc:
                if claimed:
                    try:
                        if kind != "threads" and isinstance(exc, MetaAPIError) and exc.http_status == 400 and exc.subcode == 2207042:
                            budget = 0
                            ledger.record(identifier, kind, "deferred", reason="instagram_quota_rejected", error=exc.metadata(),
                                          next_attempt_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(timespec="seconds"))
                        else:
                            metadata = {"error": exc.metadata()} if isinstance(exc, MetaAPIError) else {}
                            ledger.record(identifier, kind, "needs_review", **metadata)
                    except Exception:
                        print("IMPORTANT: ledger state requires manual inspection for", identifier, kind)
                detail = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
                failures.append(identifier + ": " + kind + " " + detail)
    rows, _ = ledger.read()
    outstanding = delivery_report(approved, rows, failures)
    for message in failures:
        print("DELIVERY INCOMPLETE", message, file=sys.stderr)
    return 1 if outstanding or failures else 0


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
    if not os.getenv("GITHUB_TOKEN") or not os.getenv("GITHUB_REPOSITORY"):
        print("GitHub ledger credentials incomplete. No posts.", file=sys.stderr)
        return 1
    ledger = GithubLedger(os.getenv("GITHUB_REPOSITORY", ""), os.getenv("GITHUB_TOKEN", ""))
    return run(articles, ledger, dict(os.environ))


if __name__ == "__main__":
    sys.exit(main())


