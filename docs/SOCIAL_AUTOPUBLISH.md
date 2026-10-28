# WORK SIGNAL｜公式SNSへの自動投稿

## 2026-10-28 現行の公開・配信手順（以下の旧記録より優先）

ユーザーの「公開」はサイト・対象SECURITY WATCH・指定SNSの公開を一度に進める指示。新記事の承認済みデータを一つのコミットにまとめ、媒体別の最終状態まで確認する。

- SECURITY WATCHは、記事に明示された `social_security_severity` と `social_security_product`、承認済みsummaryから自動登録する。深刻度や製品をタイトルから推定しない。既存 `data/security-watch.json` は過去のアラートアーカイブとして保持。新記事ごとの二重登録は不要。掲載除外は `security_watch:false` と `security_watch_exclusion_reason` を明示する。専用の短いsummary等が必要なときは記事の `security_watch` オブジェクトに設定する。
- SNSは `social_publish:true` が前提。`social_platforms` は指定媒体だけを配信する恒久的な選択。API不調の一時回避でThreads限定にして放置しない。空文字のカスタム投稿文は無効。未指定なら承認済みタイトル・summaryの定型文を使用する。
- ThreadsとInstagramのアカウント検証・投稿枠は独立。1媒体の停止だけで他媒体を止めない。投稿自体は共通ロック内で直列に実施する。
- Instagramは投稿前に実際の枠を確認する。フィードとストーリーズの両方を計上。50/100で2207042を観測したため、暫定運用上限はmin(50,API上限)。これはMeta公式仕様の固定値を意味しない。
- 台帳の `deferred` は送信前の枠待ち、または明示的な2207042拒否。指定時刻後の定期処理で再開する。`attempting` / `needs_review` は結果不明のため自動再送しない。後者の復旧には実アカウントとの照合と、鮮度レビュー済みの対象限定プランが必要。既存台帳を削除・初期化しない。
- サイト公開成功後と毎時13分・43分（UTC、JSTでも分は同じ）に配信を継続。各アカウント1回5記事まで。残件は次の実行へ回す。GitHub側のスケジュール遅延はあり得る。
- 投稿台帳だけがmainで変わった場合は継続できるが、記事・画像・スクリプト等が公開版から変わっていれば停止する。公開成功の確認を省略しない。
- ActionsのSummaryと `work-signal-social-delivery-status` artifactで、記事・媒体別のpublished / deferred / needs_review / pendingを確認する。未処理が残っていればワークフローは未完了として失敗を返す。成功表示だけで全媒体の投稿完了と報告しない。
- 投稿失敗時は安全なHTTP/code/subcode、コンテナID、API工程を保存する。トークン・生のエラーメッセージを公開しない。
- 2026-10-28の既存未投稿復旧は `.github/social-recovery-review.json` に判断と有効期限を記録。期限切れは再評価する。新しい記事をこの固定プランに継ぎ足して承認済み扱いしない。


## 公開承認の意味

今後ChatGPTで記事の「公開」を明示承認した場合は、記事のサイト公開だけでなく、Threads・Instagramフィード・Instagramストーリーズへの公式アカウント投稿も含めた承認として扱います。ただし **記事JSONの `social_publish: true` がある場合だけ** SNS投稿します。すでに公開済みの記事にはこのフラグを後付けしません。過去記事が突然SNSに再投稿されることはありません。

### 公開順

1. 一次情報・記事・Threads紹介文などを確認した後、ユーザーが「公開」と承認。
2. 編集部が `data/articles.json` の新しい記事に `social_publish: true` を付けてコミット。
3. GitHub ActionsでSEOテスト、単体テスト、ページ生成、Pages公開を実施。
4. サイト公開が成功した場合のみ、別のSNS投稿ワークフローが対象記事を処理。
5. Threads、Instagramフィード、InstagramストーリーズへMeta公式APIで投稿。3つの投稿IDをGitHubの永続台帳へ個別に記録。

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

**通常の自動投稿を有効化するには**、Repository variables に `SOCIAL_PUBLISH_ENABLED` = `true` を登録する必要があります。変数が未設定・`false` の場合、通常のSNS投稿は行われません。停止する際は `false` に戻してください。2026-10-26の監査時点で `SOCIAL_PUBLISH_ENABLED=true` の登録を確認しました。公開担当は操作時にも最新の設定と媒体別台帳を確認してください。

## 画像と重複投稿の防止

- Instagramフィード用1080×1350px JPEGを `assets/instagram/<記事ID>.jpg`、Instagramストーリーズ用1080×1920px JPEGを `assets/stories/<記事ID>.jpg` にそれぞれ生成する。既存OG画像は変更しない。
- 投稿前にMetaアカウントのユーザー名・IDが `work_signal_japan` と一致すること、記事URLとJPEGが公開済みであることを確認する。
- `.github/social-post-ledger.json` に、Threads `threads`、Instagramフィード `instagram`、ストーリーズ `instagram_story` を区別してAPI送信**前**に `attempting` を保存する。成功は `published`、曖昧なエラーは `needs_review`。どれか1媒体で失敗しても、他媒体の投稿済み記録は維持される。
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

**公開担当への指示：** ユーザーが次回「公開」と承認したら、記事の `social_publish: true` を同じコミットで記録する。サイト公開の成功後、SNSワークフローの結果を確認し、記事・Instagramフィード・Instagramストーリーズ・Threadsの成否をそれぞれ区別して伝える。

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

## 通常運用（3媒体への同時投稿）

現在の `scripts/publish_social.py` は、新規記事に **`social_publish: true`** が明示された場合、サイト公開成功後に以下の3媒体へ順次投稿する。

1. Threads：記事URLと末尾の一次情報URLを含むテキスト。
2. Instagramフィード：1080×1350pxの画像とキャプション。
3. Instagramストーリーズ：1080×1920pxの縦長画像。「記事全文はプロフィールから」への誘導。APIからリンクスタンプは付けない。

記事・画像の公開確認を投稿前に済ませ、台帳に記事IDと媒体別状態を保存する。過去記事でも承認フラグを一度に多数付けると連続配信の対象になるため、バックナンバー再紹介では通常記事の一斉配信フラグを安易に付けないこと。

### 既存記事96本の再紹介案（2026-10-26）

新しいアカウントの運用初期は、**既存記事をInstagramフィード週2～3本、Threads週3～5本、ストーリーズは再紹介日に1本**程度に抑える。これは**配信の推奨プランであり、自動スケジューラーが導入済みという意味ではない**。

- 新着記事は優先。新着が多い日・週は過去記事を減らす。
- 過去記事は一次情報・事実関係・公開日を再確認し、「過去記事の再紹介」と分かるようにする。
- 継続して価値があるマネジメント・AI活用・経済の解説を優先し、脆弱性速報、速報性の高い価格・制度情報は確認なしで再配信しない。
- 一度に全96本を `social_publish: true` にしない。再紹介スケジュールの自動化は別途実装・検証・承認する。
- 実運用2週間後にInsightsで到達数、フォロワー増加、プロフィール訪問、ストーリーズ離脱状況を確認して頻度を調整する。


## SECURITY WATCH 専用SNSアセット（編集部1スレッドで管理）

SECURITY WATCHを公開する編集部スレッドのみ、確認した深刻度を投稿時の明示フィールドに設定する。通常ニュース編集部への変更指示は不要。

```json
{
  "social_publish": true,
  "social_security_severity": "CRITICAL",
  "social_security_product": "対象製品名（確認できた場合）",
  "social_security_cve": "CVE番号（確認できた場合）",
  "social_security_action": "確認済みの推奨対応（確認できた場合）"
}
```

- `social_security_severity` は `CRITICAL` または `HIGH` のみ。有効な値の指定時にだけセキュリティ専用画像へ切替。未指定なら従来の通常ニュース画像。その他の値はビルドエラーで公開を停止する。
- CVE番号・対応・対象製品は確認済みの値だけ記載し、情報の不足を捏造やタイトルからの機械推定で補わない。
- CRITICAL: チャコール × 深紅、HIGH: ダークネイビー × アンバー。双方にSECURITY WATCHブランド、技術的なシグナル線を採用する。
- **CRITICAL / HIGHラベルは1行固定。単語途中での改行禁止。** ラベル全体が収まるサイズを計測して描画する。
- フィード1080×1350、ストーリーズ1080×1920。通常のサイト画面・SEO・OG画像は変更しない。
- 過去記事へのフラグ一括追加禁止。新規記事への公開承認後のみ各媒体へ配信する。


## SNSダッシュボード連携（2026-10-26）

Threadsの標準紹介文の記事リンクには、媒体・記事IDを識別するUTMを追加します。canonicalと一次情報URLは変更しません。承認済みのカスタム原稿は自動で書き換えず、必要な場合は原稿に計測URLを含めます。既存記事の投稿承認フラグや投稿台帳は変更しません。

Instagramのプロフィールリンクには `https://signal.amberlight.co.jp/?utm_source=instagram&utm_medium=social&utm_campaign=profile&utm_content=bio` を設定できます。共通プロフィールリンクから元のフィード/ストーリーズ記事を識別することはできません。

`Read WORK SIGNAL social insights` は既存のGitHub Secretsを使うGET専用の読み取りテストです。Metaアカウントを検証し、可能なフォロワー数・投稿指標を取得。新規の投稿、予約投稿、台帳更新は行いません。SNS投稿成功後とワークフロー手動実行で取得できます。結果は14日保存のActions artifact `work-signal-social-insights` に保存し、公開サイトやコミットには保存しません。ダッシュボードの「SNS」→「インサイトJSONを開く」で取り込めます。

投稿権限と分析権限は別です。`threads_manage_insights`、`instagram_business_manage_insights` がなければ要認証/未取得を記録します。現在値の未取得を0に変換しません。投稿指標は投稿以来の累計で、指定期間内の増分ではありません。内部指標やトークンを公開ログに出力しません。


## 2026-10-26 監査による安全性・表示の補修

- 台帳が見つからない場合は、空の台帳を自動作成せず停止します。既存台帳の削除・初期化はしないでください。
- 媒体の記録が存在するのに状態が未知・欠落・不正な場合は「未投稿」と扱わず停止します。`attempting` / `needs_review` と同様に、実投稿と台帳を確認するまで自動再送しません。
- 通常自動投稿を有効にした状態で認証情報が不足している場合、またはアカウントIDが確認できない場合は成功にしません。停止理由を解消してから再検証します。
- 1回の5記事上限は維持します。上限を超えた未処理記事が残る場合は未完了と報告します。自動予約・自動再実行が設定済みだと扱わないでください。
- ワークフローの成功表示だけで3媒体すべての実投稿成功と判定せず、媒体別の台帳状態と確認できた投稿URLを照合します。確認できないURLを推測で作らないでください。
- AMBER LIGHTダッシュボードは、不正なSNSスナップショットを共通JSONの状態更新前に拒否し、他の販売・検索・予約データも保持するよう補修しました。SNS更新の通信・検証失敗時にも取得済みの正常データを保持し、エラーと保存値の表示を併記します。未取得を0件に置き換えません。
- 投稿APIの権限とインサイトの読み取り権限は別です。Workerの直接取得が未接続の場合も、既存のActionsインサイトJSONを利用できます。指標は取得日時の値として報告し、現在値や指定期間内の増分と混同しないでください。

今回の監査で記事本文、承認フラグ、投稿履歴、既存の画像・OG画像、通常/SECURITY WATCHのデザイン、深刻度の判定基準は変更していません。

## 2026-10-27 OpenPanel Threads再送の検証済み運用

- 事例：記事 `20261027-openpanel-two-security-advisories`。通常SNSワークフローではThreadsのコンテナ作成後、公開APIがHTTP 400となり、Threadsのみ `needs_review`、Instagramフィードとストーリーズは `published` になった。3媒体同時実行が原因と断定しない。
- まず媒体別の投稿台帳、GitHub Actionsのジョブログ、実投稿履歴を確認する。投稿がないことを所有者が確認した場合に限り、Threads単独の復旧を行う。
- 復旧に成功した実装は `scripts/recover_openpanel_threads.py` と `.github/workflows/recover-openpanel-threads.yml`。復旧ワークフローは対象記事IDを固定し、Instagramには触れず、既存台帳のSHAを使ってThreadsの状態だけを `attempting` に確保してからAPIに送信する。成功時は `published` とremote_idを記録する。
- 実績：復旧ワークフロー #40470376153 は成功し、Threads remote_id `17870054637658838` を台帳に記録した。Instagramフィード `17976332022172032`、ストーリーズ `17977957820931518` は再送せず保持した。
- **次回以降**：失敗記事ごとに固定IDの復旧スクリプトをそのまま再利用してはいけない。共通の安全な単一媒体・単一記事復旧手順を用い、所有者による未投稿確認、対象ID・媒体の限定、台帳状態の検証、送信前の耐久記録、単発API送信、投稿結果の確認を必須とする。 `needs_review` を単純に削除・初期化して通常ワークフローを再起動しない。3媒体を同時に手動起動しない。
- HTTP 400の具体的なAPI理由は未確定。通常ワークフローの再試行や固定待機時間の変更だけで解決したと判断しない。

