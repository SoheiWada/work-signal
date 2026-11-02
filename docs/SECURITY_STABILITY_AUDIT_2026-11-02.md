# WORK SIGNAL 安全性・配信経路監査（2026-11-02 JST）

初期main: 8f9fa7c51c4ad0994765a6ae208cb46eeb8acd19。対象は公開・SNS配信、管理画面との接続、稼働中のActionsと依存関係。記事データ・承認フラグ・投稿台帳の一括変更は行わない。

## 修正した問題

| 問題 | 修正 |
|---|---|
| 画像生成・画像照合に使うPillow 12.3.0が、既知の修正対象だった | Pillow 13.0.0へ固定更新。pip-auditが検出した39件は更新後0件。静的サイトの閲覧者が直接Pythonを実行する機能はなく、依存の深刻度と当システムでの到達条件は区別する |
| GitHub/Meta宛てのPython通信が、Authorization付きで自動転送しうる | API認証を固定HTTPSホストに限定し、301/302/303/307/308で認証情報やPOSTを転送しない。公開画像等の認証なし取得は既存動作を維持 |
| APIエラーのHTTPレスポンスを確実に閉じていなかった | サニタイズしたエラー情報を読んだ後、失敗時にもレスポンスを閉じる |
| 古い一回限りの復旧Actionsが10件残り、昔の判断で再起動できた | .github/retired-workflows/2026-11-02へ元の定義を保存し、現行workflowから除外。共通キュー以外に独立したSNS送信経路を増やさない |
| 依存の既知脆弱性を公開前に検出していなかった | サイトCIに固定バージョンのpip-auditでPillowを照合するゲートを追加。ビルドと監査には実行時間上限を設定 |

過去の原稿、記事ID、公開日、投稿ID、attempting/needs_reviewの証拠は維持する。Instagramフィードの4/2207051保護停止は、この監査を理由に解除しない。Xは無効のまま。

## 検証

- SNS関連94件のローカルテストが成功。新規ケースでは、認証付きリダイレクトの拒否・書き込み再送なし・APIエラーの非漏洩・許可ホストへの通常通信・現行送信経路の一本化を確認する。
- Pillow 13.0.0をクリーン環境へインストールし、固定要件のpip-auditが0件であることを確認。
- サイト・SEO・SECURITY WATCH・SNS画像の全体テストとビルドは、完全なリポジトリを使うPRのActionsで実施する。コミット成功、Pages公開、SNS実行の結果を区別して確認する。
- 管理画面の同日改修では、署名済みトークンの必須時刻検証、鍵更新、サービス通信の期限、ストリーム本文上限、Wrangler/Undiciの修正版、npm監査ゲートを追加。詳細はamberlight-analyticsの同日監査記録を参照。

## 一次資料

- Pillow 13.0.0公式リリースノート: https://pillow.readthedocs.io/en/stable/releasenotes/13.0.0.html
- バイナリ依存の修正: https://github.com/python-pillow/Pillow/security/advisories/GHSA-78g4-xqwv-q3g8
- Ghostscript引数処理の修正: https://github.com/python-pillow/Pillow/security/advisories/GHSA-w889-685w-c8fh

0件は実施時点の既知勧告との照合結果であり、未知の脆弱性や将来の外部サービス停止が存在しないという意味ではない。実アカウントへの攻撃負荷や、過去記事の一括再送による検証は行わない。
