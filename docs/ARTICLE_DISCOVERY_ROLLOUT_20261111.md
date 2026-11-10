# Article SEO and reading paths

All generated canonical article pages now show the responsible WORK SIGNAL
editorial organization, a breadcrumb trail with matching JSON-LD, and a reading
rail inside the article body so it is available on small screens as well as
desktop. Up to four related stories are ranked by the existing concrete
product/CVE/topic evidence. Any remaining positions use approved same-category
news and are labeled separately. Drafts, low-score stories and the current
article are excluded. Every current article has four distinct target articles.

SECURITY WATCH articles display only their existing approved structured product,
severity and action. Missing scores, affected versions or exploit information
are not inferred. Other article content and editorial approval data are retained.

The organization author matches the visible byline and links to the existing
editorial policy. Existing real modification times are preserved. Legacy
publication dates remain date precision where no verified hour is known.
The original sitemap and URLs are retained. Separate image and news sitemaps
are linked in robots.txt. News contains only published news from the recent
48-hour window at build time, respects publication timezone and excludes future
timestamps, drafts and evergreen guides. The hourly Pages build expires news
entries during periods with no new articles. Static files reflect the latest
successful build, not a live second-by-second filter.

Existing 1200-pixel OG images are indexed without forcing duplicate text cards
into every article header. No new generated illustrations, source expansion,
mass noindex, tracking URL, subscription service or SNS retry is introduced.
The shared social queue and existing feed/unknown-write protection remain in
force when Pages success triggers its ordinary delivery check.

Validation covers all canonical article reading targets, author/breadcrumb
agreement, safe category fallback, protected source data, escaped security
fields, news expiry and date precision. The production gate includes Python
site tests, Node URL/market/NBA tests, full generation and output SEO checks.
Verify the actual live HTML and discovery XML after Pages deployment. Search
Console submissions, Google indexing/rankings and Discover inclusion are not
asserted by a successful deployment.
