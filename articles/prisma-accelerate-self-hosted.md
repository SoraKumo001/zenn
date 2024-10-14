---
title: "Prisma Accelerate の Self Hosting で Cloudflare + Remix + PostgreSQL"
emoji: "🎃"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [prisma, cloudflare, remix, postgresql, typescript]
published: true
---

# Prisma Accelerate の Self Hosting の必要性

Prisma Client でクエリを作ると、Prisma Engine を介して、各 DB に対応した SQL に変換されます。Prisma Engine は Rust で記述されており、環境ごとにバイナリが用意されています。しかし Cloudflare Workers/Pages や Vercel Edge Functions、Deno などではネイティブのバイナリが使用できないため、WebAssembly 版の Prisma Engine が提供されています。ただ、WebAssembly 版はサイズが大きく、900KB 程度あります。Cloudflare Workers/Pages の無料版や Vercel Edge Functions では 1MB というサイズ制限があるため、その他のコードと合わせてデプロイすることが難しいです。

この状況を解決するために、Prisma 公式サービスで Prisma Accelerate が提供されています。Prisma Accelerate は Prisma Client から Prisma Engine を切り離してリモートで提供するサービスです。この機能を利用すると、Prisma Client で作成されたクエリはリモートサーバで実行されるため、ローカルにエンジンを必要としなくなります。こうすることで、Prisma Engine のサイズを気にすることなく、Prisma Client を利用できます。

https://www.prisma.io/pricing

上記の通り、無料でも一ヶ月 6 万件のクエリまで無料で利用できます。それを超えると 100 万クエリあたり$18 となります。アクセスが増えた時に結構な出費となるため、自前で Prisma Accelerate に相当する機能を運用したくなります。ただ、公式で Self Hosting の提供はされていないため、自前でなんとかする必要があります。

# Self Hosting の方法

## Self Hosting 用パッケージ

こちらに Prisma Accelerate を Self Hosting するパッケージを用意しました。

https://www.npmjs.com/package/prisma-accelerate-local

## 2024/10/13 時点での問題点

https://github.com/prisma/prisma-engines/pull/5002

上記の Pull Request により、PostgreSQL の Prisma Engine が 圧縮サイズで 1MB を超えました。これにより Cloudflare の無料プランでは使用不能です。この PR が適用されたのは@prisma/client@5.20.0 からです。そのため、PostgreSQL 用の SelfHost を Cloudflare の無料プラン で行う場合、@prisma/client@5.19.1 を使用する必要があります。

## Cloudflare と Deno Deploy でサンプル

サンプルは PostgreSQL を使用していますが、他の DB でも同様の方法で利用できます。以下のリポジトリを Deploy すれば、Prisma Accelerate を Self Hosting できます。あとは、発行されたアドレスに対してリクエストを送るだけで、Prisma Accelerate を利用できます。

### Deno Deploy での Self Hosting

https://github.com/SoraKumo001/prisma-accelerate-deno

[無料枠](https://deno.com/deploy/pricing)で 100 万/月 リクエストまで利用できます。コードサイズに制限がないため、Prisma Engine のサイズを気にする必要がありません。

### Cloudflare Workers での Self Hosting

https://github.com/SoraKumo001/prisma-accelerate-workers

[無料枠](https://developers.cloudflare.com/workers/platform/pricing/)で 10 万/日 リクエストまで利用できます。無料プランでは圧縮時のコードサイズが 1MB を超えるとエラーが発生するため、Prisma Engine のサイズに注意が必要です。PostgreSQL を使用する場合は package.json の resolutions で、バージョンを 5.19.1 に固定してください。

## Self Hosting のコード解説

基本的な動作は prisma-accelerate-local が行うため、リモートアクセス時に必要となる secret の設定や、Prisma Engine を動作させるために必要な WASM ファイルの読み込みや Adapter の作成を行います。

```ts
import { Pool } from "pg";
import { PrismaPg } from "@prisma/adapter-pg";
import { createFetcher } from "prisma-accelerate-local/workers";
import WASM from "@prisma/client/runtime/query_engine_bg.postgresql.wasm";

export type Env = {
  SECRET: string;
};

export default {
  fetch: createFetcher({
    runtime: () =>
      require(`@prisma/client/runtime/query_engine_bg.postgresql.js`),
    secret: (env: Env) => env.SECRET,
    queryEngineWasmModule: WASM,
    adapter: (datasourceUrl: string) => {
      const url = new URL(datasourceUrl);
      const schema = url.searchParams.get("schema") ?? undefined;
      const pool = new Pool({
        connectionString: url.toString() ?? undefined,
      });
      return new PrismaPg(pool, {
        schema,
      });
    },
  }),
};
```

# 使い方

## API Key の作成

無料で使える PostgreSQL のサービス Supabase を使う場合の例です。速度的に 6543 の pooler の方を使うことをおすすめします。

```sh
npx prisma-accelerate-local -s secret -m postgres://postgres.xxxxxxxx:xxxxxxx@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres
```

すると以下のような Key が生成されます。

```txt
eyJhbGciOiJIUzI1NiJ9.eyJkYXRhc291cmNlVXJsIjoicG9zdGdyZXM6Ly9wb3N0Z3Jlcy54eHh4eHh4eDp4eHh4eHh4QGF3cy0wLWFwLW5vcnRoZWFzdC0xLnBvb2xlci5zdXBhYmFzZS5jb206NjU0My9wb3N0Z3JlcyIsImlhdCI6MTcyODgyNTc3NywiaXNzIjoicHJpc21hLWFjY2VsZXJhdGUifQ.Hyn0W8aBbTJ77BhqAuNkJeHEohXaLM7K0AxUtppcz8A
```

この Key を使って、Prisma の接続先を設定します。

- .env

```env
DATABASE_URL="prisma://
xxxxxx.xxxxx.workers.dev?api_key=eyJhbGciOiJIUzI1NiJ9.eyJkYXRhc291cmNlVXJsIjoicG9zdGdyZXM6Ly9wb3N0Z3Jlcy54eHh4eHh4eDp4eHh4eHh4QGF3cy0wLWFwLW5vcnRoZWFzdC0xLnBvb2xlci5zdXBhYmFzZS5jb206NjU0My9wb3N0Z3JlcyIsImlhdCI6MTcyODgyNTc3NywiaXNzIjoicHJpc21hLWFjY2VsZXJhdGUifQ.Hyn0W8aBbTJ77BhqAuNkJeHEohXaLM7K0AxUtppcz8A"
```

## Remix での利用

https://github.com/SoraKumo001/cloudflare-remix-accelerate

上記のリポジトリで、Remix で Prisma Accelerate を利用する方法を解説します。

### 環境変数

サンプルとして Supabase の接続情報を設定します。

- .env

`prisma migrate dev`を実行するのに必要な情報です。

```env
DIRECT_DATABASE_URL=postgres://postgres.xxxx:xxxxx@aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres?schema=public
```

- .dev.var

実行時に必要な情報です。Self Hosting した Prisma Accelerate のアドレスと API Key を設定します。

```env
DATABASE_URL=prisma://xxxx.xxxx.workers.dev?api_key=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### Prisma Client の利用

- app/routes/\_index.tsx

`@prisma/client/edge`から PrismaClient をインポートします。ちなみに PrismaClient のインスタンスは、リクエストを超えて使い回すことは出来ないので、毎回新しいインスタンスを作成する必要があります。詳細は[こちらを参照](https://next-blog.croud.jp/contents/9e177edf-1707-4366-97d6-3f50d0c74f0e)してください。

```tsx
import { PrismaClient } from "@prisma/client/edge";
import { LoaderFunctionArgs } from "@remix-run/cloudflare";
import { useLoaderData } from "@remix-run/react";

export default function Index() {
  const values = useLoaderData<string[]>();
  return (
    <div>
      {values.map((v) => (
        <div key={v}>{v}</div>
      ))}
    </div>
  );
}

export async function loader({
  context,
}: LoaderFunctionArgs): Promise<string[]> {
  const prisma = new PrismaClient({
    datasourceUrl: context.cloudflare.env.DATABASE_URL,
  });
  await prisma.test.create({ data: {} });
  return prisma.test.findMany({ where: {} }).then((r) => r.map(({ id }) => id));
}
```

### 実行結果

https://cloudflare-remix-accelerate.pages.dev/

![](/images/prisma-accelerate-self-hosted/2024-10-15-08-39-22.png)

# まとめ

Prisma Accelerate を Self Hosting することで、Prisma Engine のサイズを気にすることなく、Prisma Client を Cloudflare Workers/Pages の無料プランや Vercel Edge Functions でも利用できるようになります。また、WebAssembly 版の Prisma Engine を直接利用する場合は、Adapter 設定などを書く必要がありますが、Prisma Accelerate の Self Hosting を利用することで、その手間を省くことができます。特に無料プラン運用を考えると、Remix のようなフレームワークと Prisma Engine の同居はサイズ的に不可能なので 事実上 Engine 分離は必須です。
