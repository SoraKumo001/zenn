---
title: "Prisma Studio の GraphQL 版を作ってみる"
emoji: "🔥"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: []
published: false
---

# Prisma Studio とは

Prisma Studio は、Prisma が提供する GUI ツールです。Prisma が提供する ORM ライブラリを使って作成したデータベースの内容を確認・編集することができます。ただ、DB の内容の表示や操作に関して Prisma の要素は一切ありません。ただの DB 操作ツールです。

# Prisma Studio の GraphQL 版を作ってみる

Prisma の以前のバージョンではエンジン部分のプロトコルに GraphQL が使われていました。そのため Prisma の文法と GraphQL の文法は類似要素が多くなっています。そのため、Prisma を扱うのに近い形で GraphQL のクエリを作成することが出来ます。

## 作成したパッケージです

https://www.npmjs.com/package/prisma-studio-graphql

## 内部で使用しているパッケージ

| 名前                    | 用途                                           |
| ----------------------- | ---------------------------------------------- |
| Hono                    | WebServer                                      |
| Pothos GraphQL          | GraphQL フレームワーク                         |
| graphql-yoga            | GraphQL サーバー                               |
| pothos-prisma-generator | Prisma のスキーマから GraphQL のスキーマを生成 |
| graphql-auto-query      | GraphQL のクエリを自動生成                     |

Prisma スキーマから GraphQL スキーマを生成する処理の詳細はこちら  
https://github.com/node-libraries/pothos-prisma-generator/tree/master/packages/pothos-prisma-generator

GraphQL スキーマからクエリを自動生成する処理はこちら  
https://github.com/SoraKumo001/graphql-auto-query

## コードの内容

主要機能は各プラグインが行っているので、それらを呼び出すだけで作業完了です。

- builder.ts

各プラグインを設定して SchemaBuilder を作成します。

```ts
import SchemaBuilder from "@pothos/core";
import PrismaPlugin from "@pothos/plugin-prisma";
import PrismaUtils from "@pothos/plugin-prisma-utils";
import PothosPrismaGeneratorPlugin from "pothos-prisma-generator";
import { prisma } from "./prisma.js";

/**
 * Create a new schema builder instance
 */
export const createBuilder = () => {
  return new SchemaBuilder<{
    Prisma: typeof prisma;
  }>({
    plugins: [PrismaPlugin, PrismaUtils, PothosPrismaGeneratorPlugin],
    prisma: {
      client: prisma,
    },
  });
};

export type Builder = ReturnType<typeof createBuilder>;
```

- prisma.ts

PrismaClient を作成します。実際は各プロジェクト内の PrismaClient が使用されます。

```ts
import { PrismaClient } from "@prisma/client";

export const prisma = new PrismaClient({
  log: [
    {
      emit: "stdout",
      level: "warn",
    },
  ],
});
```

- index.ts

GraphQL Yoga に Schema を設定して Hono 経由で起動します。また、Playground に表示する Document を自動生成して、使用可能なクエリが一通り表示されるようにします。

```ts
#!/usr/bin/env node

import { serve } from "@hono/node-server";
import { explorer } from "apollo-explorer/html";
import { generate } from "graphql-auto-query";
import { createYoga } from "graphql-yoga";
import { Hono, Context as HonoContext } from "hono";
import { createBuilder } from "./builder.js";

const builder = createBuilder();

const schema = builder.toSchema({ sortSchema: false });
const yoga = createYoga<HonoContext>({
  graphqlEndpoint: "*",
  schema,
});

const document = generate(schema, 1);

const app = new Hono();
app.get("/", (c) => {
  return c.html(
    explorer({
      initialState: {
        document,
      },
      endpointUrl: "/",
      introspectionInterval: 5000,
    })
  );
});
app.mount("/", yoga);

serve({ fetch: app.fetch, port: 5556 });

console.log("http://localhost:5556/");
```

## 使い方

各プロジェクトで利用しているパッケージマネージャで`prisma-studio-graphql`をインストール後、`npx prisma-studio-graphql`を実行します。

```bash
npm install -D prisma-studio-graphql
npx prisma-studio-graphql
```

![](https://raw.githubusercontent.com/node-libraries/prisma-studio-graphql/master/document/image01.avif)
