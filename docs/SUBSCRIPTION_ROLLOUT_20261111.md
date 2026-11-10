# Existing-channel subscription and return paths

`/follow/` explains how to follow WORK SIGNAL on existing Threads and Instagram
accounts or subscribe through RSS. The home navigation and a compact strip,
plus canonical article end sections, link to this hub. Stories continue to
direct readers through the existing profile website link. Profiles and remote
account settings are not rewritten; no X API, mailing list, Web Push vendor or
new paid subscription service is enabled.

The RSS URL is visible, selectable and copyable. A failed clipboard operation
shows a truthful manual-copy fallback. The page works without analytics, and
ordinary channel links remain usable without JavaScript. No registration form
or claim of a completed subscription is generated.

Existing `social_follow_click` events retain their article-end placement and
add an explicit `follow_page` placement. `rss_url_copy` records successful URL
copies only. Neither event proves a follow or subscription, and neither should
be reported as subscriber growth. Site returns from SNS continue to use GA4
referrer reports. Post URLs keep their canonical form without UTM parameters.

RSS items are sorted by their validated publication time where it is known.
Known times are emitted as correct RFC 822 UTC dates. Legacy articles that have
only a date omit the optional pubDate; the builder does not invent midnight
UTC. GUIDs and article URLs stay stable, and approved article/SNS data is not
rewritten. News and image discovery files from the earlier rollout remain.

Validation covers the hub's real destinations, exact RSS copy/fallback and
analytics behavior, timezone/order and unknown date precision. Existing site
tests and all-page SEO/output audits remain gates. Chromium checks the hub and
home at 390/1440 pixels, verifies the actual copied URL and checks overflow;
screenshots are available in the build artifacts. Production deployment and
live `/follow/`, RSS and article/home return links must be checked separately
from a successful source-code commit. Instagram feed holds and existing
published/attempting/needs_review records remain authoritative.
