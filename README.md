# WORK SIGNAL

働く人のためのニュース解説メディア。AI APIを使わずにGitHub Pagesで動く初期版です。

## 実装済み
- `index.html`: レスポンシブなニュース一覧とカテゴリー絞り込み
- `data/articles.json`: 公開記事データ
- スコア80点以上かつ`status: published`のデータのみ表示
- 一次情報URLへのリンク

## 記事データの例
```json
[
  {
    "id": "article-001",
    "title": "記事タイトル",
    "summary": "30秒でわかる概要",
    "category": "AI",
    "score": 85,
    "published_at": "2026-10-18",
    "source_url": "https://example.com/source",
    "status": "published"
  }
]
```
カテゴリーは `AI`、`仕事`、`マネジメント`、`お金`、`経済`、`Crypto`。

## 公開設定
GitHub PagesのSourceは **GitHub Actions**。mainの更新を受けて `.github/workflows/pages.yml` が記事ページとサイトマップを生成・公開します。
独自ドメインは https://signal.amberlight.co.jp/ 。SEO・Threads計測の運用は `docs/analytics-seo.md` を参照。

## 注意
記事は原典と数値を確認してから公開すること。公式Instagram・Threadsの投稿機構は `docs/SOCIAL_AUTOPUBLISH.md` を参照。`social_publish: true` を明示した承認済み新規記事のみ、Pagesデプロイ成功後に公式APIで投稿する。アカウントのGitHub Secretsと有効化変数が未設定なら**外部投稿は行われない**。

## 記事詳細ページ（実装済み）
- 正規URL `/articles/<記事ID>/` を公開時に静的生成
- 旧 `article.html?id=<記事ID>` も表示互換を維持
- `data/articles.json` の記事に任意で `what_happened`, `why_it_matters`, `impact`, `caveats` を追加可能
- トップの記事カードから記事詳細へリンク
- 公開済みかつ80点以上のデータのみ詳細表示。URLパラメータに不正なIDが指定された場合は非公開
- 記事表示はテキストノードを使用し、外部データをHTMLとして解釈しない

### 例（追加フィールド）
```json
{
  "what_happened": "確認済みの事実を記述",
  "why_it_matters": "社会や業界への影響",
  "impact": "働く人にとっての意味",
  "caveats": "不確実な点や注意事項"
}
```

Threads／Instagram用投稿文は、承認記事に `social_threads_text` と `social_instagram_caption` として任意で保存できます。未指定なら承認済みのタイトル・概要を用いた定型文を生成します。`social_publish` がない過去の記事は自動投稿されません。
