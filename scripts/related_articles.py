"""Select useful, crawlable related stories without changing article content.

Editorial links take precedence, then shared advisories/products and specific
reader topics. A shared category or generic word never creates a link alone.
"""
import re
from urllib.parse import urlparse

# Explicit aliases normalize product spellings. ASCII boundaries also work when
# a Latin product name is immediately followed by Japanese text.
PRODUCTS = {
    'nodejs': r'node(?:\.js|js)',
    'undici': r'undici', 'bun': r'bun', 'brotli': r'brotli',
    'express': r'express', 'body-parser': r'body-parser', 'multer': r'multer',
    'storybook': r'storybook', 'react': r'react', 'nextjs': r'next(?:\.js|js)',
    'vite': r'vite', 'vitest': r'vitest', 'wordpress': r'wordpress',
    'fortinet': r'fortinet|fortios|fortigate', 'microsoft365': r'microsoft\s*365',
    'claude': r'claude|anthropic', 'openai': r'openai|chatgpt',
    'gemini': r'gemini', 'bitcoin': r'bitcoin|ビットコイン',
    'ethereum': r'ethereum|イーサリアム',
}
TOPICS = {
    'incident-monitoring': r'インシデント|サイバー攻撃|ランサムウェア|情報漏[え洩]',
    'compression': r'brotli|qpack|圧縮(?:データ|リクエスト|レスポンス)',
    'developer-tools': r'開発サーバー|開発環境|dev\s*server',
    'ai-security': r'ai.{0,16}(?:サイバー|攻撃|防御)|(?:サイバー|攻撃|防御).{0,16}ai',
    'real-wages': r'実質賃金|賃上げ|最低賃金',
    'interest-rates': r'利上げ|利下げ|政策金利',
    'hiring': r'採用|就職|転職|求人',
    'management': r'1on1|心理的安全性|管理職|マネジメント',
}
PATTERNS = {key: re.compile(r'(?<![a-z0-9_-])(?:' + value + r')(?![a-z0-9_-])', re.I)
            for key, value in PRODUCTS.items()}
TOPIC_PATTERNS = {key: re.compile(value, re.I) for key, value in TOPICS.items()}
GENERIC = {'security', 'critical', 'high', 'medium', 'low', 'cve', 'update',
           'http', 'https', 'tls', 'dos', 'rce', 'api', 'ai', 'web', 'server',
           'windows', 'linux', 'npm', 'github', 'signal', 'work'}


def features(article):
    # URLs in paragraphs are references, not evidence that two stories discuss
    # the same product. Do not extract arbitrary keywords from those URLs.
    lead = ' '.join(str(article.get(k) or '') for k in
                    ('title', 'summary', 'social_security_product'))
    body = lead + ' ' + ' '.join(str(section.get('body') or '')
                                for section in article.get('sections', [])
                                if isinstance(section, dict))
    products = {key for key, pattern in PATTERNS.items() if pattern.search(lead)}
    source = urlparse(article.get('source_url', ''))
    parts = source.path.strip('/').split('/')
    if source.hostname == 'github.com' and len(parts) >= 2 and parts[0] not in ('advisories', 'orgs'):
        products.add('repo:' + '/'.join(parts[:2]).lower())
    cves = set(re.findall(r'CVE-\d{4}-\d{4,}', body, re.I))
    topics = {key for key, pattern in TOPIC_PATTERNS.items() if pattern.search(lead)}
    words = set(re.findall(r'[a-z][a-z0-9_-]{2,}', article.get('title', '').lower())) - GENERIC
    words = {word for word in words if not word.startswith(('cve-', 'ghsa-'))}
    return products, {cve.upper() for cve in cves}, topics, words


def editorial_ids(article):
    value = article.get('related_article_ids', [])
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def related_articles(article, articles):
    def publishable(item):
        score = item.get('score')
        approved = (item.get('format') in ('special_story', 'management_guide')
                    or (isinstance(score, (int, float)) and not isinstance(score, bool) and score >= 80))
        return item.get('status') == 'published' and approved
    eligible = [item for item in articles if publishable(item) and item.get('id') != article['id']]
    products, cves, topics, words = features(article)
    chosen = []
    by_id = {item['id']: item for item in eligible}
    for identifier in editorial_ids(article):
        if identifier in by_id and identifier not in {item['id'] for item in chosen}:
            chosen.append(by_id[identifier])
        if len(chosen) == 2:
            return chosen
    ranked = []
    for item in eligible:
        if item['id'] in {selected['id'] for selected in chosen}:
            continue
        other_products, other_cves, other_topics, other_words = features(item)
        shared_products = products & other_products
        shared_cves = cves & other_cves
        shared_topics = topics & other_topics
        shared_words = words & other_words
        reverse = article['id'] in editorial_ids(item)
        # Require a concrete connection. A topic alone is sufficient within the
        # same category; across categories require two topics or editorial intent.
        topic_match = bool(shared_topics) and (item.get('category') == article.get('category')
                                               or len(shared_topics) >= 2)
        lexical_match = len(shared_words) >= 2
        if not (reverse or shared_cves or shared_products or topic_match or lexical_match):
            continue
        score = (500 * reverse + 200 * bool(shared_cves)
                 + 100 * bool(shared_products) + 10 * len(shared_products)
                 + 20 * topic_match + len(shared_topics) + len(shared_words))
        ranked.append((score, item.get('published_at', ''), item['id'], item))
    ranked.sort(key=lambda row: row[:3], reverse=True)
    return (chosen + [row[3] for row in ranked])[:2]
