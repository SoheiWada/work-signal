"""Canonical public identity shared by article and listing structured data.

The static home/about schemas are checked against these helpers by SEO tests.
No article byline, publication timestamp or social delivery state belongs here.
"""
BASE = "https://signal.amberlight.co.jp/"
OFFICIAL_PROFILES = {
    "Instagram": "https://www.instagram.com/work_signal_japan/",
    "Threads": "https://www.threads.com/@work_signal_japan",
    "Facebook": "https://www.facebook.com/profile.php?id=61596301937684",
}
OPERATOR_NOTE = "https://note.com/amber_light"


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
        "sameAs": list(OFFICIAL_PROFILES.values()),
        "parentOrganization": {
            "@type": "Organization",
            "@id": "https://signal.amberlight.co.jp/about/#operator",
            "name": "アンバーライト合同会社",
            "sameAs": [OPERATOR_NOTE]
        },
        "publishingPrinciples": "https://signal.amberlight.co.jp/about/#editorial-policy",
        "founder": {
            "@type": "Person",
            "@id": "https://signal.amberlight.co.jp/about/#editor-in-chief",
            "name": "和田壮平",
            "jobTitle": "編集責任者"
        }
    }
