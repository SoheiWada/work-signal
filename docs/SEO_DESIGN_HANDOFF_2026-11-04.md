# WORK SIGNAL｜デザイン・編集品質改善からSEO担当への引継ぎ

**記録日:** 2026-11-04 JST  
**リポジトリ:** [SoheiWada/work-signal](https://github.com/SoheiWada/work-signal)  
**本番URL:** https://signal.amberlight.co.jp/  
**対象の本番コミット:** [`885f41fd87af7a24abc80e57a511ddb20d16857d`](https://github.com/SoheiWada/work-signal/commit/885f41fd87af7a24abc80e57a511ddb20d16857d)  
**用途:** 別のSEO改善スレッドが既存実装を誤って壊さないための変更履歴・保守上の注意事項。公開データやSearch Consoleの現在値を示すレポートではない。

## 1. 結論：今回の改修範囲

2026年11月3日〜4日の4つのPRで、記事の余白・文字組み、概要の重複除去、読了時間、BRIEF/DEEP DIVE表示分類、記事上部の情報整理、根拠付きの独自数値図解（DATA FREQUENCY）を改善した。

| PR | 内容 | SEO担当への注意 |
| --- | --- | --- |
| [#28](https://github.com/SoheiWada/work-signal/pull/28) | 紙色とシグナルのブランド表現を維持して、記事カードと本文の余白・文字組み・モバイル操作性を整理。旧PR #27の変更を内包 | 見出し・本文表示のCSSを不用意に上書きしない |
| [#29](https://github.com/SoheiWada/work-signal/pull/29) | `summary` と `quick_take` が同内容なら「30秒でわかる」の重複表示を抑制。ホームの記事検索、LATESTと注目SECURITY記事の重複解消、読了時間の一元化、リンク表現の統一 | 既存のSEO本文に相当する `summary` は保存。重複抑制により可視テキストは変わる |
| [#30](https://github.com/SoheiWada/work-signal/pull/30) | SIGNAL BRIEF / DEEP DIVE表示分類を整え、右上を固定の「約3分」や「4–7 MIN」ではなく、計算した `03 MIN` 等のタイポグラフィに変更 | 表示分類は原稿の古い `format` 値だけで決まらない。カテゴリ・記事形式フィルターとも整合させる |
| [#32](https://github.com/SoheiWada/work-signal/pull/32) | 記事上部は見出しを主役に、カテゴリー・形式、公開日、読了時間を整理。SIGNAL SCOREは横のARTICLE INTELLIGENCEへ移動。一次情報に基づくDATA FREQUENCY初号、編集品質ルール、1記事の数値誤記訂正 | 新しい図解の母数・注記・出典リンクを維持。記事本文の一部に意図的な訂正あり |

## 2. 意図的に維持したもの（SEO・配信の不変条件）

- 公開済み記事の **記事IDと正規URL**：`https://signal.amberlight.co.jp/articles/<記事ID>/`。既存リンクの301移行やパス変更は実施していない。
- **canonical、title、meta description、OGP、Article/NewsArticleの構造化データ、robots.txt、サイトマップ、RSS、favicon** の生成ロジックは改修対象外。詳細はビルド済みHTMLでも検査すること。
- 元の **`published_at`（初回公開日）** は維持。本文・見出しを実際に訂正した記事の `dateModified` / `lastmod` は既存の履歴連動処理で変わり得る。
- GA4、Google Search Consoleの設定・計測の意図は変更していない。Search Consoleの再登録・サイトマップ再送は改修だけを理由には不要。
- `social_publish`・`social_platforms`、SNS配信ワークフロー、既存投稿台帳、過去記事の承認状態は保持。**SEO改稿はSNSへの新規投稿・再投稿の承認ではない**。配信ワークフローの成功は全媒体の投稿完了を意味しない。
- SECURITY WATCHの独立した公開・深刻度ロジックと既存記事URLを維持。

**留保:** 可視テキストの重複除去、表示ラベルや内部の回遊導線、記事内の訂正はHTMLに反映される。SEOに影響が絶対にない、順位が維持される、という保証ではない。

## 3. 現行表示・記事データに関する要点

### 3-1. 概要・「30秒でわかる」

- `summary` は記事リードおよび検索向け説明に使う。編集上の意味を変えずに維持。
- `quick_take` は理由・仕事への影響・留保を整理する別要約。同一文・ほぼ同一内容の場合、HTMLの重複表示を抑止する（既存記事の本文を一括書換したものではない）。
- 2026-11-03の静的ビルドでは、**278記事のうち156記事**で重複した `quick_take` の表示を抑制した。今後の記事追加により件数は変動する。
- 新規原稿では要約の重複自体を執筆時に防ぐ。

### 3-2. SIGNAL BRIEF / SIGNAL DEEP DIVEと「03 MIN」

- 通常ニュースの表示分類は `scripts/build_site.py:reading_format()` による一次判定。**有効な解説4章以上、本文の空白除外1,000文字以上、160文字以上の章が3つ以上**でDEEP DIVEと扱う。例外は理由付きの `reading_format_override`。特集・管理職ガイドは別分類。
- 表示時の分類を反映する場所：ホーム記事カード、絞り込み、アーカイブ、テーマ別カード、記事本文、プレビュー、生成済み`data/index.json`。
- 基準適用時の内訳：**BRIEF 102本、DEEP DIVE 169本、MANAGEMENT GUIDE 5本、SPECIAL STORY 2本**。元データの `format` を一括書換していない。
- 読了時間は表示テキスト量から算出し、`03 MIN` の数字中心の表現を使用。過去の `1–2 MIN`・`4–7 MIN` がホーム／アーカイブへ漏れると出力検査で失敗する。
- **文字数だけで記事の分析品質が保証されるわけではない。** 新規DEEP DIVEには一次情報の照合・比較背景・実務への示唆・不確実性の4点を編集上の必須条件として適用。詳細は [EDITORIAL_QUALITY_STANDARD.md](EDITORIAL_QUALITY_STANDARD.md)。

### 3-3. 記事ヒーローとARTICLE INTELLIGENCE

- 記事上部の視覚的優先順位：カテゴリー／記事形式 → 大きな日本語見出し → 公開日・更新日（存在する場合）・`03 MIN`。
- スコア表示をヒーローから外し、横の `ARTICLE INTELLIGENCE` 内のSIGNAL SCOREへ移動。**スコアデータ自体や掲載基準は変更していない**。
- 既存の紙色`#F2EFE7`、墨色`#191918`、アクセント`#FA4C24`、波形シグナルの意匠を維持。
- 旧記事の更新日表記とタイムスタンプに関する回帰テストも通過した。

### 3-4. DATA FREQUENCYの初号

- 対象記事：[`20261102-ai-productivity-gains-unreported-management-survey`](https://signal.amberlight.co.jp/articles/20261102-ai-productivity-gains-unreported-management-survey/)。
- データ：`data/editorial-figures.json`。HTML生成：`scripts/build_site.py:editorial_evidence_figure()`。画像に固定せず、静的HTML・CSSで表示。
- **95.2％ / n=546**：AIによる業務時間短縮を感じた割合。**71.1％ / n=520**：短縮を実感した回答者のうち、成果を積極的に報告していない割合。**母数が異なるため、両者の差や因果関係を表す図ではない**。実測の時間削減でもない。
- 一次資料：[`ウイングアーク１ｓｔ調査の公表資料`](https://prtimes.jp/main/html/rd/p/000000383.000053341.html)（2026-11-02）。
- 同記事の章見出しの明確な数値誤記 **「2％」→「95.2％」** を訂正。原稿データ変更はこの見出し1箇所。記事ID、記事タイトル、元の公開日は維持。編集変更に伴う更新日時の自動反映はあり得る。

## 4. 変更ファイルと触る際の注意

| ファイル | 役割 |
| --- | --- |
| `index.html` | ホームのカード／検索・カテゴリー・形式絞り込み、読了時間のデザイン |
| `article.html` / `preview.html` | 動的記事・プレビューのヒーローと文字組み。静的記事との差異に注意 |
| `scripts/build_site.py` | 公開HTML生成、BRIEF/DEEP DIVE派生分類、重複要約抑制、読了時間、DATA FREQUENCY図解 |
| `data/articles.json` | 承認済み原稿・日付・記事IDの原本。#32で数値誤記1箇所のみ訂正 |
| `data/editorial-figures.json` | 一次情報・母数を確認した図解定義 |
| `docs/EDITORIAL_QUALITY_STANDARD.md` | 今後の深い記事の質的基準・図解デザインガイド |
| `scripts/check_site_output.py` | 記事出力、表示分類、読了時間表記、図解、SEOヘッドの検査 |
| `tests/test_build_site.py` / `tests/seo/editorial_ui.test.mjs` | SEO関連の出力・静的生成・表示コードの回帰テスト |
| `docs/SEO_EDITOR_HANDOFF.md` | 既存SEO運用の基本ルール。本書を補足文書として参照 |

今後のSEO施策でタイトルや要約、内部リンクを最適化する場合も、原文の事実／読者価値／初回公開日／承認・SNS台帳を維持する。BRIEFを不必要に長文化しない。

## 5. 公開・検証ログ

- **本番デザイン公開：** [GitHub Actions #41664645218](https://github.com/SoheiWada/work-signal/actions/runs/41664645218) — `build=success`、`deploy=success`、対象コミット `885f41fd`。
- **SNS配信経路：** [#41665392297](https://github.com/SoheiWada/work-signal/actions/runs/41665392297) — ワークフロー成功。ただし「Publish explicitly approved articles」は`skipped`で、今回のデザイン変更だけを理由に記事を再投稿していない。
- **リグレッション検証：** 278記事、SECURITY WATCH 98件、重複抑制156件、分類102/169/5/2、DATA FREQUENCY 1件、サイトマップURL299件、SEO出力検査の`errors=[]`（公開時点の観測値、今後変動する）。
- **公開前バックアップ：** `backup/pre-editorial-20261103`、`backup/pre-editorial-clarity-20261103`、`backup/pre-reading-formats-20261103`、`backup/pre-data-frequency-20261104`。最新の今回の変更直前は最後のブランチ。
- **目視QAの留保：** PC・スマホのスクリーンショットを用いた実画面デザインの最終検収はまだ実施していない。Actions成功とブラウザ上の文字組み検収は別。

### 次にSEOスレッド側が重点確認すること

1. **Search Consoleの実測値**：サイト名表示（`amberlight.co.jp` と出る懸念）は未解決課題として、WebSite構造化データ・`og:site_name`・サイト名の一貫性・Google側の処理状況を確認。今回のデザイン改修だけで直ったと断定しない。
2. **高表示・低CTRの検索クエリ**（例：JP Incident Monitor）を同一期間で比較。掲載順位・表示回数・クリック・CTRを分けて読む。サイト全体のPVとGSCクリック数を混同しない。
3. **記事の重複・回遊**：`summary` と`quick_take` の役割分担、関連記事の関連性、クロール可能なアーカイブとテーマ別ページを改善。ホームのJavaScript検索結果を独立した検索登録ページとみなさない。
4. **改稿優先順位**：誤記・事実誤認 → 検索意図とタイトルの不一致 → 独自分析不足の順。記事IDと公開日は保持し、改稿差分をレビューする。
5. **ビジュアル図解とSEO**：図解にテキストの説明、一次情報リンク、母数、注記を残し、スクリーンリーダー／モバイル対応を検証。図解を装飾だけの画像に置き換えない。
6. **ページ表示実測**：実ブラウザでPC・390px・320px幅、長い見出し、トップ・アーカイブ、SECURITY WATCH、図解対象記事を確認。CLSやLCPなどの体感・実測は未監査。

## 6. テスト・公開手順（変更時）

```bash
node --test tests/seo/*.test.mjs
python3 -m unittest discover -s tests -p 'test_build_site.py'
python3 -m unittest discover -s tests -p 'test_seo_metadata.py'
python3 scripts/build_site.py
python3 -m scripts.check_site_output
python3 -m scripts.audit_seo_output
```

本番は`.github/workflows/pages.yml`でビルド後、GitHub Pagesへデプロイする。**ビルド成功とデプロイ成功を両方確認し、可能なら公開URLで直接確認**する。検索クローラーの古いキャッシュやブラウザキャッシュと、実際の生成コードを区別して調査する。

この文書は2026年11月4日時点の引継ぎであり、記事の自動追加・SEO改修・手動改稿の後は`main`の最新状態とActionsを優先する。
