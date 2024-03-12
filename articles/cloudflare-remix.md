---
title: "[すべて無料]Remix+Cloudflare Pagesでブロクシステムを作成する"
emoji: "🤖"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [remix, nextjs, react, prisma, cloudflare]
published: true
---

こちらで同システムを使って Blog を書いています。
https://next-blog.croud.jp/contents/eec22faf-3563-4a77-9a47-4dfddc604141

# 環境構成

## インフラ

| サービス           | 内容                                          |
| ------------------ | --------------------------------------------- |
| Supabase           | Database                                      |
| Firebase           | Storage <br/>認証                             |
| Cloudflare Pages   | Front(Remix) & Backend(GraphQL yoga)          |
| Cloudflare Workers | 画像最適化<br/>OGP 生成<br/>PrismaQueryEngine |

すべて無料で使用可能です。各サービスとも無料範囲が大きいのと、最終的な出力結果が 無制限で使える Cloudflare CDN キャッシュで配信されるので、一日に何万アクセスレベルでも無料でいけます。

## 主な使用パッケージ

| パッケージ     | 説明                                           |
| -------------- | ---------------------------------------------- |
| Prisma         | Database 用 ORM                                |
| Graphql Yoga   | GraphQL サーバ                                 |
| Pothos GraphQL | GraphQL フレームワーク                         |
| Remix          | Cloudflare と相性の良い React 用フレームワーク |
| Urql           | GraphQL クライアント                           |

上記構成で作りました。
バックエンドとフロントのビルドを統合したかったので、GraphQL サーバは、Remix に載せる形になっています。この構成の凄まじいのは、ローカル環境からコマンドを実行して約 17 秒で、CloudflarePages にビルド込みでデプロイされることです。

# Next.js から Remix への移植理由

もともと React のフレームワークは Next.js を使っていました。しかし商利用も可能で制限がゆるい Cloudflare Pages をインフラとして使いたかったので、相性の良い Remix に移植することにしました。

CloudflarePages でも Next.js は動くのですが、私の Blog システムで Edge 設定を行うと、謎のビルドエラーが出ました。配置したファイルの数を減らすと内容に関係なく何故かビルドが通ります。容量的に問題があるわけでもなく、結局解決不能だったので Next.js の使用は諦めました。

# 事前に知っておくべき Cloudflare Pages/Workers の制限事項

https://developers.cloudflare.com/workers/platform/limits/#worker-limits

| 項目           | 制限                                                                               |
| -------------- | ---------------------------------------------------------------------------------- |
| リクエスト数   | 10 万回/日<br>千回/分                                                              |
| メモリ         | 128MB                                                                              |
| CPU            | 10ms<br>使用している感じだと、連続してオーバーしなければある程度は許してくれる感じ |
| 外部への fetch | 最大並列数 6<br>50 回/1 アクセスあたり                                             |
| 内部サービス   | 1,000 回/1 アクセスあたり                                                          |
| Body サイズ    | 100MB                                                                              |
| Worker サイズ  | 1MB(zip 圧縮サイズで計算)                                                          |

画像の最適化の場合、1600\*1600 ぐらいの画像を変換すると高確率で CPU 制限に引っかかります。また、外部サービスを呼び出すようなコードを書いた場合、並列アクセス時にデッドロックしないように気をつける必要があります。

また、Worker サイズはバックエンドで動く JavaScript や wasm を圧縮したときのサイズです。Pages で Assets として配るファイルは計算に入れません。このサイズがどうにもならない時は、Worker を分離するしかありません。

# 必要な機能

## 画像最適化機能

別になくても困らないのですが、あったほうがページが軽くなるので推奨事項です。Cloudflare には有料での画像最適化サービスがありますが、無料というのが大前提なので却下です。

画像変換は自分で作らなくともライブラリが世の中に一通り揃っています。その手のライブラリ類はほとんどが C 言語で組まれているので、wasm にすれば JavaScript から使えるというのは誰にでも思いつくでしょう。自分で作るのはそれらを組み合わせてツギハギをする部分だけです。

https://github.com/SoraKumo001/cloudflare-workers-image-optimization

## OGP 画像生成機能

Next.js では Vercel がライブラリを提供しているので簡単に実装できます。Cloudflare で同じことをやろうとすると、wasm の読み込みなどの仕様の違いから、似たような内容を自分で再実装する必要があります。

https://github.com/SoraKumo001/cloudflare-ogp

## Prisma の QueryEngine

Cloudflare のような EdgeRuntime を Prisma から使う場合、ネイティブバイナリで実装されている QueryEngine は使えません。wasm 版を使う必要があるのですが、そのサイズが圧縮しても 900KB 程度あります。無料版の Cloudflare での最大サイズは圧縮サイズで 1MB までなので、エンジンを積んだだけで他のことがほとんど何もできなくなります。解決策は QueryEngine とそれを呼び出す部分を分離することです。

Prisma は Prisma Accelerate というサービスを提供しており、QueryEngine を外部サービスに分離する機能を最初から持っています。一応、Prisma Accelerate も無料で使えるのですが、無料枠の範囲が小さいので、アクセスが増えてくるとこの部分がネックになります。

つまり、この部分の機能も自分で実装しろということです。ということで作りました。ローカルで動かせばローカル DB へのアクセスを提供しデバッグを容易にし、CloudflareWorkers に設置すれば Prisma Accelerate の代わりになります。

https://github.com/node-libraries/prisma-accelerate-local
https://github.com/SoraKumo001/prisma-accelerate-workers

# Remix への移植

下準備に手間取りましたが、ようやく Remix へ移植できます。

## fetch に細工をする

まず、Remix の起動時に呼ばれる server.ts で fetch に対して細工を行います。まず Prisma の data-proxy 機能がローカル Proxy(127.0.0.1)にアクセスしようとしたら https を http に変換します。Prisma の data-proxy は https がハードコーディングされており、外部からの設定変更ができなかったので、この対処が必要になります。また、本番稼働時に DATABASE_URL へのアクセスを検知したら、fetch を ServiceBindings 用のものへ切り替えます。これで Workers 間のやりとりが Cloudflare の内部ネットワークで接続されるので、多少は高速化されます。

- server.ts

```tsx
import { logDevReady } from "@remix-run/cloudflare";
import { createPagesFunctionHandler } from "@remix-run/cloudflare-pages";
import * as build from "@remix-run/dev/server-build";

if (process.env.NODE_ENV === "development") {
  logDevReady(build);
}

type Env = {
  prisma: Fetcher;
  DATABASE_URL: string;
};

const initFetch = (env: Env) => {
  const that = globalThis as typeof globalThis & { originFetch?: typeof fetch };
  if (that.originFetch) return;
  const originFetch = globalThis.fetch;
  that.originFetch = originFetch;
  globalThis.fetch = (async (input: RequestInfo, init?: RequestInit) => {
    const url = new URL(input.toString());
    if (["127.0.0.1", "localhost"].includes(url.hostname)) {
      url.protocol = "http:";
      return originFetch(url.toString(), init);
    }
    const databaseURL = new URL(env.DATABASE_URL as string);
    if (url.hostname === databaseURL.hostname && env.prisma) {
      return (env.prisma as Fetcher).fetch(input, init);
    }
    return originFetch(input, init);
  }) as typeof fetch;
};

export const onRequest = createPagesFunctionHandler({
  build,
  getLoadContext: (context) => {
    initFetch(context.env);
    return context;
  },
  mode: build.mode,
});
```

## バックエンド

### GraphQL Server の作成

GraphQL Yoga + Pothos GraphQL + pothos-query-generator という組み合わせです。

pothos-query-generator は Prisma スキーマの情報を参照して GraphQL スキーマを自動生成します。こちらも以前に作りました。これを使うと、ログインなど一部のシステム依存処理以外は自分でリゾルバを書く必要がなくなります。

https://www.npmjs.com/package/pothos-query-generator

- app/routes/api.graphql.ts

```ts
import { ActionFunctionArgs, LoaderFunctionArgs } from "@remix-run/cloudflare";
import { parse, serialize } from "cookie";
import { createYoga } from "graphql-yoga";
import { getUserFromToken } from "@/libs/client/getUserFromToken";
import { Context, getPrisma } from "../libs/server/context";
import { schema } from "../libs/server/schema";

const yoga = createYoga<
  {
    request: Request;
    env: { [key: string]: string };
    responseCookies: string[];
  },
  Context
>({
  schema: schema(),
  fetchAPI: { Response },
  context: async ({ request: req, env, responseCookies }) => {
    const cookies = parse(req.headers.get("Cookie") || "");
    const token = cookies["auth-token"];
    const user = await getUserFromToken({ token, secret: env.SECRET_KEY });
    const setCookie: typeof serialize = (name, value, options) => {
      const result = serialize(name, value, options);
      responseCookies.push(result);
      return result;
    };
    return {
      req,
      env,
      prisma: getPrisma(env.DATABASE_URL),
      user,
      cookies,
      setCookie,
    };
  },
});

export async function action({ request, context }: ActionFunctionArgs) {
  const env = context.env as { [key: string]: string };
  const responseCookies: string[] = [];
  const response = await yoga.handleRequest(request, {
    request,
    env,
    responseCookies,
  });
  responseCookies.forEach((v) => {
    response.headers.append("set-cookie", v);
  });
  return new Response(response.body, response);
}

export async function loader({ request, context }: LoaderFunctionArgs) {
  const env = context.env as { [key: string]: string };
  const responseCookies: string[] = [];
  const response = await yoga.handleRequest(request, {
    request,
    env,
    responseCookies,
  });
  responseCookies.forEach((v) => {
    response.headers.append("set-cookie", v);
  });
  return new Response(response.body, response);
}
```

- app/libs/server/builder.ts

Pothos の作成処理です。

```ts
import SchemaBuilder from "@pothos/core";
import PrismaPlugin from "@pothos/plugin-prisma";
import PrismaUtils from "@pothos/plugin-prisma-utils";
import { PrismaClient } from "@prisma/client/edge";
import PothosPrismaGeneratorPlugin from "pothos-prisma-generator";
import PrismaTypes from "@/generated/pothos-types";
import { Context } from "./context";

/**
 * Create a new schema builder instance
 */

type BuilderType = {
  PrismaTypes: PrismaTypes;
  Scalars: {
    Upload: {
      Input: File;
      Output: File;
    };
  };
  Context: Context;
};

export const createBuilder = (datasourceUrl: string) => {
  const builder = new SchemaBuilder<BuilderType>({
    plugins: [PrismaPlugin, PrismaUtils, PothosPrismaGeneratorPlugin],
    prisma: {
      client: new PrismaClient({
        datasourceUrl,
      }),
    },
    pothosPrismaGenerator: {
      authority: ({ context }) => (context.user ? ["USER"] : []),
      replace: { "%%USER%%": ({ context }) => context.user?.id },
    },
  });

  return builder;
};
```

- app/libs/server/schema.ts

こちらはログインと Firebase に対するファイルアップロード処理を追加リゾルバをスキーマに加えています。

```ts
import { GraphQLScalarType, GraphQLSchema } from "graphql";

import { SignJWT } from "jose";
import { createBuilder } from "./builder";
import { prisma } from "./context";
import { getUser } from "./getUser";
import { getUserInfo } from "./getUserInfo";
import { importFile } from "./importFile";
import { normalizationPostFiles } from "./normalizationPostFiles";
import { isolatedFiles, uploadFile } from "./uploadFile";

export const schema = () => {
  let schema: GraphQLSchema;
  return ({ env }: { env: { [key: string]: string | undefined } }) => {
    if (!schema) {
      const builder = createBuilder(env.DATABASE_URL ?? "");
      builder.mutationType({
        fields: (t) => ({
          signIn: t.prismaField({
            args: { token: t.arg({ type: "String" }) },
            type: "User",
            nullable: true,
            resolve: async (_query, _root, { token }, { setCookie }) => {
              const userInfo =
                typeof token === "string"
                  ? await getUserInfo(env.NEXT_PUBLIC_projectId, token)
                  : undefined;
              if (!userInfo) {
                setCookie("auth-token", "", {
                  httpOnly: true,
                  secure: env.NODE_ENV !== "development",
                  sameSite: "strict",
                  path: "/",
                  maxAge: 0,
                  domain: undefined,
                });
                return null;
              }
              const user = await getUser(prisma, userInfo.name, userInfo.email);
              if (user) {
                const secret = env.SECRET_KEY;
                if (!secret) throw new Error("SECRET_KEY is not defined");
                const token = await new SignJWT({ payload: { user: user } })
                  .setProtectedHeader({ alg: "HS256" })
                  .sign(new TextEncoder().encode(secret));
                setCookie("auth-token", token, {
                  httpOnly: true,
                  secure: env.NODE_ENV !== "development",
                  maxAge: 1000 * 60 * 60 * 24 * 7,
                  sameSite: "strict",
                  path: "/",
                  domain: undefined,
                });
              }
              return user;
            },
          }),
          uploadSystemIcon: t.prismaField({
            type: "FireStore",
            args: {
              file: t.arg({ type: "Upload", required: true }),
            },
            resolve: async (_query, _root, { file }, { prisma, user }) => {
              if (!user) throw new Error("Unauthorized");
              const firestore = await uploadFile({
                projectId: env.GOOGLE_PROJECT_ID ?? "",
                clientEmail: env.GOOGLE_CLIENT_EMAIL ?? "",
                privateKey: env.GOOGLE_PRIVATE_KEY ?? "",
                binary: file,
              });
              const system = await prisma.system.update({
                select: { icon: true },
                data: {
                  iconId: firestore.id,
                },
                where: { id: "system" },
              });
              await isolatedFiles({
                projectId: env.GOOGLE_PROJECT_ID ?? "",
                clientEmail: env.GOOGLE_CLIENT_EMAIL ?? "",
                privateKey: env.GOOGLE_PRIVATE_KEY ?? "",
              });
              if (!system.icon) throw new Error("icon is not found");
              return system.icon;
            },
          }),
          uploadPostIcon: t.prismaField({
            type: "FireStore",
            args: {
              postId: t.arg({ type: "String", required: true }),
              file: t.arg({ type: "Upload" }),
            },
            resolve: async (
              _query,
              _root,
              { postId, file },
              { prisma, user }
            ) => {
              if (!user) throw new Error("Unauthorized");
              if (!file) {
                const firestore = await prisma.post
                  .findUniqueOrThrow({
                    select: { card: true },
                    where: { id: postId },
                  })
                  .card();
                if (!firestore) throw new Error("firestore is not found");
                await prisma.fireStore.delete({
                  where: { id: firestore.id },
                });
                return firestore;
              }
              const firestore = await uploadFile({
                projectId: env.GOOGLE_PROJECT_ID ?? "",
                clientEmail: env.GOOGLE_CLIENT_EMAIL ?? "",
                privateKey: env.GOOGLE_PRIVATE_KEY ?? "",
                binary: file,
              });
              const post = await prisma.post.update({
                select: { card: true },
                data: {
                  cardId: firestore.id,
                },
                where: { id: postId },
              });
              await isolatedFiles({
                projectId: env.GOOGLE_PROJECT_ID ?? "",
                clientEmail: env.GOOGLE_CLIENT_EMAIL ?? "",
                privateKey: env.GOOGLE_PRIVATE_KEY ?? "",
              });
              if (!post.card) throw new Error("card is not found");
              return post.card;
            },
          }),
          uploadPostImage: t.prismaField({
            type: "FireStore",
            args: {
              postId: t.arg({ type: "String", required: true }),
              file: t.arg({ type: "Upload", required: true }),
            },
            resolve: async (
              _query,
              _root,
              { postId, file },
              { prisma, user }
            ) => {
              if (!user) throw new Error("Unauthorized");
              const firestore = await uploadFile({
                projectId: env.GOOGLE_PROJECT_ID ?? "",
                clientEmail: env.GOOGLE_CLIENT_EMAIL ?? "",
                privateKey: env.GOOGLE_PRIVATE_KEY ?? "",
                binary: file,
              });
              await prisma.post.update({
                data: {
                  postFiles: { connect: { id: firestore.id } },
                },
                where: { id: postId },
              });
              return firestore;
            },
          }),
          normalizationPostFiles: t.boolean({
            args: {
              postId: t.arg({ type: "String", required: true }),
              removeAll: t.arg({ type: "Boolean" }),
            },
            resolve: async (_root, { postId, removeAll }, { prisma, user }) => {
              if (!user) throw new Error("Unauthorized");
              await normalizationPostFiles(prisma, postId, removeAll === true, {
                projectId: env.GOOGLE_PROJECT_ID ?? "",
                clientEmail: env.GOOGLE_CLIENT_EMAIL ?? "",
                privateKey: env.GOOGLE_PRIVATE_KEY ?? "",
              });
              await isolatedFiles({
                projectId: env.GOOGLE_PROJECT_ID ?? "",
                clientEmail: env.GOOGLE_CLIENT_EMAIL ?? "",
                privateKey: env.GOOGLE_PRIVATE_KEY ?? "",
              });
              return true;
            },
          }),
          restore: t.boolean({
            args: {
              file: t.arg({ type: "Upload", required: true }),
            },
            resolve: async (_root, { file }, { user }) => {
              if (!user) throw new Error("Unauthorized");
              importFile({
                file: await file.text(),
                projectId: env.GOOGLE_PROJECT_ID ?? "",
                clientEmail: env.GOOGLE_CLIENT_EMAIL ?? "",
                privateKey: env.GOOGLE_PRIVATE_KEY ?? "",
              });
              return true;
            },
          }),
        }),
      });
      const Upload = new GraphQLScalarType({
        name: "Upload",
      });
      builder.addScalarType("Upload", Upload, {});
      schema = builder.toSchema({ sortSchema: false });
    }
    return schema;
  };
};
```

## フロントエンド

### 環境変数の受け取りとセッション処理を入れる

Cloudflare Pages では、環境変数はクライアントからの接続要求を受け取った際に引き渡されます。つまり接続要求があるまでは環境変数は利用できません。Remix のドキュメントには各ルーティングページの loader で受け取るような説明が書いてありますが、handleRequest で処理してしまえば一回ですみます。

ここでは Next.js の getInitialProps のような動作をさせて、クライアントへセッションデータとおなじみの環境変数 NEXT*PUBLIC*\*を Context を通じてコンポーネントへ配っています。注意点はここで配った値は、Server 側でレンダリングするときしか有効ではいということです。クライアント側のコンポーネントでは消え去っているので、さらに別の場所で細工をする必要があります。

- app/entry.server.tsx

```ts
/**
 * By default, Remix will handle generating the HTTP Response for you.
 * You are free to delete this file if you'd like to, but if you ever want it revealed again, you can run `npx remix reveal` ✨
 * For more information, see https://remix.run/file-conventions/entry.server
 */

import { RemixServer } from "@remix-run/react";
import { renderToReadableStream } from "react-dom/server";
import { getUserFromToken } from "./libs/client/getUserFromToken";
import { getHost } from "./libs/server/getHost";
import { RootProvider } from "./libs/server/RootContext";
import type { AppLoadContext, EntryContext } from "@remix-run/cloudflare";

export default async function handleRequest(
  request: Request,
  responseStatusCode: number,
  responseHeaders: Headers,
  remixContext: EntryContext,
  // This is ignored so we can keep it in the template for visibility.  Feel
  // free to delete this parameter in your app if you're not using it!
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  loadContext: AppLoadContext
) {
  const rootValue = await getInitialProps(request, loadContext);
  const body = await renderToReadableStream(
    <RootProvider value={rootValue}>
      <RemixServer context={remixContext} url={request.url} />
    </RootProvider>,
    {
      signal: request.signal,
      onError(error: unknown) {
        // Log streaming rendering errors from inside the shell
        console.error(error);
        responseStatusCode = 500;
      },
    }
  );

  await body.allReady;

  responseHeaders.set("Content-Type", "text/html");
  return new Response(body, {
    headers: responseHeaders,
    status: responseStatusCode,
  });
}

const getInitialProps = async (
  request: Request,
  loadContext: AppLoadContext
) => {
  const env = loadContext.env as Record<string, string>;
  const cookie = request.headers.get("cookie");
  const cookies = Object.fromEntries(
    cookie?.split(";").map((v) => v.trim().split("=")) ?? []
  );
  const token = cookies["auth-token"];
  const session = await getUserFromToken({ token, secret: env.SECRET_KEY });
  const host = getHost(request);
  return {
    cookie: String(cookie),
    host,
    session: session && { name: session.name, email: session.email },
    env: Object.fromEntries(
      Object.entries(env).filter(([v]) => v.startsWith("NEXT_PUBLIC_"))
    ),
  };
};
```

### Server/Client の共通処理

entry.server.tsx で渡したデータを受け取って、初回 HTML レンダリング時にそのデータを埋め込むようにしています。クライアント側は、埋め込まれたデータを受け取って処理を行います。これでサーバ側で生成したセッション情報や環境変数がクライアントでも処理できるようになります。

GraphQL のクライアントとして Urql を使っています。この中で SSR 用の
https://www.npmjs.com/package/@react-libraries/next-exchange-ssr
を使っています。これ組み込むと、コンポーネントで Urql のクエリを普通に使うだけで勝手に SSR 化されます。ページごとに loader と useLoadData を書く必要はありません。

```tsx
import { NextSSRWait } from "@react-libraries/next-exchange-ssr";
import { cssBundleHref } from "@remix-run/css-bundle";
import {
  Links,
  LiveReload,
  Meta,
  Outlet,
  Scripts,
  ScrollRestoration,
} from "@remix-run/react";
import stylesheet from "@/tailwind.css";
import { GoogleAnalytics } from "./components/Commons/GoogleAnalytics";
import { HeadProvider, HeadRoot } from "./components/Commons/Head";
import { EnvProvider } from "./components/Provider/EnvProvider";
import { UrqlProvider } from "./components/Provider/UrqlProvider";
import { Header } from "./components/System/Header";
import { LoadingContainer } from "./components/System/LoadingContainer";
import { NotificationContainer } from "./components/System/Notification/NotificationContainer";
import { StoreProvider } from "./libs/client/context";
import { RootValue, useRootContext } from "./libs/server/RootContext";
import type { LinksFunction } from "@remix-run/cloudflare";

export const links: LinksFunction = () => [
  { rel: "stylesheet", href: stylesheet },
  ...(cssBundleHref ? [{ rel: "stylesheet", href: cssBundleHref }] : []),
];

export default function App() {
  const value = useRootContext();
  const { host, session, cookie, env } = value;
  return (
    <html lang="ja">
      <EnvProvider value={env}>
        <StoreProvider initState={() => ({ host, user: session })}>
          <UrqlProvider host={host} cookie={cookie}>
            <HeadProvider>
              <head>
                <meta charSet="utf-8" />
                <meta
                  name="viewport"
                  content="width=device-width, initial-scale=1"
                />
                <link rel="preconnect" href="https://fonts.googleapis.com" />
                <link
                  rel="preconnect"
                  href="https://fonts.gstatic.com"
                  crossOrigin="anonymous"
                />
                <Meta />
                <Links />
                <GoogleAnalytics />
                <NextSSRWait>
                  <HeadRoot />
                </NextSSRWait>
                <RootValue value={{ session, env }} />
              </head>
              <body>
                <div className={"flex h-screen flex-col"}>
                  <Header />
                  <main className="relative flex-1 overflow-hidden">
                    <Outlet />
                  </main>
                  <LoadingContainer />
                  <NotificationContainer />
                </div>
                <ScrollRestoration />
                <Scripts />
                <LiveReload />
              </body>
            </HeadProvider>
          </UrqlProvider>
        </StoreProvider>
      </EnvProvider>
    </html>
  );
}
```

### head の情報挿入

タイトルや OGP の情報を埋め込むため、head の中に情報を挿入する必要があります。Remix では meta ファンクションを使うことになっていますが、私がやりたいのは Next.js の Pages で使っていたコンポーネント内で情報を設定可能な next/head と同等の機能です。

ということでサクッと作ります。

- app/components/Commons/Head/index.tsx

```tsx
import React from "react";
import {
  FC,
  ReactNode,
  createContext,
  useContext,
  useEffect,
  useRef,
  useSyncExternalStore,
} from "react";

const DATA_NAME = "__HEAD_VALUE__";

export type ContextType<T = ReactNode[]> = {
  state: T;
  storeChanges: Set<() => void>;
  dispatch: (callback: (state: T) => T) => void;
  subscribe: (onStoreChange: () => void) => () => void;
};

export const useCreateHeadContext = <T,>(initState: () => T) => {
  const context = useRef<ContextType<T>>({
    state: initState(),
    storeChanges: new Set(),
    dispatch: (callback) => {
      context.state = callback(context.state);
      context.storeChanges.forEach((storeChange) => storeChange());
    },
    subscribe: (onStoreChange) => {
      context.storeChanges.add(onStoreChange);
      return () => {
        context.storeChanges.delete(onStoreChange);
      };
    },
  }).current;
  return context;
};

const HeadContext = createContext<
  ContextType<{ type: string; props: Record<string, unknown> }[][]>
>(undefined as never);

export const HeadProvider = ({ children }: { children: ReactNode }) => {
  const context = useCreateHeadContext<
    { type: string; props: Record<string, unknown> }[][]
  >(() => {
    if (typeof window !== "undefined") {
      return [
        JSON.parse(
          document.querySelector(`script#${DATA_NAME}`)?.textContent ?? "{}"
        ),
      ];
    }
    return [[]];
  });
  return (
    <HeadContext.Provider value={context}>{children}</HeadContext.Provider>
  );
};

export const HeadRoot: FC = () => {
  const context = useContext(HeadContext);
  const state = useSyncExternalStore(
    context.subscribe,
    () => context.state,
    () => context.state
  );
  useEffect(() => {
    context.dispatch(() => {
      return [];
    });
  }, [context]);
  const heads = state.flat();
  return (
    <>
      <script
        id={DATA_NAME}
        type="application/json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify(heads).replace(/</g, "\\u003c"),
        }}
      />
      {heads.map(({ type: Tag, props }, index) => (
        <Tag key={`HEAD${Tag}${index}`} {...props} />
      ))}
    </>
  );
};
export const Head: FC<{ children: ReactNode }> = ({ children }) => {
  const context = useContext(HeadContext);
  useEffect(() => {
    const value = extractInfoFromChildren(children);
    context.dispatch((heads) => [...heads, value]);
    return () => {
      context.dispatch((heads) => heads.filter((head) => head !== value));
    };
  }, [children, context]);

  if (typeof window === "undefined") {
    context.dispatch((heads) => [...heads, extractInfoFromChildren(children)]);
  }
  return null;
};

const extractInfoFromChildren = (
  children: ReactNode
): { type: string; props: Record<string, unknown> }[] =>
  React.Children.toArray(children).flatMap((child) => {
    if (React.isValidElement(child)) {
      if (child.type === React.Fragment) {
        return extractInfoFromChildren(child.props.children);
      }
      if (typeof child.type === "string") {
        return [{ type: child.type, props: child.props }];
      }
    }
    return [];
  });
```

HeadRoot は root.tsx に設置しています。この機能によって、各コンポーネントで Next.js 同様に Head タグを設定すれば、その情報が収集され\<head>タグの中に挿入されます。

### コンポーネントの例

graphql-codegen で作った Urql の hook からデータを読み取ってレンダリングしています。Remix の一般的な作り方と違うところは、loader と useLoadData を使用しないことです。Urql に next-exchange-ssr を組み込むだけで、クエリで吐き出した内容は自動的に SSR されるようになります。

こちらも以前に作りました。

https://www.npmjs.com/package/@react-libraries/next-exchange-ssr

- app/components/Pages/TopPage/index.tsx

```tsx
import { FC, useMemo } from "react";
import { PostsQuery, usePostsQuery, useSystemQuery } from "@/generated/graphql";
import { useLoading } from "@/hooks/useLoading";
import { PostList } from "../../PostList";
import { Title } from "../../System/Title";

interface Props {}

/**
 * TopPage
 *
 * @param {Props} { }
 */
export const TopPage: FC<Props> = ({}) => {
  const [{ data: dataSystem }] = useSystemQuery();
  const [{ fetching, data }] = usePostsQuery();
  const posts = useMemo(() => {
    if (!data?.findManyPost) return undefined;
    return [...data.findManyPost].sort(
      (a, b) =>
        new Date(b.publishedAt).getTime() - new Date(a.publishedAt).getTime()
    );
  }, [data?.findManyPost]);
  const categories = useMemo(() => {
    if (!data?.findManyPost) return undefined;
    const categoryPosts: {
      [key: string]: { name: string; posts: PostsQuery["findManyPost"] };
    } = {};
    data.findManyPost.forEach((post) => [
      post.categories.forEach((c) => {
        const value =
          categoryPosts[c.id] ??
          (categoryPosts[c.id] = { name: c.name, posts: [] });
        value.posts.push(post);
      }),
    ]);
    return Object.entries(categoryPosts).sort(([, a], [, b]) =>
      a.name < b.name ? -1 : 1
    );
  }, [data?.findManyPost]);
  const system = dataSystem?.findUniqueSystem;
  useLoading(fetching);

  if (!posts || !categories || !system) return null;
  return (
    <>
      <Title>{system.description || "Article List"}</Title>
      <div className="flex h-full w-full flex-col gap-16 overflow-auto p-8">
        <PostList id="news" title="新着順" posts={posts} limit={10} />
        {categories.map(([id, { name, posts }]) => (
          <PostList key={id} id={id} title={name} posts={posts} limit={10} />
        ))}
      </div>
    </>
  );
};
```

### その他

#### Blurhash

画像最適化機能用のコンポーネントです。与えられた URL を画像最適化用のアドレスに変換する機能と、Blurhash の機能を組み込んでいます。Blurhash は画像が読み込まれるまでの間、元画像から生成したブラーのかかったような代替画像を表示する機能です。この Blog システムでは画像アップロード時に、Blurhash で生成した短い文字列をファイル名として組み込んでいます。そのファイル名を参照して代替画像を表示しています。一応実装はしてみたものの、画像最適化機能+Cloudflare の CDN で高速に画像が配信されるため、効果の確認がし辛いです。

![](/images/cloudflare-remix/2024-03-12-09-12-35.gif)

ただ Blurhash で生成される文字列 Base83 は、そのままファイル名として使用すると URL 文字列で問題が起こるので、いったんバイナリに戻してから再変換をかけています。

- app/components/Commons/Image/index.tsx

```tsx
import { decode } from "blurhash";
import { useEffect, useRef, useState } from "react";
import { useEnv } from "@/components/Provider/EnvProvider";
import { fileNameToBase83 } from "@/libs/client/blurhash";
import { classNames } from "@/libs/client/classNames";

type Props = {
  src: string;
  width?: number;
  height?: number;
  alt?: string;
  className?: string;
};

const useBluerHash = ({
  src,
  width,
  height,
}: {
  src: string;
  width: number;
  height: number;
}) => {
  const [value, setValue] = useState<string>();
  useEffect(() => {
    const hash = src.match(/-\[(.*?)\]$/)?.[1];
    if (!hash || !width || !height) return;
    try {
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext("2d")!;
      const imageData = ctx.createImageData(width, height);
      const pixels = decode(fileNameToBase83(hash), width, height);
      imageData.data.set(pixels);
      ctx.putImageData(imageData, 0, 0);
      setValue(canvas.toDataURL("image/png"));
    } catch (e) {}
  }, [height, src, width]);
  return value;
};

export const Image = ({ src, width, height, alt, className }: Props) => {
  const env = useEnv();
  const optimizer = env.NEXT_PUBLIC_IMAGE_URL;
  const url = new URL(optimizer ?? src);
  if (optimizer) {
    url.searchParams.set("url", encodeURI(src));
    width && url.searchParams.set("w", String(width));
    url.searchParams.set("q", "90");
  }

  const [, setLoad] = useState(false);
  const hashUrl = useBluerHash({
    src,
    width: width ?? 0,
    height: height ?? 0,
  });
  const ref = useRef<HTMLImageElement>(null);
  const isBlur = hashUrl && !ref.current?.complete;
  return (
    <>
      <img
        className={classNames(isBlur ? className : "hidden")}
        src={hashUrl}
        alt={alt}
        width={width}
        height={height}
      />
      <img
        className={isBlur ? "invisible fixed" : className}
        ref={ref}
        src={url.toString()}
        width={width}
        height={height}
        alt={alt}
        loading="lazy"
        onLoad={() => setLoad(true)}
      />
    </>
  );
};
```

#### 画像の avif 変換

画像アップロード時、サイズを削減するため形式を avif に変換するようにしています。変換はブラウザ上で avif エンコード用の wasm を動きます。この wasm は 3MB あり、圧縮しても 1MB を超えますが、ブラウザ実行用の Assets として配置する場合は、1MB 制限には引っかかりません。

こちらもサクッと作りました

https://www.npmjs.com/package/@node-libraries/wasm-avif-encoder

```tsx
import { encode } from "@node-libraries/wasm-avif-encoder";
import { encode as encodeHash } from "blurhash";
import { arrayBufferToBase64 } from "@/libs/server/buffer";
import { base83toFileName } from "./blurhash";

const type = "avif";

export const convertImage = async (
  blob: Blob,
  width?: number,
  height?: number
): Promise<File | Blob | null> => {
  if (!blob.type.match(/^image\/(png|jpeg|webp|avif)/)) return blob;

  const src = await blob
    .arrayBuffer()
    .then((v) => `data:${blob.type};base64,` + arrayBufferToBase64(v));
  const img = document.createElement("img");
  img.src = src;
  await new Promise((resolve) => (img.onload = resolve));

  let outWidth = width ? width : img.width;
  let outHeight = height ? height : img.height;
  const aspectSrc = img.width / img.height;
  const aspectDest = outWidth / outHeight;
  if (aspectSrc > aspectDest) {
    outHeight = outWidth / aspectSrc;
  } else {
    outWidth = outHeight * aspectSrc;
  }

  const canvas = document.createElement("canvas");
  [canvas.width, canvas.height] = [outWidth, outHeight];
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  ctx.drawImage(img, 0, 0, img.width, img.height, 0, 0, outWidth, outHeight);
  const data = ctx.getImageData(0, 0, outWidth, outHeight);
  const value = await encode({
    data,
    worker: `/${type}/worker.js`,
    quality: 90,
  });
  if (!value) return null;
  const hash = encodeHash(data.data, outWidth, outHeight, 4, 4);
  const filename = base83toFileName(hash);
  return new File([value], filename, { type: `image/${type}` });
};

export const getImageSize = async (blob: Blob) => {
  const src = await blob
    .arrayBuffer()
    .then((v) => `data:${blob.type};base64,` + arrayBufferToBase64(v));
  const img = document.createElement("img");
  img.src = src;
  await new Promise((resolve) => (img.onload = resolve));
  return { width: img.naturalWidth, height: img.naturalHeight };
};
```

# Vite の利用

途中で Remix を Vite 対応版に変更しています。その時に発生した問題をこちらにまとめています。

https://next-blog.croud.jp/contents/390feabe-39bf-4c5e-a1f3-01a2e3d317a6

# まとめ

無いものは作る。ただこの一点です。
