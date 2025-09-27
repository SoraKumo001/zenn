---
title: "React Router + Hono + Cloudflare　のテンプレートを作る"
emoji: "👻"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [react, cloudflare, hono, typescript]
published: true
---

# React Router のテンプレート

React Router では Cloudflare 用の公式のテンプレートが用意されています。しかし Hono を含んだテンプレートがないため、今回、用意しました。

https://github.com/SoraKumo001/react-router-templates

# 使い方

使い方は基本的に公式のテンプレートと同じです。

```bash
npx create-react-router@latest --template sorakumo001/react-router-templates/cloudflare
```

# 公式のテンプレートとの違い

こちらが公式テンプレートです

https://github.com/remix-run/react-router-templates/tree/main/cloudflare

## Middleware として Hono を導入

React Router の Middleware はまだ開発段階なので、現時点では Hono を使ったほうが無難です。

## `@cloudflare/vite-plugin`を除去

`@cloudflare/vite-plugin`を使うと、開発時に Cloudflare 環境の再現性が高まるのですが、外部モジュールの初期インポートに時間がかかるので、依存モジュールが増えていくと辛くなっていきます。また、`rolldown-vite`との併用ができないため、今回は取り除きました。

## `rolldown-vite`の導入

`rolldown-vite`を使うと、ビルド速度が半分以下に短縮されます。圧倒的な速度です。

# カスタマイズ部分の解説

## vite.config.ts

Hono が使えるように設定しています。ただし Hono の Cloudflare 用の Adapter を直接使わず、処理を修正しています。理由として元の Adapter は navigator.userAgent の値を偽装する処理が入っているため、Prisma の queryCompiler の機能を使おうと思った場合に、環境の識別ができず正常に動作しなくなるためです。

また、開発実行時と Deploy 時で、起動コードを共通化するために`virtual:react-router/server-build`をエイリアスで切り替えています。`@cloudflare/vite-plugin`を使った場合は、別の方法で起動コードの自動切り替えが行われるのですが今回未使用のため、この設定を入れています。

svg など import 系の Assets に関しては、利用するものを適宜指定する必要があります。足りないものは exclude で追加指定してください。これをやらないと、開発時に対象のファイルが表示されません。

handleHotUpdate でサーバ側でのみ動作するファイルのみフルリロードするようにしています。これを入れないと、`@hono/vite-dev-server`のデフォルト動作で、どのファイルを更新してもフルリロードされます。

```ts
import { reactRouter } from "@react-router/dev/vite";
import tailwindcss from "@tailwindcss/vite";
import serverAdapter, { defaultOptions } from "@hono/vite-dev-server";
import type { cloudflareAdapter } from "@hono/vite-dev-server/cloudflare";
import { defineConfig } from "vite";
import tsconfigPaths from "vite-tsconfig-paths";
import { getPlatformProxy } from "wrangler";

// Entry file
const entry = "./workers/app.ts";

// Prevent tampering with Hono's Cloudflare parameters executed by default
const adapter: typeof cloudflareAdapter = async (options) => {
  const proxy = await getPlatformProxy(options?.proxy);
  return {
    env: proxy.env,
    executionContext: proxy.ctx,
    onServerClose: () => proxy.dispose(),
  };
};

export default defineConfig({
  resolve: {
    alias: [
      {
        find: "../build/server/index.js",
        replacement: "virtual:react-router/server-build",
      },
    ],
  },
  ssr: {
    resolve: {
      externalConditions: ["worker"],
    },
  },
  plugins: [
    serverAdapter({
      adapter,
      entry,
      // Asset adjustment
      exclude: [
        ...defaultOptions.exclude,
        "/app/**",
        /\.(css|webp|png|svg)(\?.*)?$/,
      ],
      // HMR adjustment
      handleHotUpdate: ({ server, modules }) => {
        const isServer = modules.some((mod) => {
          return mod._ssrModule?.id && !mod._clientModule;
        });
        if (isServer) {
          server.hot.send({ type: "full-reload" });
          return [];
        }
      },
    }),
    tailwindcss(),
    reactRouter(),
    tsconfigPaths(),
  ],
  experimental: { enableNativePlugin: true },
});
```

## workers/app.ts

起動コードです。Hono を使って、React Router を呼び出しています。前述した通り`../build/server/index.js`は、Vite からは`virtual:react-router/server-build`に変換され、deploy などで`wrangler`から呼び出されるときは変換せずに使われます。

```ts
import { Hono } from "hono";
import { contextStorage } from "hono/context-storage";
import { getLoadContext } from "load-context";
import { createRequestHandler } from "react-router";

const app = new Hono();
app.use(contextStorage());

app.use(async (c) => {
  // @ts-ignore
  const build = await import("../build/server/index.js");
  // @ts-ignore
  const handler = createRequestHandler(build, import.meta.env?.MODE);

  const next = (input: Request | string, init?: RequestInit) => {
    return handler(new Request(input, init), {
      cloudflare: { env: c.env },
    });
  };
  const context = getLoadContext({
    request: c.req.raw,
    context: {
      cloudflare: {
        env: c.env,
        next,
      },
    } as never,
  });
  return handler(c.req.raw, context);
});

export default app;
```

## .env

NODE_ENV を production に設定しています。これがなんの為にあるのかというと、`wrangler deploy`時に必要だからです。`wrangler`は、バックエンド側のコードを esbuild でビルドします。そして環境変数が設定されていないと node_module に含まれている react が、デバッグ用の開発パッケージをビルドに加えてしまい、性能の低下やサイズの増加を引き起こします。フロント側は影響を受けませんが、バックエンド側ではこの問題が発生します。

これ、結構重大な問題なのですが、巷のリポジトリを覗いてみても、だれも対処していません。

```env
# If this configuration is missing during `wrangler deploy`, the React development module will be used.
NODE_ENV=production
```

# まとめ

`React Router`は`Next.js`と比べると、初期設定の選択肢が多いため、それがハードルになっている感があります。ただ、Cloudflare 用の React 用フレームワークと考えた場合、他に選択肢がありません。`Next.js`を`opennext`から使うという手を思いつくかもしれませんが、ビルドで吐き出されるサイズが巨大すぎてはっきり言って問題外です。

公式のテンプレートは`@cloudflare/vite-plugin`を使ったものになっており、本番に近い環境をエミュレーションして開発できる反面、モジュールの読み込みにクセがあります。依存パッケージによっては、開発が難しくなる場合があります。原理を話すと長くなるのですが、エミュレーション環境である`workerd`でモジュールのやりとりをするとき、ESM しか対応していないので、node_modules の魑魅魍魎なパッケージ群をうまく変換しながら渡す必要があります。ビルド時は全体を一括でまとめて変換できるのでよいのですが、開発時は部分的にビルドしながら渡していかねばならず、このときにモジュールの整合性をとる作業が破滅的に複雑です。そのため、`@cloudflare/vite-plugin`を使った場合、依存パッケージが増えるに従いどんどん動作が重くなっていきます。

ということで、あえて`@cloudflare/vite-plugin`を外したテンプレートを作りました。開発時の再現性は劣りますが、快適性は圧倒的に良くなっています。公式テンプレートで、依存パッケージの問題で苦労している人は使ってみてください。
