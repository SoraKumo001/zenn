---
title: "Next.jsのAppRouter/PagesRouter実行中に、Server/Client/Pagesのどのモジュールなのかを識別する"
emoji: "🚻"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [nextjs, typescript, react, javascript, approuter]
published: true
---

# 厄介なコンポーネントの状態

Next.js の AppRouter ではデフォルトで ServerComponent の状態から始まり、`"use client"`を先頭につけることによって、ClientComponents として動作させることができます。また、コンポーネントを記述したファイルに`"use xxxxx"`を付けなかった場合は、呼び出し元のコンポーネントの状態を継承します。

つまり呼び出されたコンポーネントは、自分が ServerComponent かもしれないし、ClientComponent の可能性もあります。

Server/Client 両用コンポーネントを作りたい場合、現在の状態によって処理を切り替えたいという時が来るかもしれません。ということで、現状で可能な識別方法のサンプルを紹介します。

# サンプルコード

- app/CheckComponent.tsx

```tsx
import React from "react";

export const CheckComponent = () => {
  return (
    <div>
      {!React["useState"]
        ? "Server"
        : React["createServerContext"] || !React["useOptimistic"]
        ? "Pages"
        : "Client"}
    </div>
  );
};
```

- app/Server.tsx

```tsx
"use server";
import { CheckComponent } from "./CheckComponent";

export const Server = () => {
  return <CheckComponent />;
};
```

- app/Client.tsx

```tsx
"use client";
import { CheckComponent } from "./CheckComponent";

export const Client = () => {
  return <CheckComponent />;
};
```

- app/page.tsx

```tsx
import { Client } from "./Client";
import { Server } from "./Server";

const Page = () => {
  return (
    <>
      <div>-- App --</div>
      <Server />
      <Client />
      <div>-- Pages --</div>
      <iframe src="/pages" />
    </>
  );
};

export default Page;
```

- pages/pages.tsx

```tsx
import { CheckComponent } from "../app/CheckComponent";

const Page = () => {
  return <CheckComponent />;
};

export default Page;
```

# 出力結果

一画面に収めたかったので、PagesRouter は iframe で表示しています

![](/images/approuter-identification/2023-11-27-09-12-16.png)

# 識別方法の解説

Server/Client でそれぞれ CheckComponent を呼び出しています。CheckComponent では`React.useState`が存在するかどうかをチェックしています。ServerComponents では useState が undefined となるため、識別が可能となります。

さらに pages に置かれているかどうかという判定を加えると、少々面倒です。

- ServerComponents は useState がない
- ClientComponents は useState がある
- Pages では useState がある
- ClientComponents では createServerContext が取り除かれる
- Pages では createServerContext は取り除かれない
- createServerContext は react@canary 以降に存在する
- useOptimistic は react@canary 以降に存在する
- AppRouter は react@canary 以降で実行される
- PagesRouter はreact@18.2.0以前と react@canary のどちらかで実行される

という条件を満たすように判定する必要があります。

これはあくまで Next.js の仕様です。ServerComponents で useState がモジュールバンドラの設定で除去されるのは Next.js が勝手にやっているだけです。React の仕様ではありません。そのため、あらゆるフレームワークで状況に応じて柔軟に対応できる汎用的なコンポーネントを作るのはほぼ不可能です。本来であれば このあたりの動作は React の仕様として決めておくべきです。しかし細かい動作に関しては Next.js で動けば良いというのが垣間見えて、フレームワークが一強化したことによる弊害が出てきたように感じます。
