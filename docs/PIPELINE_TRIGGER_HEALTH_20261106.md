# Publication pipeline trigger health

The Worker wake-up path in SoheiWada/amberlight-analytics now shares the feed
pacing cases in tests/fixtures/instagram-feed-policy.json with the canonical
Python sender. tests/test_feed_policy_contract.py validates this side of the
contract. Daily waiting, rejected attempts, midnight boundaries, protective
holds and malformed timestamps cannot become reasons for a new feed attempt.

The global SNS monitor keeps the primary GitHub schedule warning and separately
reports recent successful repository_dispatch evidence from the external clock.
Only the known publisher/monitor run names qualify. Failed/incomplete runs,
invalid times and unrelated manual runs do not prove clock health. External
coverage is recent for 45 minutes; absent coverage remains a trigger warning.
Trigger health never marks an article or medium published, clears a hold, or
resets an uncertain ledger entry. All existing lock, freshness and recovery
limits remain in place.

For the private EDITOR lifecycle and live-page verification, see
SoheiWada/amberlight-analytics/docs/PIPELINE_STABILITY_20261106.md.
