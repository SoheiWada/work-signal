"""Dispatch social delivery only for newly approved articles after Pages deployment.

A change to SEO, templates, or an already-approved article must never trigger
a new social posting event. This script only reads Git history. It does not
approve, publish, amend the social ledger, or contact Meta.
"""
import json
import os
import re
import subprocess
import sys

SHA = re.compile(r"^[0-9a-f]{40}$")


def eligible(article):
    if not isinstance(article, dict) or article.get("social_publish") is not True or article.get("status") != "published":
        return False
    score = article.get("score")
    return (article.get("format") in ("special_story", "management_guide")
            or (type(score) in (int, float) and score >= 80))


def approvals(previous, current):
    """Only newly explicit approvals, not edits or reclassification."""
    before = {item["id"] for item in previous if eligible(item)}
    after = {item["id"] for item in current if eligible(item)}
    return sorted(after - before)


def source_at(sha):
    value = subprocess.check_output(
        ["git", "show", sha + ":data/articles.json"], text=True
    )
    data = json.loads(value)
    if not isinstance(data, list):
        raise ValueError("Published source is not a list")
    return data


def main():
    old, new = os.environ.get("BEFORE_SHA", ""), os.environ.get("AFTER_SHA", "")
    # Do not treat missing history as authorisation for a bulk social send.
    if not SHA.fullmatch(old) or not SHA.fullmatch(new) or old == "0" * 40:
        print("NO_DISPATCH: trustworthy before/after commit unavailable")
        return 0
    ids = approvals(source_at(old), source_at(new))
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            output.write("approved=" + ("true" if ids else "false") + "\n")
            output.write("article_ids=" + ",".join(ids) + "\n")
    print("APPROVAL_DELTA", json.dumps(ids, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
