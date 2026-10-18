# WORK SIGNAL: Threads計測とSEO

## Threads投稿のリンク

GA4は `G-X4B5F6JJZH`、プロパティは `WORK SIGNAL`（559472175）。
自サイトへのリンクには、投稿時に次のUTMを付ける。サイト内のリンクには付けない。

- `utm_source=threads`: 流入元を統一
- `utm_medium=social`: ソーシャル流入
- `utm_campaign=<記事ID>`: 記事ごとに比較
- `utm_content=post_01`: 投稿ごとに区別。再投稿は `post_02` などに変更

第1号記事:

https://signal.amberlight.co.jp/articles/20261018-eu-agentic-ai/?utm_source=threads&utm_medium=social&utm_campaign=20261018-eu-agentic-ai&utm_content=post_01

プロフィール欄:

https://signal.amberlight.co.jp/?utm_source=threads&utm_medium=social&utm_campaign=profile&utm_content=bio

GA4のトラフィック獲得レポートで「セッションの参照元 / メディア」の
`threads / social` を確認する。記事別は「セッションのキャンペーン」、
投稿別は「セッションの手動広告コンテンツ」を使う。
セッション数だけでなくエンゲージメント率・エンゲージメント時間も見る。
UTMのない既存流入について、参照元が届かなかった訪問を後から確実にThreadsへ分類することはできない。
通常レポートには反映まで時間がかかる。自分のテストアクセスもデータに含まれる。

## SEOと公開

`data/articles.json` を承認後に更新する運用は継続する。
mainへの更新を受け、GitHub Actionsが公開用の `_site/` を生成してGitHub Pagesに配信する。
手作業で生成済みHTMLを編集・コミットしない。

- `/articles/<記事ID>/`: 本文・見出し・タイトル・説明文をHTMLに含む記事ページ
- 旧 `/article.html?id=<記事ID>`: 引き続き表示でき、正規URLは新記事URLを指定
- ホームに公開記事リンクを事前生成（JavaScriptなしでも発見可能）
- 正規URL・OGP・WebSite / NewsArticle構造化データ
- `/sitemap.xml` と `/robots.txt` を自動生成
- 公開対象は `status=published`、スコア80以上、有効な記事データのみ
- GA4とカスタムドメイン・HTTPSは継続

ローカル確認:

```sh
python3 -m unittest discover -s tests
python3 scripts/build_site.py
```

Search Consoleでは `https://signal.amberlight.co.jp/` を使い、
`https://signal.amberlight.co.jp/sitemap.xml` を送信する。
所有権確認はGA4タグを利用しているため、ホームのタグを削除しない。
検索への掲載・検索順位・構造化データの検索結果表示はGoogleの判断となる。
