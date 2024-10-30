---
title: "Prisma Postgres の Early Access を試す"
emoji: "🙌"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [prisma, postgres, typescript, cloudflare]
published: true
---

# Prisma Postgres

Prisma が PostgreSQL の機能を提供するサービスを開始しました。検索で引っ掛ける時不便なので、独自名称を付けて欲しかったです。

https://www.prisma.io/blog/announcing-prisma-postgres-early-access

具体的な価格表はログイン後に確認できます。

![](/images/prisma-postgres/2024-10-30-10-01-31.png)

DB 自体のアクセスは無料で、Prisma Accelerate の利用によってコストが発生します。

# プロジェクトの作成

プロジェクトの作成時にリージョンが選べます。東京リージョンも選択可能です。

![](/images/prisma-postgres/2024-10-30-10-04-24.png)

プロジェクトを作ると、Prisma Accelerate の形式の URL が発行されます。

```env
DATABASE_URL="prisma+postgres://accelerate.prisma-data.net/?api_key=xxxxx"
```

Prisma 専用の形式なので、他のツールからはアクセスできません。必ず Prisma Accelerate を経由する必要があります。

# マイグレーション

DATABASE_URL が`prisma+postgres:`になっており、prisma@5.21.1 だと `prisma migrate dev` が通ります。今回のサービスと連携させるための専用形式のようです。以前は `Prisma Accelerate` の URL では動作しなかったのですが改善されたようです。

# 実際に使ってみる

Cloudflare Workers で動作させてみます。

- .env

```env
DATABASE_URL="prisma+postgres://accelerate.prisma-data.net/?api_key=xxxx"
```

- .dev.vars

```env
DATABASE_URL="prisma+postgres://accelerate.prisma-data.net/?api_key=xxxx"
```

- wrangler.toml

```toml
#:schema node_modules/wrangler/config-schema.json
name = "prisma-postgres"
compatibility_date = "2024-09-25"
compatibility_flags = ["nodejs_compat"]
main = "./src/index.ts"

[observability]
enabled = true
```

- prisma/prisma.schema

```prisma
generator client {
  provider        = "prisma-client-js"
  previewFeatures = ["driverAdapters"]
}

datasource db {
  provider  = "postgresql"
  url       = env("DATABASE_URL")
}

model Test {
  id String @id @default(uuid())
}
```

- src/index.ts

```ts
import { PrismaClient } from "@prisma/client/edge";

export interface Env {
  DATABASE_URL: string;
}

export default {
  async fetch(
    request: Request,
    env: Env,
    _ctx: ExecutionContext
  ): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname !== "/") return new Response("Not Found", { status: 404 });

    const prisma = new PrismaClient({ datasourceUrl: env.DATABASE_URL });

    await prisma.test.create({ data: {} });
    const result = await prisma.test
      .findMany()
      .then((r) => r.map(({ id }) => id));
    return new Response(JSON.stringify(result, undefined, "  "), {
      headers: { "content-type": "application/json" },
    });
  },
};
```

```sh
pnpm run prisma migrate dev
pnpm run prisma generate --no-engine
pnpm wrangler dev
```

- 動作結果

![](/images/prisma-postgres/2024-10-30-10-17-37.png)

# まとめ

DB を無料枠で使える選択肢が一つ増えました。ただ、`Prisma Accelerate` 経由専用サービスなので、他のツールを使って PostgreSQL に直接アクセスするという選択はとれません。また、`Prisma Accelerate` の価格を鑑みるに、ある程度の規模のアクセスがある場合は、他のサービスを利用した方がコストが安くなる可能性があります。

Cloudflare Workers で利用する場合は、重量級の PrismaEngine が不要になるので、1MB のサイズ問題を回避することが出来ます。

私の場合、Cloudflare Workers 上で Prisma を動作させるとき、 PostgreSQL は Supabase を使い、 `Prisma Accelerate` の代わりに [prisma-accelerate-local](https://www.npmjs.com/package/prisma-accelerate-local) で PrismaEngine を分離しています。

もし今回のサービスを使うとすると、実験やサンプルプログラムなどをサクッと作りたい場合などになると思います。
