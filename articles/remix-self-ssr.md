---
title: "ReactのSSRにフレームワークの機能は必要ない、Remixの機能を使わずReactの標準機能でSSR"
emoji: "🙌"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: []
published: false
---

# React の SSR にフレームワークの機能は必要ない

React で SSR を行う際、フレームワークの機能を使わずに React の標準機能だけで実現する方法を紹介します。

一般的な方法だと Remix で SSR を行う場合、routes 直下のファイルで実装した loader 関数を使ってデータを作成し、各コンポーネント内の useLoaderData データを受け取ります。この方法だと、ページの頭でどんなデータを取得するかを決めなければならず、コンポーネントの状態に合わせて柔軟にデータを用意することが困難です。

実はそんな方法を使わずとも React には、コンポーネント側でデータを取得する機能が用意されています。もちろん React の利点を殺す ServerComponents のことではありません。普通のコンポーネントで実現可能なのです。あるのに何故か誰もやらない機能を使っていきます。

# React の標準機能で SSR を行う際の必要なテクニック

## throw promise

コンポーネントで外部にあるデータを持ってくる際は、非同期という扱いになります。React の一般コンポーネントのレンダリングは通常は同期的に実行されなければなりません。ではどうやって非同期処理を同期的に扱うかというと、`throw promise`を使います。これを使うことで、コンポーネントの評価を一旦スキップすることができます。この機能により、コンポーネントの評価タイミングを自由に調整し、実態は非同期なのに、コンポーネントは同期状態として動きます。

## データルーティング

- サーバ側で必要なデータを取得
- そのデータを HTML に変換して出力
- クライアント側でその HTML を受け取り、仮想 DOM を構築し対応したノードをマウント
- クライアント側で再レンダリング ← ここで問題が発生

SSR ではサーバ側で必要なデータを揃えて、それを HTML に変換して出力します。クライント側ではその HTML を受け取った後に、仮想 DOM を構築し対応したノードをマウントします。そのままだと、マウント完了後の再レンダリング時に問題が発生します。サーバ側が持っていたデータが何なのかクライアントは知らないからです。HTML の中にはデータが入っていても、クライアントで実行されるスクリプト側にはデータが入っていないのです。すると、空データで再レンダリングされてしまい、せっかくサーバ側で吐き出したデータが消えてしまいます。

これに対処するには、サーバ側のデータをクライアントが受け取れるようにします。具体的な方法としては、データを JSON 化して HTML に埋め込みます。クライアント側はその JSON データを取得し、それを使って再レンダリングを行います。これにより、サーバ側で取得したデータをクライアント側で再利用することができます。

# サーバーとクライアントの処理

`throw promise`によるコンポーネントの評価順を制御することで、データが出揃うのを待つコンポーネントを作ることが出来ます。このコンポーネントでデータの JSON 化してレンダリングすることでサーバ側の出力は完了です。

クライアントは、サーバ側で出力された JSON データを取得し、初期データとして設定します。その後、クライアント側で再レンダリングを行います。この時、初期データがあるため、再レンダリング時にデータが消えることはありません。

# 実装例

## ソースコード

https://github.com/SoraKumo001/cloudflare-remix-ssr

## 以下の二種類のパッケージを使います

- SSR の制御を行うパッケージ(もともと Next.js 用に作ったののですが、React の標準機能しか使ってないので Remix でも動作します)

https://www.npmjs.com/package/next-ssr

- Remix での head の制御を行うパッケージ(title タグをコンポーネント内で設定するのに使います)

https://www.npmjs.com/package/remix-head

## root.tsx

RemixHeadProvider(head 制御用)と SSRProvider(SSR データ管理用)を設置します。さらに、head タグ内に RemixHeadRoot を設置して、title タグを出力する場所を作ります。

```tsx
import {
  Links,
  Meta,
  Outlet,
  Scripts,
  ScrollRestoration,
} from "@remix-run/react";
import "./tailwind.css";
import { SSRProvider, SSRWait } from "next-ssr";
import { RemixHeadProvider, RemixHeadRoot } from "remix-head";

export function Layout({ children }: { children: React.ReactNode }) {
  return (
    <RemixHeadProvider>
      <html lang="ja">
        <SSRProvider>
          <head>
            <meta charSet="utf-8" />
            <meta
              name="viewport"
              content="width=device-width, initial-scale=1"
            />
            <Meta />
            <Links />
            <SSRWait>
              <RemixHeadRoot />
            </SSRWait>
          </head>
          <body>
            {children}
            <ScrollRestoration />
            <Scripts />
          </body>
        </SSRProvider>
      </html>
    </RemixHeadProvider>
  );
}

export default function App() {
  return <Outlet />;
}
```

## routes/\_index.tsx

千葉、東京、神奈川の天気予報のリンクを作成します。RemixHead で、タイトルタグは SSR 時に head 内に出力されます。

```tsx
import { Link } from "@remix-run/react";
import { RemixHead } from "remix-head";

export default function Index() {
  const codes = { 120000: "千葉", 130000: "東京", 140000: "神奈川" } as const;
  return (
    <div className="p-2">
      <RemixHead>
        <title>天気予報</title>
      </RemixHead>
      <a href="https://github.com/SoraKumo001/next-use-ssr">Source Code</a>
      <hr />
      <div className="flex flex-col">
        {Object.entries(codes).map(([key, value]) => (
          <Link key={key} to={`/weather/${key}`} className="underline">
            {value}の天気
          </Link>
        ))}
      </div>
    </div>
  );
}
```

## weather.$id.tsx

useSSR を使って、天気予報のデータを取得します。SSR 時は内部で`throw promise`を行い、データの取得が完了するまでコンポーネントの評価をスキップします。データルーティングも自動で行われるため、クライアント側で処理される時点で、データは持った状態で始まります。その後、ユーザーの操作によってデータを再取得することも可能です。

また、動作がわかりやすいように 500ms の遅延を追加しています。

ブラウザでページを更新した際は SSR でサーバ側がデータの取得を行い、ページ遷移した場合はクライアント側がデータの取得を行います。

```tsx
import { Link, useParams } from "@remix-run/react";
import { useSSR } from "next-ssr";
import { RemixHead } from "remix-head";

export interface WeatherType {
  publishingOffice: string;
  reportDatetime: string;
  targetArea: string;
  headlineText: string;
  text: string;
}

const Weather = ({ code }: { code: number }) => {
  const { data, reload, isLoading } = useSSR<WeatherType>(
    () =>
      fetch(
        `https://www.jma.go.jp/bosai/forecast/data/overview_forecast/${code}.json`
      )
        .then((r) => r.json<WeatherType>())
        .then(
          // Additional weights (500 ms)
          (r) => new Promise((resolve) => setTimeout(() => resolve(r), 500))
        ),
    { key: code }
  );
  if (!data) return <div>loading</div>;
  const { targetArea, reportDatetime, headlineText, text } = data;
  return (
    <>
      <div>
        <Link to="..">戻る</Link>
      </div>
      <div className={`mt-4${isLoading ? " bg-gray-500 relative" : ""}`}>
        {isLoading && (
          <div className="absolute text-white top-1/2 left-1/2">loading</div>
        )}
        <RemixHead>
          <title>{`${targetArea}の天気`}</title>
        </RemixHead>
        <h1 className="flex text-4xl font-extrabold leading-none items-center gap-2">
          {targetArea}
          <button
            className="text-white bg-blue-700 hover:bg-blue-800 focus:ring-4 focus:ring-blue-300 font-medium rounded-lg text-sm px-4 py-2  dark:bg-blue-600 dark:hover:bg-blue-700 focus:outline-none dark:focus:ring-blue-800"
            onClick={reload}
          >
            Reload
          </button>
        </h1>

        <div>
          {new Date(reportDatetime).toLocaleString("ja-JP", {
            timeZone: "JST",
          })}
        </div>
        <div>{headlineText}</div>
        <div style={{ whiteSpace: "pre-wrap" }}>{text}</div>
      </div>
    </>
  );
};

export default function Page() {
  const { id } = useParams<{ id: string }>();
  return <Weather code={Number(id)} />;
}
```

# まとめ

React の SSR にはフレームワークの機能は必要ありません。React の標準機能だけで実現することが可能です。この記事では、`throw promise`を使ってコンポーネントの評価順を制御し、データの取得を行いました。また、データルーティングを行うことで、サーバ側で取得したデータをクライアント側で再利用することができるようにしました。これにより、フレームワークの機能を使わずに、React の標準機能だけで SSR を実現することができました。
