---
title: "Remix + Cloudflare + Prisma で、Node.jsとWrangler実行時にimportを適切に切り替える"
emoji: "🗂"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: []
published: false
---

# Remix + Cloudflare で Prisma を使う場合の問題点

この環境で Prisma を使う場合に必要になるパッケージ

| remix vite:dev(Node.js) | wrangler pages dev        |
| ----------------------- | ------------------------- |
| pg                      | @prisma/adapter-pg-worker |
| @prisma/adapter-pg      | @prisma/pg-worker         |

実行方法によって環境が異なるため、インポートするパッケージを変えなければなりません。

# 実行環境によるインポートファイルの切り替え

https://github.com/SoraKumo001/cloudflare-remix-env-paths

インポートの切り替えは Vite の機能を使えば簡単に行えます。

## vite でエイリアスを仕込む

- vite.config.ts

NODE_ENV に応じて、インポート時のコードが切り替わるようにします。

```ts
import {
  vitePlugin as remix,
  cloudflareDevProxyVitePlugin as remixCloudflareDevProxy,
} from "@remix-run/dev";
import { defineConfig } from "vite";
import tsconfigPaths from "vite-tsconfig-paths";
import path from "path";

export default defineConfig({
  resolve: {
    alias:
      process.env.NODE_ENV === "development"
        ? {
            "~/prisma": path.resolve(__dirname, "./app/prisma/index.dev"),
          }
        : undefined,
  },
  plugins: [
    remixCloudflareDevProxy(),
    remix({
      future: {
        v3_fetcherPersist: true,
        v3_relativeSplatPath: true,
        v3_throwAbortReason: true,
      },
    }),
    tsconfigPaths(),
  ],
});
```

## 必要なパッケージを切り出す

Node.js と Wrangler で、呼び出すパッケージの違いを吸収するため、それぞれのインポートを行います。このサンプルは必要なものを export しているだけですが、ここで Prisma クライアントを生成する関数を作っても問題ありません。

- app/prisma/index.ts

```ts
export * from "@prisma/adapter-pg-worker";
import pg from "@prisma/pg-worker";
export const Pool = pg.Pool;
```

- app/prisma/index.dev.ts

```ts
export * from "@prisma/adapter-pg";
import pg from "pg";
export const Pool = pg.Pool;
```

## paths で設定したエイリアスでインポートする

Pool と PrismaPg は、Vite のエイリアスによって環境に応じて自動的に切り替わります。

- app/routes/\_index.tsx

```tsx
import { LoaderFunctionArgs } from "@remix-run/cloudflare";
import { Pool, PrismaPg } from "~/prisma";
import { PrismaClient } from "@prisma/client";
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
  const pool = new Pool({
    connectionString: context.cloudflare.env.DATABASE_URL,
  });
  const adapter = new PrismaPg(pool);
  const prisma = new PrismaClient({ adapter });
  await prisma.test.create({ data: {} });
  return prisma.test.findMany().then((r) => r.map(({ id }) => id));
}
```

# まとめ

環境による差異は、Vite の機能で吸収可能です。ただ、Cloudflare を無料プランで動作させるのを前提とした場合は Remix + Prisma をそのまま使う組み合わせはおすすめできません。サンプルレベルの内容なら問題ないのですが、ある程度まともに作っていくと、無料プランで使用可能な容量をオーバーしてしまうからです。そうなるとフロントとバックエンドを分離するか、巨大な Prisma エンジンを分離するかという選択になります。

フロントとバックエンドの分離は Cloudflare Pages + Cloudflare Workers のような形にする必要があります。また、Prisma エンジンの分離は Prisma Accelarate を使うか、この機能をセルフホストするかという選択になります。

私の場合は全て無料にするためにセルフホストという選択を取っています。Prisma Accelarate のセルフホストから画像最適化まで、全部自前で作りました。足りないものは作れば全て解決です。

https://next-blog.croud.jp/contents/eec22faf-3563-4a77-9a47-4dfddc604141

また、画像最適化に関しては Deno Deploy で Edge Cache の機能が使えるようになったため、こちらで使うのを前提とする avif 対応のパッケージを作りました。avif のエンコードはサイズが大きく、パッケージが圧縮時で 1.5MB になるため、Cloudflare の無料プランで動かず、以前作ったパッケージではあえて機能を入れていませんでした。しかしサイズ制限のない Deno Deploy では問題なく動きます。

https://www.npmjs.com/package/wasm-image-optimization-avif

Deno Deploy 用の画像最適化の記事はこちらです。

https://next-blog.croud.jp/contents/b9a80cee-4803-4fd1-912a-2610c2aa4d70
