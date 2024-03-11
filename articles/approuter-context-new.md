---
title: "Next.jsのAppRouterでlayout.tsxを先に実行しpage.tsxにデータを配る(14系統版)"
emoji: "😸"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [JavaScript, Next.js, React, TypeScript, AppRouter]
published: true
---

# 実行順序

昨今、AppRouter で page.tsx が layout.tsx より先に実行されることが話題になっていますが、去年こんな記事を書きました。

https://zenn.dev/sora_kumo/articles/approuter-context

箸にも棒にも引っかからなかったこの記事ですが、次元を歪めることに成功し実行順序を変えています。しかし久々に実行してみると Next.js の仕様が変わって、"use server"したファイルが非同期関数しかエクスポートできないという仕様に変わっており、修正が必要になっていたので、焼き直しで記事を書くことにしました。

# layout.tsx を page.tsx より先に実行する

ということでやってみます。

## Sample コードと実行環境はこちら

- GitHub  
   https://github.com/SoraKumo001/next-approuter-context-test
- Vercel  
  https://next-approuter-context-test.vercel.app/

## app/context.tsx

React の ContextAPI 風にコンテキストを作ります。

```tsx
import { createMixContext } from "next-approuter-context";

export const context1 = createMixContext<{ text: string; color: string }>(
  "context1"
);
export const context2 = createMixContext<number>("context2");
```

## app/layout.tsx

レイアウトにデータを設置します。当然のごとく、page.tsx よりも layout.tsx が先に実行が完了されないとデータを配れません。

```tsx
import { context1, context2 } from "./context";

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <context1.Provider
          value={{ text: "Send colors and text from Layout", color: "red" }}
        >
          <context2.Provider value={123456}>{children}</context2.Provider>
        </context1.Provider>
      </body>
    </html>
  );
}
```

## app/page.tsx

Server/Client の両方のコンポーネントを呼び出します。

```tsx
import { Client } from "./client";
import { Server } from "./server";

const Page = () => {
  return (
    <>
      <Server />
      <Client />
    </>
  );
};

export default Page;
```

## app/server.tsx

Server component で、layout.tsx からのデータを受け取ります。

```tsx
"use server";

import { context1, context2 } from "./context";
import { getMixContext } from "next-approuter-context";

export const Server = async () => {
  const { text, color } = await getMixContext(context1);
  const value = await getMixContext(context2);
  return (
    <>
      <div style={{ color }}>
        Server: {text} - {value}
      </div>
    </>
  );
};
```

## app/client.tsx

Client component で、layout.tsx からのデータを受け取ります。

```tsx
"use client";

import { useMixContext } from "next-approuter-context";
import { context1, context2 } from "./context";

export const Client = () => {
  const { text, color } = useMixContext(context1);
  const value = useMixContext(context2);
  return (
    <>
      <div style={{ color }}>
        Client: {text} - {value}
      </div>
    </>
  );
};
```

## 実行結果

![](/images/approuter-context/2023-11-27-09-43-44.png)

# まとめ

AppRouter で layout.tsx の実行を先に完了させ、さらに page.tsx へデータを配ることに成功しました。React の renderToReadableStream を使っている Next.js や Remix の場合、コンポーネントの処理中に保留と再開が任意に可能です。つまりサーバ側のレンダリング処理でそのタイミングを制御するのは、やろうと思えばいくらでも可能なのです。今回も、単にデータ配布の非同期解決まで page.tsx を待たせているだけで、大したことはしていません。

まずは、それが可能だと思うことが重要です。
