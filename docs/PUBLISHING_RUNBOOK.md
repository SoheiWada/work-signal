# WORK SIGNAL 公開運用マニュアル

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
- 公開は編集者の明示的な承認後に行う。Threadsは投稿文の提示のみで、無断投稿しない。
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
10. Threads投稿文には一次情報のプレーンな `https://...` URLを本文末尾に入れる。ユーザーの承認なくThreadsに投稿しない。

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
