# Threads-only recovery candidates (2026-10-28)

The 2026-10-28 13:32 UTC read-only audit, Actions run 40697302960, confirmed the Threads collection complete (60 posts) and no article URL matches for:

- `20261028-gemini-4-argon-nasa-80000-files` (container `18132881209690068`)
- `20261028-bun-http3-qpack-memory-cpu-dos` (container `18132920314690068`)

Both have `threads.status=needs_review` and `stage=publish_requested`. User reported no matching posts. Reconcile against current Threads collection again immediately before any one-time retry, require complete pagination, exact URL absence, current ledger status and approved article. Claim and publish only Threads, one at a time, record remote ID, and stop on any ambiguous API result. Do not touch Instagram or other articles. Do not reset the ledger wholesale.
