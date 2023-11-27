---
title: "Next.jsのAppRouterでReact.cacheを使う時の基本操作"
emoji: "🚻"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [nextjs, typescript, react, javascript, approuter]
published: true
---

# AppRouter と React.cache

AppRouter で State を持たない Server コンポーネント同士のデータ共有は、React.cache が基本となります。AppRouter の話題だと fetch のキャッシュや ServerActions の話に目が持っていかれますが、それよりも根本の話になります。

React.cache の使い方を知らずに fetch や ServerActions を使いだすのは、useState を知らないのに、いきなり外部通信系のプログラムを書こうとしているような状態です。

- 公式ドキュメント
  https://ja.react.dev/reference/react/cache

# 簡単な React.cache の使い方

簡単なサンプルで React.cache の使い方を紹介します。

## app/context.ts

cache は関数をキャッシュします。その関数が戻すのは、データである必要はありません。ContextAPI でもデータ操作用の dispatch を返すような構造を取ることがありますが、同じように書くことが出来ます。

```ts
import { cache } from "react";

export const createContext = <T>(v: T) =>
  cache(() => {
    let value = v;
    return {
      set: (v: T) => (value = v),
      get: () => value,
    };
  });

export const context = createContext(0);
```

## app/Test.tsx

context には cache の戻り値が入っています。キャッシュされたインスタンスを取得するには、context()で取り出す必要があります。一般的なサンプルでは引数を取る書き方ばかりですが、引数をキーとしてインスタンスを切り替える必要がなければ不要です。

```tsx
import { context } from "./context";

export const Test = () => {
  context().set(context().get() + 1);
  return <div>{context().get()}</div>;
};
```

## app/page.tsx

```tsx
import { Test } from "./Test";

const Page = () => {
  return (
    <>
      <Test />
      <Test />
      <Test />
      <Test />
    </>
  );
};

export default Page;
```

## 実行結果

![](/images/approuter-cache/2023-11-27-09-33-24.png)

普通に値が加算されるだけのように見えますが実はそうではありません。ページをリロードしても内容は 1 ～ 4 です。それすらも当たり前のように思えますが、これがモジュール変数をそのまま使った場合などは値が初期化されず、リロード後も加算され続けます。

# 解説

React.cache は、コンポーネントツリーごとにインスタンスを生成します。つまりリロード後、新しいコンポーネントツリーが生成されると、別のメモリ空間が生成されるのです。サーバに対して複数のアクセスが同時に行われた場合も、値が混線することはありません。この構造を利用すれば ContextAPI のように、コンポーネントを飛び越えて値の共有が可能となります。

こちらは基本操作なので、layout.tsx から本格的にデータを配る内容は別記事にします。
