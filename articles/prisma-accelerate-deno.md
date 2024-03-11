---
title: "Prisma Accelerate の機能を Deno に載せて、Cloudflare WorkersからPrismaでDBへアクセスする"
emoji: "🐷"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: []
published: false
---

# Prisma の Edge Runtime での問題点

Prisma は Node.js で記述された API 部分と、DB とやり取りする Rust で記述された Engine 部分に分かれています。Rust の部分は各環境用にネイティブでコンパイルされており、Cloudflare Workers のような Edge 環境で動作させることは出来ません。回避手段としては Prisma Accelerate というサービスを利用して、Rust の Engine 部分だけリモートで実行するという方法があります。しかし、Prisma Accelerate は無料で利用できる範囲が 6 万クエリ/月ということで心もとない数字です。

しかし現在、Prisma は Rust のコードを WebAssembly で出力する作業が進んでいます。WebAssembly を使えば EdgeRuntime でも動作可能となります。ただし問題点があって、現時点でのサイズは圧縮しても 1MB を大幅に超えてしまい、CloudflareWorkers のフリープランでの制限を超えてしまいます。実装状況を見ると、今後も 1MB を切るようにするのはかなり困難ではないかと思われます。

# 無料で Prisma を EdgeRuntime で動かす方法

Cloudflare Workers のフリープランではサイズの問題から Prisma の WebAssembly を動かすことは出来ません。しかし Deno Deploy ならば動作可能です。Deno Deploy は無料で 1MB 超えの WebAssembly を動かすことが出来ます。ただ、Deno と聞くと、Node.js との互換性の問題から拒否反応を示す人も多いと思います。そのため、Prisma のエンジン部分のみを Deno Deploy に載せて、その他の部分は Cloudflare Workers からアクセスすることで、問題を解決出来ます。Deno Deploy は 100 万アクセス/月まで無料で利用できます。

# 構成

以下のような構成で動作するシステムを作ります。

![](/images/prisma-accelerate-deno/2023-12-30-10-59-31.png)

DenoDeploy に載せた Prisma Accelerate に Secret を設定しておきます。そして Secret から DB 接続文字列を JWT の APIKey を作り、CloudflareWorkers から DenoDeploy にアクセスします。これによって DenoDeploy 側は一つサービスを立ち上げてほけ場、複数の DB や複数のクライアントに対して汎用的に動作します。

# Deno Deploy に Prisma Accelerate を載せる

prisma-accelerate-local を使って、Deno Deploy に Prisma Accelerate のエミュレートをするコードです。これは PostgraduateSQL 用のコードです。環境変数の SECRET に何らかの文字列を設定しておく必要があります。後ほど APIKey を作る際に使います。

- リポジトリ  
  https://github.com/SoraKumo001/prisma-accelerate-deno

```ts
import { PrismaPg } from "npm:@prisma/adapter-pg@5.8.0-dev.42";
import { getPrismaClient } from "npm:@prisma/client@5.8.0-dev.42/runtime/library.js";
import pg from "npm:pg";
import {
  PrismaAccelerate,
  ResultError,
} from "npm:prisma-accelerate-local@0.2.0/lib";

const queryEngineWasmFileBytes = fetch(
  new URL(
    "../../node_modules/@prisma/client/runtime/query-engine.wasm",
    import.meta.url
  )
).then((r) => r.arrayBuffer());

const getAdapter = (datasourceUrl: string) => {
  const url = new URL(datasourceUrl);
  const schema = url.searchParams.get("schema");
  const pool = new pg.Pool({
    connectionString: url.toString(),
  });
  return new PrismaPg(pool, {
    schema: schema ?? undefined,
  });
};

export const createServer = ({
  secret,
}: {
  https?: { cert: string; key: string };
  secret: string;
}) => {
  const prismaAccelerate = new PrismaAccelerate({
    secret,
    adapter: (datasourceUrl) => getAdapter(datasourceUrl),
    getQueryEngineWasmModule: async () => {
      const result = new WebAssembly.Module(await queryEngineWasmFileBytes);
      return result;
    },
    getPrismaClient,
  });

  return Deno.serve(async (request) => {
    const url = new URL(request.url);
    const paths = url.pathname.split("/");
    const [_, version, hash, command] = paths;
    const headers = Object.fromEntries(request.headers.entries());
    const createResponse = (result: Promise<unknown>) =>
      result
        .then((r) => {
          return new Response(JSON.stringify(r), {
            headers: { "content-type": "application/json" },
          });
        })
        .catch((e) => {
          if (e instanceof ResultError) {
            return new Response(JSON.stringify(e.value), {
              status: e.code,
              headers: { "content-type": "application/json" },
            });
          }
          return new Response(JSON.stringify(e), {
            status: 500,
            headers: { "content-type": "application/json" },
          });
        });

    if (request.method === "POST") {
      const body = await request.text();
      switch (command) {
        case "graphql":
          return createResponse(
            prismaAccelerate.query({ body, hash, headers })
          );
        case "transaction":
          return createResponse(
            prismaAccelerate.startTransaction({
              body,
              hash,
              headers,
              version,
            })
          );
        case "itx": {
          const id = paths[4];
          switch (paths[5]) {
            case "commit":
              return createResponse(
                prismaAccelerate.commitTransaction({
                  id,
                  hash,
                  headers,
                })
              );
            case "rollback":
              return createResponse(
                prismaAccelerate.rollbackTransaction({
                  id,
                  hash,
                  headers,
                })
              );
          }
        }
      }
    } else if (request.method === "PUT") {
      const body = await request.text();
      switch (command) {
        case "schema":
          return createResponse(
            prismaAccelerate.updateSchema({
              body,
              hash,
              headers,
            })
          );
      }
    }
    return new Response("Not Found", { status: 404 });
  });
};

createServer({
  secret: Deno.env.get("SECRET")!,
});
```

# Cloudflare Workers から Deno Deploy にアクセスする

コマンドラインから以下のコマンドを実行して、APIKey を作成します。APIKey は JWT で、Deno Deploy にアクセスする際に使います。

```sh
npx prisma-accelerate-local -s secret -m postgresql://xxxx:yyyy@zzzz:5432/postgres
```

すると以下のような出力が得られます。

```text
eyJhbGciOiJIUzI1NiJ9.eyJkYXRhc291cmNlVXJsIjoicG9zdGdyZXNxbDovL3h4eHg6eXl5eUB6enp6OjU0MzIvcG9zdGdyZXMiLCJpYXQiOjE3MDM5MDM1ODEsImlzcyI6InByaXNtYS1hY2NlbGVyYXRlIn0.5tera4SWWm8roDdpMOJBGlXjJwVjiFd3Mg6wZG0wSt4
```

この時点で JWT の中に DB 接続文字列が含まれています。本家の Prisma Accelerate と違い、サーバー側で DB 接続文字列を保持する必要はありません。
次は Prisma に対して、DATABASE_URL を指定します。指定内容は以下の通りです。

```
DATABASE_URL="prisma://[Deno Deployのサービスのアドレス]/?api_key=[API_KEY]"
```

そして Cloudflare Workers 向けのコードを書く場合は、以下のように PrismaClient を import します。

```ts
import { PrismaClient } from "@prisma/client/edge";
```

# まとめ

Prisma Accelerate のエンジン部分を Deno Deploy に載せて、Cloudflare Workers からアクセスすることで、無料で Prisma を EdgeRuntime で動かすことが出来ました。Deno Deploy は 100 万アクセス/月まで無料で利用できます。ただし、Prisma の WebAssembly の機能は開発中です。そのため、個人の趣味で使う範囲に留めておくことをおすすめします。

Prisma Accelerate のエミュレーションを使わなくても、毛嫌いせず Deno Deploy にバックエンドの処理を全部載せた方が実は良いのではないかという気がしないでもないです。
