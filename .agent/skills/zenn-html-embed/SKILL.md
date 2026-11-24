---
name: zenn-html-embed
description: >-
  Creates, converts, and validates Zenn html-embed diagrams using HTML and CSS
  within Zenn's sandbox constraints. Use this skill when the user asks to
  replace Mermaid diagrams with html-embed, draw architecture/flow/sequence
  diagrams for Zenn articles, or verify html-embed blocks.
---

# Zenn `html-embed` Diagram Skill

Zenn の ` ```html-embed ` コードブロックを使って、記事内に埋め込む図解（構成図・フローチャート・シーケンス図など）を作成・変換・検証するための手順書です。
公式仕様: https://info.zenn.dev/2026-11-11-html-embed

## 1. 必須ルールと制限

- **出力形式**: コードブロックの言語名を `html-embed` にし、中身は HTML と `<style>` のみにする（`<html>`・`<head>`・`<body>` は書かない）。
- **使用禁止**:
  - JavaScript（`<script>`、`onclick` などのイベントハンドラ）。動きや切替は CSS アニメーション、`:hover`、`<input type="radio" | "checkbox">` + `:checked` を使う。
  - ページ遷移リンク（`<a>` は単なるテキスト扱い）。
  - フォーム・入力欄（`<form>`、`<button>`、`<textarea>`、`<select>`、テキスト用 `<input>`、`contenteditable`）。
  - 外部リソース（`<link>`、`@import`、Web フォント、`<iframe>`）。画像は指定された URL またはインライン SVG のみ使う。
- **サイズ上限**:
  - 1 ブロックあたり **50KB 以内**。
  - 表示高さは PC・スマホともに **500px 以内** に収める（超過時はフレーム内スクロールになる）。
- **ライト／ダークモード対応**:
  - ダークモード時は埋め込みの `<html>` に `data-theme="dark"` が付与される。
  - ルートコンテナに CSS 変数を定義し、`[data-theme="dark"] .root { ... }` で色を切り替え、背景色と文字コントラストを明示する。
- **PC・スマホ両対応**:
  - 記事本文幅（PC 約 700px、スマホ約 340px）に収める。
  - `@media (max-width: 640px)` で 1 カラム縦積み等に切り替え、横はみ出しを防ぐ。
  - Flex / Grid の子要素には `min-width: 0` と `overflow-wrap: anywhere` を設定する。
- **読みやすさ・安全**:
  - 文字サイズはすべて **12px 以上** にする。
  - 色だけに頼らず、文字やラベルでも状態を区別する。
  - アニメーションを使う場合は `@media (prefers-reduced-motion: reduce)` で停止する。

## 2. CSS ベーステンプレート

クラス名は記事内の他ブロックと衝突しない短いプレフィックスを付け、CSS 変数でテーマを切り替えます。

```css
.diag-root {
  --bg: #f8fafc;
  --surface: #ffffff;
  --border: #cbd5e1;
  --text: #0f172a;
  --muted: #475569;
  --accent: #0284c7;
  --accent-bg: #e0f2fe;
  box-sizing: border-box;
  padding: 14px;
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  font-size: 12px;
  line-height: 1.45;
}

[data-theme="dark"] .diag-root {
  --bg: #0f172a;
  --surface: #1e293b;
  --border: #334155;
  --text: #f1f5f9;
  --muted: #cbd5e1;
  --accent: #38bdf8;
  --accent-bg: #0c4a6e;
}

.diag-root *,
.diag-root *::before,
.diag-root *::after {
  box-sizing: border-box;
}
```

## 3. Mermaid からの変換パターン

縦長の図をそのまま縦に積むと 500px 上限を超えやすいため、PC 幅（約 700px）を活かして横方向に整理します。

- **フローチャート (`flowchart`)**:
  - 処理のまとまりごとに 2 カラム（CSS Grid: `grid-template-columns: 1fr 1fr`）へ分割し、ループは枠線付きコンテナ（章ループの中に節ループ等）で表現する。
  - `@media (max-width: 640px)` で `grid-template-columns: 1fr` に切り替える。
- **シーケンス図 (`sequenceDiagram`)**:
  - PC 版はアクター数分の列を持つ CSS Grid（`repeat(N, minmax(0, 1fr))`）で各メッセージを `grid-column` 配置し、`alt / else` 分岐は色分けした枠で囲む。
  - スマホ版（`@media (max-width: 640px)`）はアクターヘッダーを非表示にし、「`送信元 → 送信先`」ラベル付きの縦型タイムラインへ切り替える。

## 4. 検証

編集後、同梱の検証スクリプトで対象 Markdown ファイルをチェックします。

```sh
python .agent/skills/zenn-html-embed/scripts/validate_html_embed.py <target.md>
```

チェック項目:
1. 1 ブロック 50KB 以内であること
2. 禁止タグ・記法（`<html>`, `<script>`, `<a>`, `<form>`, `<button>`, `<iframe>`, `<link>`, `@import` 等）が含まれないこと
3. `[data-theme="dark"]` と `@media (max-width: 640px)` が含まれること
4. `font-size` に `12px` 未満の指定がないこと
