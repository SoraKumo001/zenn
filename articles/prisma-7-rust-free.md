---
title: "Prisma@7 は No Rust でも Rust Free でもない"
emoji: "📌"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [prisma, rust, typescript, postgresql]
published: true
---

# Prisma のジェネレーション時のオプションについて

このあとの話のために、最初にジェネレーション時のオプションについて説明します。

- `provider = "prisma-client"`
  TypeScript で PrismaClient のコードを生成し、自分のコードの一部としてビルドに組み込む場合

- `provider = "prisma-client-js"`
  JavaScript で PrismaClient のコードを生成し、node_modules 経由で別パッケージとして利用する従来の機能

今回、Prisma@7 で売り出しているのは`provider = "prisma-client"`です。

# Prisma@7 で生成されたファイルを確認してみる

Rust Free と呼ばれる状態を作るため、以下の設定で PrismaClient の TypeScript 用コードを生成してみます。今回、対象の DB は PostgreSQL とします

- schema.prisma

```prisma
generator client {
  provider = "prisma-client"
  engineType = "client"
  output = "../app/generated/prisma"
}
```

ここで生成されたファイル中から、QueryCompiler がどのように呼ばれるのか該当コードを確認します

- prisma/internal/class.ts から、該当部分を抽出

```ts
async function decodeBase64AsWasm(
  wasmBase64: string
): Promise<WebAssembly.Module> {
  const { Buffer } = await import("node:buffer");
  const wasmArray = Buffer.from(wasmBase64, "base64");
  return new WebAssembly.Module(wasmArray);
}

config.compilerWasm = {
  getRuntime: async () =>
    await import("@prisma/client/runtime/query_compiler_bg.postgresql.mjs"),

  getQueryCompilerWasmModule: async () => {
    const { wasm } = await import(
      "@prisma/client/runtime/query_compiler_bg.postgresql.wasm-base64.mjs"
    );
    return await decodeBase64AsWasm(wasm);
  },
};
```

この部分が何なのかというと、base64 化された QueryCompiler の WASM を取り出して、バイナリにデコードした後、WebAssembly として投入しています。この`query_compiler_bg.postgresql.wasm-base64.mjs`は 2,410KB あり、zip 圧縮をかけても 940KB ほどのサイズになります。Prisma を動作させるためには、この WASM が必須です。

QueryCompiler がどのように作られているかというと、以下が該当するコードです。

https://github.com/prisma/prisma-engines/tree/main/query-compiler

はい、Rust です。

# Prisma の言っている Rust Free とは何か？

2025/4/30 の記事を見ると、辛うじて書いてあります

https://www.prisma.io/blog/try-the-new-rust-free-version-of-prisma-orm-early-access

> Prisma ORM's core engine has undergone a major shift from the Rust based query engine to a leaner TypeScript/WASM core (the Query Compiler).

Rust ベースのクエリエンジン\(おそらくネイティブバイナリのこと\)から、Query Compiler\(TypeScript と WASM を組み合わせたもの\)になったということらしいですが、その WASM は Rust 製です。

バンドルサイズが 90%小さくなったというのは、ネイティブバイナリを使用した場合の 14MB が、WASM 化で 1.6MB になったということです。QueryEngine から QueryCompiler の移行によって、WASM が不要になったわけではありません。

そして現在 Prisma は、Rust Free、No Rust という言葉を使い続け、混沌を呼び込んでいます。実際のところは、No native libraries です。

# Prisma@7 は No Rust でも Rust Free でもない

Prisma@7 に対する公式 Blog は以下の内容になります。

https://www.prisma.io/blog/announcing-prisma-orm-7-0-0

もうバンドルサイズが何から 90% 減少したのかすら書いてません。さらに`provider = "prisma-client-js"`を`provider = "prisma-client"`にすれば rust-free になりそうな記述になってますが、後者は TypeScript のコードが生成されるというだけで、基本的な動作は変わりません。生成された TypeScript のコードは WASM を base64 の状態から読み込むのでバンドルサイズが増えます。現状、メリットがありません。

# なぜ WASM を base64 にしているのか

モジュールバンドラ対策です。WASM ファイルを直接読み込むコードがあると、あらゆる環境に対応させる必要があります。WASM ファイルがどう扱われるかは、モジュールバンドラの設定次第であり、あらゆる環境に対する対応地獄が待っています。これを解決する簡単な方法は、JavaScript 内に WASM のバイナリを内包しておき、実行時に WebAssembly として放り込むことです。

Cloudflare のように WASM のモジュールファイルを直接読み込む必要のある環境では runtime の指定で、base64 から読み込むのを回避する必要があります。ちなみに`runtime = "workerd"`のような指定をした場合、以下のようなコードが生成されます。

```ts
config.compilerWasm = {
  getRuntime: async () => await import("./query_compiler_bg.js"),

  getQueryCompilerWasmModule: async () => {
    const { default: module } = await import("./query_compiler_bg.wasm?module");
    return module;
  },
};
```

`?module`の部分は特定のモジュールバンドラに対する指示です。Cloudflare にはそのような指定方法は存在しません。つまりどういうことかというと、エラーを出して動きません。`provider = "prisma-client"`を指定して出力したコードは、直接自分で該当部分を削除しない限り動きません。

# まとめ

## Prisma もひどいが、巷の記事もひどい

誤解を招く公式 Blog の責任は大きいのですが、Rust Free、No Rust という部分を WASM を使わなくなったと誤解する記事が乱発されいます。

ちなみに Prisma を No Rust で使う方法として、Prisma Accelerate という Prisma 専用の有料サービスを使う方法があります。Prisma エンジン\(Rust 部分\)をリモート経由で外部実行する方式です。その機能を内包している Prisma Postgres というサービスがあります。このサービスは Prisma が No Rust をうたい始める前からあったのですが、そちらを利用して Prisma が No Rust になったんだという勘違い記事まで存在しています。そしてそれを参照して、さらに間違った記事が再生産されています。

## あらゆる情報を疑う必要がある

私を含め、技術記事は間違いだらけです。有名な人の記事もけっこう間違ってます。そして公式の情報も正しいとは限りません。間違った記事を参照して、さらに間違った記事を再生産しているものも見受けられます。最低限自分で検証するまで、それが正しいということを前提としないでください。
