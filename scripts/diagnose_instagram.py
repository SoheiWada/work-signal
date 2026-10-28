#!/usr/bin/env python3
"""GET-only Instagram health diagnostic. Never post or change the ledger."""
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://graph.instagram.com/v25.0/"
STATES = {"FINISHED", "IN_PROGRESS", "ERROR", "EXPIRED", "PUBLISHED"}
USAGE_KEYS = {"call_count", "total_cputime", "total_time", "estimated_time_to_regain_access", "acc_id_util_pct"}


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_usage(value):
    if not isinstance(value, dict):
        return {}
    return {k: v for k, v in value.items() if k in USAGE_KEYS and type(v) in (int, float)}


def safe_headers(headers):
    result = {}
    for name in ("x-app-usage", "x-business-use-case-usage"):
        raw = headers.get(name)
        if not raw:
            continue
        try:
            value = json.loads(raw)
            if name == "x-app-usage":
                result[name] = safe_usage(value)
            elif isinstance(value, dict):
                # Discard account/app keys, URLs, tokens, and unrecognised fields.
                result[name] = [safe_usage(row) for rows in value.values()
                                if isinstance(rows, list) for row in rows if isinstance(row, dict)]
        except (ValueError, TypeError):
            result[name] = "unreadable"
    retry = headers.get("retry-after", "")
    if retry.isdigit():
        result["retry-after-seconds"] = int(retry)
    for name in ("x-fb-trace-id", "x-fb-request-id"):
        value = headers.get(name, "")
        if re.fullmatch(r"[A-Za-z0-9_-]{5,128}", value):
            result[name] = value
    return result


def safe_error(value):
    value = value if isinstance(value, dict) else {}
    result = {k: value[k] for k in ("code", "error_subcode") if type(value.get(k)) is int}
    if type(value.get("is_transient")) is bool:
        result["is_transient"] = value["is_transient"]
    error_type = value.get("type", "")
    if re.fullmatch(r"[A-Za-z0-9_]{1,80}", error_type):
        result["type"] = error_type
    trace = value.get("fbtrace_id", "")
    if re.fullmatch(r"[A-Za-z0-9_-]{5,128}", trace):
        result["fbtrace_id"] = trace
    # Classify in memory; never output the raw error, user text, or an embedded token.
    message = " ".join(str(value.get(k, "")) for k in ("message", "error_user_title", "error_user_msg")).lower()
    patterns = {"spam_or_protective": ("spam", "protect", "restrict", "block"),
                "rate_limit": ("rate limit", "too many", "maximum number", "limit reached"),
                "permission": ("permission", "scope"), "authentication": ("expired", "access token", "oauth")}
    result["message_categories"] = [name for name, words in patterns.items() if any(w in message for w in words)]
    if message.strip():
        result["message_sha256"] = hashlib.sha256(message.encode()).hexdigest()
    return result


class Reader:
    def __init__(self, token):
        self.token = token
        self.calls = []

    def get(self, path, stage):
        if not re.fullmatch(r"(?:me|[0-9]+)(?:/(?:permissions|content_publishing_limit|media|stories))?(?:\?[^\r\n]*)?", path):
            raise ValueError("Unapproved diagnostic path")
        request = Request(BASE + path, method="GET", headers={"Authorization": "Bearer " + self.token,
                          "Accept": "application/json", "User-Agent": "WORK-SIGNAL-Diagnostic/2.0"})
        call = {"stage": stage, "checked_at": timestamp()}
        try:
            with urlopen(request, timeout=25) as response:
                value = json.loads(response.read(1_000_000))
                call.update(http_status=response.status, usage_headers=safe_headers(response.headers))
        except HTTPError as exc:
            try:
                value = json.loads(exc.read(16_384))
            except (ValueError, TypeError):
                value = {}
            call.update(http_status=exc.code, usage_headers=safe_headers(exc.headers),
                        error=safe_error(value.get("error") if isinstance(value, dict) else {}))
            value = None
        except (URLError, TimeoutError, ValueError) as exc:
            call["transport_error"] = type(exc).__name__
            value = None
        self.calls.append(call)
        return value if isinstance(value, dict) else None


def prior_attempt(entry):
    previous = entry.get("previous_attempt", {})
    return entry if entry.get("error") else previous


def main():
    token, uid = os.getenv("INSTAGRAM_ACCESS_TOKEN", ""), os.getenv("INSTAGRAM_USER_ID", "")
    if not token or not uid.isdigit():
        raise SystemExit("Instagram credentials unavailable")
    reader = Reader(token)
    report = {"checked_at": timestamp(), "method": "GET only", "containers": [], "pending_feeds": []}
    profile = reader.get("me?fields=user_id,username,account_type", "account") or {}
    verified = profile.get("username") == "work_signal_japan" and str(profile.get("user_id") or profile.get("id")) == uid
    report["account"] = {"verified": verified, "type": profile.get("account_type")}
    if not verified:
        report["calls"] = reader.calls
        print("IG_HEALTH", json.dumps(report))
        raise SystemExit("Account could not be verified; diagnostics stopped")
    quota = reader.get(uid + "/content_publishing_limit?fields=config,quota_usage", "quota") or {}
    report["quota"] = [{"quota_usage": r.get("quota_usage"), "config": {
        k: r.get("config", {}).get(k) for k in ("quota_total", "quota_duration")}}
        for r in quota.get("data", []) if isinstance(r, dict)]
    permissions = reader.get("me/permissions", "permissions")
    report["permission_query_state"] = "available" if permissions is not None else "unsupported_or_denied"
    report["permissions"] = [{"permission": r["permission"], "status": r.get("status")}
        for r in (permissions or {}).get("data", []) if isinstance(r, dict)
        and re.fullmatch(r"instagram_[a-z_]+", str(r.get("permission", "")))
        and r.get("status") in ("granted", "declined", "expired")]
    rows = json.loads((ROOT / ".github/social-post-ledger.json").read_text())
    articles = json.loads((ROOT / "data/articles.json").read_text())
    # Read every currently held container, including posts reconciled after an error.
    for aid, per_article in rows.items():
        for kind in ("instagram", "instagram_story"):
            entry = per_article.get(kind, {})
            prior = prior_attempt(entry)
            if not (entry.get("action_block_hold") or prior.get("error")):
                continue
            container = str(prior.get("container_id") or entry.get("container_id") or "")
            if not container.isdigit():
                continue
            live = reader.get(container + "?fields=status_code,status", "container:" + aid) or {}
            remote_id = str(entry.get("remote_id", ""))
            remote = reader.get(remote_id + "?fields=id,media_type,media_product_type,timestamp,permalink",
                                "published_media:" + aid) if remote_id.isdigit() else None
            report["containers"].append({"article_id": aid, "platform": kind,
                "ledger_status": entry.get("status"), "container_id": container,
                "container_status": live.get("status_code") if live.get("status_code") in STATES else "unavailable",
                "prior_error": {k: prior.get("error", {}).get(k) for k in ("http_status", "code", "subcode")},
                "container_error_summary": safe_error({"message": live.get("status", "")}),
                "container_error_codes": sorted(set(re.findall(r"\b(?:220[0-9]{4}|190|368)\b", str(live.get("status", ""))))),
                "published_media_verified": bool(remote and str(remote.get("id")) == remote_id),
                "published_media_product": (remote or {}).get("media_product_type"),
                "hold": entry.get("action_block_hold") is True, "permalink": entry.get("permalink", "")})
    for a in articles:
        if a.get("social_publish") is True and "instagram" in a.get("social_platforms", ["instagram"]):
            entry = rows.get(a["id"], {}).get("instagram", {})
            if entry.get("status") != "published":
                report["pending_feeds"].append({"article_id": a["id"], "state": entry.get("status", "pending"),
                                               "freshness_expires": a.get("social_review_valid_until")})
    report["calls"] = reader.calls
    (ROOT / "instagram-health-diagnostic.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print("IG_HEALTH", json.dumps(report, ensure_ascii=False))
    print("Read-only diagnostic completed; no posts or ledger changes")


if __name__ == "__main__":
    main()
