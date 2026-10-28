# WORK SIGNAL 公開運用マニュアル

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


最終更新: 2026-10-19

## 公開環境と原則

- 公開サイト: https://signal.amberlight.co.jp/
- GitHub: https://github.com/SoheiWada/work-signal
- 公開元: `main` ブランチ
- 公開基盤: GitHub Pages（GitHub Actionsで静的サイトをビルドしてデプロイ）
- ワークフロー: `.github/workflows/pages.yml`（`Build and deploy WORK SIGNAL`）
- 記事データ: `data/articles.json`
- ビルド: `python3 scripts/build_site.py`
- テスト: `python3 -m unittest discover -s tests`
- **GitHubへのコミット成功は公開成功ではない。buildとdeployが成功し、公開URLで記事を確認して初めて公開完了。**
- 公開は編集者の明示的な承認後に行う。2026年10月25日以降の「公開」は記事と公式SNS投稿の承認を兼ねるが、`social_publish: true` を付けた記事のみSNS対象とする。
- 記事追加の際、既存記事・デザイン・操作仕様は変更しない。変更は依頼された範囲に限定する。

## 新規記事の公開手順（毎回必須）

1. 一次情報と数値・日付・引用・留保条件を検証する。
2. `data/articles.json` の既存記事を保持して新記事を追加する。カテゴリーは `scripts/build_site.py` の `CATEGORIES` と `index.html` の `categories` にある既存の値のみ使用する（例: `経済`。**`お金・経済` は未登録**）。
3. `status: "published"`、`score >= 80`、重複しない安全な `id`、`title`、`summary`、`published_at`（ISO日付）、HTTPSの `source_url` を検証する。
4. フォーマットを検証する。SIGNAL DEEP DIVEは `format: "deep_dive"`、`quick_take`、`sections` を使用。通常記事（SIGNAL BRIEF）は `what_happened`、`why_it_matters`、`impact`、`caveats` を使用する。両者の項目構造は異なる。
5. **プッシュ前にテストとビルドを実行する。** 必要な依存関係は `requirements-build.txt` を参照。例:
   ```bash
   python3 -m pip install -r requirements-build.txt
   python3 -m unittest discover -s tests
   python3 scripts/build_site.py
   ```
   ビルド生成物は `_site/`。既存デザインと記事が保持され、記事個別ページとOG画像が生成されることを確認する。
6. 必要なファイルのみ `main` にコミット／プッシュする。
7. https://github.com/SoheiWada/work-signal/actions の最新 `Build and deploy WORK SIGNAL` を確認し、**build=success と deploy=success** の両方を確認する。失敗なら `build` ジョブのログを確認し、原因を直してから再実行／再プッシュする。失敗中は「公開済み」と報告しない。
8. https://signal.amberlight.co.jp/ のトップに新記事があり、`https://signal.amberlight.co.jp/articles/<記事ID>/` の個別記事が開くことを確認する。公開データ `/data/articles.json` も必要に応じて確認する。
9. すべて成功したら、記事URLと公開完了を報告する。確認できない場合は、何を確認できたか・できなかったかを明示する。
10. 承認された新規記事には `social_publish: true` を含める。Threads投稿文には記事URLと、末尾の一次情報プレーン `https://...` URLを入れる。Instagram用に専用JPEGも生成される。
11. SNS配信はPages公開成功後に別のGitHub Actions `Publish approved WORK SIGNAL social posts` が実施。MetaのSecrets・有効化変数が未設定なら投稿しない。**記事のサイト公開とSNSへの実投稿はそれぞれ確認・報告する。** 設定方法は `docs/SOCIAL_AUTOPUBLISH.md`。

## 2026-10-19 障害の原因と解決（再発防止）

- 記事 `20261019-bond-safe-haven-inflation` を先頭に追加した際、最初はカテゴリーを `お金・経済` としていた。サイトの有効カテゴリーは `お金` と `経済` が別々のため、`経済` に修正した（コミット `6f488f0`）。
- しかし公開されず、GitHub Actions #55（`fdd2ba1`）と #56（`6f488f0`）で **buildが失敗、deployがスキップ**されていることが判明した。
- 原因となるコード上の不整合: `tests/test_build_site.py` の `setUp` が `data/articles.json` の **先頭記事**を通常記事として使用し、テスト内で `what_happened` を参照していた。先頭がDEEP DIVE形式になるとそのキーがなく、テストが失敗する。
- 対策: テスト用の通常記事を `what_happened` の有無で選択するよう変更（コミット `705f4f7`）。ユーザーがその後「公開できた」と確認した。
- **再発防止**: 新記事の順序やフォーマットによってテストが壊れないか、必ず事前テスト。記事一覧の先頭を通常記事と決めつけない。
- ビルド失敗時に「タイムラグ」「ブラウザキャッシュ」と決めつけない。まずGitHub Actionsのbuild/deploy結果と失敗ログを見る。

## 診断の順番

1. GitHubの`main`に新記事が存在するか。
2. GitHub Actionsの最新実行でbuild/deployが成功したか。
3. 失敗なら該当ジョブログとテスト結果を確認する。
4. 成功なら公開サイトのトップ、個別記事、公開JSONを比較する。
5. その後にキャッシュ／ブラウザの問題を疑う。

この文書は、別日・別スレッドでWORK SIGNALの公開作業を始める際にも**最初に参照する運用手順**とする。

## SEO対応後の投稿確認（2026-10-22）

記事JSONと承認・公開手順は継続。新しい必須項目はない。更新日は記事単位のGit履歴から自動判定する。投稿担当への引継ぎは `docs/SEO_EDITOR_HANDOFF.md` を参照。旧記事URLの回帰検証として `node --test tests/seo/*.test.mjs` が公開ワークフローに追加されている。


### 2026-10-28 追加で判明したInstagramの保護制限

実投稿の復旧中に、フィード公開工程で `HTTP 403 / code=4 / subcode=2207051` が発生した。従来の `code=9 / subcode=2207042`（投稿数枠）とは別に扱う。この保護制限を検出した場合はその実行の以降の該当媒体への送信を止め、既存台帳に同じ未解決制限があれば次の実行でも該当媒体へは送らない。正常なThreads・他媒体は独立して継続する。投稿数枠が減ったことやプロフィールGET成功だけで解除済みとは判定しない。Instagramのアカウント状態とMetaの指示を確認し、解除の証拠が得られてから新しい復旧レビューで再開する。文面変更や短時間の再送で制限を回避しようとしない。

10月28日の実照合ではフィードに2207051が出る一方でストーリーズ5件の公開が成功し、公式アカウントの機能制限画面は「現在すべての機能を利用できます」と表示された。アカウント全体の違反確定とは扱わず、拒否された媒体の送信を止めて原因を調べる。
