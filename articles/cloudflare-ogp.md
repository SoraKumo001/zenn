---
title: "Cloudflare Workers で OGP 画像を生成する"
emoji: "📚"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [cloudflare, workers, ogp, react, satori]
published: false
---

# OGP 画像生成に使うライブラリ

| ライブラリ              | 用途                                                    |
| ----------------------- | ------------------------------------------------------- |
| satori                  | 仮想 DOM を SVG 形式に変換                              |
| yoga-wasm-web           | satori が使用しているレイアウトエンジン                 |
| svg2png-wasm            | SVG を PNG へ変換                                       |
| wasm-image-optimization | satori 未対応の WebP や Avif 画像を取り込めるように変換 |

出回っているサンプルは svg から png の変換に resvg を使っているものが多いですが svg2png-wasm の方が高速で安定しています。

# コード

src/createOGP.ts

フォントと絵文字を必要に応じてダウンロードしてキャッシュに保存し、png 形式で OGP 画像を作成するコードです。

```ts
import satori, { init } from "satori/wasm";
import initYoga from "yoga-wasm-web";
import yogaWasm from "yoga-wasm-web/dist/yoga.wasm";
import { svg2png, initialize } from "svg2png-wasm";
import wasm from "svg2png-wasm/svg2png_wasm_bg.wasm";

init(await initYoga(yogaWasm));
await initialize(wasm);

const cache = await caches.open("cloudflare-ogp");

type Weight = 100 | 200 | 300 | 400 | 500 | 600 | 700 | 800 | 900;
type FontStyle = "normal" | "italic";
type FontSrc = {
  data: ArrayBuffer | string;
  name: string;
  weight?: Weight;
  style?: FontStyle;
  lang?: string;
};
type Font = Omit<FontSrc, "data"> & { data: ArrayBuffer | ArrayBufferView };

const downloadFont = async (fontName: string) => {
  return await fetch(
    `https://fonts.googleapis.com/css2?family=${encodeURI(fontName)}`
  )
    .then((res) => res.text())
    .then(
      (css) =>
        css.match(/src: url\((.+)\) format\('(opentype|truetype)'\)/)?.[1]
    )
    .then(async (url) => {
      return url !== undefined
        ? fetch(url).then((v) =>
            v.status === 200 ? v.arrayBuffer() : undefined
          )
        : undefined;
    });
};

const getFonts = async (
  fontList: string[],
  ctx: ExecutionContext
): Promise<Font[]> => {
  const fonts: Font[] = [];
  for (const fontName of fontList) {
    const cacheKey = `http://font/${encodeURI(fontName)}`;

    const response = await cache.match(cacheKey);
    if (response) {
      fonts.push({
        name: fontName,
        data: await response.arrayBuffer(),
        weight: 400,
        style: "normal",
      });
    } else {
      const data = await downloadFont(fontName);
      if (data) {
        ctx.waitUntil(cache.put(cacheKey, new Response(data)));
        fonts.push({ name: fontName, data, weight: 400, style: "normal" });
      }
    }
  }
  return fonts.flatMap((v): Font[] => (v ? [v] : []));
};

const createLoadAdditionalAsset = ({
  ctx,
  emojis,
}: {
  ctx: ExecutionContext;
  emojis: {
    url: string;
    upper?: boolean;
  }[];
}) => {
  const getEmojiSVG = async (code: string) => {
    const cacheKey = `http://emoji/${encodeURI(
      JSON.stringify(emojis)
    )}/${code}`;
    for (const { url, upper } of emojis) {
      const emojiURL = `${url}${
        upper === false ? code.toLocaleLowerCase() : code.toUpperCase()
      }.svg`;
      let response = await cache.match(cacheKey);
      if (!response) {
        response = await fetch(emojiURL);
        if (response.status === 200) {
          ctx.waitUntil(cache.put(cacheKey, response.clone()));
        }
      }
      if (response.status === 200) {
        return await response.text();
      }
    }
    return undefined;
  };

  const loadEmoji = async (segment: string): Promise<string | undefined> => {
    const codes = Array.from(segment).map((char) => char.codePointAt(0));
    const isZero = codes.includes(0x200d);
    const code = codes
      .filter((code) => isZero || code !== 0xfe0f)
      .map((v) => v?.toString(16))
      .join("-");
    return getEmojiSVG(code);
  };

  const loadAdditionalAsset = async (code: string, segment: string) => {
    if (code === "emoji") {
      const svg = await loadEmoji(segment);
      if (!svg) return segment;
      return `data:image/svg+xml;base64,${btoa(svg)}`;
    }
    return [];
  };

  return loadAdditionalAsset;
};

export const createOGP = async (
  element: JSX.Element,
  {
    fonts,
    emojis,
    ctx,
    width,
    height,
    scale,
  }: {
    ctx: ExecutionContext;
    fonts: string[];
    emojis?: {
      url: string;
      upper?: boolean;
    }[];
    width: number;
    height?: number;
    scale?: number;
  }
) => {
  const fontList = await getFonts(fonts, ctx);
  const svg = await satori(element, {
    width,
    height,
    fonts: fontList,
    loadAdditionalAsset: emojis
      ? createLoadAdditionalAsset({ ctx, emojis })
      : undefined,
  });
  return await svg2png(svg, { scale });
};
```

## src/index.tsx

こちらは OGP 用の仮想 DOM を作っています。外部から受け取る画像に関しては、satori で取り扱えるように png 形式に変換するようにしています。

こちらは必要に応じてカスタマイズしてください。

```tsx
import React from "react";
import { createOGP } from "./createOGP";
import { optimizeImage } from "wasm-image-optimization";

const convertImage = async (url: string | null) => {
  const response = url ? await fetch(url) : undefined;
  if (response) {
    const contentType = response.headers.get("Content-Type");
    const imageBuffer = await response.arrayBuffer();
    if (contentType?.startsWith("image/")) {
      if (["image/png", "image/jpeg"].includes(contentType)) {
        return [contentType, imageBuffer as ArrayBuffer] as const;
      }
      const image = await optimizeImage({ image: imageBuffer, format: "png" });
      if (image) {
        return ["image/png", image] as const;
      }
    }
  }
  return [];
};

const outputOGP = async (
  request: Request,
  _env: object,
  ctx: ExecutionContext
): Promise<Response> => {
  const url = new URL(request.url);
  if (url.pathname !== "/") {
    return new Response(null, { status: 404 });
  }

  const name = url.searchParams.get("name") ?? "Name";
  const title = url.searchParams.get("title") ?? "Title";
  const image = url.searchParams.get("image");
  const cache = await caches.open("cloudflare-ogp");
  const cacheKey = new Request(url.toString());
  const cachedResponse = await cache.match(cacheKey);
  if (cachedResponse) {
    return cachedResponse;
  }

  const [imageType, imageBuffer] = await convertImage(image);

  const ogpNode = (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        width: "100%",
        height: "100%",
        padding: "16px 24px",
        overflow: "hidden",
        fontFamily: "NotoSansJP",
      }}
    >
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          height: "100%",
          border: "solid 16px #0044FF",
          borderRadius: "24px",
          boxSizing: "border-box",
          background: "linear-gradient(to bottom right, #ffffff, #d3eef9)",
        }}
      >
        <div
          style={{
            display: "flex",
            flex: 1,
          }}
        >
          {image && (
            <img
              style={{
                borderRadius: "100%",
                padding: "8px",
                marginRight: "16px",
                position: "absolute",
                opacity: 0.4,
              }}
              width={480}
              height={480}
              src={
                imageBuffer
                  ? `data:${imageType};base64,${btoa(
                      Array.from(new Uint8Array(imageBuffer))
                        .map((v) => String.fromCharCode(v))
                        .join("")
                    )}`
                  : undefined
              }
              alt=""
            />
          )}
          <h1
            style={{
              display: "block",
              flex: 1,
              fontSize: 72,
              alignItems: "center",
              justifyContent: "center",
              padding: "0 42px",
              wordBreak: "break-all",
              textOverflow: "ellipsis",
              lineClamp: 4,
              lineHeight: "64px",
            }}
          >
            {title}
          </h1>
        </div>
        <div
          style={{
            width: "100%",
            justifyContent: "flex-end",
            fontSize: 48,
            padding: "0 32px 32px 0",
            color: "#CC3344",
          }}
        >
          {name}
        </div>
      </div>
    </div>
  );
  const png = await createOGP(ogpNode, {
    ctx,
    scale: 0.7,
    width: 1200,
    height: 630,
    fonts: [
      "Noto Sans",
      "Noto Sans Math",
      "Noto Sans Symbols",
      // 'Noto Sans Symbols 2',
      "Noto Sans JP",
      // 'Noto Sans KR',
      // 'Noto Sans SC',
      // 'Noto Sans TC',
      // 'Noto Sans HK',
      // 'Noto Sans Thai',
      // 'Noto Sans Bengali',
      // 'Noto Sans Arabic',
      // 'Noto Sans Tamil',
      // 'Noto Sans Malayalam',
      // 'Noto Sans Hebrew',
      // 'Noto Sans Telugu',
      // 'Noto Sans Devanagari',
      // 'Noto Sans Kannada',
    ],
    emojis: [
      {
        url: "https://cdn.jsdelivr.net/gh/svgmoji/svgmoji/packages/svgmoji__noto/svg/",
      },
      {
        url: "https://openmoji.org/data/color/svg/",
      },
    ],
  });
  const response = new Response(png, {
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
  fetch: outputOGP,
};
```

## パラメータ

| parameter | description                                                                                                                              |
| --------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| title     | The title of the page                                                                                                                    |
| name      | The name of the person or organization                                                                                                   |
| image     | URL of the image to be used as the Open Graph image <br> (WebP and AVIF images are automatically converted to PNG format for processing) |

## 実行結果

デプロイした場合は、そのドメイン名に置き換えてください。

http://127.0.0.1:8787/?title=%E3%82%BF%E3%82%A4%E3%83%88%E3%83%AB&name=%E5%90%8D%E5%89%8D&image=https://raw.githubusercontent.com/SoraKumo001/cloudflare-ogp/refs/heads/master/sample/image.jpg

![](/images/cloudflare-ogp/2025-02-02-16-18-54.png)

## まとめ

Cloudflare Workers を使用して OGP を生成する方法について説明しました。無料プランで利用する場合は、10 万回/日まで実行可能です。また、カスタムドメインを使って CDN のキャッシュが使えるようにしておけば、ほぼ無制限で利用できる状況になります。
