---
title: "Zennの新機能、HTMLとCSSで描いた図を記事に埋め込んでみた（html-embed 実験室）"
emoji: "🐥"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: ["zenn", "html", "css", "markdown", "ui"]
published: true
---

# はじめに

2026年11月11日、Zenn にコードブロックの言語名を `html-embed` にするだけで HTML と CSS で描いた図をその場で記事に埋め込める機能（Beta）が追加されました。

https://info.zenn.dev/2026-11-11-html-embed

これまで Zenn の記事に図を入れるときは、「Figma や Excalidraw で画像を作ってアップロードする」か「Mermaid（`mermaid` コードブロック）で書く」のが定番でした。しかし、それぞれ以下のような悩みがありました。

- 画像アップロード: デザインの自由度は高いものの、後から文言を1文字直すだけでも画像を作り直す必要があり、Git で差分管理しにくい。また、ダークモード切り替えにも追従しづらい。
- Mermaid: テキストで管理できるものの、レイアウトの微調整や細かな色分け、アニメーション、リッチな表組みなどの表現力に限界がある。

今回追加された `html-embed` を使えば、テキスト（Markdown）のまま Git で管理でき、HTML / CSS / インライン SVG の表現力を活かした図解を記事内に直接レンダリングできます。

本記事では、各実験でどのような HTML と CSS を使って図を構築しているのかが具体的にわかるよう、埋め込み結果の下にソースコードを掲載しながら解説していきます。

---

# `html-embed` の仕様と制約の整理

実験に入る前に、公式ドキュメントに記載されている仕様とセキュリティ上の制限を整理しておきます。

| 項目 | 仕様・制限の内容 |
| :--- | :--- |
| 基本の書き方 | ```` ```html-embed ```` の中に HTML と `<style>` を書く（`<html>`・`<head>`・`<body>` は不要） |
| サイズ・高さ上限 | 1ブロックあたり 50KB 以内、表示される高さは最大 500px（超過分は埋め込み内でスクロール） |
| 表示幅の目安 | PC で約 700px、スマホで約 340px（`@media (max-width: 640px)` 等でレスポンシブ対応推奨） |
| JavaScript | 実行不可（`<script>` や `onclick` 等のイベントハンドラは使えない） |
| リンク・外部リソース | `<a>` によるページ移動不可（文字として表示）。外部 CSS（`<link>` / `@import`）、Web フォント、`<iframe>` も不可 |
| 画像 | インライン SVG、画像 URL、`data:` URI の画像が使用可能（意味のある画像は背景ではなく `<img alt="...">` を使う） |
| フォーム要素 | `<form>`・`<button>`・`<textarea>`・`<select>`・文字入力 `<input>` は非表示。ただし `type="checkbox"` と `type="radio"` の `<input>` は使用可能 |
| ダークモード判定 | ダークモード時は埋め込みの `<html>` に `data-theme="dark"` が付与される（`[data-theme="dark"]`、`light-dark()`、`<style data-theme="dark">` で分岐可能） |

特に面白いのが、JavaScript や `<button>` は使えないものの、`input[type="radio"]` と `input[type="checkbox"]` は `:checked` 用に許可されている点です。これを使えば、JS なしでもタブ切り替えや状態比較ができるインタラクティブな図解が作れます。

---

# 実験 1：ダークモード＆レスポンシブ対応のステップフロー図

まずは基本となるフロー図です。CSS カスタムプロパティ（変数）と `[data-theme="dark"]` を使ってライト・ダーク両テーマに対応させ、幅 640px 以下で矢印と並び順を縦向きに切り替えています。

### 埋め込み表示結果

```html-embed
<div class="exp1-wrap">
  <div class="exp1-header">
    <span class="exp1-badge">HTML / CSS Pipeline</span>
    <span class="exp1-title">リクエストからレスポンスまでの処理フロー</span>
  </div>
  <div class="exp1-steps">
    <div class="exp1-step">
      <div class="exp1-num">STEP 01</div>
      <div class="exp1-name">Edge CDN</div>
      <div class="exp1-desc">静的アセット配信・WAF検証</div>
      <span class="exp1-tag exp1-tag-fast">~5ms</span>
    </div>
    <div class="exp1-arrow" aria-hidden="true"></div>
    <div class="exp1-step">
      <div class="exp1-num">STEP 02</div>
      <div class="exp1-name">App Server</div>
      <div class="exp1-desc">認証認可・SSRレンダリング</div>
      <span class="exp1-tag exp1-tag-mid">~35ms</span>
    </div>
    <div class="exp1-arrow" aria-hidden="true"></div>
    <div class="exp1-step">
      <div class="exp1-num">STEP 03</div>
      <div class="exp1-name">Primary DB</div>
      <div class="exp1-desc">コネクションプール経由でクエリ</div>
      <span class="exp1-tag exp1-tag-db">~12ms</span>
    </div>
  </div>
</div>
<style>
  .exp1-wrap {
    --bg: #f8fafc;
    --card-bg: #ffffff;
    --text-main: #0f172a;
    --text-sub: #475569;
    --border: #e2e8f0;
    --accent: #3ea8ff;
    --accent-soft: #e0f2fe;
    --accent-text: #0369a1;
    padding: 20px;
    background: var(--bg);
    color: var(--text-main);
    border-radius: 8px;
    font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans", "Noto Sans JP", sans-serif;
    box-sizing: border-box;
  }
  [data-theme="dark"] .exp1-wrap {
    --bg: #0f172a;
    --card-bg: #1e293b;
    --text-main: #f1f5f9;
    --text-sub: #94a3b8;
    --border: #334155;
    --accent: #38bdf8;
    --accent-soft: #0c4a6e;
    --accent-text: #7dd3fc;
  }
  .exp1-header {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 16px;
    flex-wrap: wrap;
  }
  .exp1-badge {
    font-size: 12px;
    font-weight: 700;
    padding: 3px 10px;
    border-radius: 999px;
    background: var(--accent-soft);
    color: var(--accent-text);
  }
  .exp1-title {
    font-size: 14px;
    font-weight: 700;
  }
  .exp1-steps {
    display: flex;
    align-items: stretch;
    justify-content: space-between;
    gap: 8px;
  }
  .exp1-step {
    flex: 1;
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-top: 3px solid var(--accent);
    border-radius: 10px;
    padding: 14px;
    display: flex;
    flex-direction: column;
    gap: 6px;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.04);
  }
  .exp1-num {
    font-size: 12px;
    font-weight: 700;
    color: var(--accent);
    letter-spacing: 0.05em;
  }
  .exp1-name {
    font-size: 15px;
    font-weight: 700;
  }
  .exp1-desc {
    font-size: 12px;
    color: var(--text-sub);
    line-height: 1.4;
    flex: 1;
  }
  .exp1-tag {
    align-self: flex-start;
    font-size: 12px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 6px;
    margin-top: 4px;
  }
  .exp1-tag-fast { background: #dcfce7; color: #166534; }
  .exp1-tag-mid  { background: #fef3c7; color: #92400e; }
  .exp1-tag-db   { background: #ede9fe; color: #5b21b6; }
  [data-theme="dark"] .exp1-tag-fast { background: #14532d; color: #86efac; }
  [data-theme="dark"] .exp1-tag-mid  { background: #78350f; color: #fde68a; }
  [data-theme="dark"] .exp1-tag-db   { background: #4c1d95; color: #ddd6fe; }

  .exp1-arrow {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    position: relative;
    flex-shrink: 0;
  }
  .exp1-arrow::before {
    content: "→";
    font-size: 18px;
    font-weight: 700;
    color: var(--accent);
  }
  @media (max-width: 640px) {
    .exp1-steps {
      flex-direction: column;
    }
    .exp1-arrow {
      width: 100%;
      height: 20px;
    }
    .exp1-arrow::before {
      content: "↓";
    }
  }
</style>
```

### 使用した HTML 構造

```html
<div class="exp1-wrap">
  <div class="exp1-header">
    <span class="exp1-badge">HTML / CSS Pipeline</span>
    <span class="exp1-title">リクエストからレスポンスまでの処理フロー</span>
  </div>
  <div class="exp1-steps">
    <div class="exp1-step">
      <div class="exp1-num">STEP 01</div>
      <div class="exp1-name">Edge CDN</div>
      <div class="exp1-desc">静的アセット配信・WAF検証</div>
      <span class="exp1-tag exp1-tag-fast">~5ms</span>
    </div>
    <div class="exp1-arrow" aria-hidden="true"></div>
    <div class="exp1-step">
      <div class="exp1-num">STEP 02</div>
      <div class="exp1-name">App Server</div>
      <div class="exp1-desc">認証認可・SSRレンダリング</div>
      <span class="exp1-tag exp1-tag-mid">~35ms</span>
    </div>
    <div class="exp1-arrow" aria-hidden="true"></div>
    <div class="exp1-step">
      <div class="exp1-num">STEP 03</div>
      <div class="exp1-name">Primary DB</div>
      <div class="exp1-desc">コネクションプール経由でクエリ</div>
      <span class="exp1-tag exp1-tag-db">~12ms</span>
    </div>
  </div>
</div>
```

:::details CSS スタイルを見る
```css
.exp1-wrap {
  --bg: #f8fafc;
  --card-bg: #ffffff;
  --text-main: #0f172a;
  --text-sub: #475569;
  --border: #e2e8f0;
  --accent: #3ea8ff;
  --accent-soft: #e0f2fe;
  --accent-text: #0369a1;
  padding: 20px;
  background: var(--bg);
  color: var(--text-main);
  border-radius: 8px;
  font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans", "Noto Sans JP", sans-serif;
  box-sizing: border-box;
}
[data-theme="dark"] .exp1-wrap {
  --bg: #0f172a;
  --card-bg: #1e293b;
  --text-main: #f1f5f9;
  --text-sub: #94a3b8;
  --border: #334155;
  --accent: #38bdf8;
  --accent-soft: #0c4a6e;
  --accent-text: #7dd3fc;
}
.exp1-steps {
  display: flex;
  align-items: stretch;
  justify-content: space-between;
  gap: 8px;
}
.exp1-arrow::before {
  content: "→";
}
@media (max-width: 640px) {
  .exp1-steps {
    flex-direction: column;
  }
  .exp1-arrow::before {
    content: "↓";
  }
}
```
:::

---

# 実験 2：CSS アニメーション＋インライン SVG で「パケットが流れる構成図」

外部画像 URL を使わずにインライン `<svg>` でベクターアイコンを描き、CSS `@keyframes` で光の粒（パケット）が伝播していくアニメーションを実装しています。

### 埋め込み表示結果

```html-embed
<div class="exp2-arch">
  <div class="exp2-title">イベント駆動マイクロサービスのデータフロー（リアルタイムアニメーション）</div>
  <div class="exp2-flow">
    <!-- Client -->
    <div class="exp2-node exp2-n1">
      <svg class="exp2-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
        <rect x="3" y="4" width="18" height="12" rx="2"/>
        <path d="M2 20h20M12 16v4"/>
      </svg>
      <div class="exp2-label">Web Client</div>
      <div class="exp2-sub">HTTPS POST</div>
    </div>

    <div class="exp2-edge exp2-e1" aria-hidden="true"><i></i></div>

    <!-- API Gateway -->
    <div class="exp2-node exp2-n2">
      <svg class="exp2-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
        <path d="M12 2L2 7l10 5 10-5-10-5z"/>
        <path d="M2 17l10 5 10-5M2 12l10 5 10-5"/>
      </svg>
      <div class="exp2-label">API Gateway</div>
      <div class="exp2-sub">Rate Limit / Auth</div>
    </div>

    <div class="exp2-edge exp2-e2" aria-hidden="true"><i></i></div>

    <!-- Message Queue -->
    <div class="exp2-cluster">
      <div class="exp2-cluster-head">Async Worker Cluster</div>
      <div class="exp2-cluster-body">
        <div class="exp2-node exp2-n3">
          <svg class="exp2-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M4 6h16M4 12h16M4 18h16"/>
          </svg>
          <div class="exp2-label">Queue</div>
          <div class="exp2-sub">Pub/Sub</div>
        </div>

        <div class="exp2-edge exp2-e3" aria-hidden="true"><i></i></div>

        <div class="exp2-node exp2-n4">
          <svg class="exp2-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <ellipse cx="12" cy="5" rx="9" ry="3"/>
            <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/>
            <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>
          </svg>
          <div class="exp2-label">Analytics DB</div>
          <div class="exp2-sub">Batch Insert</div>
        </div>
      </div>
    </div>
  </div>
</div>
<style>
  .exp2-arch {
    --bg: #f0f7ff;
    --card: #ffffff;
    --text: #1e293b;
    --sub: #64748b;
    --line: #3ea8ff;
    --border: #cbd5e1;
    --cluster-bg: rgba(255, 255, 255, 0.65);
    padding: 20px;
    background: var(--bg);
    color: var(--text);
    border-radius: 10px;
    font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans", "Noto Sans JP", sans-serif;
    box-sizing: border-box;
  }
  [data-theme="dark"] .exp2-arch {
    --bg: #0b192c;
    --card: #1e293b;
    --text: #f8fafc;
    --sub: #94a3b8;
    --line: #38bdf8;
    --border: #334155;
    --cluster-bg: rgba(15, 23, 42, 0.6);
  }
  .exp2-title {
    font-size: 13px;
    font-weight: 700;
    color: var(--sub);
    margin-bottom: 16px;
    text-align: center;
  }
  .exp2-flow {
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .exp2-cluster {
    border: 1px dashed var(--line);
    border-radius: 12px;
    background: var(--cluster-bg);
    overflow: hidden;
  }
  .exp2-cluster-head {
    font-size: 12px;
    font-weight: 700;
    padding: 6px 12px;
    background: rgba(62, 168, 255, 0.12);
    color: var(--line);
    border-bottom: 1px dashed var(--line);
    text-align: center;
  }
  .exp2-cluster-body {
    display: flex;
    align-items: center;
    padding: 14px;
  }
  .exp2-node {
    width: 110px;
    min-height: 96px;
    padding: 12px 8px;
    box-sizing: border-box;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 10px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 4px;
    text-align: center;
    box-shadow: 0 2px 6px rgba(62, 168, 255, 0.12);
    animation: exp2-pulse 3.6s infinite;
  }
  .exp2-icon {
    width: 28px;
    height: 28px;
    color: var(--line);
    margin-bottom: 2px;
  }
  .exp2-label {
    font-size: 12px;
    font-weight: 700;
    line-height: 1.25;
  }
  .exp2-sub {
    font-size: 12px;
    color: var(--sub);
  }
  .exp2-edge {
    position: relative;
    width: 34px;
    height: 2px;
    background: var(--line);
    flex-shrink: 0;
  }
  .exp2-edge::after {
    content: "";
    position: absolute;
    right: -2px;
    top: -4px;
    border: 5px solid transparent;
    border-left: 7px solid var(--line);
    border-right: 0;
  }
  .exp2-edge i {
    position: absolute;
    top: -3px;
    left: 0;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #ffffff;
    box-shadow: 0 0 6px 3px var(--line);
    opacity: 0;
    animation: exp2-run-x 3.6s infinite;
  }
  .exp2-n1 { animation-delay: 0s; }
  .exp2-e1 i { animation-delay: 0.3s; }
  .exp2-n2 { animation-delay: 0.9s; }
  .exp2-e2 i { animation-delay: 1.2s; }
  .exp2-n3 { animation-delay: 1.8s; }
  .exp2-e3 i { animation-delay: 2.1s; }
  .exp2-n4 { animation-delay: 2.7s; }

  @keyframes exp2-run-x {
    0% { left: 0; opacity: 0; }
    5% { opacity: 1; }
    22% { left: calc(100% - 8px); opacity: 1; }
    27%, 100% { left: calc(100% - 8px); opacity: 0; }
  }
  @keyframes exp2-pulse {
    0%, 100% { box-shadow: 0 2px 6px rgba(62, 168, 255, 0.12); transform: translateY(0); }
    10% { box-shadow: 0 0 0 3px rgba(62, 168, 255, 0.45), 0 4px 12px rgba(62, 168, 255, 0.35); transform: translateY(-2px); }
    25% { box-shadow: 0 2px 6px rgba(62, 168, 255, 0.12); transform: translateY(0); }
  }

  @media (max-width: 640px) {
    .exp2-flow, .exp2-cluster-body {
      flex-direction: column;
    }
    .exp2-node {
      width: 210px;
      min-height: 0;
      flex-direction: row;
      justify-content: flex-start;
      padding: 8px 12px;
      gap: 10px;
      text-align: left;
    }
    .exp2-edge {
      width: 2px;
      height: 22px;
    }
    .exp2-edge::after {
      right: -4px;
      top: auto;
      bottom: -2px;
      border: 5px solid transparent;
      border-top: 7px solid var(--line);
      border-bottom: 0;
    }
    .exp2-edge i {
      left: -3px;
      animation-name: exp2-run-y;
    }
    @keyframes exp2-run-y {
      0% { top: 0; opacity: 0; }
      5% { opacity: 1; }
      22% { top: calc(100% - 8px); opacity: 1; }
      27%, 100% { top: calc(100% - 8px); opacity: 0; }
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .exp2-node, .exp2-edge i {
      animation: none;
    }
  }
</style>
```

### 使用した HTML 構造

```html
<div class="exp2-arch">
  <div class="exp2-title">イベント駆動マイクロサービスのデータフロー（リアルタイムアニメーション）</div>
  <div class="exp2-flow">
    <!-- Web Client -->
    <div class="exp2-node exp2-n1">
      <svg class="exp2-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
        <rect x="3" y="4" width="18" height="12" rx="2"/>
        <path d="M2 20h20M12 16v4"/>
      </svg>
      <div class="exp2-label">Web Client</div>
      <div class="exp2-sub">HTTPS POST</div>
    </div>

    <!-- 矢印 + 光の粒 <i> -->
    <div class="exp2-edge exp2-e1" aria-hidden="true"><i></i></div>

    <!-- API Gateway -->
    <div class="exp2-node exp2-n2">
      <svg class="exp2-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
        <path d="M12 2L2 7l10 5 10-5-10-5z"/>
        <path d="M2 17l10 5 10-5M2 12l10 5 10-5"/>
      </svg>
      <div class="exp2-label">API Gateway</div>
      <div class="exp2-sub">Rate Limit / Auth</div>
    </div>

    <div class="exp2-edge exp2-e2" aria-hidden="true"><i></i></div>

    <!-- クラスター囲み枠 -->
    <div class="exp2-cluster">
      <div class="exp2-cluster-head">Async Worker Cluster</div>
      <div class="exp2-cluster-body">
        <div class="exp2-node exp2-n3">
          <svg class="exp2-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M4 6h16M4 12h16M4 18h16"/>
          </svg>
          <div class="exp2-label">Queue</div>
          <div class="exp2-sub">Pub/Sub</div>
        </div>

        <div class="exp2-edge exp2-e3" aria-hidden="true"><i></i></div>

        <div class="exp2-node exp2-n4">
          <svg class="exp2-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <ellipse cx="12" cy="5" rx="9" ry="3"/>
            <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/>
            <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>
          </svg>
          <div class="exp2-label">Analytics DB</div>
          <div class="exp2-sub">Batch Insert</div>
        </div>
      </div>
    </div>
  </div>
</div>
```

:::details アニメーション制御の CSS を見る
```css
/* 矢印ライン */
.exp2-edge {
  position: relative;
  width: 34px;
  height: 2px;
  background: var(--line);
}
/* 光の粒 */
.exp2-edge i {
  position: absolute;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #ffffff;
  box-shadow: 0 0 6px 3px var(--line);
  animation: exp2-run-x 3.6s infinite;
}
/* 左から順番に遅延実行 */
.exp2-n1 { animation-delay: 0s; }
.exp2-e1 i { animation-delay: 0.3s; }
.exp2-n2 { animation-delay: 0.9s; }
.exp2-e2 i { animation-delay: 1.2s; }
.exp2-n3 { animation-delay: 1.8s; }
.exp2-e3 i { animation-delay: 2.1s; }
.exp2-n4 { animation-delay: 2.7s; }
```
:::

---

# 実験 3：JavaScript なし！`<input type="radio">` + `:checked` で動くインタラクティブ・タブ図解

`html-embed` では `<script>` は動きませんが、`<input type="radio">` と `<label>` を組み合わせることで JS ゼロのタブ切り替え図解を実現できます。タブをクリックして表示が切り替わることを確認できます。

### 埋め込み表示結果

```html-embed
<div class="exp3-tabs">
  <input type="radio" name="render-mode" id="tab-ssr" checked>
  <input type="radio" name="render-mode" id="tab-csr">
  <input type="radio" name="render-mode" id="tab-ssg">

  <div class="exp3-nav" role="tablist">
    <label for="tab-ssr" class="exp3-tab-label">SSR (Server-Side Rendering)</label>
    <label for="tab-csr" class="exp3-tab-label">CSR (Client-Side Rendering)</label>
    <label for="tab-ssg" class="exp3-tab-label">SSG (Static Site Generation)</label>
  </div>

  <!-- SSR Panel -->
  <div class="exp3-panel exp3-panel-ssr">
    <div class="exp3-diagram">
      <div class="exp3-box">Browser<small>リクエスト送信</small></div>
      <div class="exp3-arr">→</div>
      <div class="exp3-box exp3-highlight">Node / Edge Server<small>データ取得＋HTML生成</small></div>
      <div class="exp3-arr">→</div>
      <div class="exp3-box">Browser<small>完成済みHTML表示＋Hydration</small></div>
    </div>
    <div class="exp3-meta">
      <div class="exp3-metric"><span class="exp3-k">初回表示 (FCP)</span><span class="exp3-v exp3-good">速い（HTML到着時）</span></div>
      <div class="exp3-metric"><span class="exp3-k">動的データ</span><span class="exp3-v exp3-good">リクエストごとに最新</span></div>
      <div class="exp3-metric"><span class="exp3-k">サーバー負荷</span><span class="exp3-v exp3-warn">アクセス数に比例</span></div>
    </div>
  </div>

  <!-- CSR Panel -->
  <div class="exp3-panel exp3-panel-csr">
    <div class="exp3-diagram">
      <div class="exp3-box">CDN<small>空のHTML＋JSバンドル配信</small></div>
      <div class="exp3-arr">→</div>
      <div class="exp3-box exp3-highlight">Browser (JS実行)<small>APIフェッチ＋DOM構築</small></div>
      <div class="exp3-arr">→</div>
      <div class="exp3-box">Browser<small>画面レンダリング完了</small></div>
    </div>
    <div class="exp3-meta">
      <div class="exp3-metric"><span class="exp3-k">初回表示 (FCP)</span><span class="exp3-v exp3-warn">JS実行まで空白/スケルトン</span></div>
      <div class="exp3-metric"><span class="exp3-k">画面遷移後</span><span class="exp3-v exp3-good">SPAとして高速に動作</span></div>
      <div class="exp3-metric"><span class="exp3-k">サーバー負荷</span><span class="exp3-v exp3-good">静的配信＋APIのみ</span></div>
    </div>
  </div>

  <!-- SSG Panel -->
  <div class="exp3-panel exp3-panel-ssg">
    <div class="exp3-diagram">
      <div class="exp3-box exp3-highlight">Build Time (CI/CD)<small>全ページのHTMLを事前生成</small></div>
      <div class="exp3-arr">→</div>
      <div class="exp3-box">Edge CDN<small>エッジにキャッシュ配置</small></div>
      <div class="exp3-arr">→</div>
      <div class="exp3-box">Browser<small>最速でHTMLを受信・表示</small></div>
    </div>
    <div class="exp3-meta">
      <div class="exp3-metric"><span class="exp3-k">初回表示 (FCP)</span><span class="exp3-v exp3-good">最速（CDNエッジ応答）</span></div>
      <div class="exp3-metric"><span class="exp3-k">動的データ</span><span class="exp3-v exp3-warn">ビルド時点のデータに固定</span></div>
      <div class="exp3-metric"><span class="exp3-k">サーバー負荷</span><span class="exp3-v exp3-good">最小（オリジン不要）</span></div>
    </div>
  </div>
</div>
<style>
  .exp3-tabs {
    --bg: #f8fafc;
    --surface: #ffffff;
    --border: #cbd5e1;
    --text: #0f172a;
    --sub: #64748b;
    --accent: #2563eb;
    --accent-bg: #eff6ff;
    background: var(--bg);
    color: var(--text);
    padding: 16px;
    border-radius: 10px;
    font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans", "Noto Sans JP", sans-serif;
    box-sizing: border-box;
  }
  [data-theme="dark"] .exp3-tabs {
    --bg: #0f172a;
    --surface: #1e293b;
    --border: #334155;
    --text: #f8fafc;
    --sub: #94a3b8;
    --accent: #60a5fa;
    --accent-bg: #1e3a8a;
  }
  .exp3-tabs > input[type="radio"] {
    position: absolute;
    opacity: 0;
    pointer-events: none;
  }
  .exp3-nav {
    display: flex;
    gap: 6px;
    margin-bottom: 14px;
    border-bottom: 1px solid var(--border);
    padding-bottom: 10px;
    flex-wrap: wrap;
  }
  .exp3-tab-label {
    padding: 7px 14px;
    font-size: 12px;
    font-weight: 700;
    border-radius: 8px;
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--sub);
    cursor: pointer;
    user-select: none;
    transition: all 0.15s ease;
  }
  .exp3-tab-label:hover {
    border-color: var(--accent);
    color: var(--text);
  }
  #tab-ssr:checked ~ .exp3-nav label[for="tab-ssr"],
  #tab-csr:checked ~ .exp3-nav label[for="tab-csr"],
  #tab-ssg:checked ~ .exp3-nav label[for="tab-ssg"] {
    background: var(--accent);
    color: #ffffff;
    border-color: var(--accent);
  }
  .exp3-panel {
    display: none;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 16px;
  }
  #tab-ssr:checked ~ .exp3-panel-ssr,
  #tab-csr:checked ~ .exp3-panel-csr,
  #tab-ssg:checked ~ .exp3-panel-ssg {
    display: block;
  }
  .exp3-diagram {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 14px;
  }
  .exp3-box {
    flex: 1;
    padding: 12px;
    border-radius: 8px;
    border: 1px solid var(--border);
    text-align: center;
    font-size: 13px;
    font-weight: 700;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .exp3-box small {
    font-size: 12px;
    font-weight: 400;
    color: var(--sub);
  }
  .exp3-highlight {
    border: 2px solid var(--accent);
    background: var(--accent-bg);
  }
  .exp3-arr {
    font-size: 18px;
    font-weight: 700;
    color: var(--accent);
  }
  .exp3-meta {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
    border-top: 1px solid var(--border);
    padding-top: 12px;
  }
  .exp3-metric {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .exp3-k {
    font-size: 12px;
    color: var(--sub);
  }
  .exp3-v {
    font-size: 12px;
    font-weight: 700;
  }
  .exp3-good { color: #16a34a; }
  .exp3-warn { color: #d97706; }
  [data-theme="dark"] .exp3-good { color: #4ade80; }
  [data-theme="dark"] .exp3-warn { color: #fbbf24; }

  @media (max-width: 640px) {
    .exp3-diagram {
      flex-direction: column;
    }
    .exp3-box {
      width: 100%;
      box-sizing: border-box;
    }
    .exp3-arr {
      transform: rotate(90deg);
    }
    .exp3-meta {
      grid-template-columns: 1fr;
    }
  }
</style>
```

### 使用した HTML 構造

```html
<div class="exp3-tabs">
  <!-- 状態を保持する非表示のラジオボタン群 -->
  <input type="radio" name="render-mode" id="tab-ssr" checked>
  <input type="radio" name="render-mode" id="tab-csr">
  <input type="radio" name="render-mode" id="tab-ssg">

  <!-- クリック可能なタブナビゲーション (<label>) -->
  <div class="exp3-nav" role="tablist">
    <label for="tab-ssr" class="exp3-tab-label">SSR (Server-Side Rendering)</label>
    <label for="tab-csr" class="exp3-tab-label">CSR (Client-Side Rendering)</label>
    <label for="tab-ssg" class="exp3-tab-label">SSG (Static Site Generation)</label>
  </div>

  <!-- 各タブに対応するパネル -->
  <div class="exp3-panel exp3-panel-ssr">...</div>
  <div class="exp3-panel exp3-panel-csr">...</div>
  <div class="exp3-panel exp3-panel-ssg">...</div>
</div>
```

:::details 切り替えの CSS テクニック
```css
/* ラジオボタン自体は画面から隠す */
.exp3-tabs > input[type="radio"] {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}

/* 選択されたタブのラベルスタイル */
#tab-ssr:checked ~ .exp3-nav label[for="tab-ssr"] {
  background: var(--accent);
  color: #ffffff;
}

/* 選択されたラジオボタンと一致するパネルだけを表示 */
.exp3-panel { display: none; }
#tab-ssr:checked ~ .exp3-panel-ssr { display: block; }
#tab-csr:checked ~ .exp3-panel-csr { display: block; }
#tab-ssg:checked ~ .exp3-panel-ssg { display: block; }
```
:::

---

# 実験 4：`<input type="checkbox">` トグルスイッチで「障害時のフェイルオーバー経路」をシミュレートする

`<input type="checkbox">` の ON / OFF をスイッチ UI として装飾し、平常時と DB 障害時のルーティング切替をシミュレートします。

### 埋め込み表示結果

```html-embed
<div class="exp4-sim">
  <input type="checkbox" id="failover-toggle">

  <div class="exp4-toolbar">
    <div class="exp4-status">
      <span class="exp4-dot"></span>
      <span class="exp4-status-normal">現在: 平常運転（Primary DB へ接続中）</span>
      <span class="exp4-status-fail">現在: フェイルオーバー発動！（Standby DB へ昇格・切替中）</span>
    </div>
    <label for="failover-toggle" class="exp4-switch">
      <span class="exp4-switch-track"><span class="exp4-switch-thumb"></span></span>
      <span class="exp4-switch-text">Primary 障害をシミュレート</span>
    </label>
  </div>

  <div class="exp4-grid">
    <div class="exp4-app">
      <div class="exp4-box-title">Application Pool</div>
      <div class="exp4-box-sub">Connection Router</div>
    </div>

    <div class="exp4-routes">
      <!-- Route to Primary -->
      <div class="exp4-route exp4-route-pri">
        <div class="exp4-line exp4-line-pri">
          <span class="exp4-line-label exp4-label-active">Read / Write (Active)</span>
          <span class="exp4-line-label exp4-label-down">✕ Connection Timeout</span>
        </div>
        <div class="exp4-db exp4-db-pri">
          <div class="exp4-db-head">
            <span>Primary DB (ap-northeast-1a)</span>
            <span class="exp4-badge-ok">HEALTHY</span>
            <span class="exp4-badge-ng">DOWN</span>
          </div>
          <div class="exp4-db-desc">通常時はすべての書き込みと読み取りを処理</div>
        </div>
      </div>

      <!-- Route to Standby -->
      <div class="exp4-route exp4-route-std">
        <div class="exp4-line exp4-line-std">
          <span class="exp4-line-label exp4-label-idle">Sync Replication (Standby)</span>
          <span class="exp4-line-label exp4-label-promoted">⚡ Promoted! Read / Write</span>
        </div>
        <div class="exp4-db exp4-db-std">
          <div class="exp4-db-head">
            <span>Standby DB (ap-northeast-1c)</span>
            <span class="exp4-badge-std">STANDBY</span>
            <span class="exp4-badge-pro">ACTIVE (PROMOTED)</span>
          </div>
          <div class="exp4-db-desc">障害検知時に自動で Primary に昇格して通信を引き継ぐ</div>
        </div>
      </div>
    </div>
  </div>
</div>
<style>
  .exp4-sim {
    --bg: #f8fafc;
    --card: #ffffff;
    --border: #cbd5e1;
    --text: #0f172a;
    --sub: #64748b;
    --ok: #16a34a;
    --ok-bg: #dcfce7;
    --ng: #dc2626;
    --ng-bg: #fee2e2;
    padding: 16px;
    background: var(--bg);
    color: var(--text);
    border-radius: 10px;
    font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans", "Noto Sans JP", sans-serif;
    box-sizing: border-box;
  }
  [data-theme="dark"] .exp4-sim {
    --bg: #0f172a;
    --card: #1e293b;
    --border: #334155;
    --text: #f8fafc;
    --sub: #94a3b8;
    --ok: #4ade80;
    --ok-bg: #14532d;
    --ng: #f87171;
    --ng-bg: #7f1d1d;
  }
  #failover-toggle {
    position: absolute;
    opacity: 0;
    pointer-events: none;
  }
  .exp4-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding-bottom: 12px;
    margin-bottom: 14px;
    border-bottom: 1px solid var(--border);
    flex-wrap: wrap;
  }
  .exp4-status {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    font-weight: 700;
  }
  .exp4-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: var(--ok);
    box-shadow: 0 0 0 3px var(--ok-bg);
  }
  .exp4-status-fail { display: none; color: var(--ng); }
  #failover-toggle:checked ~ .exp4-toolbar .exp4-dot {
    background: var(--ng);
    box-shadow: 0 0 0 3px var(--ng-bg);
  }
  #failover-toggle:checked ~ .exp4-toolbar .exp4-status-normal { display: none; }
  #failover-toggle:checked ~ .exp4-toolbar .exp4-status-fail { display: inline; }

  .exp4-switch {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
    user-select: none;
    font-size: 12px;
    font-weight: 700;
    padding: 6px 10px;
    border-radius: 8px;
    border: 1px solid var(--border);
    background: var(--card);
  }
  .exp4-switch-track {
    width: 34px;
    height: 18px;
    background: #94a3b8;
    border-radius: 999px;
    position: relative;
    transition: background 0.2s;
  }
  .exp4-switch-thumb {
    width: 14px;
    height: 14px;
    background: #ffffff;
    border-radius: 50%;
    position: absolute;
    top: 2px;
    left: 2px;
    transition: transform 0.2s;
  }
  #failover-toggle:checked ~ .exp4-toolbar .exp4-switch-track {
    background: #ef4444;
  }
  #failover-toggle:checked ~ .exp4-toolbar .exp4-switch-thumb {
    transform: translateX(16px);
  }

  .exp4-grid {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .exp4-app {
    width: 140px;
    padding: 16px 12px;
    background: var(--card);
    border: 2px solid #3ea8ff;
    border-radius: 10px;
    text-align: center;
    flex-shrink: 0;
  }
  .exp4-box-title { font-size: 13px; font-weight: 700; }
  .exp4-box-sub { font-size: 12px; color: var(--sub); margin-top: 4px; }

  .exp4-routes {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .exp4-route {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .exp4-line {
    width: 140px;
    padding: 6px 8px;
    border-bottom: 3px solid var(--ok);
    text-align: center;
    font-size: 12px;
    font-weight: 700;
    flex-shrink: 0;
    transition: all 0.2s;
  }
  .exp4-line-std {
    border-bottom: 2px dashed var(--sub);
    color: var(--sub);
  }
  .exp4-label-down, .exp4-label-promoted, .exp4-badge-ng, .exp4-badge-pro {
    display: none;
  }
  .exp4-db {
    flex: 1;
    padding: 12px;
    background: var(--card);
    border: 2px solid var(--ok);
    border-radius: 10px;
    transition: all 0.2s;
  }
  .exp4-db-std {
    border: 1px dashed var(--border);
    opacity: 0.75;
  }
  .exp4-db-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 6px;
    font-size: 13px;
    font-weight: 700;
    margin-bottom: 4px;
    flex-wrap: wrap;
  }
  .exp4-db-desc {
    font-size: 12px;
    color: var(--sub);
  }
  .exp4-badge-ok, .exp4-badge-pro {
    font-size: 12px;
    padding: 2px 8px;
    border-radius: 999px;
    background: var(--ok-bg);
    color: var(--ok);
  }
  .exp4-badge-ng {
    font-size: 12px;
    padding: 2px 8px;
    border-radius: 999px;
    background: var(--ng-bg);
    color: var(--ng);
  }
  .exp4-badge-std {
    font-size: 12px;
    padding: 2px 8px;
    border-radius: 999px;
    background: var(--border);
    color: var(--text);
  }

  /* Failover Checked State */
  #failover-toggle:checked ~ .exp4-grid .exp4-line-pri {
    border-bottom: 2px dashed var(--ng);
    color: var(--ng);
  }
  #failover-toggle:checked ~ .exp4-grid .exp4-label-active { display: none; }
  #failover-toggle:checked ~ .exp4-grid .exp4-label-down { display: inline; }

  #failover-toggle:checked ~ .exp4-grid .exp4-db-pri {
    border-color: var(--ng);
    opacity: 0.6;
  }
  #failover-toggle:checked ~ .exp4-grid .exp4-badge-ok { display: none; }
  #failover-toggle:checked ~ .exp4-grid .exp4-badge-ng { display: inline-block; }

  #failover-toggle:checked ~ .exp4-grid .exp4-line-std {
    border-bottom: 3px solid var(--ok);
    color: var(--ok);
  }
  #failover-toggle:checked ~ .exp4-grid .exp4-label-idle { display: none; }
  #failover-toggle:checked ~ .exp4-grid .exp4-label-promoted { display: inline; }

  #failover-toggle:checked ~ .exp4-grid .exp4-db-std {
    border: 2px solid var(--ok);
    opacity: 1;
    box-shadow: 0 0 0 3px var(--ok-bg);
  }
  #failover-toggle:checked ~ .exp4-grid .exp4-badge-std { display: none; }
  #failover-toggle:checked ~ .exp4-grid .exp4-badge-pro { display: inline-block; }

  @media (max-width: 640px) {
    .exp4-grid, .exp4-route {
      flex-direction: column;
      align-items: stretch;
    }
    .exp4-app, .exp4-line {
      width: 100%;
      box-sizing: border-box;
    }
  }
</style>
```

### 使用した HTML 構造

```html
<div class="exp4-sim">
  <!-- 状態を保持するチェックボックス -->
  <input type="checkbox" id="failover-toggle">

  <div class="exp4-toolbar">
    <div class="exp4-status">
      <span class="exp4-dot"></span>
      <span class="exp4-status-normal">現在: 平常運転（Primary DB へ接続中）</span>
      <span class="exp4-status-fail">現在: フェイルオーバー発動！（Standby DB へ昇格・切替中）</span>
    </div>

    <!-- スイッチ風に装飾する label -->
    <label for="failover-toggle" class="exp4-switch">
      <span class="exp4-switch-track"><span class="exp4-switch-thumb"></span></span>
      <span class="exp4-switch-text">Primary 障害をシミュレート</span>
    </label>
  </div>

  <div class="exp4-grid">
    <div class="exp4-app">
      <div class="exp4-box-title">Application Pool</div>
      <div class="exp4-box-sub">Connection Router</div>
    </div>

    <div class="exp4-routes">
      <!-- 通常系 (Primary) ルート -->
      <div class="exp4-route exp4-route-pri">
        <div class="exp4-line exp4-line-pri">
          <span class="exp4-label-active">Read / Write (Active)</span>
          <span class="exp4-label-down">✕ Connection Timeout</span>
        </div>
        <div class="exp4-db exp4-db-pri">...</div>
      </div>

      <!-- 待機系 (Standby) ルート -->
      <div class="exp4-route exp4-route-std">
        <div class="exp4-line exp4-line-std">
          <span class="exp4-label-idle">Sync Replication (Standby)</span>
          <span class="exp4-label-promoted">⚡ Promoted! Read / Write</span>
        </div>
        <div class="exp4-db exp4-db-std">...</div>
      </div>
    </div>
  </div>
</div>
```

:::details トグル切替時の CSS 挙動
```css
/* チェックボックスの ON 時、平常テキストを非表示にして障害時テキストを表示 */
#failover-toggle:checked ~ .exp4-toolbar .exp4-status-normal { display: none; }
#failover-toggle:checked ~ .exp4-toolbar .exp4-status-fail { display: inline; }

/* トグルスイッチのつまみを右に移動し背景色を赤へ */
#failover-toggle:checked ~ .exp4-toolbar .exp4-switch-track { background: #ef4444; }
#failover-toggle:checked ~ .exp4-toolbar .exp4-switch-thumb { transform: translateX(16px); }

/* Standby DB のボーダーをアクティブ色に変更 */
#failover-toggle:checked ~ .exp4-grid .exp4-db-std {
  border: 2px solid var(--ok);
  box-shadow: 0 0 0 3px var(--ok-bg);
}
```
:::

---

# 実験 5：Markdown テーブルでは表現できない「棒グラフ＆バッジ付きベンチマーク比較表」

通常の Markdown テーブルでは入れられない横棒グラフ（バーチャート）やハイライトバッジを組み込み、視覚的に結果がわかるベンチマーク表を作っています。

### 埋め込み表示結果

```html-embed
<div class="exp5-bench">
  <div class="exp5-head">
    <div class="exp5-title">Vitest DOM 環境の実行時間比較（短いほど高速）</div>
    <div class="exp5-legend">
      <span class="exp5-leg-item"><i class="exp5-dot-jsdom"></i>jsdom (31.0.0)</span>
      <span class="exp5-leg-item"><i class="exp5-dot-wasm"></i>wasm-quickjs-dom (1.0.17)</span>
    </div>
  </div>

  <div class="exp5-rows">
    <!-- Metric 1 -->
    <div class="exp5-row">
      <div class="exp5-metric-info">
        <span class="exp5-metric-name">1ファイルあたりの環境起動コスト</span>
        <span class="exp5-speedup">約 6.1 倍高速</span>
      </div>
      <div class="exp5-bars">
        <div class="exp5-bar-line">
          <span class="exp5-env">jsdom</span>
          <div class="exp5-track"><div class="exp5-fill exp5-fill-jsdom" style="width: 100%;"></div></div>
          <span class="exp5-val">1,151.1 ms</span>
        </div>
        <div class="exp5-bar-line">
          <span class="exp5-env">wasm</span>
          <div class="exp5-track"><div class="exp5-fill exp5-fill-wasm" style="width: 16.3%;"></div></div>
          <span class="exp5-val exp5-val-win">187.3 ms</span>
        </div>
      </div>
    </div>

    <!-- Metric 2 -->
    <div class="exp5-row">
      <div class="exp5-metric-info">
        <span class="exp5-metric-name">テストスイート全体（並列 / 93件）</span>
        <span class="exp5-speedup">約 31% 短縮</span>
      </div>
      <div class="exp5-bars">
        <div class="exp5-bar-line">
          <span class="exp5-env">jsdom</span>
          <div class="exp5-track"><div class="exp5-fill exp5-fill-jsdom" style="width: 100%;"></div></div>
          <span class="exp5-val">4,699.5 ms</span>
        </div>
        <div class="exp5-bar-line">
          <span class="exp5-env">wasm</span>
          <div class="exp5-track"><div class="exp5-fill exp5-fill-wasm" style="width: 69.2%;"></div></div>
          <span class="exp5-val exp5-val-win">3,251.4 ms</span>
        </div>
      </div>
    </div>

    <!-- Metric 3 -->
    <div class="exp5-row">
      <div class="exp5-metric-info">
        <span class="exp5-metric-name">テストスイート全体（直列 1 worker / 93件）</span>
        <span class="exp5-speedup">約 45% 短縮</span>
      </div>
      <div class="exp5-bars">
        <div class="exp5-bar-line">
          <span class="exp5-env">jsdom</span>
          <div class="exp5-track"><div class="exp5-fill exp5-fill-jsdom" style="width: 100%;"></div></div>
          <span class="exp5-val">24,053.1 ms</span>
        </div>
        <div class="exp5-bar-line">
          <span class="exp5-env">wasm</span>
          <div class="exp5-track"><div class="exp5-fill exp5-fill-wasm" style="width: 54.5%;"></div></div>
          <span class="exp5-val exp5-val-win">13,113.3 ms</span>
        </div>
      </div>
    </div>
  </div>
</div>
<style>
  .exp5-bench {
    --bg: #f8fafc;
    --card: #ffffff;
    --border: #e2e8f0;
    --text: #0f172a;
    --sub: #64748b;
    --track: #f1f5f9;
    --jsdom: #94a3b8;
    --wasm: #3ea8ff;
    padding: 18px;
    background: var(--bg);
    color: var(--text);
    border-radius: 10px;
    font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans", "Noto Sans JP", sans-serif;
    box-sizing: border-box;
  }
  [data-theme="dark"] .exp5-bench {
    --bg: #0f172a;
    --card: #1e293b;
    --border: #334155;
    --text: #f8fafc;
    --sub: #94a3b8;
    --track: #0f172a;
    --jsdom: #64748b;
    --wasm: #38bdf8;
  }
  .exp5-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    margin-bottom: 14px;
    flex-wrap: wrap;
  }
  .exp5-title {
    font-size: 14px;
    font-weight: 700;
  }
  .exp5-legend {
    display: flex;
    gap: 12px;
    font-size: 12px;
    color: var(--sub);
  }
  .exp5-leg-item {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .exp5-dot-jsdom, .exp5-dot-wasm {
    width: 10px;
    height: 10px;
    border-radius: 3px;
    display: inline-block;
  }
  .exp5-dot-jsdom { background: var(--jsdom); }
  .exp5-dot-wasm { background: var(--wasm); }

  .exp5-rows {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .exp5-row {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px 14px;
  }
  .exp5-metric-info {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 8px;
    flex-wrap: wrap;
  }
  .exp5-metric-name {
    font-size: 13px;
    font-weight: 700;
  }
  .exp5-speedup {
    font-size: 12px;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 999px;
    background: rgba(62, 168, 255, 0.15);
    color: var(--wasm);
  }
  .exp5-bars {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .exp5-bar-line {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .exp5-env {
    width: 44px;
    font-size: 12px;
    font-weight: 600;
    color: var(--sub);
    flex-shrink: 0;
  }
  .exp5-track {
    flex: 1;
    height: 12px;
    background: var(--track);
    border-radius: 6px;
    overflow: hidden;
  }
  .exp5-fill {
    height: 100%;
    border-radius: 6px;
  }
  .exp5-fill-jsdom { background: var(--jsdom); }
  .exp5-fill-wasm { background: linear-gradient(90deg, #3ea8ff, #2563eb); }
  .exp5-val {
    width: 82px;
    text-align: right;
    font-size: 12px;
    font-variant-numeric: tabular-nums;
    color: var(--sub);
    flex-shrink: 0;
  }
  .exp5-val-win {
    font-weight: 700;
    color: var(--text);
  }
</style>
```

### 使用した HTML 構造

```html
<div class="exp5-bench">
  <div class="exp5-head">
    <div class="exp5-title">Vitest DOM 環境の実行時間比較（短いほど高速）</div>
    <div class="exp5-legend">
      <span class="exp5-leg-item"><i class="exp5-dot-jsdom"></i>jsdom (31.0.0)</span>
      <span class="exp5-leg-item"><i class="exp5-dot-wasm"></i>wasm-quickjs-dom (1.0.17)</span>
    </div>
  </div>

  <div class="exp5-rows">
    <div class="exp5-row">
      <div class="exp5-metric-info">
        <span class="exp5-metric-name">1ファイルあたりの環境起動コスト</span>
        <span class="exp5-speedup">約 6.1 倍高速</span>
      </div>
      <div class="exp5-bars">
        <div class="exp5-bar-line">
          <span class="exp5-env">jsdom</span>
          <div class="exp5-track"><div class="exp5-fill exp5-fill-jsdom" style="width: 100%;"></div></div>
          <span class="exp5-val">1,151.1 ms</span>
        </div>
        <div class="exp5-bar-line">
          <span class="exp5-env">wasm</span>
          <div class="exp5-track"><div class="exp5-fill exp5-fill-wasm" style="width: 16.3%;"></div></div>
          <span class="exp5-val exp5-val-win">187.3 ms</span>
        </div>
      </div>
    </div>
    <!-- 他のメトリクス行も同様の構成 -->
  </div>
</div>
```

:::details CSS スタイルを見る
```css
/* 棒グラフのレールとバー */
.exp5-track {
  flex: 1;
  height: 12px;
  background: var(--track);
  border-radius: 6px;
  overflow: hidden;
}
.exp5-fill-wasm {
  background: linear-gradient(90deg, #3ea8ff, #2563eb);
}
/* 数値の桁幅を揃える */
.exp5-val {
  width: 82px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
```
:::

---

# 実験してわかった実践テクニックと注意点

一通り `html-embed` でいろいろな図を作って試してみて、押さえておくと良さそうなポイントをまとめます。

## 1. ダークモード対応は「CSS変数」または `light-dark()` が快適

Zenn の Markdown 記法一覧によると、ダークモード時の切り替え方法は次の 3 通りがサポートされています。

1. `[data-theme="dark"]` セレクタで切り替える
2. CSS の `light-dark()` 関数で切り替える（例：`background: light-dark(#eaf6ff, #1a2f3f);`）
3. テーマごとの `<style>` タグを書く（`<style data-theme="light">` と `<style data-theme="dark">`）

要素数が多い図解では、ルート要素に `--bg`, `--card`, `--text`, `--border` などの CSS カスタムプロパティを定義しておき、`[data-theme="dark"]` で変数だけ上書きするパターンが一番見通しよく書けました。

## 2. 高さ 500px 制限とスマホ幅（約340px）の意識

`html-embed` の表示領域は高さ最大 500px です。PC 幅（約 700px）では横に並べられて高さ 200px 程度で収まっていても、`@media (max-width: 640px)` で縦積みにしたときに高さが 500px を超えると、埋め込みフレーム内で縦スクロールが発生します。

そのため、スマホ幅のメディアクエリでは単に `flex-direction: column` にするだけでなく、パディングや最小高さ（`min-height`）をコンパクトに詰めるスタイルをセットで書いておくと、スマホでもスクロールなしで綺麗に収まります。

## 3. JS なしでも `:checked`・`:hover`・`<details>` で十分な表現力がある

セキュリティのため JavaScript は動きませんが、記事内の図解としては以下の CSS 機能だけで幅広い表現ができます。

- タブ切り替え: `<input type="radio">` + `:checked` + `<label>`
- 状態トグル・比較: `<input type="checkbox">` + `:checked` + `<label>`
- ツールチップ・補足表示: `:hover` / `:focus-within` や `<details><summary>`
- データの流れの可視化: `@keyframes` アニメーション（＋ `prefers-reduced-motion: reduce` への配慮）

---

# まとめ

`html-embed` のおかげで、「Mermaid では表現しきれないけれど、画像で作るとメンテナンスやダークモード対応が大変」という図解の悩みが解消されそうです。

さらに、公式のお知らせページには生成 AI に `html-embed` の作図を頼むための公式プロンプトも用意されています。構造やデータの数値だけ伝えて AI にベースとなる HTML / CSS を出力してもらい、細部をテキストエディタで微調整するワークフローが今後の技術記事執筆の定番になりそうです。
