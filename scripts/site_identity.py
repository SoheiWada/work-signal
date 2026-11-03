"""Canonical public identity shared by article and listing structured data.

The static home/about schemas are checked against these helpers by SEO tests.
No article byline, publication timestamp or social delivery state belongs here.
"""
BASE = "https://signal.amberlight.co.jp/"


def publisher_identity():
    """Return a fresh object so article-specific callers cannot mutate identity."""
    return {
        "@type": "Organization",
        "@id": "https://signal.amberlight.co.jp/#publisher",
        "name": "WORK SIGNAL",
        "alternateName": [
            "WORK.SIGNAL",
            "ワークシグナル"
        ],
        "url": "https://signal.amberlight.co.jp/",
        "description": "AI・仕事・マネジメント・経済の変化を一次情報から読み解くニュース解説メディア。",
        "logo": {
            "@type": "ImageObject",
            "url": "https://signal.amberlight.co.jp/favicon-192.png",
            "width": 192,
            "height": 192
        },
        "sameAs": [
            "https://www.instagram.com/work_signal_japan/",
            "https://www.threads.com/@work_signal_japan"
        ],
        "parentOrganization": {
            "@type": "Organization",
            "@id": "https://signal.amberlight.co.jp/about/#operator",
            "name": "アンバーライト合同会社"
        },
        "publishingPrinciples": "https://signal.amberlight.co.jp/about/#editorial-policy"
    }
