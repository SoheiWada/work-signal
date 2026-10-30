# WORK SIGNAL｜X追加・初回接続手順

2026年10月31日。既存のThreads・Instagram・ストーリーズを維持してXを追加する。
Xの認証・予算確認・有効化変数の設定が済むまで、XへのAPI投稿は行わない。

## 実装した動作

- `social-publish.yml` の独立した `publish-x` ジョブで処理。Metaジョブが失敗してもXを検証し、Xが失敗しても先行したMeta投稿を取り消さない。
- ワークフロー共通の `work-signal-social-publishing` ロック内で直列実行。別ワークフローを同じロックで競合起動させない。Pagesの公開・SEOテストはXの認証・APIに依存しない。
- ページ公開成功をXジョブ自身でも確認。承認・記事・コードが未公開版へ変わっていれば投稿せず停止し、台帳だけの差分を許可する。
- 有効化時点の `X_PUBLISH_START_SHA` に既にSNS承認されていた記事をすべて除外する。過去記事への承認フラグ追加や一括投稿はしない。
- 以降の `social_publish:true` の承認済み記事だけが対象。初回公開からJSTで2日以内、鮮度レビュー有効期限内。既存記事のSEO改稿だけでは再投稿しない。
- JSTの1日最大3回の送信試行。投稿成功だけでなく、結果不明の `attempting` / `needs_review` も日次枠へ計上。1実行も最大3回。キュー内ではCRITICAL→HIGH→通常、同順位ではスコアを優先。
- 日本語・絵文字・URLの重みは公式 `twitter-text` で検証。通常アカウント向けの280加重文字以内。記事タイトル・summaryだけを要約し、新しい事実を生成しない。確認済みのセキュリティ深刻度だけラベル化する。
- テキストと記事リンクを送る。記事リンクのOG画像は既存の設定を使用し、専用画像のアップロードやサイトデザインの変更はしない。
- 公式 `POST /2/tweets` を一度だけ送信。送信前に共通台帳へ `x:attempting` を耐久記録し、応答の投稿IDも保持する。投稿をGETし、所有者・本文・展開後URLが一致してから `published` と実投稿URLを記録。
- タイムアウト、料金・認証エラー、照合失敗は以降の送信を止める。送信後の曖昧な結果を自動再送しない。`needs_review` / `attempting` の復旧は実アカウントとの確認後に対象限定で行う。
- 台帳は既存 `.github/social-post-ledger.json` を共有し、Xの状態だけを更新。既存3媒体の記録・保護停止・承認を変更しない。

## 料金と有効化前の確認

X公式料金表の2026年10月31日確認時点では、URL付き投稿は1回 **0.20米ドル**。
3本/日×30日なら投稿分は最大 **18米ドル**。プロフィール・実投稿の確認GETは別料金。
消費税・換算レート・料金変更は含まない。課金単価はDeveloper Consoleを最終確認する。

この実装はクレジット購入、カード登録、自動チャージの有効化を行わない。
有効化前に、所有者がDeveloper Consoleで予算上限を設定する。例として月20ドルを検討できるが、3本/日の全件配信や読み取りまで収まることを保証する金額ではない。

一次情報：
- https://github.com/xdevplatform/docs/blob/main/x-api/getting-started/pricing.mdx
- https://help.x.com/en/rules-and-policies/x-automation
- https://github.com/xdevplatform/docs/blob/main/fundamentals/counting-characters.mdx
- https://github.com/xdevplatform/docs/blob/main/fundamentals/authentication/oauth-1-0a/overview.mdx

## 初回接続

1. WORK SIGNAL用のXアカウントを用意。Developer Console https://console.x.com/ でそのアカウントのAppを設定する。他アカウントの所有Appの場合は対象アカウントのOAuth同意が必要。
   今回所有者が提示した開設アカウントは https://x.com/work_signal_jp 。送信前のAPI照合は別途必要。
2. AppのUser authenticationで読み取り・書き込み権限を設定し、OAuth 1.0a User ContextのAPI Key/Secret、Access Token/Secretを取得。読み取り専用トークンを既に作成していた場合、書き込み許可後のトークンを使う。
3. https://github.com/SoheiWada/work-signal/settings/secrets/actions に4件を登録する。チャット・記事JSON・Issueへは貼り付けない。

| Repository secret | 値 |
|---|---|
| `X_API_KEY` | AppのAPI Key |
| `X_API_SECRET` | AppのAPI Secret |
| `X_ACCESS_TOKEN` | 対象アカウントのAccess Token |
| `X_ACCESS_TOKEN_SECRET` | 対象アカウントのAccess Token Secret |

4. Actionsの **Check WORK SIGNAL X account (GET only)** を手動実行。初回は `identify_only=true` で接続先のユーザー名・IDを表示するだけ。投稿・台帳更新なし。表示されたアカウントがWORK SIGNAL用であることを所有者が確認する。このGETにもAPI利用料がかかる場合がある。
5. https://github.com/SoheiWada/work-signal/settings/variables/actions で以下を設定する。X開始基準には、設定時点の最新mainの完全な40桁コミットSHAを使う。これより前の承認済み記事は配信しない。

| Repository variable | 設定内容 |
|---|---|
| `X_USERNAME` | 確認したXユーザー名。先頭の@なし |
| `X_USER_ID` | GETで確認した数値のユーザーID |
| `X_PUBLISH_START_SHA` | 有効化時点の最新main、40桁SHA |
| `X_PUBLISH_ENABLED` | 最後に `true`。未設定・falseでは送信しない |

既存の `SOCIAL_PUBLISH_ENABLED=true` も必要。全SNS停止スイッチをXが無視しない。
有効化前に `identify_only=false` で再度接続確認を実施し、設定したユーザー名とIDの一致を確認する。

## 投稿担当へ共有

通常記事に新しい必須入力はない。開始基準より後の新規SNS承認記事は自動で候補になる。
既存 `social_platforms:["threads"]` 等の明示的な媒体制限は維持し、Xを勝手に追加しない。
新規承認記事に限り、任意の `social_x_publish:true` でX追加、`false` でX除外できる。
`social_platforms` に `x` を追加しない（既存Meta/Editorの列挙値を変更しないため）。

任意の `social_x_text` はX専用の承認済み原稿。280加重文字以内で、正規記事URLまたは標準UTM付き記事URLを独立したURLとして含み、末尾を一次情報URLとする。
カスタム原稿を自動で短縮・書き換えない。標準原稿の記事リンクには `utm_source=x&utm_medium=social&utm_campaign=work_signal&utm_content=<記事ID>` を付け、GA4で送客を区別する。

公開承認・初回公開日・記事ID・採点・一次情報・SECURITY WATCHの確認ルールは従来どおり。
X追加作業そのものを、既存記事の再紹介承認として扱わない。

## 確認と停止

- `publish-x` ジョブ、Summary、artifact `work-signal-x-delivery-status` と台帳の `x` を確認する。
- 日次枠による `waiting_daily_limit` は予定された待機。翌JST日の定期処理で、公開日・鮮度の条件を再確認する。一定期間内の全記事投稿を保証しない。
- ジョブ成功を、待機記事も含む全件配信完了と読み替えない。`published` の記事と、待機・要確認を区別する。
- Xだけ止める場合は `X_PUBLISH_ENABLED=false`。Threads/Instagramを止めない。
- オフライン原稿プレビュー：`npm --prefix tools/x-publisher ci --ignore-scripts` 後、`python3 scripts/publish_x.py`。過去記事がプレビューされても送信キューではない。
- テスト：`node --test tests/x/*.test.mjs` と `python3 -m unittest discover -s tests -p 'test_x_publish.py'`。外部送信はすべてモックする。

追加時点ではXアカウント接続・実投稿・到達確認は未実施。認証と予算確認後、最初の新規承認記事で実投稿URLまで確認して導入完了とする。
