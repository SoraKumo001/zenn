---
title: "Next.js の Client Component で async/await を使う"
emoji: "🐷"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [nextjs, react, typescript, javascript, approuter]
published: true
---

# クライアントコンポーネントでも async/await は使える

クライアントコンポーネントをサーバ上で動かす際、async/await が使えないという誤解があります  
その誤解を解くために最小限のサンプルを用意しました

このサンプルではサーバ上で非同期データを取得し HTML で出力、ブラウザ上で Hydration して動作します

重要な点は、`throw property.promise`の部分です。ここで Promise が解決された際に、コンポーネントが再レンダリングされます。この機能は React の`renderToReadableStream`実行時の標準動作です。`<Suspense>`で囲むと、非同期待ちではなくストリーミングになってしまうので注意が必要です

クライアントコンポーネントは Hydration 時、サーバ側で持っていたデータを失います。サーバコンポーネントと連携する際は、このデータの引き渡しが自動で生成されますが、クライアントコンポーネント単独の場合は、自分でやり取りする必要があります。この引き渡し作業は自動で生成される内容とほぼ同じです。

- サンプルコード

https://github.com/SoraKumo001/next-client-async

- サンプルを Vercel にデプロイしたもの

https://next-client-async.vercel.app/

```tsx
"use client";
import { useRef, useSyncExternalStore, type FC } from "react";

const DATA_NAME = "DATA_TEST";

const Weather: FC<{
  property: { data?: unknown; promise?: Promise<void> };
}> = ({ property }) => {
  const data = useSyncExternalStore(
    () => () => {},
    () => property.data,
    () => {
      if (!property.data) {
        if (typeof window !== "undefined") {
          // ブラウザ側でHydration直後にデータを受け取る
          const node = document.getElementById(DATA_NAME);
          property.data = JSON.parse(node.innerHTML);
        } else if (!property.promise) {
          // サーバ(物理)動作時に天気予報データを取得
          const getWeather = async () => {
            const result = await fetch(
              `https://www.jma.go.jp/bosai/forecast/data/overview_forecast/130000.json`
            );
            property.data = await result.json();
          };
          property.promise = getWeather();
          // Promiseを解決後、再レンダリングさせる
          throw property.promise;
        }
      }
      return property.data;
    }
  );
  return (
    <>
      {/* クライアントへ渡すデータをHTML化 */}
      <script
        id={DATA_NAME}
        type="application/json"
        dangerouslySetInnerHTML={{
          // データをJSON文字列に変換と、HTML用にエスケープ
          __html: JSON.stringify(data).replace(/</g, "\\u003c"),
        }}
      />
      {/* 確認表示用 */}
      <pre>{JSON.stringify(data, null, 2)}</pre>
    </>
  );
};

const Page = () => {
  const property = useRef<{
    data?: unknown;
    promise?: Promise<void>;
  }>({}).current;
  return <Weather property={property} />;
};

export default Page;
```

# まとめ

Next.js のクライアントコンポーネントは、サーバ上で async/await を使うことができます。そこで取得したデータは、Server Component と同様に HTML に埋め込んでブラウザ側に引き渡し、Hydration 後も利用可能です。この動作は React の標準動作内で実行されるため、クライアントコンポーネントに限らず、Next.js の PagesRouter や React Router など、他の環境でも同様に利用できます。
