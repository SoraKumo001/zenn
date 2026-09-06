---
title: "Cloudflare Workersの64MiB緩和で実現するHTML画像変換＆画像最適化（wasm-html-to-image）"
emoji: "🦁"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: ["cloudflare", "workers", "wasm", "html", "ogp"]
published: true
---

- サンプルリポジトリ
  https://github.com/SoraKumo001/wasm-html-to-image-samples
- npm パッケージ
  https://www.npmjs.com/package/wasm-html-to-image
- 公式ドキュメント
  https://sorakumo001.github.io/wasm-html-to-image/master/docs/

# はじめに

2026年9月4日、Cloudflare Workers に非常に大きなアップデートが行われました。Worker のデプロイサイズ制限が劇的に緩和され、これまでエッジ環境で動かすには重すぎた大規模な WebAssembly（WASM）モジュールをそのまま組み込めるようになりました。

https://developers.cloudflare.com/changelog/post/2026-09-04-increased-worker-size-limit/

これまで Cloudflare Workers 上で OGP 画像生成や画像最適化を行う際、**「WASM のサイズ制限」** は常に最大の壁でした。特に AVIF のデコードエンジンや Skia 等の高機能な描画エンジンを同居させようとすると、制限サイズを超過してしまい、機能を削るか複数のライブラリに切り分ける必要がありました。

今回の制限緩和によりその制約が解消されたため、**HTML からの画像レンダリング（Skia + litehtml）と画像フォーマット最適化（AVIF / WebP / JPEG / PNG / SVG / PDF 等の相互変換・圧縮）を 1 つに合体させた統合 WASM パッケージ [`wasm-html-to-image`](https://www.npmjs.com/package/wasm-html-to-image)** を作成・公開しました。

このライブラリの最大の特徴は、**「HTML」を渡しても「画像データ」を渡しても、まったく同じ `render` 関数 1 つで指定したフォーマットの画像に変換・最適化できる** 点にあります。

本記事では、Cloudflare のサイズ制限緩和のポイントと、新パッケージ `wasm-html-to-image` を使って Cloudflare Workers 上で OGP 生成や画像最適化を実装する方法について解説します。

---

# Cloudflare Workers のサイズ制限緩和（2026年9月4日）

従来の Cloudflare Workers では、Wrangler がバンドルしたコードを gzip 圧縮した後のサイズに対して制限が課されていました。

- **従来の制限:**
  - Free プラン: 圧縮後 **3 MB**
  - Paid プラン: 圧縮後 **10 MB**

WASM ファイルはバイナリデータであるため gzip の圧縮が効きにくく、高機能な C++ / Rust 製ライブラリを持ち込もうとすると、無料プランの 3MB 枠はもちろん有料プランの 10MB 枠でもギリギリになるケースが多々ありました。

### 緩和後の新仕様

今回の変更により、**gzip 圧縮後のサイズチェックは完全に撤廃**されました。代わりに「非圧縮時のバンドルサイズ（Uncompressed bundle size）」のみがチェックされるようになり、制限値は全プラン共通で **64 MiB** に拡大されました。

| 項目            | 以前              | 現在 (2026-09-04 以降)           |
| :-------------- | :---------------- | :------------------------------- |
| **Free プラン** | 圧縮後 3 MB       | **非圧縮 64 MiB**                |
| **Paid プラン** | 圧縮後 10 MB      | **非圧縮 64 MiB**                |
| **判定基準**    | gzip 圧縮後サイズ | **非圧縮サイズ（Total Upload）** |

現在のバンドルサイズは以下のコマンドで確認できます。

```bash
wrangler deploy --outdir bundled/ --dry-run
```

出力例：

```text
Total Upload: 12.45 MiB / gzip: 4.21 MiB
```

`Total Upload` が 64 MiB 以内であればデプロイ可能です（`gzip` は参考値として表示されるのみで、制限の判定には使われません）。

これにより、従来は分割せざるを得なかった大規模な WASM バイナリや、組み込みフォント、複数の画像コーデックを躊躇なくデプロイできるようになりました。

---

# これまでの課題と統合の背景

これまで筆者は、エッジ環境での画像処理に向けていくつかのライブラリを公開・解説してきました。

- `satori` + `svg2png-wasm` + `wasm-image-optimization`
- `satoru-render`（Skia + litehtml の WASM ポート）

以前のアーキテクチャでは、「HTML をパースしてベクター描画するエンジン」と「WebP や AVIF などの各種画像をデコード・エンコードする画像最適化ライブラリ」を別々に用意する必要がありました。

特に **AVIF のデコードエンジン**（`libdav1d` など）はライブラリ単体でもサイズが大きく、Skia 描画エンジンと一緒にまとめると無料プランの 3MB 上限に収まりませんでした。そのため、やむを得ずパッケージを分割したり、対応フォーマットを削るなどのトレードオフを強いられていました。

しかし、非圧縮 64 MiB まで許容されるようになったことで、**HTML レンダリングエンジンと主要な画像コーデック群を単一の WASM モジュールに統合** することが可能になりました。

---

# 統合パッケージ `wasm-html-to-image`

そうして誕生したのが [`wasm-html-to-image`](https://www.npmjs.com/package/wasm-html-to-image) です。

このライブラリの最大の強みは、**「HTML」を入れても「画像」を入れても、まったく同じ `render` 関数 1 つで指定したフォーマットの画像に変換できる** 点にあります。

### 入力に応じたパイプラインの自動判定

`render({ value, format, ... })` を呼び出す際、入力となる `value` に何を渡すかによって、内部の処理パイプラインが自動的に切り替わります。

| `value` に渡す入力                                  | 内部のパイプライン                                                             | 出力結果（`format` で指定）                                    |
| :-------------------------------------------------- | :----------------------------------------------------------------------------- | :------------------------------------------------------------- |
| **HTML 文字列**<br>（`<div...` などのタグ文字列）   | **HTML レンダリング**<br>litehtml（パース）＋ Skia（ベクター描画）             | 指定フォーマットの画像にレンダリング（WebP / AVIF / PNG 等）   |
| **画像データ**<br>（`Uint8Array` / `Buffer` / URL） | **画像最適化・フォーマット変換**<br>各画像コーデックによるデコード ＆ リサイズ | 指定フォーマットの画像へ相互変換・圧縮（WebP / AVIF / PNG 等） |

呼び出し側のインターフェースは完全に共通です。

```typescript
// パターンA: HTML を渡す → WebP / PNG などの画像を出力（OGP 生成など）
const ogpImage = await render({
  value: `<div style="background: #1e293b; color: white; padding: 40px;">
    <h1>Hello World</h1>
  </div>`,
  width: 1200,
  height: 630,
  format: "webp",
});

// パターンB: 既存画像を渡す → AVIF / WebP への変換やリサイズを出力（画像最適化など）
const optimizedImage = await render({
  value: srcImageBinary, // Uint8Array または ArrayBuffer
  width: 800,
  quality: 80,
  format: "avif",
});
```

これまでのように「HTML から画像を生成したいから Satori やレンダラーを導入する」「WebP や AVIF に圧縮したいから別個の画像最適化ライブラリを入れる」といった使い分けは一切不要です。**すべて同じ `render()` 関数に投げるだけ** で、意図した画像フォーマットが出力されます。HTMLの変換は、CSSのレイヤーや変数、複雑なレイアウトやブラー、縦書きなど、ほぼブラウザと同レベルまで再現できます。

どのぐらいの再現性があるのかはこちらで確認出来ます。

https://sorakumo001.github.io/wasm-html-to-image/master/

### サポートする入出力

- **入力形式:**
  - HTML 文字列（JSX からの変換 HTML、Tailwind クラス付き HTML など）
  - Web サイト URL（`http://` または `https://` で直接フェッチして画像化）
  - 画像バイナリ（PNG, JPEG, WebP, GIF, AVIF, BMP の `Uint8Array` / `ArrayBuffer`）
  - Data URL（`data:image/...;base64,...`）
- **出力フォーマット (`format`):**
  - `webp`: 高圧縮・高画質 WebP 画像
  - `avif`: 次世代の超高圧縮 AVIF 画像
  - `png`: 劣化のない PNG 画像
  - `jpeg`: 標準的な JPEG 画像（`quality` 指定可能）
  - `svg`: ベクター描画ストリーム（HTML レンダリング時）
  - `pdf`: ベクター PDF ドキュメント
  - `thumbhash`: プレビュー用の超軽量プレースホルダー
- **Cloudflare Workers (`workerd`) にネイティブ対応:**
  - `wasm-html-to-image/workerd` を提供。Workers 特有の WASM モジュールバインドに最適化。
  - Preact / React JSX の HTML 化や、Tailwind CSS のユーティリティ抽出（`createCSS`）も同梱。

---

# Cloudflare Workers での実装

実際のサンプルコード（リポジトリ: [`wasm-html-to-image-samples`](https://github.com/SoraKumo001/wasm-html-to-image-samples)）をベースに、Workers 上での実装例を紹介します。

## 1. プロジェクト設定 (`wrangler.jsonc`)

Wrangler の設定ファイルを用意します。WASM モジュールをバンドルするため、`rules` に `CompiledWasm` を指定します。

```jsonc
{
  "$schema": "node_modules/wrangler/config-schema.json",
  "name": "cloudflare-ogp",
  "main": "src/index.tsx",
  "compatibility_date": "2025-02-04",
  "rules": [
    { "type": "CompiledWasm", "globs": ["**/*.wasm"], "fallthrough": false },
  ],
  "observability": {
    "enabled": true,
  },
}
```

必要な依存関係をインストールします。

```bash
pnpm add wasm-html-to-image preact
pnpm add -D wrangler typescript @cloudflare/workers-types
```

## 2. JSX + Tailwind による OGP 画像生成

Preact の JSX でレイアウトを記述し、Google Fonts の Web フォントと Tailwind CSS を適用して PNG 画像を生成・配信する例です。

```tsx:src/index.tsx
/** @jsx h */
import { h, toHtml } from "wasm-html-to-image/preact";
import { render } from "wasm-html-to-image/workerd";
import { createCSS } from "wasm-html-to-image/tailwind";

const fetch = async (
  request: Request,
  _env: object,
  ctx: ExecutionContext,
): Promise<Response> => {
  const url = new URL(request.url);
  if (url.pathname !== "/") {
    return new Response(null, { status: 404 });
  }

  const subtitle = url.searchParams.get("subtitle") ?? "subtitle";
  const title = url.searchParams.get("title") ?? "Title";
  const image =
    url.searchParams.get("image") ??
    "https://raw.githubusercontent.com/SoraKumo001/cloudflare-ogp/refs/heads/master/sample/image.jpg";

  // キャッシュの確認
  const cache = await caches.open("satoru-cloudflare-ogp");
  const cacheKey = new Request(url.toString());
  const cachedResponse = await cache.match(cacheKey);
  if (cachedResponse) {
    return cachedResponse;
  }

  // JSX で OGP の HTML レイアウトを定義
  // Google Fonts の Noto Sans JP を読み込み
  const html = toHtml(
    <html className="m-0 p-0">
      <head>
        <link
          href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@100..900&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="m-0 p-0">
        <div className="w-[1200px] h-[630px] flex relative bg-[#0a0a0c] overflow-hidden">
          <div className="absolute top-[-150px] right-[-150px] w-[600px] h-[600px] rounded-[300px] bg-[radial-gradient(circle,_rgba(79,70,229,0.3)_0%,_rgba(79,70,229,0)_70%)] flex" />
          <div className="absolute bottom-[-100px] left-[-50px] w-[400px] h-[400px] rounded-[200px] bg-[radial-gradient(circle,_rgba(168,85,247,0.2)_0%,_rgba(168,85,247,0)_70%)] flex" />

          <div className="flex flex-row w-full h-full p-[60px] items-center justify-between z-10">
            <div className="flex flex-col w-[60%]">
              <div className="flex items-center mb-5">
                <div className="w-10 h-1 bg-[#6366f1] mr-[15px] rounded-sm" />
                <div className="text-2xl font-bold color-[#818cf8] tracking-widest uppercase flex">
                  Featured Content
                </div>
              </div>

              <div className="text-[80px] font-black text-white leading-[1.1] mb-[30px] break-words flex">
                {title}
              </div>

              <div className="text-[32px] font-normal text-[#94a3b8] leading-[1.4] flex">
                {subtitle}
              </div>
            </div>

            <div className="flex w-[35%] relative justify-center items-center">
              <div className="absolute w-[420px] h-[420px] rounded-[40px] border border-white/10 bg-white/3 rotate-[-3deg] flex" />
              <div className="w-[400px] h-[400px] rounded-[32px] overflow-hidden border-4 border-white/10 flex">
                <img
                  className="w-full h-full object-cover"
                  src={image}
                  alt=""
                />
              </div>
            </div>
          </div>
          <div className="absolute bottom-10 left-[60px] flex items-center z-20">
            <div className="px-4 py-2 bg-white/5 border border-white/10 rounded-[10px] text-lg text-[#e2e8f0] font-medium flex">
              cloudflare-ogp
            </div>
          </div>
        </div>
      </body>
    </html>,
  );

  // HTML + Tailwind CSS から PNG 画像をレンダリング
  const png = await render({
    value: html,
    css: await createCSS(html),
    width: 1200,
    height: 630,
    format: "png",
  });

  const response = new Response(png.data as BodyInit, {
    headers: {
      "Content-Type": "image/png",
      "Cache-Control": "public, max-age=31536000, immutable",
      date: new Date().toUTCString(),
    },
    cf: {
      cacheEverything: true,
      cacheTtl: 31536000,
    },
  });

  ctx.waitUntil(cache.put(cacheKey, response.clone()));
  return response;
};

export default {
  fetch,
};
```

### ポイント

- **`toHtml(...)`**: Preact JSX をそのまま HTML 文字列へ変換します。
- **`createCSS(html)`**: HTML 内で使われている Tailwind のユーティリティクラスを解析し、最小限の CSS を自動生成します。
- **`render(...)`**: HTML・CSS・外部フォント・外部画像を統合処理し、ヘッドレスブラウザ不要で高品質な画像をエッジ上でレンダリングします。

---

## 3. リサイズ＆画像フォーマット最適化（AVIF / WebP）

ここでも使うのは、**先ほどの OGP 生成とまったく同じ `render` 関数** です。`value` に HTML ではなく画像バイナリ（`ArrayBuffer` / `Uint8Array`）を渡すだけで、自動的に画像最適化パイプラインへと切り替わり、**画像リサイズ＆フォーマット変換プロキシ** として動作します。

ブラウザの `Accept` ヘッダーを判別して、AVIF や WebP へ自動変換・圧縮配信する例です。

```typescript:src/index.ts
import { render } from "wasm-html-to-image/workerd";

const isValidUrl = (url: string) => {
  try {
    new URL(url);
    return true;
  } catch {
    return false;
  }
};

const isType = (accept: string | null, type: string) => {
  return (
    accept
      ?.split(",")
      .map((format) => format.trim())
      .some((format) => [`image/${type}`, "*/*", "image/*"].includes(format)) ?? true
  );
};

export default {
  async fetch(request: Request, _env: object, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const params = url.searchParams;
    const type = ["avif", "webp", "png", "jpeg"].find((v) => v === params.get("type")) as
      | "avif"
      | "webp"
      | "png"
      | "jpeg"
      | undefined;

    const accept = request.headers.get("accept");
    const isAvif = isType(accept, "avif");
    const isWebp = isType(accept, "webp");

    const cache = await caches.open(`img-${isAvif ? "-avif" : ""}${isWebp ? "-webp" : ""}`);
    const cacheKey = new Request(url.toString());
    const cachedResponse = await cache.match(cacheKey);
    if (cachedResponse) {
      return cachedResponse;
    }

    const imageUrl = params.get("url");
    if (!imageUrl || !isValidUrl(imageUrl)) {
      return new Response("url is required", { status: 400 });
    }

    const width = params.get("w");
    const quality = params.get("q");

    // ソース画像を取得
    const [srcImage, contentType] = await fetch(imageUrl, { cf: { cacheKey: imageUrl } })
      .then(async (res) => (res.ok ? ([await res.arrayBuffer(), res.headers.get("content-type")] as const) : []))
      .catch(() => []);

    if (!srcImage) {
      return new Response("image not found", { status: 404 });
    }

    // SVG や GIF はそのまま返却
    if (contentType && ["image/svg+xml", "image/gif"].includes(contentType)) {
      const response = new Response(srcImage, {
        headers: {
          "Content-Type": contentType,
          "Cache-Control": "public, max-age=31536000, immutable",
        },
      });
      ctx.waitUntil(cache.put(cacheKey, response.clone()));
      return response;
    }

    // 出力フォーマットを決定（パラメータ指定優先、なければブラウザ対応状況から自動判別）
    const format = type ?? (isAvif ? "avif" : isWebp ? "webp" : contentType === "image/jpeg" ? "jpeg" : "png");

    // 画像のデコード、リサイズ、エンコードを WASM で一括実行
    const { data } = await render({
      value: srcImage,
      width: width ? Number(width) : 0,
      quality: quality ? Number(quality) : undefined,
      format,
      speed: 9,
    });

    const response = new Response(data, {
      headers: {
        "Content-Type": `image/${format}`,
        "Cache-Control": "public, max-age=31536000, immutable",
        date: new Date().toUTCString(),
      },
    });

    ctx.waitUntil(cache.put(cacheKey, response.clone()));
    return response;
  },
};
```

ご覧のように、OGP 生成のコードと見比べても、呼び出しているのは **全く同じ `render` 関数** であり、オプションに渡す `format` や `width` などの指定方法も完全に同一です。

HTML レンダリングと画像最適化の内部パイプラインが完全に抽象化されているため、呼び出し側は「元のデータが HTML か画像か」を意識することなく、統一された API で出力画像をコントロールできます。

これまで Cloudflare Workers ではデコーダーのサイズ都合で難しかった **AVIF への変換・圧縮（および AVIF ソースの取り込み）** も、64 MiB 枠のおかげで極めてスムーズに実現できます。

---

# サンプルプロジェクトと他環境への展開

今回作成したサンプルコードは、GitHub リポジトリ [`wasm-html-to-image-samples`](https://github.com/SoraKumo001/wasm-html-to-image-samples) にて公開しています。

リポジトリ内には Cloudflare Workers 向けの実装だけでなく、多様なフレームワーク・ランタイムでの実装例が含まれています。

- **`cloudflare-ogp`**: 本記事で紹介した Cloudflare Workers 上での JSX + Tailwind OGP 生成
- **`cloudflare-image-optimization`**: Cloudflare Workers 上での AVIF/WebP 自動画像変換プロキシ
- **`next-image-convert`**: Next.js 16 (App Router) でのクライアントサイド画像変換
- **`react-router-image-convert`**: React Router v7 + Vite でのクライアントサイド画像変換
- **`node-image-convert`**: Node.js CLI によるローカルバッチ画像変換
- **`playground`**: ブラウザ上で HTML 編集と画像変換を即時試せる React 19 + Vite アプリ

### マルチスレッド対応（Worker Pool）

ブラウザや Node.js 環境では、`wasm-html-to-image/workers` を使用することでマルチスレッド（Web Worker プール）による高速な並列バッチ処理も可能です。

```typescript
import { render } from "wasm-html-to-image/workers";

// マルチコアを活用して一括バッチ生成
const results = await Promise.all(
  items.map((item) =>
    render({
      value: `<h1>${item.title}</h1>`,
      width: 1200,
      height: 630,
      format: "webp",
    }),
  ),
);
```

---

# まとめ

Cloudflare Workers のデプロイ制限が「非圧縮 64 MiB」へと引き上げられたことで、エッジコンピューティングにおける WASM の可能性は飛躍的に広がりました。

- **サイズ制限の呪縛からの解放**: 圧縮後 3MB/10MB を気にして WASM モジュールを分割・削減する必要がなくなった。
- **HTML レンダリングと画像最適化の合体**: `wasm-html-to-image` により、Skia + litehtml の高精度な HTML 画像化と、AVIF/WebP などの高度な画像圧縮処理が 1 パッケージで完結。
- **統一された `render` インターフェース**: HTML 文字列でも画像バイナリでも、まったく同じ `render()` 関数に渡すだけで指定フォーマットの画像を出力可能。ユースケースごとに別ライブラリや別関数を使い分けるストレスから解放されます。
- **ヘッドレスブラウザ不要**: 重厚な Chromium などを動かすことなく、ミリ秒単位のエッジレスポンスで動的な OGP や最適化画像を提供可能。

Cloudflare Workers での OGP 動的配信や画像最適化パイプラインを検討されている方は、ぜひ試してみてください。

容量が大幅に緩和された今、JavaScriptが苦手な処理も、WASMを使えば既存のライブラリを組み合わせてやりたい放題です。
