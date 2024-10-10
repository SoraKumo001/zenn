---
title: "Cloudflare で Prisma + PostgreSQL を使う場合、リクエストを超えてインスタンスを使いまわしてはいけない"
emoji: "🙆"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [cloudflare, prisma, postgresql, typescript]
published: true
---

# Cloudflare Workers の制限

Cloudflare Workers では、Workers 内で生成したコネクションはリクエストを超えて使いまわすことができません。そのため、Prisma や PostgreSQL などの外部コネクションを使う場合は、リクエストごとに新しいインスタンスを生成する必要があります。D1 のようなコネクションを伴わない DB であれば、インスタンスを使いまわしても問題ありません。

# Prisma + PostgreSQL の例

最小限のコードで Prisma インスタンスを使いまわしたらどうなるのかという検証を行いました。以下のリンク先で実際に動作させていますが、一回目は成功するものの、二回目はエラーになります。そして Worker が落ちるので、三回目は成功します。そして失敗と成功を繰り返します。

https://cloudflare-workers-prisma-connection.mofon001.workers.dev/

```ts
export * from "@prisma/adapter-pg";
import { Pool } from "pg";
import { PrismaPg } from "@prisma/adapter-pg";
import { PrismaClient } from "@prisma/client";

export interface Env {
  DATABASE_URL: string;
  prisma: Fetcher;
}

// Errors occur when Prisma instances are used around.
let prisma: PrismaClient;

export default {
  async fetch(
    request: Request,
    env: Env,
    _ctx: ExecutionContext
  ): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname !== "/") return new Response("Not Found", { status: 404 });
    if (!prisma) {
      const databaseUrl = new URL(env.DATABASE_URL);
      const schema = databaseUrl.searchParams.get("schema") ?? undefined;
      const pool = new Pool({
        connectionString: env.DATABASE_URL,
      });
      const adapter = new PrismaPg(pool, { schema });
      prisma = new PrismaClient({ adapter });
    }
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

- 成功したリクエスト

![](/images/cloudflare-workers-prisma-connection/2024-10-11-08-35-19.png)

- 出力されたエラー

![](/images/cloudflare-workers-prisma-connection/2024-10-11-08-32-30.png)

# まとめ

Cloudflare Workers で Prisma や PostgreSQL を使う場合は、リクエストごとに新しいインスタンスを生成しましょう。

ちなみに `compatibility_flags` で `nodejs_compat_v2` を有効にし、さらに [pg-compat](https://www.npmjs.com/package/pg-compat) パッケージをインストールすれば、Cloudflare 上で Node.js 環境と同じように pg を直接使うことが出来ます。
