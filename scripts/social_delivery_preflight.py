"""Read-only duplicate protection before a previously unclaimed delivery.

Complete account history is required. Stories are matched by their image,
never by an empty caption; absence needs a known published positive control.
This module never posts or changes the ledger.
"""
from datetime import datetime, timezone, timedelta
try:
    from . import publish_social as social
    from .audit_social_delivery import collect, matches, story_image_checks
except ImportError:
    import publish_social as social
    from audit_social_delivery import collect, matches, story_image_checks


class DeliveryPreflight:
    def __init__(self, articles, rows, credentials, *, target_ids=()):
        self.articles, self.rows, self.credentials = articles, rows, credentials
        self.target_ids = target_ids
        self.histories = {}
        self.story_checks = None

    def history(self, kind):
        if kind not in self.histories:
            thread = kind == "threads"
            prefix = "THREADS" if thread else "INSTAGRAM"
            endpoint = {"threads": "threads", "instagram": "media",
                        "instagram_story": "stories"}[kind]
            fields = ("id,text,timestamp,permalink" if thread else
                      "id,caption,timestamp,permalink,media_url")
            items, complete = collect(
                social.THREADS_API if thread else social.IG_API,
                self.credentials[prefix + "_USER_ID"] + "/" + endpoint,
                self.credentials[prefix + "_ACCESS_TOKEN"], fields)
            if not complete:
                raise RuntimeError("Incomplete live history; delivery withheld")
            self.histories[kind] = items
        return self.histories[kind]

    def existing(self, article, kind):
        items = self.history(kind)
        if kind == "instagram_story":
            if self.story_checks is None:
                self.story_checks = story_image_checks(
                    self.articles, self.rows, items,
                    target_ids=self.target_ids)
            evidence = self.story_checks.get(article["id"], {})
            ids = {str(x) for x in evidence.get("matching_ids", [])}
            found = [x for x in items if str(x["id"]) in ids]
            if not found:
                # An active-story endpoint cannot exclude an expired story.
                # First-publication dates have day precision, so only today's
                # unclaimed stories have a safe <24h observation window.
                today = datetime.now(timezone(timedelta(hours=9))).date().isoformat()
                if article.get("published_at") != today or not evidence.get("absence_verified"):
                    raise RuntimeError("Story absence not verified within 24h; manual review required")
        else:
            found = matches(article, kind, items)
        if len(found) > 1:
            raise RuntimeError("Multiple matching live posts; manual review required")
        return found[0] if found else None
