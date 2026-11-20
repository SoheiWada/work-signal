# Facebook Page delivery — owner instruction 2026-11-18

Target: WORK-SIGNAL.jp, Graph API Page ID `1522891270900103`.
Public profile ID: `61596301937684`.
https://www.facebook.com/profile.php?id=61596301937684

## Verified identity mapping — 2026-11-19 JST

The requested public profile URL resolves to the same WORK-SIGNAL.jp Page whose management sidebar links to Meta Business Suite with `asset_id=1522891270900103`. The owner-authorized OAuth asset selector lists this API ID, and the Page token GET `/v27.0/me?fields=id,name,link` returns `id=1522891270900103`, `name=WORK-SIGNAL.jp`, `link=https://www.facebook.com/1522891270900103`. API writes, token identity and composite post IDs use this exact API ID; the supplied public profile URL remains unchanged. Never accept the public profile ID as an alternative API author.

## Implemented publication contract

- Facebook is an independent channel in the existing locked `social-publish.yml` publisher. No IG crossposting and no separate writer. The Instagram feed pause remains in place.
- The central Editor must explicitly select `facebook` in each new approved article's `social_platforms`. An absent selection still defaults only to the legacy three channels. Threads-only selections remain Threads-only.
- `.github/facebook-channel.json` records a fixed introduction time, a separate `activated_at` (initially null), and all 425 existing article IDs, from immutable articles blob `1b7397a150a457418b1845744d050d9bd7f52422`. Those IDs never qualify, even if their timestamps/approval fields are changed. A new ID also requires a precise timezone-aware publication timestamp after activation and on its declared JST date. Null activation permits no Facebook post. Do not clear the exclusions or move the boundary backwards.
- Only approved, fresh, live-site articles are considered. A Page token must identify the exact Page via `/me`.
- The post is `POST /v27.0/1522891270900103/feed` with title + summary + plain canonical article URL in `message`, and the same canonical URL in `link`. No UTM or invented fbclid. No link-preview overrides.
- Before POST, complete Page history is checked for an existing matching article link. Conflicting duplicates and incomplete history withhold the write. The durable shared ledger is claimed `attempting`, then `publish_requested` is persisted. There is only one POST.
- Success requires a GET confirming the Page author, composite post ID, published flag, approved title and summary, canonical article link attachment and HTTPS Facebook permalink. Meta can move the URL out of the message into its card and wrap the attached URL in its HTTPS link shim. Verify the exact destination by parsing the link locally.
- Automatic follow-up under the common publisher lock reads recorded Facebook post IDs for `publish_response_received` and updates only confirmed entries to `published`. Unknown or absent responses retain `needs_review`. The follow-up makes no Meta write and does not rearm the queue.
- The publisher and backlog monitor both read the `SOCIAL_PAUSED_PLATFORMS` repository variable. Leave it unset to keep the Instagram feed paused by default. An explicit value of `none` clears operator pauses, subject to the existing channel safeguards.
- Facebook has its own account/batch/error state. Missing/expired Facebook credentials cannot suppress Threads or Stories. IG quota/action-block/pacing rules are never applied to Facebook. The common 5-article batch and bounded continuation remain.
- The audit report includes Facebook account/history, per-article match and remote ID. `check_social_channel_outcomes.py` requires both the publication report and a published ledger entry with Page post ID/permalink. Enablement alone is not success.

## Activation sequence — never enable before authentication

Code deployment does not activate posting. Leave repository variable `FACEBOOK_PUBLISH_ENABLED` unset/false until the following are complete. No existing article JSON or ledger is modified by this rollout.

1. In the existing **WORK SIGNAL Social** Meta app, authorize the Page administrator using Facebook Login. Request `pages_show_list`, `pages_read_engagement` and `pages_manage_posts`. The administrator must have the Page's content-creation task. Do not create another app or buy a service.
2. Select **only WORK-SIGNAL.jp / 1522891270900103** in the consent flow. Obtain the corresponding **Page access token**, not a personal user token. If the app's business/asset access screen actually requires a portfolio assignment or consent, the owner completes it. A new Page is not assumed to require a Business transfer.
3. Store the Page token directly as the public **SoheiWada/work-signal repository Actions secret** `FACEBOOK_PAGE_ACCESS_TOKEN` using GitHub Settings → Secrets and variables → Actions. Never put it in chat, Issues, workflow files, articles, command output or artifacts. The private analytics repository does not need this posting token.
4. Use the existing **Audit WORK SIGNAL live social delivery** workflow to read back `/me` and complete `published_posts` history. `accounts.facebook.verified=true` and `page_id=1522891270900103` confirm identity/read access, not successful posting or a permanent token lifetime. Confirm the granted publishing permission separately in Meta. No test POST to an old article.
5. After the public consumer and compatible private Editor/clock are deployed and the read-only connection is verified, commit the actual UTC activation time into `activated_at` in the rollout config (never backdate it), and set public repository Actions variable `FACEBOOK_PUBLISH_ENABLED=true`. Then reread private control Issue #143 and append `facebook` to its existing allowed platform sequence, preserving every other policy field and owner hold. Do not set the policy while the old Worker still rejects four channels. Do not edit #242's clock-managed body.
6. The first qualifying article published **after activation** must be the first live validation. Check its real Page post's body/link/ID/permalink against the ledger. Keep any already-published article excluded, including articles published while authentication was pending. Do not bulk-select them or rewrite their JSON.

If owner authentication cannot be completed in the available session, report code/tests/deployment separately from the remaining Meta consent and secret setup. Do not claim Facebook is operational. Do not repeatedly retry a rejected/unknown POST.

## Read-only activation checks

Run `python scripts/check_facebook_connection.py` with the secret provided via the environment. It prints only Page identity and history count; it never posts or writes the ledger. A successful read does not prove `pages_manage_posts` or delivery. Existing audit workflow uses the same checks and includes the Page in its account report.

Official endpoint contract: https://developers.facebook.com/docs/graph-api/reference/page/feed/
