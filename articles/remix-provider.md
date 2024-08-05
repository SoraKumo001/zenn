---
title: "Remix + Cloudflare で環境変数などをクライアントへ引き渡す方法"
emoji: "🤖"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [remix, cloudflare, env, ssr]
published: false
---

# Cloudflare と環境変数

Cloudflare の Pages や Workers は、プロセス起動時点では環境変数が設定されていません。各エンドポイントが呼び出された時点で、環境変数が設定されます。そのため、サーバーサイドで環境変数を使う場合は、リクエスト毎に環境変数を取得する必要があります。

このため、クライアント側に環境変数の値を真っ当に引き渡そうとすると、routes ごとに loader を設置して、ページごとに環境変数を配布するコードを書く必要があります。これは非常に面倒です。

そこで、環境変数を簡単にクライアント側に引き渡すための方法を紹介します。

# 使用パッケージ

必要な機能をまとめたパッケージを作りました

https://www.npmjs.com/package/remix-provider

# 実装例

- source code

https://github.com/SoraKumo001/remix-provider

- execution result

https://remix-provider.pages.dev/

### entry.server.tsx

ServerProvider を設置して、クライアントに渡したいデータを設定します。

初回リクエスト時にデータを設定するため、routes ごとに loader を設置する必要はありません。

```tsx
import type { AppLoadContext, EntryContext } from "@remix-run/cloudflare";
import { RemixServer } from "@remix-run/react";
import { isbot } from "isbot";
import { renderToReadableStream } from "react-dom/server";
import { ServerProvider } from "remix-provider";

export default async function handleRequest(
  request: Request,
  responseStatusCode: number,
  responseHeaders: Headers,
  remixContext: EntryContext,
  loadContext: AppLoadContext
) {
  const body = await renderToReadableStream(
    // Set the values you want to distribute to clients.
    <ServerProvider
      value={{
        env: loadContext.cloudflare.env,
        host: request.headers.get("host"),
      }}
    >
      <RemixServer context={remixContext} url={request.url} />
    </ServerProvider>,
    {
      signal: request.signal,
      onError(error: unknown) {
        // Log streaming rendering errors from inside the shell
        console.error(error);
        responseStatusCode = 500;
      },
    }
  );

  if (isbot(request.headers.get("user-agent") || "")) {
    await body.allReady;
  }

  responseHeaders.set("Content-Type", "text/html");
  return new Response(body, {
    headers: responseHeaders,
    status: responseStatusCode,
  });
}
```

### root.tsx

RootProvider と RootValue の設置を行います。RootValue には、サーバから送られたデータが格納されます。

```tsx
import {
  Links,
  Meta,
  Outlet,
  Scripts,
  ScrollRestoration,
} from "@remix-run/react";
import "./tailwind.css";
import { RootProvider, RootValue } from "remix-provider";

export function Layout({ children }: { children: React.ReactNode }) {
  return (
    // Additional providers.
    <RootProvider>
      <html lang="en">
        <head>
          <meta charSet="utf-8" />
          <meta name="viewport" content="width=device-width, initial-scale=1" />
          <Meta />
          <Links />
          {/* Install components to transfer data to clients. */}
          <RootValue />
        </head>
        <body>
          {children}
          <ScrollRestoration />
          <Scripts />
        </body>
      </html>
    </RootProvider>
  );
}

export default function App() {
  return <Outlet />;
}
```

### routes/\_index.tsx

各コンポーネントでデータを取得する場合は useRootContext を使います。ServerProvider で設定した値が取得できます。

データは環境変数に限らず、任意の値を設定し受け取ることができます。エンドポイントリクエスト時のヘッダ類や cookie の値などもデータとして渡すことができます。

```tsx
import { useRootContext } from "remix-provider";

export default function Index() {
  // Get the value distributed to clients.
  const value = useRootContext();
  return <div className="whitespace-pre">{JSON.stringify(value, null, 2)}</div>;
}
```

### Execution Result

- Output

```json
{
  "env": {
    "ASSETS": {},
    "CF_PAGES": "1",
    "CF_PAGES_BRANCH": "master",
    "CF_PAGES_COMMIT_SHA": "dfc64ad01b02b6832fae2fd3a61453ac14f6fb35",
    "CF_PAGES_URL": "https://f3f206fa.remix-provider.pages.dev"
  },
  "host": "remix-provider.pages.dev"
}
```

# まとめ

簡単にサーバー側のデータをクライアントに配ることが出来ました。これにより、環境変数やリクエストヘッダなどをクライアント側で利用することが可能になります。

Remix + Cloudflare でブログシステムを作ったときに、必要だったので作った機能を分離させて、今回パッケージ化しました。同じようパッケージが他に見当たらないのが不思議なのですが、みなさん真面目に loader を書いて環境変数を配っているのでしょうか？

https://next-blog.croud.jp/contents/eec22faf-3563-4a77-9a47-4dfddc604141

こちらで記事を書いていますが、Remix を便利に使う機能から Prisma の容量問題の解決や画像最適化まで、必要な機能は全部その時に作りました。足りない機能はサクッと作るのが一番早いです。
