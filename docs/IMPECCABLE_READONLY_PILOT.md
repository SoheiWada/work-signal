# WORK SIGNAL — Impeccable read-only pilot

作成日: 2026-11-03 JST
状態: **準備済み / Impeccable本体によるスキャン未実施**

## 目的と範囲

既存のWORK SIGNALブランド（紙色・墨色・オレンジ、英日タイポグラフィ）、静的HTML/CSS、記事詳細、SECURITY WATCHのデザインを壊さず、アクセシビリティ・可読性・レスポンシブ品質を監査する。SEO、公開フロー、Threads/Instagramの処理には一切手を加えない。

公式: https://github.com/pbakaus/impeccable および https://impeccable.style/docs/detector/
確認時の上流 `package.json` は `4.8.0`（npmへの実際の公開状況は未検証）。ライセンスはApache-2.0。

## 安全境界

- 本パイロットは独立ブランチのみ。 `main`、`.github/workflows/pages.yml`、SNSワークフロー、データ・台帳、編集部Workersを変更しない。
- Impeccableの `install` / `init` / hook / `live` / Apply / 自動編集コマンドは実行しない。`detect` のみを手動実行する。
- Impeccableのliveモードは環境設定次第で権限チェックを回避したCLI起動へフォールバックするため、このパイロットでは**禁止**。
- サードパーティCLIの初回 `npx` 実行にはnpm通信およびネイティブエンジンの取得が発生し得る。実行環境とパッケージの真正性を別途確認する。GitHub Secrets等を持つ環境では実行しない。
- 結果ファイルは`/tmp`配下に作り、Git管理下へ自動保存しない。テレメトリー無効化のため `DO_NOT_TRACK=1` を設定する（外部リクエスト全体を禁止する設定ではない）。
- 自動修正、CSS差替、デプロイ、SNS投稿は行わない。修正は別PRでレビューする。

## 実行方法（手動、read-only）

Node.js 18.19+、npm、URL検査ではChrome/Chromiumが必要。

```bash
bash tools/ui-audit-impeccable.sh index.html
bash tools/ui-audit-impeccable.sh article.html
bash tools/ui-audit-impeccable.sh assets/css/signal-interactions.css
bash tools/ui-audit-impeccable.sh https://signal.amberlight.co.jp/ desktop
bash tools/ui-audit-impeccable.sh https://signal.amberlight.co.jp/ mobile
```

安全な手動スキャンのみ実施。スクリプトは`impeccable@4.8.0 detect`を呼び出すが、パッケージがダウンロードできない場合はエラーとして終了する。発見事項が存在するCLI終了コード2は「正常に監査して問題を検出した」と判定する。実行できないコード1と区別する。

URL検査は実ページのレンダリングを使い、デスクトップ1280×800 / モバイル390×844で確認。記事個別ページは最新公開URLを別途確認して指定する。SECURITY WATCHはトップ内の専用セクションと個別記事の両方を対象とする。

## 2026-11-03 実コードによる初期所見（Impeccable実行結果ではない）

| 重要度 | 所見 | 根拠／検証課題 |
| --- | --- | --- |
| P1候補 | `#fa4c24` のオレンジ文字を `#f2efe7` の淡い背景に使う場合のコントラストは約2.98:1。通常サイズ文字のWCAG AA 4.5:1に届かない | `index.html` の`:root` とアクセントラベル等。装飾と文字の使い分けが必要 |
| P1候補 | スマホのメインナビからLATESTおよびABOUT相当のリンクが隠れる | `index.html` の `@media(max-width:700px){.navlinks a:not(.nav-nba){display:none}}` 。別導線が十分か実機確認 |
| P2候補 | 9〜11pxのラベルや小さな補助文字がトップやマーケットUIに散在する | `index.html`、`assets/css/hero-market.css` 。実機で可読性と拡大表示を確認 |
| 維持 | `prefers-reduced-motion: reduce` および一部の `:focus-visible` が実装済み | `index.html`, `article.html`, `assets/css/signal-interactions.css` |

コントラスト値は色コードからの計算であり、各コンポーネントの最終的な合否・DOM配置はブラウザで確認する。上記のP1/P2は**修正優先度候補**であり、自動監査の確定判定ではない。

## 次の判定基準

1. 実行ログでCLIが正常終了したことを確認する（問題発見による終了コード2も許容）。
2. ソース監査とレンダリング監査を分けて一覧化。実ページで再現できない警告やブランド固有の意匠は安易に修正しない。
3. P0/P1候補の再現確認を優先し、修正案・Before/After画像を**別PR**で提示。
4. デザイン変更後に既存の `python3 -m unittest discover -s tests`、`node --test tests/seo/*.test.mjs`、`python3 scripts/build_site.py`、`python3 -m scripts.check_site_output`、`python3 -m scripts.audit_seo_output` を実行。さらに公開HTML、記事・SECURITY WATCH、SNS連携に変更がないことを検証。
5. 本番反映は別途承認する。デザイン監査をGitHub Actionsの自動投稿経路へ組み込まない。

## 計測できていないこと

現時点ではブラウザでの画面比較、パフォーマンス計測（Lighthouse/CrUX）、実際のImpeccable detector出力、CSS変更後の回帰テストを実施していない。これらを実施済みと報告しない。
