---
title: "Zennの記事一覧からAI関連の記事をAIの力によって滅ぼし、そして私も消えよう"
emoji: "🪄"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: ["chromeextension", "javascript", "gemini", "builtinai", "css"]
published: true
---

## はじめに

最近、Zennを開くと生成AIやLLM関連記事が多く目につきます。技術の進歩を追えるのは良いことですが、時にはフロントエンドやバックエンド、インフラの動向や、あるいは低レイヤの泥臭い技術記事を静かに読みたい日もあります。Zennには標準で特定のキーワードやトピックを非表示にするフィルター機能がないため、自分でChrome拡張機能を作成しました。

Chrome 138以降で利用できるBuilt-in AI（Gemini Nano）を活用し、記事本文やフィルタールールを外部の生成AI APIへ送らずに、クライアントサイドで要約とフィルタリングを行います。開発する上で遭遇したローカルLLM特有の課題や、要素を非表示にした後のレイアウト崩れを防ぐUIハックなど、実装上のいくつかの工夫について整理しました。

サンプルコードは以下に置いています。

https://github.com/SoraKumo001/zenn-extentions

動作させるとこういう感じになります。ローカルLLMなのでGPU性能などによって速度が変わってくるのと、4GBのLLMなので誤判定などもけっこうあります。一度判定した記事は情報がキャッシュされます。

![](/images/zenn-ai-filter/2026-06-02-08-56-38.webp)

---

## 拡張機能の概要とファイル構成

この拡張機能は、記事のAI要約（キュー管理付き）と、キーワードまたはLLMを用いた記事一覧フィルター、およびローカルLLMの動作診断機能を備えています。LLMフィルターは「AI関連を題材にした記事を表示しない」といったルールを自然言語で記述可能です。

構成ファイルは以下のようになっています。

- `manifest.json`：拡張機能のマニフェストです。
- [`background.js`](https://github.com/SoraKumo001/zenn-extentions/blob/main/background.js)：ローカルLLM（Prompt API / Summarizer API）を呼び出すService Workerです。
- [`content.js`](https://github.com/SoraKumo001/zenn-extentions/blob/main/content.js)：Zennのページに対するUIの注入やDOM監視、非表示にした記事のレイアウト再構築、判定結果のキャッシュ制御を担当します。
- [`content.css`](https://github.com/SoraKumo001/zenn-extentions/blob/main/content.css)：コンテンツスクリプトで追加するUIや、フィルター後の再配置レイアウトのスタイルです。
- `popup.html` / `popup.js` / `popup.css`：拡張機能ポップアップのUIと、ローカルLLMが正常に準備されているかの診断ロジックを格納しています。

---

## 技術解説1：ローカルLLM（Prompt/Summarizer API）の二重フォールバック

ChromeブラウザでローカルLLMを動かす仕様は現在策定中であり、バージョンやフラグの設定によって利用できるAPIが異なります。現時点では、要約に特化した `ai.summarizer` と、汎用的なテキスト生成を行う `LanguageModel`（Prompt API）の両方が存在しています。

本拡張機能では、まず要約特化の `ai.summarizer` での処理を試み、失敗した場合は `LanguageModel` にフォールバックする構成にしました。

`background.js` での実装は以下のようになっています。

```javascript
// background.js より抜粋
async function handleSummarize(text) {
  // 1. まず要約特化型の Summarizer API があるか確認して使用を試みる
  const summarizerAPI =
    (typeof ai !== "undefined" && ai.summarizer) ||
    (typeof self !== "undefined" && self.ai && self.ai.summarizer) ||
    (typeof globalThis !== "undefined" &&
      globalThis.ai &&
      globalThis.ai.summarizer);

  if (summarizerAPI) {
    try {
      const capabilities = await summarizerAPI.capabilities();
      if (capabilities && capabilities.available !== "no") {
        const summarizer = await summarizerAPI.create({
          type: "key-points",
          format: "markdown",
          length: "medium",
        });
        try {
          const response = await summarizer.summarize(text);
          if (response && response.trim()) {
            return response;
          }
        } finally {
          if (summarizer && typeof summarizer.destroy === "function") {
            summarizer.destroy();
          }
        }
      }
    } catch (e) {
      console.warn(
        "Summarizer APIでの要約生成に失敗したため、LanguageModelへフォールバックします:",
        e,
      );
    }
  }

  // 2. 従来の LanguageModel (Prompt API) へのフォールバック
  const languageModelEntry = getLanguageModelAPI();
  if (!languageModelEntry) {
    throw new Error("ChromeのローカルLLMがサポートされていません。");
  }

  const languageModel = languageModelEntry.api;
  // (中略) LanguageModelでの要約処理を実行...
}
```

グローバルオブジェクトの参照先（`globalThis`、`self`、`chrome.aiOriginTrial` など）は、実行コンテキストやChromeのバージョンによって異なります。このため、`getLanguageModelAPI` というヘルパーを定義してアクセスを抽象化しました。
実装ではさらに、`LanguageModel.availability()` が使える環境では入出力言語として日本語を指定し、古い形のAPIでは `capabilities()` を参照するようにしています。モデルがまだ準備できていない場合に備え、`monitor` でダウンロード進捗もログに出力するようにしました。
また、ローカルLLMのセッションはブラウザのメモリリソースを消費するため、`try...finally` ブロックを用いて、不要になったセッションの `.destroy()` を確実に実行する必要があります。

---

## 技術解説2：LLMフィルターの「遅い」「壊れる」「矛盾する」への対策

記事一覧をローカルLLMでリアルタイムに分類するにあたり、処理速度の低下や出力フォーマットの崩れといった、いくつかの課題に対処しました。

### 1. 処理速度の課題とバッチ判定

ローカルLLMでの推論には一定の時間がかかります。記事を1件ずつシリアルに判定すると、スクロール時の読み込みで表示の遅延が目立ちます。
この対策として、複数の記事タイトルをまとめて一度のプロンプトで判定するバッチ処理を導入しました。

```javascript
// プロンプトの一部
const FILTER_BATCH_SYSTEM_PROMPT =
  'あなたは記事タイトル分類器です。ユーザーの除外ルールに基づき、複数の記事タイトルを非表示にすべきか判定してください。必ずJSON配列のみを返し、形式は [{"index":0,"hide":true|false,"category":"カテゴリ名","confidence":0.0,"matched_terms":["一致語"],"reason":"短い理由"}] にしてください。indexは入力順の0始まりです。confidenceは0.0〜1.0、matched_termsは文字列配列です。';
```

入力に `[0] タイトルA`、`[1] タイトルB` のようにインデックスを付与し、LLMからは対応するインデックスを持つJSON配列を返させます。これにより、セッション構築やプロンプト処理のオーバーヘッドを削減しました。バッチ判定全体がエラーとなった場合は、安全策として個別判定によるリトライ処理に切り替える設計です。

### 2. 出力フォーマットの崩れと正規表現パース

プロンプトでJSONのみの出力を要求しても、マークダウンのコードブロックで囲まれたり、前書きが挿入されたりすることがあります。単純に `JSON.parse` を行うとパースエラーで処理が中断してしまいます。
そこで、文字列から `{` と `}`（配列なら `[` と `]`）の位置を検知して切り出しを試み、それでもパースできない場合は、正規表現で強引にキーと値を抽出するフォールバック処理を設けました。
これはあくまで最終手段ですが、フォールバック結果には `reason` や `confidence` を付けて、後続処理で扱いやすい形に正規化しています。

```javascript
function fallbackExtractJson(text) {
  const hideMatch = text.match(/"hid(?:e|den)"\s*:\s*(true|false)/i);
  const reasonMatch = text.match(/"reason"\s*:\s*"([^"]*)"/i);
  // (中略) 各種キーを正規表現でマッチング
  if (hideMatch) {
    return {
      hide: hideMatch[1].toLowerCase() === "true",
      reason: reasonMatch ? reasonMatch[1] : "Regex Fallback",
      // ...
    };
  }
  throw new Error("パースに失敗しました。");
}
```

### 3. 判定結果と判定理由の矛盾の補正

ローカルLLMの出力では、論理と結果が一致しないケースがあります。例えば、「AI関連記事を除外する」というルールに対し、「Vue 3の基本」というタイトルを渡したとき、理由（`reason`）には「AI関連の記事ではないため、非表示にする必要はありません」と出力しながら、判定結果（`hide`）に誤って `true` を返してくることがありました。
これを防ぐため、理由テキストに否定的な表現（「関連ではない」「非表示にしない」など）が含まれている場合は、強制的に `hide` の値を `false` に補正する処理（`normalizeLlmDecision`）を追加しています。

---

## 技術解説3：CSS Gridの崩れを防ぐバランスレイアウト

Zennの記事一覧は、CSS Gridを用いた複数カラムで構成されています。フィルター対象となった記事要素に単に `display: none` を適用すると、グリッド内に歯抜けのスペースが生じ、レイアウトが崩れてしまいます。

この問題を解決するため、除外されなかった記事のみを左右のカラムに再配置する「バランスレイアウト」を実装しました。

再配置のプロセスは以下の通りです。

1. フィルター処理の前に、元の並び順を `data-zenn-ai-order` 属性として各要素に退避します。
2. 一覧の親コンテナ内に、左右2列のカラム（`div`）を動的に作成します。
3. 非表示対象ではない記事を順にスキャンします。
4. 各カード要素の高さ（`getBoundingClientRect().height`）を測定し、累積の高さが低い方のカラムへ順番に追加していきます。

```javascript
// content.js より抜粋
function applyBalancedListLayout(container) {
  const items = getDirectArticleItems(container);
  if (items.length === 0) return;
  ensureOriginalOrder(items);

  let wrapper = container.querySelector(".zenn-ai-balance-wrap");
  if (!wrapper) {
    wrapper = document.createElement("div");
    wrapper.className = "zenn-ai-balance-wrap";
    wrapper.innerHTML =
      '<div class="zenn-ai-balance-col zenn-ai-balance-col-left"></div><div class="zenn-ai-balance-col zenn-ai-balance-col-right"></div>';
    container.appendChild(wrapper);
  }

  const leftCol = wrapper.querySelector(".zenn-ai-balance-col-left");
  const rightCol = wrapper.querySelector(".zenn-ai-balance-col-right");

  let leftHeight = 0;
  let rightHeight = 0;
  const sorted = [...items].sort(
    (a, b) => Number(a.dataset.zennAiOrder) - Number(b.dataset.zennAiOrder),
  );

  sorted.forEach((item) => {
    const h = Math.max(1, Math.round(item.getBoundingClientRect().height));
    if (leftHeight <= rightHeight) {
      leftCol.appendChild(item);
      leftHeight += h;
    } else {
      rightCol.appendChild(item);
      rightHeight += h;
    }
  });
}
```

この再配置により、何件の記事が非表示になっても左右のカラムで高さのバランスが保たれ、Masonry風の2列レイアウトが維持されます。
一方で、左右カラムへ振り分ける都合上、視覚的な並びは完全な時系列順ではありません。そこで、フィルター解除時には元の順番へ戻せるように、最初に付与した `data-zenn-ai-order` を復元用の基準として使っています。
また、ユーザーが特定の記事を一時的に再表示させたり、フィルター自体を無効化した際には、保持していた `data-zenn-ai-order` に基づいて元のDOM配置へ復元（リフロー）するようにしました。

---

## 導入方法（開発者モード）

ローカルLLMを利用して開発を行うためのセットアップ手順は以下の通りです。

1. **Prompt APIの有効化**
   - Chromeブラウザ（138以降）で `chrome://flags` を開きます。
   - 必要に応じて `Prompt API for Gemini Nano` を `Enabled` に設定し、ブラウザを再起動してください。
2. **モデルの準備**
   - `chrome://components` で `Optimization Guide On Device Model` の「アップデートを確認」をクリックし、モデルデータをダウンロードします。
   - 環境によってはモデルの準備に時間がかかるため、拡張機能ポップアップのステータス表示で `available` / `downloadable` / `downloading` などの状態を確認してください。
3. **拡張機能のインストール**
   - `chrome://extensions` でデベロッパーモードを有効化します。
   - 「パッケージ化されていない拡張機能を読み込む」からソースフォルダを選択してください。
4. **動作確認**
   - Zenn（`zenn.dev`）を開き、各記事の「要約」ボタンや画面左下の「フィルター」パネルが動作することを確認します。

---

## おわりに

Built-in AI（ローカルLLM）は、外部のクラウドAPIを利用する場合と比べていくつか明確なメリットがあります。

- **推論時の外部API通信が不要**: モデルの準備後は、記事本文やフィルタールールを外部の生成AI APIへ送らずに処理できます。
- **運用のしやすさ**: ユーザー側のPCリソースを消費するため、API利用料やレートリミットを考慮しなくて良い点もメリットです。
- **データのプライバシー**: 解析したコンテンツやルールが外部サーバーへ送信されません。

一方で、API仕様の過渡期における実装のブレや、LLM特有の出力のゆらぎ、さらに非表示に伴うDOMレイアウトの再編など、実用性を担保するためにはクライアントサイドで泥臭い作り込みが必要となります。
増え続けるAI関連の情報を、あえてローカルLLMで取捨選択する仕組みについて、実装のアプローチを整理しました。
