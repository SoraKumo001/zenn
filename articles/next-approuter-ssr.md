---
title: "Next.js@15 の AppRouter の Client Component のみで SSR を行う"
emoji: "🐙"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [react, nextjs, approuter, typescript, ssr]
published: true
---

- サンプルリポジトリ

https://github.com/SoraKumo001/next-approuter-ssr

- 実行確認

https://next-approuter-ssr.vercel.app/

# ServerComponents に疲れていませんか？

Next.js のバージョン 15 のリリースを迎えた昨今 AppRouter を中心に据えられるようになり、SSR を行うには ServerComponents が避けて通れません。しかし Pages Router を使っていた頃と比べると、大きく使い勝手が変わってしまったため、この変更に対応する対処に疲れてはいないでしょうか？ということで、余計なことを考えずに簡単に SSR を行う方法を紹介します。

# 作るのは ClientComponent のみで OK

非同期データの取得に ServerComponents の構造を必要としないため、全てを問答無用で Client Component にして問題ありません。

# 作り方

React 標準機能で SSR させる `next-ssr` パッケージを使用します。素の React でも動作可能なので、フレームワークの独自機能を必要としません。ただし React のレンダリングを renderToReadableStream で行う必要があります。Next.js や Remix ではこの API が使われているため、特に追加の処置は必要ありません。

- src/app/layout.tsx

SSR のデータを保持するための Provider を設置と、`<head>` タグにデータを挿入するためのコンポーネントを設置します。もちろん`use client`です。

```tsx
"use client";
import { SSRHeadRoot, SSRProvider } from "next-ssr";

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <SSRProvider>
        <head>
          <SSRHeadRoot />
        </head>
        <body>{children}</body>
      </SSRProvider>
    </html>
  );
}
```

- src/app/page.tsx

データ取得と表示を行うコンポーネントを作成します。コンポーネント上で使用している非同期処理は SSR され、HTML で出力されると共にクライアントにも渡されます。もちろん`use client`です。

```tsx
"use client";
import { SSRHead, useSSR } from "next-ssr";
import Link from "next/link";

interface Center {
  name: string;
  enName: string;
  officeName?: string;
  children?: string[];
  parent?: string;
  kana?: string;
}
interface Centers {
  [key: string]: Center;
}

const fetchCenters = (): Promise<Centers> =>
  fetch(`https://www.jma.go.jp/bosai/common/const/area.json`).then((r) =>
    r.json()
  );

const Page = () => {
  const { data } = useSSR<Centers>(fetchCenters, { key: "centers" });
  if (!data) return <div>loading</div>;
  return (
    <>
      <SSRHead>
        <title>天気予報地域一覧</title>
      </SSRHead>
      <div>
        {data &&
          Object.entries(data.offices).map(([code, { name }]) => (
            <div key={code}>
              <Link href={`/weather/${code}`}>{name}</Link>
            </div>
          ))}
      </div>
    </>
  );
};
export default Page;
```

- src/app/weather/[id]/page.tsx

もちろん`use client`です。

```tsx
"use client";
import { useSSR, SSRHead } from "next-ssr";
import Link from "next/link";
import { useParams } from "next/navigation";

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
  ).then((r) => r.json());

/**
 * Components for displaying weather information
 */

const Page = () => {
  const params = useParams();
  const code = Number(params["id"]);
  const { data, reload, isLoading } = useSSR<WeatherType>(
    () => fetchWeather(code),
    { key: code }
  );
  if (!data) return <div>loading</div>;
  const { targetArea, reportDatetime, headlineText, text } = data;
  return (
    <>
      <SSRHead>
        <title>{targetArea}</title>
      </SSRHead>
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
        <Link href="..">⏪️Home</Link>
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
    </>
  );
};

export default Page;
```

# 実行結果

きちんと非同期で取得したデータが HTML で出力されていることが確認できます。また、JavaScript を OFF にしても動作します。

![](/images/next-approuter-ssr/2024-10-22-11-36-27.png)

# まとめ

フレームワーク達よ、お前らのルールには従わない。
