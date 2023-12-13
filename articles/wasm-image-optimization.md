---
title: "Cloudflare Workers の無料プランで画像を圧縮する"
emoji: "🐷"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [nextjs, cloudflare, wasm, workers, WebAssembly]
published: true
---

# Cloudflare Workers の無料プランで画像を圧縮する

Next.js のプロジェクトを Cloudflare にデプロイする場合、問題になるのが Vercel が提供している画像の自動圧縮機能です。これを Cloudflare でも実現するためには、Cloudflare Workers が使えそうですが、無料プランでは画像の圧縮機能を提供していません。意地でも無料で実現したいという乞食精神に乗っ取り、画像変換コードを書くことにしました。

# 画像の変換方法

Cloudflare Workers では、一度のリクエストで処理できる CPU 時間は 10ms です。非同期アクセスの待ち時間は含まれないので、純粋な処理時間です。高速に処理するのならネイティブコードを使うのが一番ですが、もちろん使えません。そこで、WebAssembly を使うことにしました。最近 WebAssembly というと Rust が主流ですが、libwebp を直接使いたいので、今回は C++を選択しました。

# コンパイラは Emscripten の emcc を使う

Emscripten は、C++ を JavaScript にコンパイルするためのツールです。これを使うことで、C++ で書いたコードを WebAssembly にコンパイルすることが出来ます。ということで、早速作ることにしました。

# Emscripten では libpng と libjpeg がすぐに使える

Emscripten は既存のライブラリを取り込む仕組みとして ports というものを提供しています。これを使うことで、コンパイル時にオプション指定するだけで libpng や libjpeg を組み込んだ状態でビルドすることが出来ます。ただし、libwebp は組み込まれていません。自分でソースをダウンロードしてビルドに混ぜる必要があります。

# Emscripten には SDL2 もいる

SDL2 は、画像の読み込みや描画を簡単に行うことが出来るライブラリです。これも ports に含まれています。libpng、libjpeg、libwebp を使えるようにしておけば、SDL にバイナリを放り込むだけで画像を読み込むことが出来ます。ただし webp 出力はサポートされていないので、そこは libwebp の命令を使うことになります。

# 画像変換のコード

ということで作りました。ものすごく簡単に書けるのですが、何故かネット上ではこういうコードは見つかりませんでした。

```cpp
#include <emscripten.h>
#include <emscripten/bind.h>
#include <emscripten/val.h>
#include <webp/encode.h>
#include <SDL_image.h>
#include <SDL2/SDL.h>

using namespace emscripten;

val optimize(std::string img_in, float width, float height, float quality) {
    SDL_RWops* rw = SDL_RWFromConstMem(img_in.c_str(), img_in.size());
    if (!rw) {
        return val::null();
    }

    SDL_Surface* srcSurface = IMG_Load_RW(rw, 1);
    if (!srcSurface) {
        SDL_FreeRW(rw);
        return val::null();
    }

    int srcWidth = srcSurface->w;
    int srcHeight = srcSurface->h;
    if (srcWidth == 0 || srcHeight == 0) {
        SDL_FreeSurface(srcSurface);
        return val::null();
    }

    int outWidth = width?width:srcWidth;
    int outHeight = height?height:srcHeight;
    float aspectSrc = static_cast<float>(srcWidth) / srcHeight;
    float aspectDest = outWidth / outHeight;

    if (aspectSrc > aspectDest) {
        outHeight = outWidth / aspectSrc;
    } else {
        outWidth = outHeight * aspectSrc;
    }

    SDL_Surface* newSurface = SDL_CreateRGBSurfaceWithFormat(0, static_cast<int>(outWidth), static_cast<int>(outHeight), 32, SDL_PIXELFORMAT_RGBA32);
    if (!newSurface) {
        SDL_FreeSurface(srcSurface);
        return val::null();
    }

    SDL_BlitScaled(srcSurface, nullptr, newSurface, nullptr);

    SDL_FreeSurface(srcSurface);

    uint8_t* img_out = nullptr;
    int stride = static_cast<int>(outWidth) * 4;
    size_t size = WebPEncodeRGBA(reinterpret_cast<uint8_t*>(newSurface->pixels), static_cast<int>(outWidth), static_cast<int>(outHeight), stride, quality, &img_out);

    if (size == 0 || !img_out) {
        SDL_FreeSurface(newSurface);
        return val::null();
    }

    val result = val::global("Uint8Array").new_(typed_memory_view(size, img_out));
    WebPFree(img_out);
    SDL_FreeSurface(newSurface);

    return result;
}

EMSCRIPTEN_BINDINGS(my_module) {
  function("optimize", &optimize);
}
```

# Cloudflare Workers で動くパッケージを作る

Cloudflare Workers の JavaScript から WebAssembly を呼び出すには、wasm を import する必要があります。一般的な V8 エンジンのように、ネットワーク越しに wasm をダウンロードしてくることは出来ません。そのため、必ず wasm を含んだパッケージを作る必要があります。

ちなみに Cloudflare Workers では、Worker あたりのパッケージサイズが 1MB 以内と決められています。wasm のサイズは 1MB を超えていましたが、パッケージとして圧縮されると 400KB 程度になるのでセーフでした。

https://www.npmjs.com/package/wasm-image-optimization

# Cloudflare Workers で動かす

先程の wasm-image-optimization パッケージを使って、Next.js の画像圧縮パラメータと互換性をもたせた Worker を作りました。これを使うと、Next.js の画像圧縮パラメータをそのまま使うことが出来ます。

```ts
import { optimizeImage } from "wasm-image-optimization";
export interface Env {}

const isValidUrl = (url: string) => {
  try {
    new URL(url);
    return true;
  } catch (err) {
    return false;
  }
};

const handleRequest = async (
  request: Request,
  _env: Env,
  ctx: ExecutionContext
): Promise<Response> => {
  const url = new URL(request.url);
  const params = url.searchParams;
  const imageUrl = params.get("url");
  if (!imageUrl || !isValidUrl(imageUrl)) {
    return new Response("url is required", { status: 400 });
  }
  const cache = caches.default;
  const cachedResponse = await cache.match(
    new Request(url.toString(), request)
  );
  if (cachedResponse) {
    return cachedResponse;
  }

  const width = params.get("w");
  const quality = params.get("q");

  const srcImage = await fetch(imageUrl, { cf: { cacheKey: imageUrl } })
    .then((res) => (res.ok ? res.arrayBuffer() : null))
    .catch((e) => null);

  if (!srcImage) {
    return new Response("image not found", { status: 404 });
  }
  const image = await optimizeImage({
    image: srcImage,
    width: width ? parseInt(width) : undefined,
    quality: quality ? parseInt(quality) : undefined,
  });
  const response = new Response(image, {
    headers: {
      "Content-Type": "image/webp",
      "Cache-Control": "public, max-age=31536000, immutable",
    },
  });
  ctx.waitUntil(cache.put(request, response.clone()));
  return response;
};

export default {
  fetch: handleRequest,
};
```

ちなみに next.config.js の設定で Workers のデプロイ先のアドレスを指定することによって、Workers で画像を圧縮することが出来ます。

```js
/**
 * @type { import("next").NextConfig}
 */
const config = {
  images: {
    path: "https://xxx.yyy.workers.dev/",
  },
};
export default config;
```

# 変換してみる

1024\*1024 の 266KB の画像を`?url=https://xxx&w=256&q=75`というようなオプションで変換してみます。

![](/images/wasm-image-optimization/2023-12-13-09-08-07.jpg)

256\*256 の画像になりました。サイズは 18.4KB です。

![](/images/wasm-image-optimization/2023-12-13-09-09-31.webp)

# まとめ

Cloudflare Workers は、無料プランでも 100,000 リクエスト/日まで無料で使えます。それだけあれば、無料生活ユーザーには十分なのではないでしょうか。無ければ作る、それが無料で乗り切る秘訣です。
