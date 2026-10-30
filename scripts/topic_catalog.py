"""Editorial reading paths; never alter publication or social approval fields."""
import re

TOPICS = (
    {
        "id": "ai-work",
        "name": "AIを仕事で活用する",
        "title": "AIの業務活用｜導入事例・AIエージェント・情報管理の読み方",
        "description": "生成AIを仕事で使う前に確認したい導入事例、AIエージェントの利用条件、社内情報の扱いを、WORK SIGNALの一次情報に基づく記事から読む。",
        "intro": "AIの新機能を知るところから、職場で任せる仕事と確認する人を決めるところまで。発表された機能、企業の導入事例、WORK SIGNALの考察を分けて読み、実際の業務に合うかを判断するための入口です。",
        "reviewed_at": "2026-10-30",
        "categories": ("AI", "仕事", "マネジメント"),
        "pattern": r"業務|仕事|働き|Copilot|Duet|エージェント|人事|顧客|契約|社内|導入|Model Spec",
        "steps": (
            {"title": "1. 任せたい仕事を具体的にする", "text": "企業の導入人数や利用率に加えて、どの業務が変わったのかを確認します。事例の成果を自社でも再現できると決めつけず、利用条件と評価方法を読みます。",
             "articles": ("20261028-fujitsu-copilot-100k-service-desk-ai", "20261026-volkswagen-copilot-330000-adoption")},
            {"title": "2. AIエージェントの条件と承認を知る", "text": "提供地域・契約・研究プレビューといった利用条件を先に確認します。作業を任せる場合は、人の承認が必要な操作と、終了後に確認する内容を決める視点で読みます。",
             "articles": ("20261022-anthropic-claude-duet", "20261030-openai-model-spec-five-values-human-intent")},
            {"title": "3. 入力する情報と運用を見直す", "text": "個人情報や社内情報をどこまで入力できるか、接続先や権限を誰が管理するかを確認します。便利さだけでなく、失敗したときの対応まで考える材料を集めます。",
             "articles": ("20261026-panasonic-hr-data-generative-ai-governance", "20261029-microsoft-copilot-harness-foundry-preview")},
        ),
    },
    {
        "id": "security-practice",
        "name": "企業のセキュリティ対策",
        "title": "企業のセキュリティ対策｜情報収集・無料相談・更新確認の読み方",
        "description": "管理職・運用担当者向けに、公開インシデントの調べ方、公的な無料相談、脆弱性の影響範囲と更新確認を読む順番で案内。SECURITY WATCHの公式情報にもつなぐ。",
        "intro": "事故のニュースを見たとき、まず何を調べ、誰に相談し、どの製品を確認すればよいか。経営・運用の視点から読み始め、必要に応じて個別製品の公式勧告へ進むためのガイドです。最新の修正版や悪用状況は記事内の一次情報でも確認してください。",
        "reviewed_at": "2026-10-30",
        "categories": ("SECURITY", "仕事", "AI"),
        "pattern": r"インシデント|サイバー|セキュリティ|脆弱性|情報漏|不正アクセス",
        "steps": (
            {"title": "1. 公開情報と原典を確認する", "text": "インシデント情報を集めるサービスは調査の入口になります。掲載情報の有無だけで安全を判断せず、対象企業の公式発表や、公表日・発生日の違いまで確認する視点で読みます。",
             "articles": ("20261021-jp-incident-monitor-cyber-risk-management", "20261020-ai-cyberattacks-japan-artex")},
            {"title": "2. 自社で判断できない点を相談する", "text": "機器や委託先、対応する人が把握できているかを整理します。公的支援の記事では対象・利用方法を確認し、製品の更新情報では利用中の製品と系列を照合するところから始めます。",
             "articles": ("20261028-sme-cybersecurity-free-consultation", "20261024-fortinet-security-hardening-critical-updates")},
            {"title": "3. 更新が稼働環境に反映されたか確かめる", "text": "本体、周辺ライブラリ、コンテナなど、更新する対象を分けて読みます。バージョン番号だけでなく、対象となる機能や導入方法、更新後の確認事項にも目を向けます。",
             "articles": ("20261026-aspnetcore-linux-tarball-ownership-cve-2026-114148", "20261024-express-body-parser-compressed-request-dos")},
        ),
    },
    {
        "id": "management",
        "name": "管理職の実務",
        "title": "管理職の実務｜業務棚卸し・1on1・属人化を見直す読み方",
        "description": "管理職の仕事が減らない、1on1で部下が話さない、できる人に仕事が集中する。現場の悩みから、業務棚卸し・対話・役割分担を考える実践解説へ案内する。",
        "intro": "予定が埋まり続ける、部下との対話が進まない、特定の人に仕事が集中する。現場の悩みを分けて考え、小さく試せる改善へつなぐための読む順番をまとめました。ここで案内する独自解説は、ニュース記事と形式を区別して掲載しています。",
        "reviewed_at": "2026-10-30",
        "categories": ("仕事", "マネジメント", "AI"),
        "pattern": r"管理職|マネジメント|1on1|1対1|属人化|部下|業務棚卸し|人材育成",
        "steps": (
            {"title": "1. 抱えている仕事を整理する", "text": "仕事の量を増やす前に、やめる基準や役割分担を考えます。忙しさを一つの問題として扱わず、予定・判断・作業のどこに負担が集中しているかを整理する材料として読みます。",
             "articles": ("20261021-management-stop-doing-work", "20261021-management-margin-20-percent")},
            {"title": "2. 日々の対話を見直す", "text": "1on1の場だけで解決を急がず、普段の会話とのつながりを考えます。AIなどで生まれた時間を何に使うかという視点も、部下との関係づくりを見直す入口になります。",
             "articles": ("20261021-one-on-one-daily-conversation", "20261021-ai-time-for-people")},
            {"title": "3. 特定の人への集中をほどく", "text": "担当者の努力だけに任せず、仕事が集まる理由や、引き継ぎ・相談の経路を確認します。個人の能力と組織の仕組みを分けて考え、試す範囲を決めるための解説を読みます。",
             "articles": ("20261021-prevent-work-concentration",)},
        ),
    },
)


def eligible(article):
    score = article.get("score")
    return article.get("status") == "published" and (
        article.get("format") in ("special_story", "management_guide") or
        (isinstance(score, (int, float)) and not isinstance(score, bool) and score >= 80))


def matches(topic, article):
    curated = {aid for step in topic["steps"] for aid in step["articles"]}
    if article.get("id") in curated:
        return True
    lead = article.get("title", "") + " " + article.get("summary", "")
    return article.get("category") in topic["categories"] and bool(re.search(topic["pattern"], lead, re.I))


def topic_articles(topic, articles, limit=12):
    rows = [a for a in articles if eligible(a) and matches(topic, a)]
    lookup = {a["id"]: a for a in rows}
    chosen = []
    for step in topic["steps"]:
        for aid in step["articles"]:
            if aid in lookup and aid not in {a["id"] for a in chosen}:
                chosen.append(lookup[aid])
    recent = sorted(rows, key=lambda a: (a.get("published_at", ""), a["id"]), reverse=True)
    return (chosen + [a for a in recent if a["id"] not in {x["id"] for x in chosen}])[:limit]


def active_topics(articles):
    return [topic for topic in TOPICS if topic_articles(topic, articles)]


def article_topics(article):
    return [topic for topic in TOPICS if matches(topic, article)][:2]
