---
title: "Cloudflare Workers + PrismaでGraphQLサーバを作る"
emoji: "🕌"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: []
published: false
---

# Prisma の QueryEngine を Cloudflare Workers で動かす

## Prisma の QueryEngine の Edge Functions 対応

Prisma はその中心部と言える QueryEngine を Rust で記述していますが、WebAssembly 版を作成し、現在は Preview という状態ですが Edge Functions として動作させることができるようになりました。これにより、Prisma の QueryEngine を Cloudflare Workers などの Edge Computing プラットフォームで動作させることができるようになります。

https://www.prisma.io/blog/prisma-orm-support-for-edge-functions-is-now-in-preview

## Prisma の WebAssembly 版を Cloudflare Workers で動かす場合の問題点

Prisma の WebAssembly 版を動かすためには、巨大な wasm ファイルと、関連する Adapter モジュールが必要になります。これらを組み込んで DB とやり取りしようとすると、サイズが大きくなります。無料プランの Cloudflare Workers では、圧縮時のサイズで 1MB 以内と決められています。そして実際に必要な状態までコードを組むと、900KB 程度のサイズになってしまうのです。残り 100KB 以内でアプリケーションを構築する必要があります。

## Prisma の QueryEngine を Cloudflare Workers で動かすための方法

Prisma の WebAssembly 版を使用する場合は schema.prisma に previewFeatures で driverAdapters という設定を加える必要があります。今までとの違いはそれだけです。

- prisma/schema.prisma

```
generator client {
  provider = "prisma-client-js"
  previewFeatures = ["driverAdapters"]
}
```

あとは`prisma generate`を実行すれば、必要なファイルが生成されます。ただし注意点があります。

https://github.com/prisma/prisma/pull/22962

この変更によって、WebAssembly 版で出力される wasm.js の runtimeDataModel が不十分な出力結果となっており、DataModel を必要としている関連パッケージが正常に動作しなくなります。仕方がないので、他のファイルから runtimeDataModel を復元するスクリプトを組んで`prisma generate`の後に実行することにしました。

```ts
import fs from "fs";

const srcPath = "node_modules/.prisma/client/index.js";
const destPath = "node_modules/.prisma/client/wasm.js";

const src = fs.readFileSync(srcPath);
const runtimeDataModel = String(src).match(
  /config\.runtimeDataModel = JSON\.parse\(".*"\)/
)?.[0];
if (runtimeDataModel) {
  const dist = fs.readFileSync(destPath);
  const newRuntimeDataModel = String(dist).replace(
    /config\.runtimeDataModel = JSON\.parse\(".*"\)/,
    runtimeDataModel
  );
  fs.writeFileSync(destPath, newRuntimeDataModel);
}
```

## node_compat 問題

CloudflareWorkers では Node ランタイムの Polyfill が提供されています。Prisma の DB 接続用の Adapter の中にはこれを要求するものがあります。それは仕方がないのですが、

https://github.com/prisma/prisma/pull/23013

上記リファクタリングによって、本来 Polyfill を必要としない Adapter 類まで Polyfill が必要な状態になっています。諦めて`node_compat = true`を設定しましょう。
