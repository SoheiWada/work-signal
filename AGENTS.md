# WORK SIGNAL の公開・配信作業

作業前に `docs/PUBLISHING_RUNBOOK.md` と `docs/SOCIAL_AUTOPUBLISH.md` の「2026-10-28 現行」節を読む。ユーザーの現在の明示指示を優先する。

- 「公開」の承認は、記事サイト・対象SECURITY WATCH・指定された公式SNSまでを一つの作業として扱う。新規承認記事には `social_publish: true` を同じコミットで含める。明示的な媒体除外は尊重する。
- SECURITY WATCHは承認済みの `social_security_severity`、`social_security_product`、summaryから自動生成される。記事追加後に別途 `data/security-watch.json` へ登録する指示は不要。旧JSONはアーカイブとして保持する。
- 製品名・深刻度・対応策は一次情報を確認し、明示する。タイトルから推測して補わない。WATCH除外は `security_watch: false` と理由を明示する。
- `social_platforms: ["threads"]` は恒久的な媒体選択として扱われる。Instagram障害の一時回避として設定して放置しない。投稿枠待ちは台帳の `deferred` で管理する。
- 過去記事へSNS承認フラグを一括追加しない。復旧は記事ID・媒体・一次情報の鮮度・既存の実投稿を照合し、対象を限定する。
- `attempting` / `needs_review` を削除・初期化して再送しない。結果不明は実アカウントで照合する。ストーリーズのcaptionが空であることだけを未投稿の根拠にしない。
- 投稿は共通ロック内で直列実行する。臨時の固定記事用投稿スクリプトを増やさず、共通キューと対象限定の復旧レビューを使う。
- 公開前にテストとビルドを行う。カテゴリーは既存の値を使う。画像の必須ラベル・文字数・レイアウトの検証を省略しない。
- コミット成功、Pages成功、SNS成功は別々に検証する。Summaryと媒体別台帳、可能な投稿URLを照合し、待機・要確認を「全件完了」に含めない。
- Instagram投稿数制限の2207042は認証切れと決めつけない。APIの実枠と安全なエラーコード・工程を確認する。トークンや生のAPIエラー本文をログへ出さない。
