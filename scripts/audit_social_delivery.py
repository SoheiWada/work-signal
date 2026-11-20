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
        data = response.get("data")
        if not isinstance(data, list) or any(not isinstance(x, dict) or not x.get("id") for x in data):
            raise RuntimeError("Invalid media history; absence cannot be established")
        items.extend(data)
        paging = response.get("paging", {})
        if not paging.get("next"):
            return items, True
        after = paging.get("cursors", {}).get("after")
        if not after:
            break
    return items, False


def matches(article, kind, items):
    if kind == "facebook":
        return social.facebook.matches(article, items, social.article_url(article))
    if kind == "threads":
        needle = social.article_url(article)
        return [x for x in items if needle in (x.get("text") or "")]
    try:
        return social.instagram_feed_matches(article, items)
    except ValueError:
        return []


def story_image_checks(articles, ledger, stories, *, target_ids=()):
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
    live_ids = {str(item["id"]) for item, _ in live}
    bindings = {}
    for a in articles:
        entry = ledger.get(a["id"], {}).get("instagram_story", {})
        remote = str(entry.get("remote_id", ""))
        if entry.get("status") == "published" and remote in live_ids:
            bindings.setdefault(remote, []).append(a)
    controls = [bound[0] for bound in bindings.values() if len(bound) == 1][:3]
    targets = [a for a in articles if a["id"] in target_ids or
               ledger.get(a["id"], {}).get("instagram_story", {}).get("status") == "needs_review"]
    expected_images = {}
    def expected_image(a):
        if a["id"] not in expected_images:
            expected_images[a["id"]] = image(social.story_image_url(a), own=True)
        return expected_images[a["id"]]
    def difference(a, b):
        return sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / 3
    output = {}
    for a in controls + targets:
        expected = expected_image(a)
        scores, known_other = [], []
        for item, picture in live:
            score = difference(expected, picture)
            bound = bindings.get(str(item["id"]), [])
            # Similar headlines (e.g. adjacent CVE numbers) can pass the
            # coarse image threshold. A confirmed remote ID belongs to ONE
            # delivery. Exclude it only when its distinct original asset also
            # matches the live image measurably better. Unknown, duplicated,
            # identical and visually ambiguous bindings remain candidates.
            if score < 4.0 and len(bound) == 1 and bound[0]["id"] != a["id"]:
                other = expected_image(bound[0])
                own_score = difference(other, picture)
                if (ImageChops.difference(expected, other).getbbox() is not None
                        and own_score <= 2.0 and own_score + 0.1 < score):
                    known_other.append(str(item["id"]))
                    continue
            scores.append((score, item))
        scores.sort(key=lambda x: x[0])
        best, item = scores[0] if scores else (None, {})
        output[a["id"]] = {"closest_difference": round(best, 4) if best is not None else None,
                           "closest_id": item.get("id"), "is_control": a in controls,
                           "matching_ids": [x.get("id") for score, x in scores if score <= 2.0],
                           "known_other_ids": known_other,
                           "unresolved_images_inspected": len(scores),
                           "all_images_inspected": len(live)}
    control_ok = any(x["is_control"] and
                     str(ledger[aid]["instagram_story"]["remote_id"]) in
                     [str(value) for value in x["matching_ids"]]
                     for aid, x in output.items())
    for a in targets:
        row = output[a["id"]]
        row["absence_verified"] = bool(control_ok and live and (
            row["unresolved_images_inspected"] == 0 or
            (row["closest_difference"] is not None and row["closest_difference"] >= 4.0)))
    return output


def main():
    articles = json.loads((social.ROOT / "data/articles.json").read_text())
    ledger = social.GithubLedger(os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"])
    rows, _ = ledger.read()
    result = {"checked_at": social.now(), "accounts": {}, "quota": None, "collections": {}, "articles": []}
    try:
        def public_json(path):
            with urlopen(Request(social.BASE + path, headers={"Cache-Control": "no-cache", "User-Agent": "WORK-SIGNAL-Audit/1.0"}), timeout=30) as response:
                return json.load(response)
        public_articles = public_json("data/articles.json")
        public_watch = public_json("data/security-watch.json")
        expected_watch = {a["id"] for a in articles if a.get("social_security_severity") and a.get("security_watch") is not False}
        visible_watch = {x["article_id"] for x in public_watch}
        result["site"] = {"article_count": len(public_articles), "watch_count": len(public_watch),
                          "missing_security_articles": sorted(expected_watch - visible_watch),
                          "source_article_ids_match": {x["id"] for x in public_articles} == {x["id"] for x in articles}}
        print("LIVE_SITE_CHECK", json.dumps(result["site"]))
    except Exception as exc:
        result["site"] = {"error": type(exc).__name__}
        print("LIVE_SITE_CHECK", json.dumps(result["site"]))
    streams = {}
    review_file = social.ROOT / ".github/social-recovery-review.json"
    reviewed_ids = ({x["article_id"] for x in json.loads(review_file.read_text()).get("items", [])}
                    if review_file.is_file() else set())
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
        token = os.environ["FACEBOOK_PAGE_ACCESS_TOKEN"]
        profile = social.facebook.verify_account(social.request_json, token)
        items = social.facebook.history(social.request_json, token)
        streams["facebook"] = items
        result["accounts"]["facebook"] = {"verified": True, "page_id": profile["id"]}
        result["collections"]["facebook"] = {"count": len(items), "complete": True}
    except Exception as exc:
        result["collections"]["facebook"] = {"error": type(exc).__name__, "complete": False}
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
        row = {"id": aid, "approved": article.get("social_publish") is True, "platforms": article.get("social_platforms", list(social.LEGACY_DEFAULT_PLATFORMS)), "ledger": state, "matches": {}}
        row["remote_id_seen"] = {kind: bool(state.get(kind, {}).get("remote_id")
                                     and state[kind]["remote_id"] in {str(x.get("id")) for x in items})
                                 for kind, items in streams.items()}
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
        # Read-only delivery evidence for dashboard and incident triage.
        # An API published response is not equivalent to live visibility.
        row["delivery_evidence"] = {}
        for kind in ("threads", "instagram_story"):
            entry = state.get(kind, {})
            remote_id = str(entry.get("remote_id", ""))
            items = streams.get(kind, [])
            found = next((x for x in items if remote_id and str(x.get("id")) == remote_id), None)
            evidence = {
                "ledger_status": entry.get("status", "untracked"),
                "remote_id": remote_id or None,
                "live_verified": bool(found),
                "collection_complete": result["collections"].get(kind, {}).get("complete", False),
                "checked_at": result["checked_at"],
                "published_at": found.get("timestamp") if found else None,
                "permalink": found.get("permalink") if found else None,
            }
            if kind == "instagram_story":
                # Active-story API only exposes currently available stories.
                # Absence after expiry is NOT evidence of a failed publication.
                evidence["verification_scope"] = "currently_active_stories_only"
                evidence["historical_visibility_unknown"] = not bool(found)
            row["delivery_evidence"][kind] = evidence
        result["articles"].append(row)
        if review or not row["approved"] or article.get("social_platforms") or aid in reviewed_ids:
            print("RECONCILE", json.dumps(row, ensure_ascii=False))
    out = social.ROOT / "social-delivery-audit.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print("AUDIT_SUMMARY", json.dumps({k: result[k] for k in ("checked_at", "accounts", "quota", "collections")}, ensure_ascii=False))
    print("Read-only audit finished; no Meta posts and no ledger writes")
    required = ["threads", "instagram"]
    if any("facebook" in social.requested_platforms(a) for a in social.approved_articles(articles)):
        required.append("facebook")
    return 0 if all(result["accounts"].get(k, {}).get("verified") for k in required) else 1



def facebook_reconciliation_evidence():
    """Read a complete Page history and check only the eight reviewed article IDs."""
    import re
    from urllib.parse import parse_qs, urlsplit

    targets = ["20261118-nvidia-rtx-spark-compact-desktops","20261118-openai-amd-chip-design-14ppa","20261118-google-gemini-4-neon-coding-science","20261118-fomc-minutes-october-ai-debt-risks","20261118-anthropic-ipo-priced-83-biggest-ever","20261120-openai-performance-factory-regression","20261120-gemini-tool-retrieval-on-demand","20261117-anthropic-claude-linked-billing"]
    articles = {row["id"]: row for row in json.loads(
        (social.ROOT / "data/articles.json").read_text())}
    ledger = social.GithubLedger(os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"])
    rows, _ = ledger.read()
    token = os.environ["FACEBOOK_PAGE_ACCESS_TOKEN"]
    profile = social.facebook.verify_account(social.request_json, token)
    items = social.facebook.history(social.request_json, token)
    by_id = {item["id"]: item for item in items}
    if len(by_id) != len(items):
        raise RuntimeError("Duplicate post IDs in Facebook history")

    def link_matches(url, canonical):
        if social.facebook.canonical_link(url, canonical):
            return True
        parsed = urlsplit(url)
        if (parsed.scheme == "https" and parsed.hostname in
                ("l.facebook.com", "lm.facebook.com", "www.facebook.com", "facebook.com")
                and parsed.path == "/l.php" and not parsed.username and not parsed.password):
            links = parse_qs(parsed.query).get("u", [])
            return len(links) == 1 and social.facebook.canonical_link(links[0], canonical)
        return False

    def facts(item, article, canonical):
        message = str(item.get("message") or "")
        urls = social.facebook.attachment_urls(item)
        permalink = item.get("permalink_url")
        return {
            "id": item["id"],
            "page_author_matches": str((item.get("from") or {}).get("id", "")) == profile["id"],
            "published_flag": item.get("is_published"),
            "body_matches": message == social.facebook.text(article, canonical),
            "title_visible": article["title"].strip() in message,
            "canonical_url_in_body": any(link_matches(url, canonical) for url in re.findall(r"https://[^\s<>]+", message)),
            "canonical_attachment": any(social.facebook.canonical_link(link, canonical) for link in urls),
            "canonical_attachment_or_shim": any(link_matches(link, canonical) for link in urls),
            "permalink": permalink if social.facebook.safe_permalink(permalink) else None,
        }

    report = {"checked_at": social.now(), "page_id": profile["id"], "history_complete": True,
              "history_post_count": len(items), "articles": {}}
    for aid in targets:
        article = articles[aid]
        canonical = social.article_url(article)
        entry = rows.get(aid, {}).get("facebook", {})
        expected_id = entry.get("remote_id") or entry.get("container_id")
        known = by_id.get(expected_id)
        indexed = [facts(item, article, canonical) for item in items]
        candidates = [x for x in indexed if x["canonical_url_in_body"]
                      or x["canonical_attachment_or_shim"] or x["title_visible"]]
        report["articles"][aid] = {"canonical_url": canonical, "expected_id": expected_id,
                                   "matched_history_id": facts(known, article, canonical) if known else None,
                                   "candidates": candidates}
        if expected_id:
            try:
                item = social.request_json(social.facebook.API + "/" + expected_id + "?" +
                                           urlencode({"fields": social.facebook.FIELDS}), token=token)
                if item.get("id") == expected_id:
                    report["articles"][aid]["current_exact_id"] = facts(item, article, canonical)
            except social.MetaAPIError as exc:
                report["articles"][aid]["exact_id_error"] = {
                    "http_status": exc.http_status, "code": exc.code, "subcode": exc.subcode
                }
            except (RuntimeError, OSError, ValueError, TypeError, KeyError) as exc:
                report["articles"][aid]["exact_id_error"] = {"type": type(exc).__name__}
    (social.ROOT / "social-delivery-audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print("FACEBOOK_RECONCILIATION_AUDIT", json.dumps(report, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(facebook_reconciliation_evidence())
