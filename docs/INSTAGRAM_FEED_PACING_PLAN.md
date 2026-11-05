# Instagram feed pacing and protective cooldown — draft

This change is a reviewable implementation proposal. It does not clear the live
feed hold, change article/media approvals, modify the ledger, or publish anything
until merged and explicitly run through the existing production workflow.

## Local operating policy

- Instagram feed only: at most one new publish attempt per workflow execution,
  at most one per JST calendar day, and at least 24 hours between attempts.
  Crossing midnight does not reset the 24-hour interval. Deterministic spacing
  replaces burst delivery; no jitter or caption randomization is introduced.
- A durable `feed_attempted_at` is recorded before the first remote operation and
  survives later delivery updates. API rejection still consumes that day's
  attempt. Existing records fall back to `updated_at`; missing, invalid, or
  implausibly future activity timestamps require review.
- Feed 4/2207051 records `restricted_until` 48 hours after detection, including
  when F1 reconciliation proves that the errored request actually published.
  This is a conservative local minimum, **not a Meta release guarantee**.
- An active `action_block_hold` still requires deliberate, audited manual
  clearance. Time alone never clears it. Clearing a new hold early cannot
  bypass its stored minimum cooldown. Legacy active holds derive their deadline
  from the recorded `updated_at` without modifying historical ledger entries.
- Threads and Instagram Stories keep their existing publishing, preflight,
  quota and confirmation protections. An Instagram account-wide API quota can
  still affect both Instagram surfaces; feed pacing itself does not stop them.
- Existing `attempting` / `needs_review` entries remain non-retryable. The
  separately reviewed single-feed recovery probe retains its stricter seven-day
  quiet-period and one-call rules; this proposal does not enable or dispatch it.

## Queue and reporting

Scheduled selection skips feed-only work while the policy blocks new attempts;
other selected channels can still be processed. Inside a mixed batch, deliberate
feed waiting is recorded as `deferred`, `reason=instagram_feed_pacing`, with
`next_attempt_at`. This is **not a published post**. A valid future pacing
deferral alone does not fail an otherwise successful batch; real API failures,
uncertain writes, and other incomplete channels still do.

The global backlog report derives the account-level policy even when an article
has never been attempted. It distinguishes interval waiting from protective
hold, and exposes the relevant deadline and manual-release requirement. No fake
pending/published ledger entries are added solely for queue visibility.

Existing freshness limits continue to apply. At one feed per day, some queued
articles will become stale before their turn and require editorial re-review.
The proposal does not extend approval deadlines or publish the old backlog.

## Rollout and measurement

1. Review and merge the draft after CI passes. Keep the current protective hold.
2. Inspect the live ledger and actual feed, then review clearance separately;
   do not retry just because 48 hours elapsed. Do not change tokens or apps as
   part of this pacing experiment.
3. Observe up to two weeks after an authorized restart: attempt time, confirmed
   remote ID/permalink, error code/subcode/fbtrace, cooldown and unresolved holds.
   Count a confirmed publication separately from the HTTP response outcome.
4. Any 2207051 immediately restores the manual hold and local minimum cooldown.
   No retry loop, automatic increase, or timed auto-release is provided.
5. Ten clean observations are useful operational evidence, not proof that cadence
   caused the original restriction. The default cap does not automatically loosen
   after two weeks or any success count.

## Validation

Network-mocked tests cover daily and cross-midnight spacing, another workflow
run, all-channel continuation, malformed history, manual holds after 48 hours,
early-clearance cooldown, F1's error-but-published outcome, and truthful queue /
channel reporting. These tests make no real social publishing calls. The
publisher CI and production preflight include the new tests.
