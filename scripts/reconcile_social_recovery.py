#!/usr/bin/env python3
"""Reconcile only owner-reviewed delivery failures; never publish from this script."""
import base64
import json
import os
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen
try:
    from . import publish_social as social
    from .audit_social_delivery import collect, matches, story_image_checks
except ImportError:
    import publish_social as social
    from audit_social_delivery import collect, matches, story_image_checks


def save_verified(ledger, aid, kind, expected, replacement):
    rows, sha = ledger.read()
    current = rows.get(aid, {}).get(kind)
    if current != expected or current.get("status") != "needs_review":
        raise RuntimeError("Recovery lease changed; do not overwrite publication history")
    replacement["previous_attempt"] = expected
    rows[aid][kind] = replacement
    payload = {"message": "Reconcile verified social delivery " + aid + " " + kind,
               "content": base64.b64encode((json.dumps(rows, ensure_ascii=False, indent=2) + "\n").encode()).decode(),
               "sha": sha, "branch": "main"}
    req = Request(ledger.url, method="PUT", data=json.dumps(payload).encode(),
                  headers={"Authorization": "Bearer " + ledger.token, "Accept": "application/vnd.github+json", "Content-Type": "application/json"})
    with urlopen(req, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError("Could not persist verified reconciliation")


def may_retry_story(entry, visual, current=None):
    current = current or datetime.now(timezone.utc)
    attempt = datetime.fromisoformat(entry["updated_at"])
    return (attempt.tzinfo is not None and timedelta(0) <= current - attempt < timedelta(hours=24)
            and visual.get("absence_verified") is True and not visual.get("matching_ids"))


def main():
    path = social.ROOT / ".github/social-recovery-review.json"
    if not path.is_file():
        print("No explicit recovery review. No reconciliation writes.")
        return
    plan = json.loads(path.read_text())
    expires = datetime.fromisoformat(plan["valid_until"])
    if expires.tzinfo is None or datetime.now(timezone.utc) > expires:
        print("Freshness review expired; no automatic recovery")
        return
    articles = json.loads((social.ROOT / "data/articles.json").read_text())
    index = {a["id"]: a for a in articles}
    ledger = social.GithubLedger(os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"])
    rows, _ = ledger.read()
    for kind, base, token_key, uid_key, endpoint, fields in (
        ("threads", social.THREADS_API, "THREADS_ACCESS_TOKEN", "THREADS_USER_ID", "threads", "id,text,timestamp,permalink"),
        ("instagram", social.IG_API, "INSTAGRAM_ACCESS_TOKEN", "INSTAGRAM_USER_ID", "media", "id,caption,timestamp,permalink"),
        ("instagram_story", social.IG_API, "INSTAGRAM_ACCESS_TOKEN", "INSTAGRAM_USER_ID", "stories", "id,caption,timestamp,permalink,media_url"),
    ):
        targets = [item for item in plan["items"] if item["decision"] == "deliver_missing_platforms_only"
                   and kind in item.get("platforms", [])
                   and rows.get(item["article_id"], {}).get(kind, {}).get("status") == "needs_review"]
        if not targets:
            continue
        try:
            token, uid = os.environ[token_key], os.environ[uid_key]
            social.verify_account(base, token, uid, instagram=kind != "threads")
            media, complete = collect(base, uid + "/" + endpoint, token, fields)
            if not complete:
                raise RuntimeError("Incomplete media history; recovery withheld")
            visual = story_image_checks(articles, rows, media) if kind == "instagram_story" else {}
        except Exception as exc:
            print("RECOVERY HOLD", kind, str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__)
            continue
        for item in targets:
            aid = item["article_id"]
            a = index[aid]
            if a.get("social_publish") is not True or kind not in social.requested_platforms(a):
                continue
            old = rows[aid][kind]
            found = matches(a, kind, media) if kind != "instagram_story" else [m for m in media if m.get("id") in visual.get(aid, {}).get("matching_ids", [])]
            if len(found) == 1:
                replacement = {"status": "published", "updated_at": social.now(), "remote_id": str(found[0]["id"]),
                               "permalink": found[0].get("permalink", ""), "reconciled_at": social.now()}
            elif found:
                print("RECOVERY HOLD", aid, kind, "multiple matching posts")
                continue
            else:
                if kind == "instagram_story":
                    if not may_retry_story(old, visual.get(aid, {})):
                        print("RECOVERY HOLD", aid, kind, "Story absence cannot be established")
                        continue
                replacement = {"status": "deferred", "updated_at": social.now(),
                               "next_attempt_at": social.now(), "reason": "freshness_reviewed_and_live_absence_verified",
                               "reconciled_at": social.now()}
            save_verified(ledger, aid, kind, old, replacement)
            print("RECONCILED", aid, kind, replacement["status"])
    print("Reconciliation finished. No Meta publishing calls made.")


if __name__ == "__main__":
    main()
