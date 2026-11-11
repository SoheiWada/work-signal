#!/usr/bin/env bash
# Opt-in UI quality audit only. This script never edits site sources or triggers deployments.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

target="${1:-index.html}"
mode="${2:-desktop}"

case "$target" in
  index.html|article.html|assets/css/signal-interactions.css|assets/css/hero-market.css|https://signal.amberlight.co.jp/|https://signal.amberlight.co.jp/articles/*)
    ;;
  *)
    printf 'Unsupported audit target: %s\n' "$target" >&2
    exit 64
    ;;
esac

case "$mode" in
  desktop|mobile) ;;
  *)
    printf 'Mode must be desktop or mobile.\n' >&2
    exit 64
    ;;
esac

flags=()
if [[ "$target" == https://* ]] && [[ "$mode" == mobile ]]; then
  flags=(--viewport 390x844)
fi
if [[ "$target" != https://* ]] && [[ "$mode" == mobile ]]; then
  printf 'Mobile viewport applies to URL scans; source scan uses default mode.\n' >&2
  exit 64
fi

if ! command -v node >/dev/null || ! command -v npx >/dev/null; then
  printf 'Node.js and npx are required.\n' >&2
  exit 1
fi

report_dir="$(mktemp -d "${TMPDIR:-/tmp}/work-signal-ui-audit.XXXXXX")"
report_json="$report_dir/results.json"
report_log="$report_dir/stderr.log"

# Avoid changing the production repo. npm/engine caches may still be written to user home.
# No install/init/hooks/live commands are executed.
set +e
DO_NOT_TRACK=1 npx --yes impeccable@4.8.0 detect --json "${flags[@]}" "$target" >"$report_json" 2>"$report_log"
status=$?
set -e

printf 'Target: %s (%s)\nReports: %s\n' "$target" "$mode" "$report_dir"
case "$status" in
  0)
    printf 'Scan completed with no primary findings.\n'
    ;;
  2)
    printf 'Scan completed and reported primary findings; review results.json.\n'
    ;;
  *)
    printf 'Scan could not complete (exit %s). Review stderr.log.\n' "$status" >&2
    exit 1
    ;;
esac
