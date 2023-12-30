---
title: "Cloudflare Workers の無料プランで画像を圧縮する その2"
emoji: "🐷"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [nextjs, cloudflare, wasm, workers, WebAssembly]
published: true
---

# accept で変換形式を出し分ける

https://zenn.dev/sora_kumo/articles/wasm-image-optimization

こちらの続きになります。

前回は、Cloudflare Workers で画像を圧縮し、Webp 形式で出力するを紹介しました。今回は、Accept ヘッダーに応じて変換形式を出し分ける方法を紹介します。そのためにはまず、WebAssembly で画像を変換するコードに、jpeg と png の出力を追加する必要があります。ということで実装しました。

# 画像変換のコード

前回のコードに IMG_SavePNG_RW と IMG_SaveJPG_RW を追加しています。SDL の標準機能としてサポートされているので簡単に実装できましたと言いたいところなのですが、ファイルではなくバイナリで出力するサンプルがネット上に見つからず、やり方を見つけ出すのに苦労しました。最終的に MemoryRW というクラスを作って、そこでバイナリを受け取るようにしました。

前回からの追加で avif の入力もサポートしています。ただし出力機能は断念しました。理由はエンコード部分のサイズがでかすぎて、圧縮状態でも 1MB を遥かに超える wasm が生成されたからです。今後 Cloudflare Workers のフリープランの許容サイズが増えたら実装を加えます。

```cpp
#include <emscripten.h>
#include <emscripten/bind.h>
#include <emscripten/val.h>
#include <webp/encode.h>
#include <SDL_image.h>
#include <SDL2/SDL.h>

using namespace emscripten;

class MemoryRW
{
public:
    MemoryRW()
    {
        m_rw = SDL_AllocRW();
        m_rw->hidden.unknown.data1 = &m_buffer;
        m_rw->write = MemWrite;
        m_rw->close = MemClose;
    }
    ~MemoryRW()
    {
        SDL_FreeRW(m_rw);
    }
    operator SDL_RWops *() const { return m_rw; }
    size_t size() const { return m_buffer.size(); }
    const uint8_t *data() const { return m_buffer.data(); }

protected:
    static size_t MemWrite(SDL_RWops *context, const void *ptr, size_t size, size_t num)
    {
        std::vector<uint8_t> *buffer = (std::vector<uint8_t> *)context->hidden.unknown.data1;
        const uint8_t *bytes = (const uint8_t *)ptr;
        buffer->insert(buffer->end(), bytes, bytes + size * num);
        return num;
    }
    static int MemClose(SDL_RWops *context)
    {
        return 0;
    }

private:
    SDL_RWops *m_rw;
    std::vector<uint8_t> m_buffer;
};

val optimize(std::string img_in, float width, float height, float quality, std::string format)
{
    SDL_RWops *rw = SDL_RWFromConstMem(img_in.c_str(), img_in.size());
    if (!rw)
    {
        return val::null();
    }

    SDL_Surface *srcSurface = IMG_Load_RW(rw, 1);
    SDL_FreeRW(rw);
    if (!srcSurface)
    {
        return val::null();
    }

    int srcWidth = srcSurface->w;
    int srcHeight = srcSurface->h;
    if (srcWidth == 0 || srcHeight == 0)
    {
        SDL_FreeSurface(srcSurface);
        return val::null();
    }

    int outWidth = width ? width : srcWidth;
    int outHeight = height ? height : srcHeight;
    float aspectSrc = static_cast<float>(srcWidth) / srcHeight;
    float aspectDest = outWidth / outHeight;

    if (aspectSrc > aspectDest)
    {
        outHeight = outWidth / aspectSrc;
    }
    else
    {
        outWidth = outHeight * aspectSrc;
    }

    SDL_Surface *newSurface = SDL_CreateRGBSurfaceWithFormat(0, static_cast<int>(outWidth), static_cast<int>(outHeight), 32, SDL_PIXELFORMAT_RGBA32);
    if (!newSurface)
    {
        SDL_FreeSurface(srcSurface);
        return val::null();
    }

    SDL_BlitScaled(srcSurface, nullptr, newSurface, nullptr);
    SDL_FreeSurface(srcSurface);

    if (format == "png" || format == "jpeg")
    {
        MemoryRW memoryRW;
        if (format == "png")
        {
            IMG_SavePNG_RW(newSurface, memoryRW, 1);
        }
        else
        {
            IMG_SaveJPG_RW(newSurface, memoryRW, 1, quality);
        }
        SDL_FreeSurface(newSurface);
        val result = val::null();
        if (memoryRW.size())
        {
            result = val::global("Uint8Array").new_(typed_memory_view(memoryRW.size(), memoryRW.data()));
        }
        return result;
    }
    else
    {
        uint8_t *img_out;
        val result = val::null();
        int stride = static_cast<int>(outWidth) * 4;
        size_t size = WebPEncodeRGBA(reinterpret_cast<uint8_t *>(newSurface->pixels), static_cast<int>(outWidth), static_cast<int>(outHeight), stride, quality, &img_out);
        if (size > 0 && img_out)
        {
            result = val::global("Uint8Array").new_(typed_memory_view(size, img_out));
        }
        WebPFree(img_out);
        SDL_FreeSurface(newSurface);
        return result;
    }
}

EMSCRIPTEN_BINDINGS(my_module)
{
    function("optimize", &optimize);
}
```

# Cloudflare Workers で動かす

http のリクエストヘッダの accept を確認して、webp で出力するかどうか判断するようにしました。webp が使えない場合、元の画像が jpeg なら jpeg、それ以外は png 形式で出力します。クエリパラメータとして w(幅)と q(クオリティ 1 ～ 100)を設定できます。

```ts
import { optimizeImage } from "wasm-image-optimization";

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
  _env: {},
  ctx: ExecutionContext
): Promise<Response> => {
  const accept = request.headers.get("accept");
  const isWebp =
    accept
      ?.split(",")
      .map((format) => format.trim())
      .some((format) => ["image/webp", "*/*", "image/*"].includes(format)) ??
    true;

  const url = new URL(request.url);

  const params = url.searchParams;
  const imageUrl = params.get("url");
  if (!imageUrl || !isValidUrl(imageUrl)) {
    return new Response("url is required", { status: 400 });
  }

  const cache = caches.default;
  url.searchParams.append("webp", isWebp.toString());
  const cacheKey = new Request(url.toString());
  const cachedResponse = await cache.match(cacheKey);
  if (cachedResponse) {
    return cachedResponse;
  }

  const width = params.get("w");
  const quality = params.get("q");

  const [srcImage, contentType] = await fetch(imageUrl, {
    cf: { cacheKey: imageUrl },
  })
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
    ctx.waitUntil(cache.put(cacheKey, response.clone()));
    return response;
  }

  const format = isWebp
    ? "webp"
    : contentType === "image/jpeg"
    ? "jpeg"
    : "png";
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
  ctx.waitUntil(cache.put(cacheKey, response.clone()));
  return response;
};

export default {
  fetch: handleRequest,
};
```

# テストを書く

各画像の変換後の形式と、キャッシュの有無を確認しています。ちなみに Cloudflare Workers を jest でテストする方法もネットににまとまった情報がありませんでした。

```ts
import { beforeAllAsync } from "jest-async";
import { unstable_dev } from "wrangler";

const images = ["test01.png", "test02.jpg", "test03.avif", "test04.gif"];
const imageUrl = (image: string) =>
  `https://raw.githubusercontent.com/SoraKumo001/cloudflare-workers-image-optimization/master/images/${image}`;

describe("Wrangler", () => {
  const property = beforeAllAsync(async () => {
    const worker = await unstable_dev("./src/index.ts", {
      experimental: { disableExperimentalWarning: true },
      ip: "127.0.0.1",
    });
    const time = Date.now();
    return { worker, time };
  });

  afterAll(async () => {
    const { worker } = await property;
    await worker.stop();
  });

  test("GET /", async () => {
    const { worker } = await property;
    const res = await worker.fetch("/");
    expect(res.status).toBe(400);
    expect(await res.text()).toBe("url is required");
  });
  test("not found", async () => {
    const { worker, time } = await property;
    for (let i = 0; i < images.length; i++) {
      const url = imageUrl("_" + images[i]);
      const res = await worker.fetch(`/?url=${encodeURI(url)}&t=${time}`, {
        headers: { accept: "image/webp,image/jpeg,image/png" },
      });
      expect(res.status).toBe(404);
    }
  });
  test("webp", async () => {
    const { worker, time } = await property;
    const types = ["webp", "webp", "webp", "gif"];
    for (let i = 0; i < images.length; i++) {
      const url = imageUrl(images[i]);
      const res = await worker.fetch(`/?url=${encodeURI(url)}&t=${time}`, {
        headers: { accept: "image/webp,image/jpeg,image/png" },
      });
      expect(res.status).toBe(200);
      expect(Object.fromEntries(res.headers.entries())).toMatchObject({
        "content-type": `image/${types[i]}`,
      });
      expect(res.headers.get("cf-cache-status")).toBeNull();
    }
  });
  test("webp(cache)", async () => {
    const { worker, time } = await property;
    const types = ["webp", "webp", "webp", "gif"];
    for (let i = 0; i < images.length; i++) {
      const url = imageUrl(images[i]);
      const res = await worker.fetch(`/?url=${encodeURI(url)}&t=${time}`, {
        headers: { accept: "image/webp,image/jpeg,image/png" },
      });
      expect(res.status).toBe(200);
      expect(Object.fromEntries(res.headers.entries())).toMatchObject({
        "content-type": `image/${types[i]}`,
        "cf-cache-status": "HIT",
      });
    }
  });
  test("not webp", async () => {
    const { worker, time } = await property;
    const types = ["png", "jpeg", "png", "gif"];
    for (let i = 0; i < images.length; i++) {
      const url = imageUrl(images[i]);
      const res = await worker.fetch(`/?url=${encodeURI(url)}&t=${time}`, {
        headers: { accept: "image/jpeg,image/png" },
      });
      expect(res.status).toBe(200);
      expect(Object.fromEntries(res.headers.entries())).toMatchObject({
        "content-type": `image/${types[i]}`,
      });
      expect(res.headers.get("cf-cache-status")).toBeNull();
    }
  });
  test("not webp(cache)", async () => {
    const { worker, time } = await property;
    const types = ["png", "jpeg", "png", "gif"];
    for (let i = 0; i < images.length; i++) {
      const url = imageUrl(images[i]);
      const res = await worker.fetch(`/?url=${encodeURI(url)}&t=${time}`, {
        headers: { accept: "image/jpeg,image/png" },
      });
      expect(res.status).toBe(200);
      expect(Object.fromEntries(res.headers.entries())).toMatchObject({
        "content-type": `image/${types[i]}`,
        "cf-cache-status": "HIT",
      });
    }
  });
});
```

# まとめ

この WebAssembly を使用したプログラムは C++で書いているわけですが、Web アプリ時代に再び C++を使うことになるとは感慨深いものがあります。CloudflareWorkers や DenoDeploy などの制限された Edge 環境では、こういったものが活躍する場が稀に出てくるので、また何か面白いものが思いついたら、何かしら作っていこうと思っています。
