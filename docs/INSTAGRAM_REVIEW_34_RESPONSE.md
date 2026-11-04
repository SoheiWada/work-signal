# AEGIS: Museレビュー #34 対応記録

対象: https://github.com/SoheiWada/work-signal/issues/34

2026-11-05。読み取り専用レビューを最新コードと照合し、再現テストの後に以下を補修。新たなInstagram公開テスト・記事データの変更・投稿台帳の編集・保護停止の解除は行っていない。

| 指摘 | 対応 | 検証 |
|---|---|---|
| F1: 通常フィードのエラー後照合がない | 通常配信とプローブでGET専用の `verify_instagram_delivery` を共有。公開境界へ到達した失敗だけを照合し、実投稿を一意に確認できればエラー詳細と `action_block_hold` を維持してpublishedにする | 403＋実投稿、タイムアウト＋実投稿、公開前失敗、次記事への保護停止 |
| F2: 反映待ちが短い | 完全な履歴を0/5/15/30/60/120秒で最大6回確認。公開リクエストの再試行は追加しない | 通常配信・プローブとも60秒遅延で確認。最後まで未確認ならneeds_review |
| F3: タイトル一致の誤判定 | 公開後と通常preflightはcaption完全一致または正規記事URLのホスト・パス全体で照合。タイトルのみ一致はプローブの警告に限定。応答IDがある場合はそのIDとの一致も要求 | タイトルだけの別投稿、記事URLの前方一致・偽ホスト、複数一致、応答ID相違を拒否 |
| F4: 途中停止したclaimの棚卸し | `diagnose_instagram.review_inventory` に全Instagramのattempting/needs_reviewを一覧化。再開手順に記載 | claim直後の強制終了後も通常配信・プローブとも再送なし。時刻不明も一覧に残す |
| F5: 成功応答を無検証で記録 | フィードは成功応答後も実履歴を確認。ストーリーズは所有アカウントのstories一覧で応答IDの実在を確認し、空captionで照合しない | 成功IDが不在・別ID・履歴不完全ならneeds_review、正しいStory IDのみ確認 |

## 検証結果

- 変更前: 新しい確認テスト11件中、失敗8件・未実装関数に対するエラー2件で指摘を再現（合格1件）。
- 変更後: `test_social_*.py` 56件、`test_delivery*.py` 33件、`test_instagram*.py` 37件、計126件がオフラインで合格。
- 照合の実ページング処理がGETしか呼ばないこともトランスポートのモックで確認。Metaの投稿APIは実行していない。
- 着手時のmain台帳 `eb6125b3ccd3fca9061ddddadec32736d8e84ed0` を読み取り棚卸しした結果、Instagramのattempting/needs_reviewは0件。これは全件配信完了の意味ではなく、既存のpublished＋action_block_holdと送信前のフィード保留は継続している。
- 既存の `media_publish` 呼び出し箇所、claim先行、SHA楽観ロック、共通concurrency、公開承認・対象媒体、7日間のプローブ間隔は維持。

## 運用上の限界

- 120秒はMetaが保証する反映時間ではない。期限を超えたもの、不完全な履歴、複数一致は手動の正の証拠による照合が必要。
- エラーで公開IDが不明なストーリーズは空captionから推定しない。従来の画像照合・対象限定復旧レビューを使う。
- この変更は2207051解除の証拠でも、追加の投稿実験やフィード自動配信の再開承認でもない。

関連: [公開運用マニュアル](PUBLISHING_RUNBOOK.md)、`tests/test_instagram_delivery_confirmation.py`、`tests/test_instagram_feed_probe.py`、`tests/test_instagram_diagnostics.py`。
