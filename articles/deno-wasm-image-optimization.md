---
title: "Deno Deploy で無料画像最適化(avif対応)"
emoji: "🐡"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [deno, deploy, wasm, avif, webp]
published: true
---

# Deno Deploy の Web Cache API サポート

2024/8/27 に Deno Deploy が Web Cache API をサポートしました。

https://deno.com/blog/deploy-cache-api

これにより、生成したコンテンツをキャッシュして高速に配信することができるようになりました。

# 画像最適化

画像の最適化は、Web サイトのパフォーマンスを向上させるために重要です。本来なら事前に最適な状態にしておくのが望ましいのですが、状況に応じてサイズや品質を調整しなければならないこともあります。しかし画像の変換は CPU を多く消費するため、時間のかかる処理です。そのため一度変換した画像をキャッシュすることによって、処理時間の短縮を図る必要があります。

# Deno Deploy と Cloudflare Workers の無料枠の比較

画像最適化は Cloudflare 用の記事をこちらで書いています

https://next-blog.croud.jp/contents/161ec5f7-3b10-4ac4-9dd9-7fadf744a39c
https://next-blog.croud.jp/contents/aebd7b12-a070-4573-b8f1-600904a1ebbb

今回は Deno Deploy での画像最適化を行います。その前に、Deno Deploy と Cloudflare Workers の無料枠を比較してみます。

https://deno.com/deploy/pricing
https://developers.cloudflare.com/workers/platform/pricing/

重要なところだけ抜粋すると以下のようになります。

|          | Deno Deploy     | Cloudflare Workers |
| -------- | --------------- | ------------------ |
| Requests | 1,000,000/month | 100,000/day        |
| CPU      | 50ms            | 10ms               |
| Size     | -               | 1MB(圧縮時)        |

無料枠のリクエスト数は Deno Deploy が月単位で、Cloudflare Workers が日単位です。どちらも普通に使うには十分な数が用意されています。ちなみに Vercel で画像最適化をやると無料枠は 1000/月です。

CPU に関しては、Cloudflare の 10ms はけっこうキツイです。2K 解像度をを Webp に変換しようとすると、かなりの確率で失敗します。デジカメで撮った写真をそのままアップロードしているようなケースでは問題が発生します。

サイズに関しては、プログラムコードを圧縮したときの値です。Deno Deploy は特に制限がないようです。Cloudflare の 1MB は、普通のコードなら何の問題もないのですが、画像変換に関しては wasm を使うことになるためそれなりにタイトです。そのため Workers 用の画像変換ライブラリには avif エンコーダを含めることが出来ませんでした。avif エンコーダは圧縮しても 1MB を超えます。

また、Cloudflare ではキャッシュ機能を利用するのにこちらはカスタムドメインの設定が必要ですが、Deno Deploy の Cache はドメインの設定は不要です。

# 画像変換プログラム

画像変換にはこちらのライブラリを使います。Cloudflare Workers 用に作ったものに avif エンコード機能を追加しています。

https://www.npmjs.com/package/wasm-image-optimization-avif

```ts
import { optimizeImage } from "npm:wasm-image-optimization-avif/esm";

const isValidUrl = (url: string) => {
  try {
    new URL(url);
    return true;
  } catch (_e) {
    return false;
  }
};

const isType = (accept: string | null, type: string) => {
  return (
    accept
      ?.split(",")
      .map((format) => format.trim())
      .some((format) => [`image/${type}`, "*/*", "image/*"].includes(format)) ??
    true
  );
};

Deno.serve(async (request) => {
  const url = new URL(request.url);
  const params = url.searchParams;
  const type = ["avif", "webp", "png", "jpeg"].find(
    (v) => v === params.get("type")
  ) as "avif" | "webp" | "png" | "jpeg" | undefined;
  const accept = request.headers.get("accept");
  const isAvif = isType(accept, "avif");
  const isWebp = isType(accept, "webp");

  const cache = await caches.open(
    `image-${isAvif ? "-avif" : ""}${isWebp ? "-webp" : ""}`
  );

  const cached = await cache.match(request);
  if (cached) {
    return cached;
  }

  const imageUrl = params.get("url");
  if (!imageUrl || !isValidUrl(imageUrl)) {
    return new Response("url is required", { status: 400 });
  }

  if (isAvif) {
    url.searchParams.append("avif", isAvif.toString());
  } else if (isWebp) {
    url.searchParams.append("webp", isWebp.toString());
  }

  const cacheKey = new Request(url.toString());
  const cachedResponse = await cache.match(cacheKey);
  if (cachedResponse) {
    return cachedResponse;
  }

  const width = params.get("w");
  const quality = params.get("q");

  const [srcImage, contentType] = await fetch(imageUrl)
    .then(async (res) =>
      res.ok
        ? ([await res.arrayBuffer(), res.headers.get("content-type")] as const)
        : []
    )
    .catch(() => []);

  if (!srcImage) {
    return new Response("image not found", { status: 404 });
  }

  if (contentType && ["image/svg+xml", "image/gif"].includes(contentType)) {
    const response = new Response(srcImage, {
      headers: {
        "Content-Type": contentType,
        "Cache-Control": "public, max-age=31536000, immutable",
      },
    });
    cache.put(request, response.clone());
    return response;
  }

  const format =
    type ??
    (isAvif
      ? "avif"
      : isWebp
      ? "webp"
      : contentType === "image/jpeg"
      ? "jpeg"
      : "png");
  const image = await optimizeImage({
    image: srcImage,
    width: width ? parseInt(width) : undefined,
    quality: quality ? parseInt(quality) : undefined,
    format,
  });
  const response = new Response(image, {
    headers: {
      "Content-Type": `image/${format}`,
      "Cache-Control": "public, max-age=31536000, immutable",
      date: new Date().toUTCString(),
    },
  });
  cache.put(request, response.clone());
  return response;
});
```

以下のような URL でアクセスすることで画像を最適化することが出来ます。サイズもパラメータで指定することが出来ます。Next.js の画像最適化とパラメータの互換性があるので next.config.js で Deno Deploy の対象アドレスを設定すれば、Vercel の画像最適化と同じように使うことが出来ます。

https://deno-image.deno.dev/?url=https://raw.githubusercontent.com/SoraKumo001/cloudflare-workers-image-optimization/master/images/test01.png

https://deno-image.deno.dev/?url=https://raw.githubusercontent.com/SoraKumo001/cloudflare-workers-image-optimization/master/images/test01.png&w=256

png を avif に変換しているのを確認できます。二回目以降のアクセスにはキャッシュが使われるので 13ms 程度で結果が返ってきます。

# まとめ

Deno Deploy の欠点はしばらくアクセスがなかった場合の Cold Starts で遅延が発生することです。それ以外はコードサイズに制限がないぶん Cloudflare よりも扱いやすいと言えます。今回 Web Cache API のサポートが追加されたことで、使い勝手が格段に良くなりました。ランタイムが Deno だからと敬遠せず、一度試してみてください。
