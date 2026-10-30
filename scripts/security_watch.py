"""Build SECURITY WATCH from reviewed article metadata plus the legacy alert archive."""
from datetime import datetime, timezone


STALE_STATUS = "修正状況は最新記事で確認"


def _parse_utc(value):
    """Return a comparable UTC datetime; invalid/missing evidence is not trusted."""
    if not isinstance(value, str) or not value:
        return None
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return instant.astimezone(timezone.utc) if instant.tzinfo else None
    except ValueError:
        return None


def _current_status(record, article):
    """Never publish an old remediation claim after a newer article revision.

    A reviewed timestamp MUST be later than the article revision. Older legacy
    rows without timestamps retain their status only until the article is updated.
    This deliberately avoids inferring patch availability from article prose.
    """
    status = record.get("status", "")
    updated = article.get("updated_at")
    if not updated or not status:
        return status
    verified = _parse_utc(record.get("status_reviewed_at"))
    article_updated = _parse_utc(updated)
    if article_updated is None or verified is None or verified < article_updated:
        return STALE_STATUS
    return status


def security_feed(articles, legacy):
    if not isinstance(legacy, list):
        raise ValueError("SECURITY WATCH archive must be a list")
    alerts = {}
    for row in legacy:
        aid = row.get("article_id")
        if not isinstance(aid, str) or aid in alerts:
            raise ValueError("Duplicate or invalid SECURITY WATCH article reference")
        alerts[aid] = dict(row)
    for article in articles:
        level = article.get("social_security_severity")
        explicit = article.get("security_watch")
        if explicit is False:
            if not article.get("security_watch_exclusion_reason"):
                raise ValueError("SECURITY WATCH exclusion needs a reviewed reason")
            alerts.pop(article["id"], None)
            continue
        if explicit is not None and not isinstance(explicit, dict):
            raise ValueError("Invalid article SECURITY WATCH metadata")
        if article["id"] in alerts and explicit is None:
            # Legacy records retain reviewed IDs, initial dates and response
            # status. Display headline and summary always come from the
            # canonical published article, so updated findings cannot drift.
            existing = alerts[article["id"]]
            existing["headline"] = article.get("security_headline") or article["title"]
            existing["summary"] = article["summary"]
            if level in ("HIGH", "CRITICAL"):
                existing["severity"] = level
                existing["product"] = article.get("social_security_product") or existing["product"]
            existing["status"] = _current_status(existing, article)
            continue
        if not level and explicit is None:
            continue
        if level not in ("HIGH", "CRITICAL"):
            raise ValueError("Explicit reviewed security severity is required")
        metadata = explicit or {}
        product = metadata.get("product", article.get("social_security_product"))
        summary = metadata.get("summary", article.get("summary"))
        if not isinstance(product, str) or not product.strip() or not isinstance(summary, str) or not summary.strip():
            raise ValueError("Reviewed product and summary required for SECURITY WATCH")
        alerts[article["id"]] = {
            "id": article["id"], "article_id": article["id"],
            "date": article["published_at"], "severity": level,
            "product": product.strip(), "summary": summary.strip(),
            "headline": article.get("security_headline") or article["title"],
            "status": metadata.get("status", "対応・影響条件は記事を参照"),
            **({"status_reviewed_at": metadata["status_reviewed_at"]}
               if metadata.get("status_reviewed_at") else {}),
        }
        alerts[article["id"]]["status"] = _current_status(alerts[article["id"]], article)
    return list(alerts.values())
