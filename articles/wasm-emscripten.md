---
title: "[WebAssembly]Cloudflare/DenoDeployで使えるEmscriptenによる画像最適化ライブラリの作り方"
emoji: "🎃"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [wasm, emscripten, sdl2, webp, avif, exif]
published: true
---

# はじめに

Emscripten は C/C++のコードを WebAssembly に変換することが出来ます。また、標準で SDL2 をサポートしているため、画像処理ライブラリの作成に適しています。今回は、Emscripten を使って画像最適化ライブラリを作成する方法を紹介します。

画像最適化ライブラリは png や jpeg など比較的圧縮率が低いフォーマットから、webp や avif などの高圧縮率のフォーマットに変換したり、サイズの調整する機能を提供します。

作成したものがどんなものかは以下のリンクから確認できます。

https://www.npmjs.com/package/wasm-image-optimization
https://www.npmjs.com/package/wasm-image-optimization-avif

WebAssembly 化したときの利点は、ブラウザ上で動作させたり、Cloudflare や Deno のサーバ上の無料枠で動作させることが出来る点です。

# 環境構築

ローカル環境に Emscripten をインストールして設定を行うのはダルいので、Docker を使って環境構築を行います。

- Dockerfile

```Dockerfile
FROM emscripten/emsdk
WORKDIR /app
```

環境構築が完了しました。簡単ですね。

# 必要なパッケージのインストール

Emscripten は SDL2 によって png,jpeg,gif などは標準で使えるのですが、webp や avif などは追加で必要なパッケージを取ってくる必要があります。また、jpeg の exif 情報を使って回転情報を取得するためにも対応するパッケージが必要です。

- Dockerfile

```Dockerfile
FROM emscripten/emsdk
WORKDIR /app
RUN  apt-get update && apt-get install -y dh-autoreconf ninja-build yasm &&\
    git clone https://github.com/webmproject/libwebp &&\
    git clone https://github.com/AOMediaCodec/libavif &&\
    git clone https://github.com/libexif/libexif &&\
    ln -s /app/libwebp/src/webp /emsdk/upstream/lib/clang/20/include/webp &&\
    ln -s /app/libavif/include/avif /emsdk/upstream/lib/clang/20/include/avif
```

ということで、必要なパッケージをインストールしました。ビルドに必要なツール類も入れておきます。さらにパッケージの include パスをシンボリックリンクで Emscripten のヘッダーファイルに追加します。

- docker-compose.yml

```yaml
version: "3.7"
services:
  emcc:
    container_name: wasm-image-optimization
    build:
      context: .
      dockerfile: ./Dockerfile
    volumes:
      - app:/app
      - cache:/emsdk/upstream/emscripten/cache
      - ../Makefile:/app/Makefile
      - ../src:/app/src
      - ../dist:/app/dist
volumes:
  app:
  cache:
```

ホスト側の src ディレクトリの中に画像最適化ライブラリのソースコードを配置し、dist ディレクトリにビルド結果を出力出来るようにします。

# Makefile の作成

webp と avif と exif のライブラリをビルドし、各パッケージをリンクできるようにします。さらに出力時に wasm と併用して使う.js ファイルを esm と cjs 形式で出力するように、二回ビルドを行います。

- Makefile

ビルドが通るように試行錯誤してできたものは、控えめに言ってカオスです。

```Makefile
SHELL=/bin/bash
WORKDIR=work
DISTDIR=dist
ESMDIR=$(DISTDIR)/esm
WORKERSDIR=$(DISTDIR)/workers
LIBDIR=libavif/ext

TARGET_ESM_BASE = $(notdir $(basename src/libImage.cpp))
TARGET_ESM = $(ESMDIR)/$(TARGET_ESM_BASE).js
TARGET_WORKERS = $(WORKERSDIR)/$(TARGET_ESM_BASE).js

CFLAGS = -O3 -msimd128 \
        -Ilibwebp -Ilibwebp/src -Ilibavif/include -Ilibavif/third_party/libyuv/include -Ilibavif/ext/aom \
        -Ilibexif \
        -DAVIF_CODEC_AOM_ENCODE -DAVIF_CODEC_AOM_DECODE -DAVIF_CODEC_AOM=LOCAL

CFLAGS_ASM = --bind \
             -s WASM=1 -s ALLOW_MEMORY_GROWTH=1 -s ENVIRONMENT=web -s DYNAMIC_EXECUTION=0 -s MODULARIZE=1 \
             -s USE_SDL=2 -s USE_SDL_IMAGE=2 -s USE_SDL_GFX=2 \
             -s SDL2_IMAGE_FORMATS='["png","jpg","webp","svg","avif"]'

WEBP_SOURCES := $(wildcard libwebp/src/dsp/*.c) \
                $(wildcard libwebp/src/enc/*.c) \
                $(wildcard libwebp/src/utils/*.c) \
                $(wildcard libwebp/src/dec/*.c) \
                $(wildcard libwebp/sharpyuv/*.c)
AVIF_SOURCES := libavif/src/alpha.c \
                libavif/src/avif.c \
                libavif/src/colr.c \
                libavif/src/colrconvert.c \
                libavif/src/diag.c \
                libavif/src/exif.c \
                libavif/src/io.c \
                libavif/src/mem.c \
                libavif/src/obu.c \
                libavif/src/rawdata.c \
                libavif/src/read.c \
                libavif/src/reformat.c \
                libavif/src/reformat_libsharpyuv.c \
                libavif/src/reformat_libyuv.c \
                libavif/src/scale.c \
                libavif/src/stream.c \
                libavif/src/utils.c \
                libavif/src/write.c \
                libavif/src/codec_aom.c \
                libavif/third_party/libyuv/source/scale.c \
                libavif/third_party/libyuv/source/scale_common.c \
                libavif/third_party/libyuv/source/scale_any.c \
                libavif/third_party/libyuv/source/row_common.c \
                libavif/third_party/libyuv/source/planar_functions.c

EXIF_SOURCES := $(wildcard libexif/libexif/*.c) \
                $(wildcard libexif/libexif/canon/*.c) \
                $(wildcard libexif/libexif/fuji/*.c) \
                $(wildcard libexif/libexif/olympus/*.c) \
                $(wildcard libexif/libexif/pentax/*.c)

WEBP_OBJECTS := $(WEBP_SOURCES:.c=.o)
AVIF_OBJECTS := $(AVIF_SOURCES:.c=.o)
EXIF_OBJECTS := $(EXIF_SOURCES:.c=.o)

.PHONY: all esm workers clean

all: esm workers

$(WEBP_OBJECTS) $(AVIF_OBJECTS): %.o: %.c | $(LIBDIR)/aom_build/libaom.a
	@emcc $(CFLAGS) -c $< -o $@

$(LIBDIR)/aom_build/libaom.a:
	@echo Building aom...
	@cd $(LIBDIR) && ./aom.cmd && mkdir aom_build && cd aom_build && \
	emcmake cmake ../aom \
    -DENABLE_CCACHE=1 \
    -DAOM_TARGET_CPU=generic \
    -DENABLE_DOCS=0 \
    -DENABLE_TESTS=0 \
    -DCONFIG_ACCOUNTING=1 \
    -DCONFIG_INSPECTION=1 \
    -DCONFIG_MULTITHREAD=0 \
    -DCONFIG_RUNTIME_CPU_DETECT=0 \
    -DCONFIG_WEBM_IO=0 \
    -DCMAKE_BUILD_TYPE=Release && \
	make aom

$(WORKDIR):
	@mkdir -p $(WORKDIR)

$(WORKDIR)/webp.a: $(WORKDIR) $(WEBP_OBJECTS)
	@emar rcs $@ $(WEBP_OBJECTS)

$(WORKDIR)/avif.a: $(WORKDIR) $(AVIF_OBJECTS)
	@emar rcs $@ $(AVIF_OBJECTS)

$(WORKDIR)/libexif.a: $(EXIF_SOURCES)
	@cd libexif && autoreconf -i && emconfigure ./configure && cd libexif && emmake make
	@emar rcs $@ $(EXIF_OBJECTS)

$(ESMDIR) $(WORKERSDIR):
	@mkdir -p $@

esm: $(TARGET_ESM)

$(TARGET_ESM): src/libImage.cpp $(WORKDIR)/webp.a $(WORKDIR)/avif.a $(WORKDIR)/libexif.a $(LIBDIR)/aom_build/libaom.a | $(ESMDIR)
	emcc $(CFLAGS) -o $@ $^ \
       $(CFLAGS_ASM)  -s EXPORT_ES6=1

workers: $(TARGET_WORKERS)

$(TARGET_WORKERS): src/libImage.cpp $(WORKDIR)/webp.a $(WORKDIR)/avif.a $(WORKDIR)/libexif.a $(LIBDIR)/aom_build/libaom.a | $(WORKERSDIR)
	emcc $(CFLAGS) -o $@ $^ \
       $(CFLAGS_ASM)
	@rm $(WORKERSDIR)/$(TARGET_ESM_BASE).wasm

clean:
	@echo Cleaning up...
	@rm -rf $(WORKDIR) $(LIBDIR)/aom_build $(DISTDIR)/esm $(DISTDIR)/workers
```

# 画像最適化ライブラリのソースを作成

集めた力を結集し、C++で画像最適化ライブラリを作成します。

- src/libImage.cpp

```cpp
#include <emscripten.h>
#include <emscripten/bind.h>
#include <emscripten/val.h>
#include <webp/encode.h>
#include <SDL2/SDL2_rotozoom.h>
#include <SDL2/SDL_image.h>
#include <SDL2/SDL.h>
#include <libexif/exif-data.h>
#include <avif/avif.h>

using namespace emscripten;

EM_JS(void, js_console_log, (const char *str), {
    console.log(UTF8ToString(str));
});

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

int getOrientation(std::string img)
{
    int orientation = 1;
    ExifData *ed = exif_data_new_from_data((const unsigned char *)img.c_str(), img.size());
    if (!ed)
    {
        return orientation;
    }
    ExifEntry *entry = exif_content_get_entry(ed->ifd[EXIF_IFD_0], EXIF_TAG_ORIENTATION);
    if (entry)
    {
        orientation = exif_get_short(entry->data, exif_data_get_byte_order(entry->parent->parent));
    }
    exif_data_unref(ed);
    return orientation;
}

val optimize(std::string img_in, float width, float height, float quality, std::string format)
{
    int orientation = getOrientation(img_in);

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

    SDL_Surface *newSurface = zoomSurface(srcSurface, (float)outWidth / srcWidth, (float)outHeight / srcHeight, SMOOTHING_ON);
    SDL_FreeSurface(srcSurface);
    if (!newSurface)
    {
        return val::null();
    }

    if (orientation > 1)
    {
        double angle = 0;
        double x = 1;
        double y = 1;
        switch (orientation)
        {
        case 2:
            x = -1.0;
            break;
        case 3:
            angle = 180.0;
            break;
        case 4:
            y = -1.0;
            break;
        case 5:
            angle = 90.0;
            x = -1.0;
            break;
        case 6:
            angle = 270.0;
            break;
        case 7:
            angle = 270.0;
            x = -1.0;
            break;
        case 8:
            angle = 90.0;
            break;
        }
        SDL_Surface *rotatedSurface = rotozoomSurfaceXY(newSurface, angle, x, y, SMOOTHING_ON);
        SDL_FreeSurface(newSurface);
        newSurface = rotatedSurface;
    }

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
        if (newSurface->format->format != SDL_PIXELFORMAT_RGBA32)
        {
            SDL_Surface *convertedSurface = SDL_ConvertSurfaceFormat(newSurface, SDL_PIXELFORMAT_RGBA32, 0);
            SDL_FreeSurface(newSurface);
            if (convertedSurface == NULL)
            {
                return val::null();
            }
            newSurface = convertedSurface;
        }
        if (format == "webp")
        {
            uint8_t *img_out;
            val result = val::null();
            int width = newSurface->w;
            int height = newSurface->h;
            int stride = width * 4;
            size_t size = WebPEncodeRGBA(reinterpret_cast<uint8_t *>(newSurface->pixels), width, height, stride, quality, &img_out);
            if (size > 0 && img_out)
            {
                result = val::global("Uint8Array").new_(typed_memory_view(size, img_out));
            }
            WebPFree(img_out);
            SDL_FreeSurface(newSurface);
            return result;
        }
        else
        {
            int width = newSurface->w;
            int height = newSurface->h;
            avifImage *image = avifImageCreate(width, height, 8, AVIF_PIXEL_FORMAT_YUV444);

            avifRGBImage rgb;
            avifRGBImageSetDefaults(&rgb, image);
            rgb.depth = 8;
            rgb.format = AVIF_RGB_FORMAT_RGBA;
            rgb.pixels = (uint8_t *)newSurface->pixels;
            rgb.rowBytes = width * 4;

            if (avifImageRGBToYUV(image, &rgb) != AVIF_RESULT_OK)
            {
                return val::null();
            }
            avifEncoder *encoder = avifEncoderCreate();
            encoder->quality = (int)((quality) / 100 * 63);
            encoder->speed = 6;

            avifRWData raw = AVIF_DATA_EMPTY;

            avifResult encodeResult = avifEncoderWrite(encoder, image, &raw);
            avifEncoderDestroy(encoder);
            avifImageDestroy(image);
            if (encodeResult != AVIF_RESULT_OK)
            {
                return val::null();
            }
            val result = val::global("Uint8Array").new_(typed_memory_view(raw.size, raw.data));
            avifRWDataFree(&raw);
            return result;
        }
      }
}

EMSCRIPTEN_BINDINGS(my_module)
{
    function("optimize", &optimize);
}

```

ソースの内容は送られてきた画像を展開し回転情報を処理して、指定されたエンコーダーに変換を投げます。特別なロジックはいらないので、C++に慣れていない人でも多少試行錯誤すれば書けると思います。

# ビルド

```bash
docker compose -f docker/docker-compose.yml run --build --rm emcc make -j
```

これでビルドが行われ、wasm ファイルが出力されます。

# まとめ

Emscripten を使って画像最適化ライブラリを作成する方法を紹介しました。最も面倒くさいのは、必要なライブラリを集めてリンク可能な状態にする部分です。便利なエコシステムなどありません。Makefile は地獄です。何をどうすればいいのか、カンが要求されます。

肝心の自分で組むコードの部分はただのツギハギです。スキルもへったくれもいらないというのがお分かりいただけると思います。
