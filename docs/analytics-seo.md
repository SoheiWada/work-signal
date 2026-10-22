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
- トップと記事ごとの1200×630 PNG共有画像を自動生成。記事の構造化データにも画像URLを設定
- `/sitemap.xml` と `/robots.txt` を自動生成
- 公開対象は `status=published`、スコア80以上、有効な記事データのみ
- GA4とカスタムドメイン・HTTPSは継続

ローカル確認:

```sh
python3 -m pip install -r requirements-build.txt
python3 -m unittest discover -s tests
python3 scripts/build_site.py
```

共有時は `/articles/<記事ID>/` を使用する。この固定URLではタイトル・説明文・画像を
JavaScript実行前のHTMLに出力している。旧 `article.html?id=...` は表示互換用として継続する。

Search Consoleでは `https://signal.amberlight.co.jp/` を使い、
`https://signal.amberlight.co.jp/sitemap.xml` を送信する。
所有権確認はGA4タグを利用しているため、ホームのタグを削除しない。
検索への掲載・検索順位・構造化データの検索結果表示はGoogleの判断となる。

## 2026-10-22 SEO補強

- 正規URLは `/articles/<記事ID>/` を維持。旧 `article.html?id=...` も全公開形式のsectionsを表示する。
- WebSiteのnameはWORK SIGNAL。画面にもあるWORK.SIGNALをalternateNameに指定。
- 既存のW＋オレンジの点を維持し、SVGに加え96px・192px PNG、ICO、180px Apple用アイコンを固定URLで自動生成。
- `scripts/seo_metadata.py` が記事本文・見出し・概要・情報源等のGit履歴から記事単位の更新日を取得。並び替え、採点、別記事追加、再デプロイで既存記事の日付は変わらない。
- published_atは公開日。任意のupdated_atはYYYY-MM-DDまたはタイムゾーン付きISO日時を使用可能。必須フィールドの追加なし。
- 更新日の表示、dateModified、article:modified_time、sitemapのlastmodに同じ値を使用。履歴不明なら更新日は省略し、記事のlastmodは公開日。ABOUT等の不明な日付は推測しない。
- Actionsは全履歴を取得する。浅いcheckoutやZIP単体では更新履歴が利用できず、更新日は省略される。
- 同じカテゴリーでタイトルの語句が共通する公開記事を最大2件、既存サイドバーの目次と同じ書式でリンク。本文データは変更しない。
- 検証: `python3 -m unittest discover -s tests` と `node --test tests/seo/*.test.mjs`。
- 親ドメイン、DNS、AdSense、GA4、公開承認手順は維持。

Search Consoleは既存sitemapの成功・最終読み込み、トップと代表記事のURL検査でcanonical・Googlebot取得可否を確認する。WebSiteはSchema Markup Validator、ArticleはRich Results Test等で検証する。Googleによるサイト名・faviconの採用、インデックス登録は保証されない。
