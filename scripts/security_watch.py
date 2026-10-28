"""Build SECURITY WATCH from reviewed article metadata plus the legacy alert archive."""
import re


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
        if not level and explicit is None:
            continue
        if level not in ("HIGH", "CRITICAL"):
            raise ValueError("Explicit reviewed security severity is required")
        if article["id"] in alerts and explicit is None:
            continue
        metadata = explicit or {}
        product = metadata.get("product", article.get("social_security_product"))
        summary = metadata.get("summary", article.get("summary"))
        if not isinstance(product, str) or not product.strip() or not isinstance(summary, str) or not summary.strip():
            raise ValueError("Reviewed product and summary required for SECURITY WATCH")
        alerts[article["id"]] = {
            "id": article["id"], "article_id": article["id"],
            "date": article["published_at"], "severity": level,
            "product": product.strip(), "summary": summary.strip(),
            "status": metadata.get("status", "対応・影響条件は記事を参照"),
        }
    return list(alerts.values())
