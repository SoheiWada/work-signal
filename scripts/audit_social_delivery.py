#!/usr/bin/env python3
"""Read-only reconciliation of approved delivery, live Meta media and deployed assets."""
import json
import os
from datetime import datetime, timezone
from urllib.parse import urlencode
try:
    from . import publish_social as social
except ImportError:
    import publish_social as social


def collect(base, path, token, fields, *, pages=8):
    items, after = [], None
    for _ in range(pages):
        args = {"fields": fields, "limit": 100}
        if after:
            args["after"] = after
        response = social.request_json(base + "/" + path + "?" + urlencode(args), token=token)
        items.extend(response.get("data", []))
        paging = response.get("paging", {})
        if not paging.get("next"):
            return items, True
        after = paging.get("cursors", {}).get("after")
        if not after:
            break
    return items, False


def matches(article, kind, items):
    if kind == "threads":
        needle = social.article_url(article)
        return [x for x in items if needle in (x.get("text") or "")]
    try:
        caption = social.instagram_text(article).strip()
    except ValueError:
        return []
    # Full approved caption is compared; no fuzzy title matching authorizes a retry.
    return [x for x in items if (x.get("caption") or "").strip() == caption]


def main():
    articles = json.loads((social.ROOT / "data/articles.json").read_text())
    ledger = social.GithubLedger(os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"])
    rows, _ = ledger.read()
    result = {"checked_at": social.now(), "accounts": {}, "quota": None, "collections": {}, "articles": []}
    streams = {}
    for key, base, token_name, uid_name, path, fields in (
        ("threads", social.THREADS_API, "THREADS_ACCESS_TOKEN", "THREADS_USER_ID", "threads", "id,text,timestamp,permalink"),
        ("instagram", social.IG_API, "INSTAGRAM_ACCESS_TOKEN", "INSTAGRAM_USER_ID", "media", "id,caption,media_type,media_product_type,timestamp,permalink"),
        ("instagram_story", social.IG_API, "INSTAGRAM_ACCESS_TOKEN", "INSTAGRAM_USER_ID", "stories", "id,caption,media_type,timestamp,permalink"),
    ):
        try:
            token, uid = os.environ[token_name], os.environ[uid_name]
            if key != "instagram_story":
                profile = social.verify_account(base, token, uid, instagram=key == "instagram")
                result["accounts"][key] = {"verified": True, "type": profile.get("account_type")}
            items, complete = collect(base, uid + "/" + path, token, fields)
            streams[key] = items
            result["collections"][key] = {"count": len(items), "complete": complete}
        except Exception as exc:
            result["collections"][key] = {"error": str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__, "complete": False}
    try:
        quota = social.request_json(social.IG_API + "/" + os.environ["INSTAGRAM_USER_ID"] + "/content_publishing_limit?fields=config,quota_usage", token=os.environ["INSTAGRAM_ACCESS_TOKEN"])
        result["quota"] = quota.get("data")
    except Exception as exc:
        result["quota_error"] = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
    for article in articles:
        aid = article["id"]
        state = rows.get(aid, {})
        if not (article.get("social_publish") is True or article.get("social_security_severity")):
            continue
        row = {"id": aid, "approved": article.get("social_publish") is True, "platforms": article.get("social_platforms", list(social.SOCIAL_PLATFORMS)), "ledger": state, "matches": {}}
        for kind, items in streams.items():
            found = matches(article, kind, items)
            row["matches"][kind] = [{k: x.get(k) for k in ("id", "permalink", "timestamp")} for x in found]
        review = any(v.get("status") in ("attempting", "needs_review") for v in state.values())
        if review or article.get("social_publish") is False or article.get("social_platforms"):
            row["assets"] = {}
            for name, url, jpg in (("article", social.article_url(article), False), ("feed", social.image_url(article), True), ("story", social.story_image_url(article), True)):
                try:
                    social.verify_live(url, jpg=jpg, attempts=1)
                    row["assets"][name] = "visible"
                except RuntimeError as exc:
                    row["assets"][name] = str(exc)
        result["articles"].append(row)
        if review or not row["approved"] or article.get("social_platforms"):
            print("RECONCILE", json.dumps(row, ensure_ascii=False))
    out = social.ROOT / "social-delivery-audit.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print("AUDIT_SUMMARY", json.dumps({k: result[k] for k in ("checked_at", "accounts", "quota", "collections")}, ensure_ascii=False))
    print("Read-only audit finished; no Meta posts and no ledger writes")
    return 0 if all(result["accounts"].get(k, {}).get("verified") for k in ("threads", "instagram")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
