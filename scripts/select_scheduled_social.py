"""Narrow scheduled recovery to recent, review-valid, safe-to-attempt posts.

Old needs_review / attempting entries are NEVER re-sent and are reported as
historical holds. Meta's protective block prevents writes to that channel.
No state is mutated by this selector.
"""
import json
import os
from datetime import date, datetime, timedelta, timezone
try:
    from . import publish_social as social
except ImportError:
    import publish_social as social

JST = timezone(timedelta(hours=9))


def scheduled_ids(articles, rows, now=None):
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(JST).date()
    blocked = {name for entry in rows.values() if isinstance(entry, dict)
               for name, value in entry.items()
               if name in ("instagram", "instagram_story") and
               isinstance(value, dict) and social.active_instagram_action_block(value)}
    chosen = []
    for article in social.approved_articles(articles):
        aid = article["id"]
        try:
            initial = date.fromisoformat(article["published_at"])
            if initial > today or (today - initial) > timedelta(days=2):
                continue
            if article.get("social_review_valid_until"):
                expiry = datetime.fromisoformat(article["social_review_valid_until"].replace("Z", "+00:00"))
                if expiry.tzinfo is None or expiry <= now:
                    continue
            states = rows.get(aid, {})
            if not isinstance(states, dict):
                continue
            remaining = social.remaining_platforms(states)
            if any(p in social.requested_platforms(article) and p not in blocked for p in remaining):
                chosen.append(aid)
        except (KeyError, TypeError, ValueError, RuntimeError):
            # Unknown evidence is a manual review case, not a social write.
            print("SCHEDULED_HOLD_UNCERTAIN", aid)
    return sorted(chosen)


def main():
    feed = json.loads((social.ROOT / "data/articles.json").read_text())
    ledger = social.GithubLedger(os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"])
    rows, _ = ledger.read()
    ids = scheduled_ids(feed, rows)
    if os.getenv("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            output.write("ready=" + ("true" if ids else "false") + "\n")
            output.write("article_ids=" + ",".join(ids) + "\n")
    print("SCHEDULED_SAFE_TARGETS", json.dumps(ids))
    print("Historical/blocked entries remain visible in ledger but do not restart.")


if __name__ == "__main__":
    main()
