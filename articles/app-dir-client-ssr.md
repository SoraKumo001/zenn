---
title: Next.jsのAppRouterを使い、ClientComponentsのみで非同期データのSSRを行う
emoji: "🚻"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [react, nextjs, typescript, ssr, appRouter]
published: true
---

# 最初に

今回のサンプルコードのリンク

- GitHub  
  https://github.com/SoraKumo001/next-ssr-sample

- Vercel  
  https://next-use-ssr.vercel.app/

# AppRouter 使用時の一般的な非同期データの SSR

AppRouter で非同期データを含んだ SSR を行う場合、ServerComponents でデータを取得して自身でレンダリングするか、それを ClientComponents に渡すかする必要があります。ブラウザ側でユーザの入力に合わせて柔軟に表示内容を変えようとすると ServerComponents と ClientComponents のやり取りをそれぞれ記述しなければならず、PagesRouter 上で getServerSideProps からデータを渡していたときと労力に差がありません。

# ClientComponents で非同期データを扱えば、コードの記述が楽になる

ServerComponents を使えば、その部分のコンポーネントの js コードをクライアントに渡す必要がなくなり、少しだけ通信量が節約できます。ただ、節約できるサイズは微々たるものです。そのためにデータ取得用コンポーネントと UI 用コンポーネントを分離するのは手間になります。だったら ClientComponents で非同期データを扱えるようにすれば良いのです。

# 必要なもの

- Next.js で SSR を簡単に行うためのパッケージ

https://www.npmjs.com/package/next-ssr

以下のような形で Next.js 環境下に追加でパッケージを入れます。

```sh
yarn add next-ssr
```

# 単純な非同期 SSR のサンプル

## src/app/layout.tsx

SSR 用のデータを取り扱う Provider を layout に設置します。これで配下のコンポーネントから、簡単 SSR 機能が使えるようになります。

```tsx
import { SSRProvider } from "next-ssr";

export const metadata = {
  title: "samples of next-ssr",
  description: "SSR with AppRouter.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <SSRProvider>{children}</SSRProvider>
      </body>
    </html>
  );
}
```

## src/app/simple/page.tsx

非同期データを扱うための最小限のコードです。非同期関数から'Hello world!'を渡しています。もちろん fetch などで取得したデータも使えます。

```
'use client';
import { useSSR } from 'next-ssr';

/**
 * Page display components
 */
const Page = () => {
  const { data } = useSSR(async () => 'Hello world!');
  return <div>{data}</div>;
};
export default Page;
```

## 出力された HTML

body タグの直後に、`<div>Hello world!</div>`が入っています。非同期データの SSR に成功しています。

![](/images/app-dir-client-ssr/2023-11-08-09-22-46.png)

# 天気予報のサンプル

気象庁のサイトからデータを fetch して内容を表示しています。SSR 後は ClientComponents なので、UI イベントで再ロードも行えます。その際はクライアント側で fetch が行われます。

## src/app/weather/page.tsx

```tsx
"use client";
import { useSSR } from "next-ssr";

export interface WeatherType {
  publishingOffice: string;
  reportDatetime: string;
  targetArea: string;
  headlineText: string;
  text: string;
}

/**
 * Data obtained from the JMA website.
 */
const fetchWeather = (id: number): Promise<WeatherType> =>
  fetch(
    `https://www.jma.go.jp/bosai/forecast/data/overview_forecast/${id}.json`
  )
    .then((r) => r.json())
    .then(
      // Additional weights (500 ms)
      (r) => new Promise((resolve) => setTimeout(() => resolve(r), 500))
    );

/**
 * Components for displaying weather information
 */
const Weather = ({ code }: { code: number }) => {
  const { data, reload, isLoading } = useSSR<WeatherType>(
    () => fetchWeather(code),
    { key: code }
  );
  if (!data) return <div>loading</div>;
  const { targetArea, reportDatetime, headlineText, text } = data;
  return (
    <div
      style={
        isLoading ? { background: "gray", position: "relative" } : undefined
      }
    >
      {isLoading && (
        <div
          style={{
            position: "absolute",
            color: "white",
            top: "50%",
            left: "50%",
          }}
        >
          loading
        </div>
      )}
      <h1>{targetArea}</h1>
      <button onClick={reload}>Reload</button>
      <div>
        {new Date(reportDatetime).toLocaleString("ja-JP", {
          timeZone: "JST",
        })}
      </div>
      <div>{headlineText}</div>
      <div style={{ whiteSpace: "pre-wrap" }}>{text}</div>
    </div>
  );
};

/**
 * Page display components
 */

const Page = () => {
  return (
    <>
      {/* Chiba  */}
      <Weather code={120000} />
      {/* Tokyo */}
      <Weather code={130000} />
      {/* Kanagawa */}
      <Weather code={140000} />
    </>
  );
};
export default Page;
```

## 出力された HTML

天気予報の内容が SSR されています。

- HTML
  ![](/images/app-dir-client-ssr/2023-11-08-09-23-01.png)

- 表示内容
  ![](/images/app-dir-client-ssr/2023-11-08-09-23-10.png)

# まとめ

AppRouter の本来の機能をガン無視しています。そのため page.tsx に記述している内容は、PagesRouter 上にそのまま持って行ってもファイル名だけ直せば同じ動きをします。

そもそのもところで、Next.js が React のレンダリングに使っている react-dom/server の renderToPipeableStream は、コンポーネントの`throw promise`で非同期待ちしてくれるので、ServerComponents と ClientComponents の種別に関わりなく非同期待ちが可能です。あとは必要に応じて、データを配るコードを足してやれば便利に動くようになります。

ちなみにここちらの[Blog システム](https://next-blog.croud.jp/)は今回紹介した動作原理を Urql のプラグインとして実装して運用していますが、コードを書くのも楽だし、特になんの問題もなくキビキビ動いています。

- PagesRouter 版
  https://github.com/SoraKumo001/md-blog

- AppRouter 版
  https://github.com/SoraKumo001/md-blog/tree/AppRouter

ほとんどコードに違いがないので、Pages から App の移植は簡単です。ただ、ページ遷移時に Pages の方がファイルの読み取り頻度が低いので、最終的に Pages のままにするという結論に至りました。ちなみに PagesRouter 版でも AppRouter を APIRoute の代替としては使ってます。

今のところ AppRouter にメリットは感じないので趣味でいじりつつ、しばらくは様子見したいと思っています。
