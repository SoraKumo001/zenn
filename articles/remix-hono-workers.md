---
title: "Remix + Hono + Cloudflare Workers で process.env を使う"
emoji: "✨"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [hono, remix, cloudflare, react, prisma]
published: true
---

# process.env が使えない問題

Cloudflare 用のプログラムを作る場合、Node.js ランタイム上では当たり前のように使えていた process.env が使用できないという問題の洗礼を受けます。Cloudflare では env を持った Context は、クライアントからのコネクションが成立した際に作られ、その後ではければ環境変数を参照できません。このため、Context が使用可能となった後に、環境変数を必要としている場所へ配らねばなりません。Node.js 用のプログラムを Cloudflare 向けに移植する際に、大幅にコードを書き換える必要が出てきます。

一応、Cloudflare Workers 用のプログラムは`compatibility_flags`に`nodejs_compat`を加えることで、process.env が読み書きできるようになります。ただし、元々の中身は空です。

# Hono を使って process.env を使えるようにする

サンプルは以下のリポジトリにあります。

https://github.com/SoraKumo001/remix-hono-workers/

## 初期コード作成

元となるコードは以下のコマンドでテンプレートから生成します。

```sh
npm create cloudflare@latest . -- --framework=remix --experimental
```

## server.ts

初期コードは完全に無視して、Hono を組み込んだコードに置き換えます。`remix vite:dev`と`wrangler dev`の entry コードを共通化しています。元々のテンプレートだと server.ts は`remix vite:dev`では使われませんが、今回は共通のコードで動作させます。

Hono の`contextStorage`でコンテキストをバケツリレーせず`getContext`で取得出来るようにしています。さらに`Object.getOwnPropertyDescriptor`で process.env で`context.env`を返すようにしています。

`./build/server`がビルド時、`virtual:remix/server-build`は開発モード時に利用され、このモジュール読み込み時に Remix 用に作った各コードの実行が開始されます。

```ts
import { Hono } from "hono";
import { contextStorage, getContext } from "hono/context-storage";
import {
  type AppLoadContext,
  createRequestHandler,
} from "@remix-run/cloudflare";

const app = new Hono();
app.use(contextStorage());
app.use(async (_c, next) => {
  if (!Object.getOwnPropertyDescriptor(process, "env")?.get) {
    const processEnv = process.env;
    Object.defineProperty(process, "env", {
      get() {
        try {
          return { ...processEnv, ...getContext().env };
        } catch {
          return processEnv;
        }
      },
    });
  }
  return next();
});

app.use(async (c) => {
  const build =
    process.env.NODE_ENV !== "development"
      ? import("./build/server")
      : // eslint-disable-next-line @typescript-eslint/ban-ts-comment
        // @ts-expect-error
        // eslint-disable-next-line import/no-unresolved
        import("virtual:remix/server-build");
  const handler = createRequestHandler(await build);
  return handler(c.req.raw, {
    cloudflare: {
      env: c.env,
    },
  } as AppLoadContext);
});

export default app;
```

## vite.config.ts

Vite の設定で Hono を利用可能にしています。`remix vite:dev`の開発モードでの起動時は`server.ts`を読み込むようにしています。また`externalConditions: ["workerd", "worker"]`を追加していますが、これがないと開発モードで React の renderToReadableStream がインポートエラーを起こすので注意してください。

```ts
import { defineConfig } from "vite";
import { vitePlugin as remix } from "@remix-run/dev";
import tsconfigPaths from "vite-tsconfig-paths";
import adapter from "@hono/vite-dev-server/cloudflare";
import serverAdapter from "hono-remix-adapter/vite";

declare module "@remix-run/cloudflare" {
  interface Future {
    v3_singleFetch: true;
  }
}

export default defineConfig({
  plugins: [
    remix({
      future: {
        v3_fetcherPersist: true,
        v3_relativeSplatPath: true,
        v3_throwAbortReason: true,
        v3_singleFetch: true,
        v3_lazyRouteDiscovery: true,
      },
    }),
    serverAdapter({
      adapter,
      entry: "server.ts",
    }),
    tsconfigPaths(),
  ],
  ssr: {
    resolve: {
      conditions: ["workerd", "worker", "browser"],
      externalConditions: ["workerd", "worker"],
    },
  },
  resolve: {
    mainFields: ["browser", "module", "main"],
  },
  build: {
    minify: true,
  },
});
```

## wrangler.toml

`compatibility_flags`の追加と、テスト用の環境変数を作っています。

```toml
#:schema node_modules/wrangler/config-schema.json
name = "remix-hono-workers"
compatibility_date = "2024-11-12"
compatibility_flags = ["nodejs_compat"]
main = "./server.ts"
assets = { directory = "./build/client" }

# Workers Logs
# Docs: https://developers.cloudflare.com/workers/observability/logs/workers-logs/
# Configuration: https://developers.cloudflare.com/workers/observability/logs/workers-logs/#enable-workers-logs
[observability]
enabled = true

[vars]
a = "123"
```

## app/routes/\_index.tsx

Remix 用のコードですが、`process.env`をモジュール直下で使っています。この状態でも、きちんと動作することが確認できます。

```tsx
import { useLoaderData } from "@remix-run/react";

export default function Index() {
  const value = useLoaderData<string>();
  return <pre>{value}</pre>;
}

// At the point of module execution, process.env is available.
const value = JSON.stringify(process.env, null, 2);

export const loader = () => {
  return value;
};
```

## 出力結果

![](/images/remix-hono-workers/2024-11-19-08-37-13.png)

# Prisma をインポートした変数から直接使えるようにする

サンプルは以下のリポジトリにあります。

https://github.com/SoraKumo001/remix-hono-workers/tree/prisma

## app/routes/\_index.tsx

Node.js 用のコードだと、こんな形で PrismaClient を使うことが多いですが、Cloudflare 向けではこういうコードは使えません。しかし不可能を可能にしました。

```tsx
import { useLoaderData } from "@remix-run/react";
import { prisma } from "~/libs/prisma";

export default function Index() {
  const value = useLoaderData<string>();
  return <div>{value}</div>;
}

export async function loader(): Promise<string> {
  //You can directly use the PrismaClient instance received from the module
  const users = await prisma.user.findMany();
  return JSON.stringify(users);
}
```

## libs/prisma.ts

`prisma`という変数を直接使っているように見えますが、実際には`getContext`で取得した PrismaClient インスタンスを返しています。このようにすることで、PrismaClient インスタンスを見た目上、変数から直接使うことができます。

今回 process.env を使っていますが、本来は getContext 側から D1Database を持ってくるほうが良いでしょう。

```ts
import { PrismaClient } from "@prisma/client";
import { PrismaD1 } from "@prisma/adapter-d1";
import { getContext } from "hono/context-storage";

type Env = {
  Variables: {
    prisma: PrismaClient;
  };
};

// Create a proxy that returns a PrismaClient instance on SessionContext with the variable name prisma
export const prisma = new Proxy<PrismaClient>({} as never, {
  get(_target: unknown, props: keyof PrismaClient) {
    const context = getContext<Env>();
    if (!context.get("prisma")) {
      const adapter = new PrismaD1(process.env.DB as unknown as D1Database);
      context.set("prisma", new PrismaClient({ adapter }));
    }
    return context.get("prisma")[props];
  },
});
```

## 出力結果

![](/images/remix-hono-workers/2024-11-19-08-37-39.png)

# まとめ

Cloudflare 向けのプログラムを極力 Node.js に近い形で書くために、Hono を使って process.env を使えるようにしました。また、PrismaClient を直接変数から使えるようにすることで、Node.js のコードをそのまま使えるようにしました。これにより、Node.js のコードを Cloudflare 向けに移植する際に、大幅なコードの書き換えを減らすことができます。
