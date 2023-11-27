---
title: "Next.jsのAppRouterでlayout.tsxからServer/Clientコンポーネントにデータを配る"
emoji: "🚻"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [nextjs, typescript, react, javascript, approuter]
published: true
---

# Context を利用できない Server コンポーネント

Next.js の AppRouter の Server コンポーネントでは、`createContext`が使用できません。これに加え、Next.js では`createServerContext`も使用できなくなったため、Context を使ってデータをコンポーネントツリーに配ることができません。

PagesRouter 上では\_app.tsx から Context を配ることが出来てとても便利でした。しかし AppRouter の Server コンポーネントにはその機能がありません。

# そもそも page.tsx が layout.tsx よりも先に実行される

AppRouter のコンポーネント評価順序は以下のようになります。

(1) page.tsx
(2) layout.tsx

つまり、先に page.tsx が実行され、その後 layout.tsx のコンポーネントが評価されます。そのため、layout から page にデータを配ろうにも、データを配る前に page が実行されてしまい、データを配ることができません。

# データを配ることも出来なければ、そもそも実行順序も違う

そう、不可能なのです。普通にやったら。

# 不可能を可能にする

ということで、不可能を可能とするコードを書きました。
npm にパッケージ化したものを登録してあります。

https://www.npmjs.com/package/next-approuter-context

# サンプルソース

- GitHub  
   https://github.com/SoraKumo001/next-approuter-context-test
- Vercel  
  https://next-approuter-context-test.vercel.app/
- CodeSandbox  
  https://codesandbox.io/p/github/SoraKumo001/next-approuter-context-test/master

## app/context.ts

Server コンポーネント間で共有するコンテキストを生成します。
Server/Client 間で Context のインスタンスを自動識別する方法がどうしても思いつかなかったので、複数の Context を扱うときはユニークな名前が必要です。

```tsx
import { createMixContext } from "next-approuter-context";

export const context1 = createMixContext<{ text: string; color: string }>(
  "context1"
);
export const context2 = createMixContext<number>("context2");
```

## app/layout.tsx

既存の ContextAPI に似せて Provider を作る書き方にしています。

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

動作確認用に Server/Client コンポーネントを呼び出します。

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

Server コンポーネントから Context を取得しています。コンポーネントを async にする場合は、データの取得方法が getMixContext を使った形に書き換える必要があります。

```tsx
"use server";

import { useMixContext } from "next-approuter-context";
import { context1, context2 } from "./context";

export const Server = () => {
  // If the component is async, it should be written as follows
  // const { text, color } = await getMixContext<ContextType1>();
  const { text, color } = useMixContext(context1);
  const value = useMixContext(context2);
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

Client コンポーネントから Context を取得しています。基本的に Server コンポーネントと同じコードになるように、ライブラリを作ってあります。

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

見事、データが配れない問題と実行順序の問題を解決しました。

![](/images/approuter-context/2023-11-27-09-43-44.png)

色々なことを力技で解決していますが、具体的なソースはこちらを見てください。

https://github.com/ReactLibraries/next-approuter-context/tree/master/src

# まとめ

Server/Client の両方に layout.tsx からデータを配れるようになりました。このやり方を使えば、UI ライブラリのテーマ設定も簡単です。
