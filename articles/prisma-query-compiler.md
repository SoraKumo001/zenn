---
title: "Prisma queryCompiler の誤解を解く"
emoji: "🔖"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [prisma, hono, pothos, cloudflare, graphql]
published: true
---

# queryCompiler は no rust ではない

queryCompiler は Rust の使用をやめて、JavaScript ベースのエンジンに移行するために作られています。しかし queryCompiler 自体は現時点で Rust で作られています。queryEngine は JavaScript だったとしても、queryCompiler は Rust で書かれています。no rust でも rust free でもありません。

Prisma 公式 Blog が誤解を招く内容を発信しているところが問題です。

https://www.prisma.io/blog/prisma-6-9-0-release#prisma-orm-without-rust-engines-for-postgresql--sqlite-preview

また、queryCompiler の動作確認をするときに気をつけなければならないのは、Prisma が公式で PostgreSQL の DB を提供しているサービス、`Prisma Postgres`を使用してはならないということです。このサービス、一般的な PostgreSQL の機能ではなく、Prisma Accelerate による PrismaEngine を含んだ Prisma 独自のサービスです。このサービスを使うと、リモートで PrismaEngine が動作するので、手元にある queryCompiler を使いません。prisma.schema で `previewFeatures = ["queryCompiler"]`を設定しても意味がないのです。

ちなみに PrismaEngine をリモートに分離する方法は、公式の`Prisma Accelerate`や`Prisma Postgres`の他に、セルフホストするために以下の物を作っています。ただしこれを使うと queryCompiler を使用する必要がなくなります。

https://www.npmjs.com/package/prisma-accelerate-local

## 重要な点

- queryCompiler は Rust で書かれている
- `Prisma Postgres`は PrismaEngine を含んだ Prisma 専用のサービスであり、queryCompiler を使わない

# queryCompiler の使い方

サンプルコードは以下のリポジトリにあります。hono + pothos + prisma で GraphQL API を構築するサンプルです。

https://github.com/SoraKumo001/hono-pothos-prisma-cloudflare

![](/images/prisma-query-compiler/2025-06-18-09-47-05.webp)

- prisma.schema の設定

queryCompiler 以下の設定を書く必要があります。output は動的に生成される Prisma Client の出力先です。

```prisma
generator client {
  provider     = "prisma-client-js"
  previewFeatures = ["driverAdapters","queryCompiler"]
  output       = "../node_modules/.prisma/client"
}

```

# queryCompiler の有無によって出力されるものの違い

`prisma generate`を実行すると、以下のようなファイルが生成されます。

- queryCompiler を有効にした場合

`query_compiler_bg.wasm`が Rust で書かれた queryCompiler です。1,887KB あります。

![](/images/prisma-query-compiler/2025-06-18-09-23-27.png)

- queryCompiler を無効にした場合

`query_engine_bg.wasm`が Rust で書かれた Prisma Engine です。2,226KB あります。

![](/images/prisma-query-compiler/2025-06-18-09-26-37.png)

Cloudflare にデプロイする場合、queryCompiler を有効にしたほうが、圧縮サイズで 100KB 強小さくなります。ただし、未だ多数の不具合を抱えているため、安定性を重視するなら、queryCompiler を無効にしておく方が無難です。

ちなみに queryCompiler を有効にしつつ、`prisma generate --no-engine`を実行すると以下のようになります

`query_compiler_bg.wasm`が無くなっていますが、デプロイ時には別の場所からきっちり拾ってくるので、サイズが縮むことはありません

![](/images/prisma-query-compiler/2025-06-18-09-31-48.png)

## Cloudflare のサイズ制限

古い情報だとフリープランが 1MB となっていることがありますが、2024 年 11 月の時点で 3MB です。

https://developers.cloudflare.com/workers/platform/limits/

| プラン     | 圧縮後サイズ |
| ---------- | ------------ |
| Free(無料) | 3MB          |
| Paid(有料) | 10MB         |

## wasm ファイルの圧縮時のサイズ比較

フリープランでも 3MB 使えるので、サイズがぎりぎりになることはまずありません。

| 種類          | 圧縮前サイズ | 圧縮後サイズ |
| ------------- | ------------ | ------------ |
| queryCompiler | 1,887KB      | 723KB        |
| queryEngine   | 2,226KB      | 870KB        |

# まとめ

Cloudflare で Prisma を使う場合、queryCompiler を有効にしても、相変わらず巨大な wasm ファイルをデプロイに含める必要があります。ただ、現在 CloudflareWorkers のフリープランでの圧縮サイズ制限は 3MB あります。圧縮サイズ 723KB の wasm を含めても、それほどギリギリにはなりません。PrismaEngine 版の wasm でも 870KB です。有料プランなら最大容量は 10MB あるので、このサイズなら困ることはありません。

結論として、現時点 Prisma を Cloudflare で使うなら、サイズも大して変わらないので、安定している PrismaEngine の wasm 版を使うのが無難そうです。
