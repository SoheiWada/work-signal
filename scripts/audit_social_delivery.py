#!/usr/bin/env python3
"""Read-only reconciliation of approved delivery, live Meta media and deployed assets."""
import json
import os
from io import BytesIO
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.parse import urlparse
from urllib.request import Request, urlopen
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


def story_image_checks(articles, ledger, stories):
    """Stories have no captions: compare the unchanged title area, including a positive control."""
    from PIL import Image, ImageChops, ImageStat
    def image(url, own=False):
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if parsed.scheme != "https" or (not own and not (host.endswith(".cdninstagram.com") or host.endswith(".fbcdn.net"))):
            raise RuntimeError("Unexpected media image host")
        with urlopen(Request(url, headers={"User-Agent": "WORK-SIGNAL-Audit/1.0"}), timeout=30) as response:
            data = response.read(12_000_000)
        picture = Image.open(BytesIO(data)).convert("RGB")
        if abs(picture.width / picture.height - 1080 / 1920) > 0.02:
            raise RuntimeError("Unexpected Story aspect ratio")
        return picture.resize((1080, 1920)).crop((65, 550, 1015, 1370)).resize((160, 160))
    live = [(item, image(item["media_url"])) for item in stories]
    controls = [a for a in articles if ledger.get(a["id"], {}).get("instagram_story", {}).get("remote_id")
                in {str(x[0].get("id")) for x in live}][:3]
    targets = [a for a in articles if ledger.get(a["id"], {}).get("instagram_story", {}).get("status") == "needs_review"]
    output = {}
    for a in controls + targets:
        expected = image(social.story_image_url(a), own=True)
        scores = [(sum(ImageStat.Stat(ImageChops.difference(expected, picture)).mean) / 3, item) for item, picture in live]
        scores.sort(key=lambda x: x[0])
        best, item = scores[0] if scores else (None, {})
        output[a["id"]] = {"closest_difference": round(best, 4) if best is not None else None,
                           "closest_id": item.get("id"), "is_control": a in controls,
                           "matching_ids": [x.get("id") for score, x in scores if score <= 2.0],
                           "all_images_inspected": len(live)}
    control_ok = any(x["is_control"] and x["matching_ids"] for x in output.values())
    for a in targets:
        row = output[a["id"]]
        row["absence_verified"] = bool(control_ok and live and row["closest_difference"] is not None and row["closest_difference"] >= 4.0)
    return output


def main():
    articles = json.loads((social.ROOT / "data/articles.json").read_text())
    ledger = social.GithubLedger(os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"])
    rows, _ = ledger.read()
    result = {"checked_at": social.now(), "accounts": {}, "quota": None, "collections": {}, "articles": []}
    streams = {}
    for key, base, token_name, uid_name, path, fields in (
        ("threads", social.THREADS_API, "THREADS_ACCESS_TOKEN", "THREADS_USER_ID", "threads", "id,text,timestamp,permalink"),
        ("instagram", social.IG_API, "INSTAGRAM_ACCESS_TOKEN", "INSTAGRAM_USER_ID", "media", "id,caption,media_type,media_product_type,timestamp,permalink"),
        ("instagram_story", social.IG_API, "INSTAGRAM_ACCESS_TOKEN", "INSTAGRAM_USER_ID", "stories", "id,caption,media_type,timestamp,permalink,media_url"),
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
    try:
        if result["collections"].get("instagram_story", {}).get("complete"):
            result["story_image_checks"] = story_image_checks(articles, rows, streams.get("instagram_story", []))
            print("STORY_IMAGE_CHECKS", json.dumps(result["story_image_checks"]))
    except Exception as exc:
        print("STORY_IMAGE_CHECK_ERROR", type(exc).__name__)
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
