#!/usr/bin/env python3
"""Allow ledger-only drift while requiring all publishable source to be deployed."""
import os
import subprocess
try:
    from . import publish_social as social
except ImportError:
    import publish_social as social


def safe_drift(paths):
    return all(path == ".github/social-post-ledger.json" for path in paths)


def main():
    expected = os.environ.get("EXPECTED_SHA", "")
    if not expected:
        response = social.request_json("https://api.github.com/repos/" + os.environ["GITHUB_REPOSITORY"]
                                       + "/actions/runs?branch=main&status=success&per_page=50",
                                       token=os.environ["GITHUB_TOKEN"])
        matches = [r for r in response.get("workflow_runs", []) if r.get("name") == "Build and deploy WORK SIGNAL"
                   and r.get("conclusion") == "success" and r.get("head_branch") == "main"]
        if not matches:
            raise RuntimeError("No successful Pages deployment found")
        expected = matches[0]["head_sha"]
    if len(expected) != 40 or any(c not in "0123456789abcdef" for c in expected):
        raise RuntimeError("Invalid deployment revision")
    subprocess.run(["git", "fetch", "--no-tags", "origin", "main", expected], check=True)
    def changed(left, right):
        return subprocess.check_output(["git", "diff", "--name-only", left, right], text=True).splitlines()
    if not safe_drift(changed(expected, "HEAD")) or not safe_drift(changed(expected, "origin/main")):
        raise RuntimeError("Publication source is not fully deployed; wait for the next scheduled run")
    print("VERIFIED_DEPLOYED_REVISION", expected, "only ledger drift allowed")


if __name__ == "__main__":
    main()
