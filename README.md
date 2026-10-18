# WORK SIGNAL

働く人のためのニュース解説メディア。AI APIを使わずにGitHub Pagesで動く初期版です。

## 実装済み
- `index.html`: レスポンシブなニュース一覧とカテゴリー絞り込み
- `data/articles.json`: 公開記事データ（現在は空）
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
GitHubリポジトリの **Settings → Pages → Build and deployment → Deploy from a branch → main / (root) → Save** を選択。

## 注意
記事は原典と数値を確認してから公開すること。ChatGPT内の承認ボタンからの自動反映、ニュース自動収集、Threads自動投稿は**未実装**。Threads投稿文の生成と手動投稿は継続する。

## 記事詳細ページ（実装済み）
- `article.html?id=<記事ID>` で記事詳細を表示
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

Threads用投稿文はサイト公開用JSONに保存せず、承認時にChatGPTで同時生成して提示する運用を予定しています。
