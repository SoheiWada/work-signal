# NBA実データ接続（費用0円）

確認日: 2026-10-21。提供元: [BALLDONTLIE](https://www.balldontlie.io/)。

## 公開する範囲

- 終了を確認したNBAの試合結果と詳細。直近7試合日分を表示します。
- 30チームの勝敗・勝率、および同勝率を同順位にする参考順位。公式タイブレークや公式シードではありません。
- 試合日は米東部の日付、取得・更新確認時刻はJSTで表示します。ライブ実況ではありません。
- 無料のGamesをregular / ist / playin / playoffsの区分で取得。プレシーズンを取得せず、NBAカップ決勝・プレーイン・プレーオフはレギュラーシーズンの勝敗に算入しません。regularとistに重複する同一試合は一度だけ集計します。
- ページネーションの完了、30チーム、スコアと試合状態、ID、シーズン区分、集計整合性を検証。提供元の網羅性そのものを公式記録と同一とは保証しません。確認不能の試合状態がある場合は順位の集計を保留します。
- 選手別成績・公式順位APIなど有料エンドポイントは呼びません。

## 費用と許諾

[無料プランのTeams / Gamesと毎分5リクエスト](https://docs.balldontlie.io/)のみ使用します。[提供元規約](https://www.balldontlie.io/terms.html)のメディア利用・表示の許諾範囲を確認しました。公式リーグ提供・提携と表示せず、NBA・チームのロゴも使いません。元データ一式を配信するAPIサービスは作らず、サイト表示に必要な正規化・集計済みデータだけを保持します。

この公開リポジトリの標準GitHub-hosted runnerは[無料](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)。非公開リポジトリでは更新ジョブを実行しない条件を付けます。新しいサーバー・契約・有料枠・カード・有料トライアルは使いません。

## ファイルと秘密情報

- `services/nba-data/collector.mjs`: サーバー側取得。呼出先は提供元のTeams / Gamesだけに固定し、リダイレクトを拒否。15秒以上の間隔・1回最大50リクエスト。429や認証エラーで停止し、自動アップグレードしません。
- `scripts/fetch_nba.mjs`: キーを環境変数`BALLDONTLIE_API_KEY`だけから受領。キー、ヘッダー、提供元の生レスポンスをログ・HTML・JSONへ出しません。
- `nba/data.json`: 公開用の結果・参考勝敗・取得時刻のみ。失敗時は最後の成功データを保持し、更新失敗と最終確認時刻を記録。26時間以上更新されない場合はブラウザーでも更新停止と表示します。
- `nba/feed.mjs`: 公開データの構造・未来時刻・チーム参照・スコアを検証。形式不正を表示に流しません。
- `nba/app.mjs`: 同じサイトの静的JSONのみ取得。閲覧者のブラウザーへAPIキーを渡さず、提供元への呼び出しを行いません。表示中は30分ごとに共有JSONを確認します。
- `.github/workflows/nba-data.yml`: 原則07:23 / 19:23 JSTに更新。実行待ちで遅れることがあります。`NBA_DATA_ENABLED=true`のときだけ実行します。

キーはリポジトリのActions secret `BALLDONTLIE_API_KEY`へ保存します。値はコード・チャット・コミットメッセージへ記載せず、再発行した場合も同じ非公開設定を差し替えます。

## 更新の公開

データ更新ジョブはJSONを検証して`nba/data.json`だけをコミットします。`GITHUB_TOKEN`のpushだけではPagesのpushワークフローが起動しないため、既存`pages.yml`を明示的に起動します。失敗状態も公開した後にジョブを失敗として報告します。記事やRSSは更新しません。

手動で更新する場合は「Refresh free NBA display data」を実行します。無効化はリポジトリ変数`NBA_DATA_ENABLED`を`false`にします。

## 初回の照合

2026-10-21の無料API取得は5リクエスト、終了済み3試合、30チーム。次のNBA公式公開ページとスコアを照合しました（公式データを転載取得するための接続先には使用していません）。

- [BOS 113 / DET 121](https://www.nba.com/game/bos-vs-det-0022600001)
- [PHI 106 / NYK 100](https://www.nba.com/watch/video/game-recap-76ers-106-knicks-100)
- [OKC 116 / SAS 104](https://www.nba.com/spurs/game/0022600003-thunder-vs-spurs-san-antonio-tx-10-20-2026/box-score)

テスト用の架空データは`prototypes/`と`tests/`のまま公開ビルドから除外します。
