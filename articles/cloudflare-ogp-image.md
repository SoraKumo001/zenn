---
title: "Cloudflare で OGP Image の統合環境を作る"
emoji: "🖼️"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [cloudflare, workers, ogp, react, hono]
published: true
---

- リポジトリ
  https://github.com/SoraKumo001/ogp-image-creator

# はじめに

以前、Cloudflare Workers 上で OGP 画像を生成するライブラリについて解説しました。

https://zenn.dev/sora_kumo/articles/cloudflare-ogp

こちらは「satori + svg2png-wasm でJSX要素からPNGを作る」ライブラリの解説で、コードに組み込んで使うことが前提でした。今回はその発展形として、**HTMLを編集するだけでOGP画像を作り・保存し・URLで配信できる統合環境**を作りました。

- ブラウザ上でHTML/CSSを編集してライブプレビュー
- `{{キー名}}` のマクロでパラメータ化
- テンプレートを保存して `/ogp/:id` で画像配信（クエリで上書き可能）
- Cloudflare Workers AI で自然言語からHTMLを生成（ストリーミング）
- ヘッドレスブラウザ不要（WASMベースのレンダリング）

OGPイメージの作成から配布まで、一貫して行うことが出来ます。配布用URLでパラメータが指定できるので、タイトル部分だけ差し替えるような動作もサポートしています。

Cloudflareの無料範囲で使えるAIを組み込んであるので、プロンプトを使って内容を書き換えることも可能です。

- キャプチャ動画
  ![](/images/cloudflare-ogp-image/capture.webp)

# 技術スタック

| レイヤ         | 技術                                                                                   |
| -------------- | -------------------------------------------------------------------------------------- |
| バックエンド   | Cloudflare Workers + [Hono](https://hono.dev/)                                         |
| レンダリング   | [satoru-render](https://www.npmjs.com/package/satoru-render)（WASM / Skia + litehtml） |
| AI 生成        | Cloudflare Workers AI（`env.AI` binding・SSE ストリーミング）                          |
| フロントエンド | React + Vite + Monaco Editor                                                           |
| ストレージ     | Cloudflare KV（テンプレート保存）                                                      |

前回の `cloudflare-ogp` は satori（仮想DOM → SVG → PNG）を使っていましたが、今回は [satoru-render](https://github.com/SoraKumo001/satoru)（litehtml + Skia のWASMポート）を採用しています。HTML/CSSを直接レンダリングできるため、Monacoエディタで編集したHTMLをそのまま画像化できるのが最大の違いです。外部にあるフォントや画像データを利用する場合も、そのままHTMLに書くことで使用できます。satori に存在するスタイルなどの制約はありません。

# アーキテクチャ

## バックエンドのルート構成

`src/index.ts` でHonoアプリを組み立て、各機能ごとにルートを分割しています。

```ts
import { Hono } from "hono";
import { renderRoutes } from "./routes/render";
import { ogpRoutes } from "./routes/ogp";
import { authRoutes } from "./routes/auth";
import { adminRoutes } from "./routes/admins";
import { proxyRoutes } from "./routes/proxy";
import { templateRoutes } from "./routes/templates";
import { generateRoutes } from "./routes/generate";
import { assetRoutes } from "./routes/assets";
import type { AppEnv } from "./types";

const app = new Hono<AppEnv>();

app.route("/", renderRoutes);
app.route("/", ogpRoutes);
app.route("/", authRoutes);
app.route("/", adminRoutes);
app.route("/", proxyRoutes);
app.route("/", templateRoutes);
app.route("/", generateRoutes);
app.route("/", assetRoutes);

// GET / (static assets)
app.get("*", (c) => c.env.ASSETS.fetch(c.req.raw));

export default app;
```

| メソッド | パス                 | 説明                            | 認証 |
| -------- | -------------------- | ------------------------------- | ---- |
| `GET`    | `/api/auth/status`   | 認証状態の確認                  | -    |
| `POST`   | `/api/setup`         | 初回管理者登録                  | -    |
| `POST`   | `/api/login`         | ログイン                        | -    |
| `POST`   | `/api/logout`        | ログアウト                      | -    |
| `GET`    | `/api/admins`        | 管理者一覧                      | 必要 |
| `POST`   | `/api/admins`        | 管理者追加                      | 必要 |
| `DELETE` | `/api/admins/:id`    | 管理者削除                      | 必要 |
| `POST`   | `/api/render`        | HTML を画像にレンダリング       | -    |
| `GET`    | `/ogp/:id`           | 保存済みテンプレートを画像配信  | -    |
| `GET`    | `/api/proxy?url=`    | 外部リソース取得（CORS 回避）   | 必要 |
| `GET`    | `/api/templates`     | テンプレート一覧                | 必要 |
| `POST`   | `/api/templates`     | テンプレート保存                | 必要 |
| `GET`    | `/api/templates/:id` | テンプレート取得                | 必要 |
| `DELETE` | `/api/templates/:id` | テンプレート削除                | 必要 |
| `GET`    | `/api/models`        | 利用可能な AI モデル一覧        | 必要 |
| `POST`   | `/api/generate`      | AI で HTML をストリーミング生成 | 必要 |

`/ogp/:id` と `/api/render` はクローラやプレビュー用途で認証なしで叩けるのがポイントです。編集系（テンプレート・アセット・AI生成・プロキシ）は `requireAuth` ミドルウェアで保護しています。

## wrangler.jsonc

```jsonc
{
  "$schema": "node_modules/wrangler/config-schema.json",
  "name": "ogp-image-creator",
  "main": "src/index.ts",
  "compatibility_date": "2026-08-20",
  "observability": { "enabled": true },
  "upload_source_maps": true,
  "assets": { "directory": "./public/", "binding": "ASSETS" },
  "ai": { "binding": "AI", "remote": true },
  "kv_namespaces": [{ "binding": "OGP-IMAGE-CREATOR" }],
}
```

ポイントは3つ:

- **`assets`** — `public/` にビルドしたフロントエンドを `ASSETS` bindingで配信。`app.get('*', (c) => c.env.ASSETS.fetch(c.req.raw))` でフォールバック
- **`ai`** — Workers AI の binding。`remote: true` で `wrangler dev` 時もリモート推論
- **`kv_namespaces`** — `id` を指定しない「自動プロビジョニング」。`wrangler deploy` 時にKVネームスペースが自動作成され、IDがこのファイルに書き戻されます

# レンダリング: satoru-render

## src/render.ts

satoru-render は litehtml（HTML/CSSパーサ）と Skia（描画エンジン）をWASMにコンパイルしたレンダリングエンジンで、Chromiumを必要とせずHTML/CSSを直接画像化できます。

```ts
import type { Context } from "hono";
import { render } from "satoru-render";
import { createCSS } from "satoru-render/tailwind";
import { getAsset, decodeBase64 } from "./assets";
import type { RenderFormat } from "./types";

const CONTENT_TYPES: Record<RenderFormat, string> = {
  png: "image/png",
  webp: "image/webp",
  svg: "image/svg+xml",
};

export function parseFormat(value: string | null | undefined): RenderFormat {
  if (value === "webp" || value === "svg") return value;
  return "png";
}

export function parsePositiveInt(
  value: string | null | undefined,
  fallback: number,
): number {
  if (value == null) return fallback;
  const n = Number.parseInt(value, 10);
  if (Number.isNaN(n) || n <= 0) return fallback;
  return n;
}

export async function renderImage(
  c: Context,
  html: string,
  width: number,
  height: number,
  format: RenderFormat,
): Promise<Response> {
  const result = await render({
    value: html,
    css: await createCSS(html),
    width,
    height,
    format,
    resolveResource: async (resource, defaultResolver) => {
      // 相対パス画像（/assets/:id）は KV から解決する。
      // それ以外は defaultResolver に委譲する。
      if (resource.url.startsWith("/assets/")) {
        const id = resource.url.slice("/assets/".length);
        const asset = await getAsset(c.env, id);
        if (asset) return decodeBase64(asset.data);
        return null;
      }
      return defaultResolver(resource);
    },
  });
  const body = typeof result === "string" ? result : new Uint8Array(result);
  return c.body(body, 200, {
    "Content-Type": CONTENT_TYPES[format],
    "Cache-Control": "public, max-age=3600",
  });
}
```

注目点:

- **`createCSS(html)`** — `satoru-render/tailwind` からTailwind CSSのユーティリティクラスを抽出し、インラインCSSに展開します。AI生成時にTailwindを使えるのはこの仕組みのおかげです
- **`resolveResource`** — 画像やフォントの解決をカスタマイズ。`/assets/:id` で始まるURLはKVに保存したアップロード画像から解決し、それ以外はデフォルトの解決器に委譲します
- **`format`** — `png` / `webp` / `svg` をサポート。SVGの場合は文字列が返るので分岐しています

## フロントエンドのライブプレビュー

フロントエンドでも同じ satoru-render を動かし、編集中のHTMLを即座にプレビューします。

`frontend/src/useRenderer.ts`:

```ts
import { useCallback, useRef, useState } from "react";
import { render, type RequiredResource } from "satoru-render";
import { createCSS } from "satoru-render/tailwind";
import { applyMacros, type MacroParams } from "./macros";
import { decodeBase64 } from "../../shared/encoding";
import type { RenderSettings } from "./types";

interface RenderState {
  status: "idle" | "rendering" | "done" | "error";
  imageUrl?: string;
  error?: string;
}

/**
 * `resolveResource` をオーバーライドし、外部リソースを
 * `/api/proxy` 経由で取得する（CORS 回避）。
 * 戻り値は Uint8Array（画像・CSS）として返す。
 */
async function resolveViaProxy(
  resource: RequiredResource,
): Promise<Uint8Array | null> {
  const { url } = resource;
  // data: URL はそのまま直接解決（外部取得不要）
  if (url.startsWith("data:")) {
    try {
      const base64 = url.slice(url.indexOf(",") + 1);
      return decodeBase64(base64);
    } catch {
      return null;
    }
  }
  // アップロード済みアセット（/assets/）はプロキシを介さず直接取得する
  if (url.startsWith("/assets/")) {
    try {
      const res = await fetch(url, { credentials: "include" });
      if (!res.ok) return null;
      const buf = await res.arrayBuffer();
      return new Uint8Array(buf);
    } catch {
      return null;
    }
  }
  // 相対パスやスキームのない URL はプロキシ対象外
  if (!/^https?:\/\//i.test(url)) return null;

  try {
    const res = await fetch(`/api/proxy?url=${encodeURIComponent(url)}`, {
      credentials: "include",
    });
    if (!res.ok) return null;
    const buf = await res.arrayBuffer();
    return new Uint8Array(buf);
  } catch {
    return null;
  }
}

export function useRenderer(settings: RenderSettings) {
  const [state, setState] = useState<RenderState>({ status: "idle" });
  const renderSeq = useRef(0);

  const renderHtml = useCallback(
    async (html: string, params: MacroParams = {}) => {
      const seq = ++renderSeq.current;
      setState({ status: "rendering" });
      try {
        const result = await render({
          value: applyMacros(html, params),
          css: await createCSS(html),
          width: settings.width,
          height: settings.height,
          format: settings.format,
          resolveResource: async (resource) => resolveViaProxy(resource),
        });
        if (seq !== renderSeq.current) return; // 古いレンダリングは破棄
        const blob =
          result instanceof Uint8Array
            ? new Blob([new Uint8Array(result)], {
                type: settings.format === "webp" ? "image/webp" : "image/png",
              })
            : new Blob([result], { type: "image/svg+xml" });
        const imageUrl = URL.createObjectURL(blob);
        setState((prev) => {
          if (prev.imageUrl) URL.revokeObjectURL(prev.imageUrl);
          return { status: "done", imageUrl };
        });
      } catch (err) {
        if (seq !== renderSeq.current) return;
        setState({
          status: "error",
          error: err instanceof Error ? err.message : String(err),
        });
      }
    },
    [settings.width, settings.height, settings.format],
  );

  return { state, renderHtml };
}
```

外部リソース（Google Fontsや外部画像）はCORSで直接取得できないため、`/api/proxy` 経由で取得します。`renderSeq` で連続編集時の古いレンダリング結果を破棄するのも定番のハンドリングです。

# マクロ（パラメータ）機能

## shared/macros.ts

HTML内に `{{キー名}}` と書くと、エディタ下部のパラメータパネルにそのキーに対応する入力欄が自動表示されます。入力した値でプレビューが更新され、配信時のクエリパラメータで上書きできます。

```ts
export type MacroParams = Record<string, string>;

const MACRO_RE = /\{\{\s*([\w-]+)\s*\}\}/g;

/**
 * HTML から `{{key}}` 形式のマクロキーを抽出する。
 * 重複は除去し、出現順で返す。
 */
export function extractMacroKeys(html: string): string[] {
  const keys = new Set<string>();
  for (const m of html.matchAll(MACRO_RE)) {
    keys.add(m[1]);
  }
  return [...keys];
}

/**
 * HTML 内の `{{key}}` を params の値で置換する。
 * キーが params に存在しない場合は `{{key}}` をそのまま残す。
 */
export function applyMacros(html: string, params: MacroParams): string {
  return html.replace(MACRO_RE, (match, key: string) => {
    return Object.prototype.hasOwnProperty.call(params, key)
      ? params[key]
      : match;
  });
}
```

バックエンド・フロントエンド双方から参照するため `shared/` に配置しています。キー名には英数字とハイフンが使えます（例: `{{site-name}}`）。値が未入力のキーは `{{キー名}}` のまま残るので、プレースホルダ表示としても機能します。

# テンプレート管理とOGP配信

## KVのキー設計

`src/kv.ts` でテンプレートのKVアクセスを、`src/assets.ts` でアップロード画像のKVアクセスをそれぞれ閉じ込めています。

```ts
export interface TemplateData {
  html: string;
  width?: number;
  height?: number;
}

export interface TemplateMetadata {
  name: string;
  updatedAt: number;
}

export async function putTemplate(
  env: Env,
  id: string,
  data: TemplateData,
  metadata: TemplateMetadata,
): Promise<void> {
  await kv(env).put(id, JSON.stringify(data), { metadata });
}

export async function getTemplateMetadata(
  env: Env,
  id: string,
): Promise<Partial<TemplateMetadata>> {
  const entry = await kv(env).getWithMetadata(id);
  return (entry.metadata ?? {}) as Partial<TemplateMetadata>;
}
```

テンプレート本体（HTML）を値に、`name` と `updatedAt` をメタデータに格納しています。`updatedAt` は後述のキャッシュ無効化で重要になります。

アップロード画像は `__asset__:` プレフィックスを付け、テンプレート一覧と衝突しないようにしています。

```ts
const ASSET_PREFIX = "__asset__:";

export async function putAsset(
  env: Env,
  id: string,
  record: AssetRecord,
): Promise<void> {
  const metadata: AssetMetadata = {
    name: record.name,
    contentType: record.contentType,
    size: record.size,
    updatedAt: Date.now(),
  };
  await kv(env).put(ASSET_PREFIX + id, record.data, { metadata });
}
```

`listTemplates` は `__` 始まりのキーを除外するため、アセットとテンプレートは同じKVネームスペースに共存できます。

## POST /api/templates

```ts
templateRoutes.post("/api/templates", requireAuth, async (c) => {
  try {
    const body = await c.req.json<{
      id?: string;
      name?: string;
      html?: string;
      width?: number;
      height?: number;
    }>();
    if (!isNonEmptyString(body.html)) {
      return c.json({ error: "html is required" }, 400);
    }
    if (!isNonEmptyString(body.name)) {
      return c.json({ error: "name is required" }, 400);
    }
    // id（スラッグ）が指定された場合は形式を検証する。空文字は UUID 自動生成にフォールバック。
    if (body.id != null && body.id !== "" && !isValidSlug(body.id)) {
      return c.json(
        {
          error:
            "id must be alphanumeric (with - or _), starting with a letter or number",
        },
        400,
      );
    }
    const id = body.id && body.id !== "" ? body.id : crypto.randomUUID();
    const data: TemplateData = {
      html: body.html,
      width: body.width,
      height: body.height,
    };
    const metadata: TemplateMetadata = {
      name: body.name,
      updatedAt: Date.now(),
    };
    await putTemplate(c.env, id, data, metadata);
    return c.json({ id });
  } catch (e) {
    return c.json({ error: `save failed: ${errorMessage(e)}` }, 500);
  }
});
```

`id` を省略すると `crypto.randomUUID()` で発行します。スラッグ形式の `id` を指定すれば `/ogp/my-release-note` のような読みやすいURLにもできます。

## GET /ogp/:id

保存したテンプレートを画像として配信するのがこのアプリの核心です。

```ts
ogpRoutes.get("/ogp/:id", async (c) => {
  const id = c.req.param("id");
  const template = await getTemplate(c.env, id);
  if (template == null) {
    return c.json({ error: "template not found" }, 404);
  }
  try {
    const meta = await getTemplateMetadata(c.env, id);
    const updatedAt = meta.updatedAt ?? 0;
    const { width: defaultWidth, height: defaultHeight } =
      resolveTemplateSize(template);
    const width = parsePositiveInt(c.req.query("w"), defaultWidth);
    const height = parsePositiveInt(c.req.query("h"), defaultHeight);
    const format = parseFormat(c.req.query("format"));
    const allQuery = c.req.query();
    const params: Record<string, string> = {};
    for (const [key, value] of Object.entries(allQuery)) {
      if (key === "w" || key === "h" || key === "format") continue;
      params[key] = value;
    }
    const html = applyMacros(template.html, params);

    // テンプレート ID + updatedAt + クエリパラメータ + サイズ + 形式ごとにレンダリング結果をキャッシュする。
    // updatedAt をキーに含めることで、テンプレート更新時に古いキャッシュが自然に無効化される。
    const cacheKey = renderCacheKey(["ogp", id, String(updatedAt)], {
      w: String(width),
      h: String(height),
      format,
      ...params,
    });
    const cached = await caches.default.match(cacheKey);
    if (cached) return cached;

    const response = await renderImage(c, html, width, height, format);
    await caches.default.put(cacheKey, response.clone());
    return response;
  } catch (e) {
    return c.json({ error: `render failed: ${errorMessage(e)}` }, 500);
  }
});
```

クエリパラメータの仕様:

- `w` / `h` … 画像サイズの上書き
- `format` … 出力形式（`png` / `webp` / `svg`）
- その他のクエリ … マクロキー名として解釈され、`{{キー名}}` を置換

例:

```
/ogp/abc123?title=新しいタイトル&category=News&w=800&h=420&format=webp
```

キャッシュの仕組みが重要で、`updatedAt` をキャッシュキーに含めることで、テンプレートを更新すると自動的に新しいキャッシュが作られます。Cache API はGETリクエストしかキーにできないため、`renderCacheKey` で内部用のURLを組み立ててキーにしています。

```ts
export function renderCacheKey(
  segments: string[],
  query: Record<string, string>,
): Request {
  const url = new URL("https://ogp-cache.local/");
  url.pathname = "/" + segments.map(encodeURIComponent).join("/");
  for (const [key, value] of Object.entries(query)) {
    url.searchParams.set(key, value);
  }
  return new Request(url.toString());
}
```

## POST /api/render

プレビュー用のエンドポイントもほぼ同じ構造ですが、HTML本体をボディで受け取るため、入力内容のハッシュをキャッシュキーにします。

```ts
renderRoutes.post("/api/render", async (c) => {
  try {
    const body = await c.req.json<{
      html?: string;
      width?: number;
      height?: number;
      format?: RenderFormat;
      params?: Record<string, string>;
    }>();
    if (!isNonEmptyString(body.html)) {
      return c.json({ error: "html is required" }, 400);
    }
    const format = parseFormat(body.format);
    const width = body.width ?? DEFAULT_WIDTH;
    const height = body.height ?? DEFAULT_HEIGHT;
    const html = applyMacros(body.html, body.params ?? {});

    // 同一入力（HTML + パラメータ + サイズ + 形式）のレンダリング結果をキャッシュする。
    const cacheKey = renderCacheKey(["render", await hashString(html)], {
      w: String(width),
      h: String(height),
      format,
    });
    const cached = await caches.default.match(cacheKey);
    if (cached) return cached;

    const response = await renderImage(c, html, width, height, format);
    await caches.default.put(cacheKey, response.clone());
    return response;
  } catch (e) {
    return c.json({ error: `render failed: ${errorMessage(e)}` }, 500);
  }
});
```

# 外部リソースプロキシ

`/api/proxy` は外部のフォント・画像をCORS制約を回避して取得するためのプロキシです。

```ts
proxyRoutes.get("/api/proxy", requireAuth, async (c) => {
  const target = c.req.query("url");
  if (!target) {
    return c.json({ error: "url query parameter is required" }, 400);
  }
  let parsed: URL;
  try {
    parsed = new URL(target);
  } catch {
    return c.json({ error: "invalid url" }, 400);
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    return c.json({ error: "only http/https urls are allowed" }, 400);
  }
  try {
    const upstream = await fetch(parsed.toString());
    const headers = new Headers(upstream.headers);
    headers.set("Access-Control-Allow-Origin", "*");
    return new Response(upstream.body, {
      status: upstream.status,
      headers,
    });
  } catch (e) {
    return c.json({ error: `proxy fetch failed: ${errorMessage(e)}` }, 502);
  }
});
```

`http:` / `https:` 以外のスキームを弾き、レスポンスに `Access-Control-Allow-Origin: *` を付与してフロントエンドから読めるようにしています。認証必須にして外部のSSRF踏み台にならないようにしています。

# AI生成

## システムプロンプト

`src/generate/prompt.ts` で、OGP画像用HTMLを生成するためのシステムプロンプトを組み立てます。プロンプトは厳格な制約を並べていて、要点は以下の通りです。

- キャンバスサイズは `${width}×${height}px`、`body` に `width/height/margin:0/overflow:hidden` を指定
- `<!DOCTYPE html>` で始まり `</html>` で終わる完全なHTMLドキュメント
- Tailwind CSS 使用可否でプロンプトを切り替え（`useTailwind`）
- 外部 `<script>` / `<link>` は禁止、`@import` は Google Fonts のみ許可
- 可変テキストは `{{title}}` `{{category}}` `{{description}}` `{{site}}` `{{cta}}` のマクロプレースホルダで記述
- マークダウンのコードフェンスは使わない、説明文は一切出さない
- satoru-render（litehtml + Skia）でレンダリングされる前提でCSSを書く

さらに「デザインの多様性」セクションで、グラデーション、グラスモーフィズム、大胆なタイポグラフィ、ジオメトリック装飾、ダーク・ネオン、ミニマルなどのアプローチを提示し、毎回同じようなデザインにならないよう指示しています。Tailwind ON/OFF それぞれで2つのデザイン例をプロンプトに埋め込んでいます。

## POST /api/generate

```ts
generateRoutes.post("/api/generate", requireAuth, async (c) => {
  try {
    const body = await c.req.json<{
      prompt?: string;
      model?: string;
      width?: number;
      height?: number;
      useTailwind?: boolean;
    }>();

    if (!isNonEmptyString(body.prompt)) {
      return c.json({ error: "prompt is required" }, 400);
    }

    const model = body.model ?? DEFAULT_MODEL;
    if (!ALLOWED_MODELS.includes(model)) {
      return c.json({ error: "unsupported model" }, 400);
    }

    const width =
      typeof body.width === "number" &&
      Number.isInteger(body.width) &&
      body.width > 0
        ? body.width
        : DEFAULT_WIDTH;
    const height =
      typeof body.height === "number" &&
      Number.isInteger(body.height) &&
      body.height > 0
        ? body.height
        : DEFAULT_HEIGHT;

    const useTailwind = body.useTailwind !== false; // default true

    const systemPrompt = buildSystemPrompt({ width, height, useTailwind });

    const messages = [
      { role: "system", content: systemPrompt },
      { role: "user", content: body.prompt },
    ];

    try {
      // model は文字列変数のため、unknown-model オーバーロードに解決される。
      // stream: true の場合は ReadableStream が返るのでキャストする。
      const rawStream = (await c.env.AI.run(model, {
        messages,
        max_tokens: 4096,
        temperature: 0.8,
        stream: true as const,
      })) as unknown as ReadableStream;

      // qwen3.8-27b は OpenAI 互換形式（choices[0].delta.content / delta.reasoning）で返す。
      // フロントエンドは Llama 形式（{response: "token"}）を期待するため、SSE を正規化する。
      // reasoning トークンは推論過程なので破棄し、content のみを抽出する。
      const normalized = normalizeSseStream(rawStream);
      return new Response(normalized, {
        headers: {
          "content-type": "text/event-stream",
          "cache-control": "no-cache",
          connection: "keep-alive",
        },
      });
    } catch (e) {
      const message = errorMessage(e);
      if (
        message.includes("3036") ||
        message.includes("daily free allocation")
      ) {
        return c.json(
          { error: "AIの無料枠を使い切りました（10,000 neurons/日）" },
          429,
        );
      }
      if (
        message.includes("3040") ||
        message.includes("capacity") ||
        message.includes("Out of capacity")
      ) {
        return c.json(
          {
            error:
              "AIのGPU容量が不足しています。時間をおいて再試行してください",
          },
          503,
        );
      }
      if (message.includes("3007") || message.includes("timeout")) {
        return c.json({ error: "AI生成がタイムアウトしました" }, 504);
      }
      return c.json({ error: `generate failed: ${message}` }, 500);
    }
  } catch (e) {
    return c.json({ error: `generate failed: ${errorMessage(e)}` }, 500);
  }
});
```

利用可能なモデルはハードコードで2つ:

```ts
const MODELS: ModelOption[] = [
  {
    id: "@cf/google/gemma-4-26b-a4b-it",
    label: "Gemma 4 26B",
    hint: "Gemma 4 26B・高品質・マルチモーダル",
    isDefault: true,
  },
  {
    id: "@cf/qwen/qwen3.8-27b",
    label: "Qwen 3.8 27B",
    hint: "Qwen 3.8 27B・マルチモーダル対応",
    isDefault: false,
  },
];
```

`stream: true` でSSEストリームを取得し、`normalizeSseStream` で形式を正規化してからフロントエンドに流します。エラーレスポンスはWorkers AIのエラーコード（3036/3040/3007）を見て適切なステータスコードに変換しています。

## SSEの正規化

`src/generate/sse.ts` がストリームの正規化を担います。qwen3.8-27b はOpenAI互換形式（`choices[0].delta.content`）で返すのに対し、フロントエンドはLlama形式（`{response: "token"}`）を期待するため、変換が必要です。

```ts
const encoder = new TextEncoder();
const decoder = new TextDecoder();

// 単一の SSE フレーム（`data: ...` 行の集合）を処理し、正規化済みの出力を controller に流す。
function processFrame(
  frame: string,
  controller: TransformStreamDefaultController<Uint8Array>,
): void {
  for (const line of frame.split("\n")) {
    const trimmed = line.replace(/^\r/, "").trimStart();
    if (!trimmed.startsWith("data:")) continue;
    const payload = trimmed.slice(5).trim();
    if (payload === "[DONE]") {
      controller.enqueue(encoder.encode("data: [DONE]\n\n"));
      continue;
    }
    try {
      const data = JSON.parse(payload);
      // OpenAI 互換形式（qwen3.8-27b）: choices[0].delta.content を抽出
      const content = data?.choices?.[0]?.delta?.content;
      if (typeof content === "string" && content !== "") {
        controller.enqueue(
          encoder.encode(`data: ${JSON.stringify({ response: content })}\n\n`),
        );
      }
      // reasoning トークンは破棄
      // Llama 形式（念のためフォールバック）: data.response
      if (typeof data.response === "string" && data.response !== "") {
        controller.enqueue(
          encoder.encode(
            `data: ${JSON.stringify({ response: data.response })}\n\n`,
          ),
        );
      }
    } catch {
      // JSON パース失敗は無視
    }
  }
}

export function normalizeSseStream(rawStream: ReadableStream): ReadableStream {
  let sseBuffer = "";

  return rawStream.pipeThrough(
    new TransformStream({
      transform(chunk, controller) {
        sseBuffer += decoder.decode(chunk, { stream: true });
        const frames = sseBuffer.split("\n\n");
        sseBuffer = frames.pop() ?? "";
        for (const frame of frames) {
          processFrame(frame, controller);
        }
      },
      flush(controller) {
        // 残りのバッファを処理
        if (sseBuffer) {
          processFrame(sseBuffer, controller);
        }
      },
    }),
  );
}
```

`reasoning` トークン（推論過程）は破棄し、`content` のみを抽出して `{ response: "..." }` 形式に包み直します。SSEフレームは `\n\n` で区切られるため、バッファリングして不完全なフレームを保持する仕組みも入っています。

## フロントエンドのAI生成パネル

`frontend/src/components/GeneratePanel.tsx` がAI生成のUIです。`streamGenerate` でSSEを読み込み、トークンが来るたびに `accumulatedRef.current` に蓄積してプレビュー表示します。

```ts
handleRef.current = streamGenerate(
  { prompt: trimmed, model: selectedModel, width, height, useTailwind },
  {
    onChunk: (token) => {
      accumulatedRef.current += token;
      setOutput(accumulatedRef.current);
      setTokenCount((c) => c + 1);
    },
    onDone: () => {
      const clean = stripCodeFences(accumulatedRef.current);
      handleRef.current = null;
      setGenerating(false);
      if (!clean) {
        setError(
          "生成された HTML が空です。プロンプトを変えてもう一度お試しください。",
        );
        return;
      }
      onInsert(clean);
      notify("AIでHTMLを生成し、エディタに挿入しました");
      onClose();
    },
    onError: (e) => {
      handleRef.current = null;
      setGenerating(false);
      setError(e.message || "生成に失敗しました");
    },
  },
);
```

完了時に `stripCodeFences` で markdown のコードフェンスを取り除き、エディタに挿入します。パネルを閉じると進行中のストリームをキャンセルする制御も入っています。

`frontend/src/api.ts` の `streamGenerate` は `AbortController` でキャンセル可能なハンドルを返します。

```ts
export function streamGenerate(
  opts: {
    prompt: string;
    model?: string;
    width?: number;
    height?: number;
    useTailwind?: boolean;
  },
  handlers: {
    onChunk: (token: string) => void;
    onDone: () => void;
    onError: (e: Error) => void;
  },
): GenerateHandle {
  const controller = new AbortController();

  const promise = (async () => {
    try {
      const res = await fetch("/api/generate", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: opts.prompt,
          model: opts.model,
          width: opts.width,
          height: opts.height,
          useTailwind: opts.useTailwind,
        }),
        signal: controller.signal,
      });

      await ensureOk(res, { extractJsonError: true });

      const body = res.body;
      if (!body)
        throw new ApiError("ストリームを取得できませんでした", res.status);

      const reader = body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // SSE フレームは \n\n で区切られる。最後の断片は不完全の可能性があるため保持する。
        const frames = buffer.split("\n\n");
        buffer = frames.pop() ?? "";

        for (const frame of frames) {
          for (const rawLine of frame.split("\n")) {
            const line = rawLine.replace(/\r$/, "").trimStart();
            if (!line.startsWith("data:")) continue;
            const payload = line.slice(5).trim();
            if (payload === "[DONE]") {
              handlers.onDone();
              return;
            }
            try {
              const data = JSON.parse(payload) as {
                response?: string;
                usage?: unknown;
              };
              // response が空で usage のみ存在する会計フレームは無視
              if ((!data.response || data.response === "") && data.usage)
                continue;
              if (typeof data.response === "string" && data.response !== "") {
                handlers.onChunk(data.response);
              }
            } catch {
              // JSON パース失敗は無視
            }
          }
        }
      }

      handlers.onDone();
    } catch (e) {
      // キャンセル時はサイレントに終了
      if (controller.signal.aborted) return;
      handlers.onError(e instanceof Error ? e : new Error(String(e)));
    }
  })();

  return { cancel: () => controller.abort(), promise };
}
```

# 認証

## 初回セットアップとセッション

`src/auth.ts` が認証の中核です。パスワードは PBKDF2（SHA-256・100,000回）でハッシュし、ソルト付きでKVに保存します。

```ts
const PBKDF2_ITERATIONS = 100000;

export async function hashPassword(password: string): Promise<string> {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const keyMaterial = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(password),
    "PBKDF2",
    false,
    ["deriveBits"],
  );
  const bits = await crypto.subtle.deriveBits(
    {
      name: "PBKDF2",
      salt,
      iterations: PBKDF2_ITERATIONS,
      hash: "SHA-256",
    },
    keyMaterial,
    256,
  );
  const hash = new Uint8Array(bits);
  return `${encodeBase64(salt)}:${encodeBase64(hash)}`;
}
```

セッションは `crypto.randomUUID()` で生成したトークンをKVに保存し、`__session__:` プレフィックスを付けます。TTLは7日。

```ts
const SESSION_TTL_MS = 7 * 24 * 60 * 60 * 1000; // 7 days

export async function createSession(
  env: Env,
  adminId: string,
): Promise<string> {
  const token = crypto.randomUUID();
  const record: SessionRecord = {
    adminId,
    expiresAt: Date.now() + SESSION_TTL_MS,
  };
  await kv(env).put(sessionKey(token), JSON.stringify(record), {
    expirationTtl: Math.floor(SESSION_TTL_MS / 1000),
  });
  return token;
}
```

`getSession` では期限チェックに加え、セッションの `adminId` が実際に存在する管理者かを検証します。管理者が削除済みならセッションを無効化します。

## CookieのSecure属性

`src/middleware.ts` で、ローカル開発（http://localhost）と本番（https://）でCookieの `Secure` 属性を切り替えています。

```ts
export function sessionCookieHeader(
  c: Context,
  token: string,
  maxAge: number,
): string {
  const secure = c.req.url.startsWith("https://");
  const secureAttr = secure ? "; Secure" : "";
  return `${SESSION_COOKIE}=${token}; HttpOnly; SameSite=Lax${secureAttr}; Path=/; Max-Age=${maxAge}`;
}
```

`requireAuth` ミドルウェアはCookieからトークンを取り出し、`getSession` で検証します。

```ts
export const requireAuth: MiddlewareHandler<AppEnv> = async (c, next) => {
  const cookies = parseCookies(c.req.header("Cookie"));
  const token = cookies[SESSION_COOKIE];
  if (!token) {
    return c.json({ error: "unauthorized" }, 401);
  }
  const adminId = await getSession(c.env, token);
  if (adminId == null) {
    return c.json({ error: "unauthorized" }, 401);
  }
  c.set("adminId", adminId);
  await next();
};
```

# デプロイ

```bash
# 依存のインストール
pnpm install

# フロントエンドのビルド（public/ に出力）
pnpm build

# ローカル開発サーバー起動（http://localhost:8787）
pnpm dev

# Cloudflare にデプロイ
pnpm deploy
```

KVネームスペースは `wrangler.jsonc` の `kv_namespaces` で `id` を指定していないため、`wrangler deploy` 時に自動作成され、そのIDが設定ファイルに書き戻されます。AI binding も設定済みで、デプロイ時に自動的に有効化されます。

初回起動時はセットアップ画面が表示され、管理者のIDとパスワードを登録すると以降はその認証情報でログインして編集画面を利用できます。

# 制限事項

## CPU時間

レンダリングはCloudflareの10ms CPU制限を確実に超過します。アクセス数が少ない場合や、同じOGP画像に対するアクセス（キャッシュヒット）が多い場合はそのまま動きますが、そうでない場合は$5のPaidプランが必要です。

## Workers AIのNeurons

AI生成機能は Workers AI の GPU リソース（Neurons）を消費します。

- 無料枠は 10,000 Neurons/日
- 1回の生成あたり約 0.07〜0.5 Neurons を消費
- `wrangler dev` のローカル開発でも推論は Cloudflare アカウントに接続して実行されるため、枠を消費します
- 日次無料枠を使い切るとエラー（429）。翌日 00:00 UTC にリセット
- GPU混雑時は一時的に利用できない場合があります（503）

# まとめ

前回の `cloudflare-ogp` が「ライブラリとしてOGP画像を生成する」ものであったのに対し、今回は「ブラウザ上でHTMLを編集し、テンプレートとして保存し、URLで配信できる統合環境」を作りました。

ポイントを振り返ると:

- **satoru-render** でヘッドレスブラウザ不要のHTML/CSS → 画像レンダリング（Tailwindも使える）
- **マクロ機能** で `{{キー名}}` をパラメータ化し、配信時にクエリで上書き可能
- **KV + Cache API** でテンプレート保存とレンダリング結果のキャッシュ。`updatedAt` で自動キャッシュ無効化
- **Workers AI** で自然言語からOGP用HTMLをストリーミング生成
- **`/api/proxy`** でCORS回避しつつ外部リソースを取得
- **PBKDF2 + セッション** で編集画面を保護

Cloudflare Workersの機能の範囲内でここまで出来るので、OGP画像生成意外にも応用が利きそうです。
