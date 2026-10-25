# WORK SIGNAL｜公式SNSへの自動投稿

## 公開承認の意味

今後ChatGPTで記事の「公開」を明示承認した場合は、記事のサイト公開だけでなく、ThreadsとInstagramへの公式アカウント投稿も含めた承認として扱います。ただし **記事JSONの `social_publish: true` がある場合だけ** SNS投稿します。すでに公開済みの記事にはこのフラグを後付けしません。過去記事が突然SNSに再投稿されることはありません。

### 公開順

1. 一次情報・記事・Threads紹介文などを確認した後、ユーザーが「公開」と承認。
2. 編集部が `data/articles.json` の新しい記事に `social_publish: true` を付けてコミット。
3. GitHub ActionsでSEOテスト、単体テスト、ページ生成、Pages公開を実施。
4. サイト公開が成功した場合のみ、別のSNS投稿ワークフローが対象記事を処理。
5. InstagramとThreadsへMeta公式APIで投稿。投稿IDをGitHubの永続台帳へ記録。

### 記事追加フィールド（すべて任意）

```json
{
  "social_publish": true,
  "social_threads_text": "記事URLを含み、一次情報URLで終わる承認済みのThreads原稿",
  "social_instagram_caption": "Instagram用の承認済み紹介文（プロフィールのリンクへ誘導）"
}
```

投稿文の2項目を省略した場合は、承認済みの記事タイトルとsummaryだけに基づく定型文で投稿します。新しい事実の生成はしません。Threadsは500字以内かつ記事URL・一次情報URLを含み、最後は一次情報URL。Instagramは通常、本文中のURLをクリックできないためプロフィールのリンクへ誘導します。

## Meta側の初期設定

1. https://developers.facebook.com/ でMeta開発者アカウントとアプリを用意。
2. Instagram `@work_signal_japan` を**ビジネスまたはクリエイターのプロアカウント**にする。
3. Instagram API with Instagram Loginで `instagram_business_basic` と `instagram_business_content_publish` の権限を有効化する。
4. Threads APIで `threads_basic` と `threads_content_publish` の権限を有効化する。
5. **InstagramとThreadsは別々の認証・トークン・ユーザーID**が必要。両方の長期トークン、ユーザーIDを取得する。外部ユーザー向けの利用ではMetaアプリの追加審査が必要な場合があります。

Meta公式ドキュメント：
- https://developers.facebook.com/documentation/threads/posts
- https://developers.facebook.com/documentation/instagram-platform/content-publishing
- https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login

## GitHub Secrets（機密情報）

GitHub： https://github.com/SoheiWada/work-signal/settings/secrets/actions

**Settings → Secrets and variables → Actions → Repository secrets** で4件を追加します。

| Secret名 | 登録値 |
|---|---|
| `THREADS_ACCESS_TOKEN` | Threads API用アクセストークン |
| `THREADS_USER_ID` | Threads公式アカウントID |
| `INSTAGRAM_ACCESS_TOKEN` | Instagram Login API用アクセストークン |
| `INSTAGRAM_USER_ID` | InstagramプロアカウントID |

トークンはチャット、記事JSON、コミット、Issueなどに決して貼り付けないでください。GitHub Secretsとしてのみ保存します。トークンには有効期限があるため、期限前に更新してください。

その後、**Repository variables** で `SOCIAL_PUBLISH_ENABLED` = `true` を追加すると自動投稿が有効になります。それまでは外部投稿されません。停止する際は `false` に変更します。

## 画像と重複投稿の防止

- Instagram用に記事ごとに1080×1350pxのJPEGを `assets/instagram/<記事ID>.jpg` へ生成し、Metaが取得できる公開URLから投稿する。既存OG画像は変更しない。
- 投稿前にMetaアカウントのユーザー名・IDが `work_signal_japan` と一致すること、記事URLとJPEGが公開済みであることを確認する。
- `.github/social-post-ledger.json` に、API送信**前**に `attempting` を保存する。成功は `published`、曖昧なエラーは `needs_review`。
- APIタイムアウト後は投稿が成功している可能性があるため、二重投稿を防ぐ目的で自動再試行はしない。人間が実投稿を確認してから復旧する。
- GitHub Actionsの再実行やNBAデータの更新だけで同じ記事を再投稿しない。
- 投稿スイッチOFF／両アカウントのSecrets未設定の場合は外部投稿しない。
- 記事のサイト公開が成功しても、SNS側の認証に問題があればSNS投稿は未完了として別に報告する。

## 自動化のテスト

```sh
python -m unittest discover -s tests -p 'test_social_publish.py'
python scripts/publish_social.py        # ドライラン。外部投稿なし
python -m unittest discover -s tests
node --test tests/seo/*.test.mjs
```

**公開担当への指示：** ユーザーが次回「公開」と承認したら、記事の `social_publish: true` を同じコミットで記録する。サイト公開の成功後、SNSワークフローの結果を確認し、記事・Instagram・Threadsの成否をそれぞれ区別して伝える。

## 2026-10-26 Instagramストーリーズ単独テスト

- 対象は公開済み記事 `20261024-nec-ai-work-wellbeing-survey` のみ。
- 1080×1920pxのストーリーズ専用JPEGを `assets/stories/<記事ID>.jpg` に生成。
- 先行するサイトのビルド・テスト・Pagesデプロイが成功した場合のみ、
  一度限りの `social-story-first-post.yml` が投稿を試みる。
- フィード投稿やThreads投稿は**一切再送しない**。
- 投稿前に `.github/social-post-ledger.json` の `instagram_story` を
  `attempting` として記録し、成功時に `published`、曖昧なエラー時は
  `needs_review` として重複を防ぐ。
- 本番の通常自動投稿変数 `SOCIAL_PUBLISH_ENABLED` は変更しない。
- APIのStories投稿ではリンクスタンプや画面上のリンク誘導は追加できないため、
  画像内でプロフィールのWORK SIGNALリンクを案内する。
- このテストは通常運用へのストーリーズ自動投稿追加を意味しない。
