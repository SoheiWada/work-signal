"""Conservative local Instagram feed pacing; not Meta's quota or release policy.

No network or writes. A 48-hour local minimum never releases an active hold.
"""
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))
MIN_INTERVAL = timedelta(hours=24)
COOLDOWN = timedelta(hours=48)


def _stamp(value):
    if not isinstance(value, str):
        raise ValueError("Timestamp required")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timezone required")
    return result.astimezone(timezone.utc)


def restriction_metadata(checked_at):
    return {"restricted_until": (_stamp(checked_at) + COOLDOWN).isoformat(timespec="seconds")}


def feed_pacing_state(rows, clock=None):
    clock = clock or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        raise ValueError("Timezone required")
    activities, restrictions, active_hold = [], [], False
    for history in rows.values():
        if not isinstance(history, dict):
            return {"allowed":False, "reason":"feed_history_unknown", "manual_release_required":True}
        entry = history.get("instagram")
        if entry is None:
            continue
        if not isinstance(entry, dict):
            return {"allowed":False, "reason":"feed_history_unknown", "manual_release_required":True}
        error = entry.get("error", {})
        hold = (entry.get("action_block_hold") is True or
                (entry.get("status") == "needs_review" and isinstance(error, dict)
                 and error.get("code") == 4 and error.get("subcode") == 2207051))
        active = hold and not entry.get("action_block_cleared_at")
        active_hold |= active
        try:
            if entry.get("restricted_until"):
                restrictions.append(_stamp(entry["restricted_until"]))
            elif active:
                restrictions.append(_stamp(entry["updated_at"]) + COOLDOWN)
            if entry.get("status") in ("published", "attempting", "needs_review") or entry.get("feed_attempted_at"):
                stamp = _stamp(entry.get("feed_attempted_at") or entry.get("updated_at"))
                if stamp > clock + timedelta(minutes=5):
                    raise ValueError("Future feed activity")
                activities.append(stamp)
        except (KeyError, TypeError, ValueError):
            return {"allowed":False, "reason":"feed_history_time_unknown", "manual_release_required":True}
    deadline = max(restrictions) if restrictions else None
    if active_hold or (deadline and deadline > clock):
        return {"allowed":False, "reason":"protective_hold" if active_hold else "minimum_cooldown",
                "restricted_until":deadline.isoformat() if deadline else None,
                "manual_release_required":bool(active_hold)}
    if activities:
        last = max(activities)
        today = clock.astimezone(JST).date()
        today_used = sum(t.astimezone(JST).date() == today for t in activities)
        until = last + MIN_INTERVAL
        if today_used:
            midnight = datetime.combine(today + timedelta(days=1), datetime.min.time(), JST)
            until = max(until, midnight)
        if today_used or until > clock:
            return {"allowed":False, "reason":"feed_pacing", "next_attempt_at":until.isoformat(),
                    "manual_release_required":False, "attempts_today":today_used}
    return {"allowed":True, "reason":"ready", "manual_release_required":False}


def safe_pacing_deferral(entry, clock=None):
    clock = clock or datetime.now(timezone.utc)
    try:
        return (isinstance(entry, dict) and entry.get("status") == "deferred"
                and entry.get("reason") == "instagram_feed_pacing"
                and not any(entry.get(k) for k in ("remote_id", "container_id", "previous_attempt", "stage"))
                and _stamp(entry["next_attempt_at"]) > clock)
    except (KeyError, TypeError, ValueError):
        return False
