---
title: "Next.js の AppRouter で React Query を用いた SSR（Server Component不使用）"
emoji: "👋"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [Nextjs, ReactQuery, typescript, react, AppRouter]
published: true
---

# React の SSR にフレームワークの機能は必要ない

React で SSR を行う際、フレームワークの機能を使わずに React の標準機能だけで実現する方法を紹介します。React Router(Remix) でも同じ方法が有効なので、これを使えば Next.js への依存が最小になります。

Next.js での一般的な方法だと App Router で SSR を行う場合、データを Server Component で取得する必要があります。この方法だと、取得したデータをクライアント側で動的に制御したい場合、Server Component と Client Component を連結させた二重構造にする必要があります。

実はそんな方法を使わずとも React には、Client Component でもデータを取得する機能が用意されています。Server Component を使わずに実現可能なのです。

# React の標準機能で SSR を行う際の必要なテクニック

## throw promise

コンポーネントで外部にあるデータを持ってくる際は、非同期という扱いになります。React の一般コンポーネントを SSR でレンダリングする場合は、同期的に実行されなければなりません。ではどうやって非同期処理を同期的に扱うかというと、throw promise を使います。throw promise、データが出揃うまでコンポーネントの評価を一旦スキップすることができます。この機能により、コンポーネントの評価タイミングを自由に調整し、実態は非同期なのに、コンポーネントは同期状態という形で SSR が可能になります。

この機能、各ライブラリで suspense という名前で提供されていますが、React の Suspense は一切使う必要はありません。逆に、使ってしまうと意図通り動かなくなるので注意が必要です。Suspense が必要なのは Streaming SSR の場合ですが、今回はこの機能を利用しません。

## データルーティング

- サーバ側で必要なデータを取得
- そのデータを HTML に変換して出力
- クライアント側でその HTML を受け取り、仮想 DOM を構築し対応したノードをマウント
- クライアント側で再レンダリング ← ここで問題が発生

SSR ではサーバ側で必要なデータを揃えて、それを HTML に変換して出力します。クライント側ではその HTML を受け取った後に、仮想 DOM を構築し対応したノードをマウントします。そのままだと、マウント完了後の再レンダリング時に問題が発生します。サーバ側が持っていたデータが何なのかクライアントは知らないからです。HTML の中にはデータが入っていても、クライアントで実行されるスクリプト側にはデータが入っていないのです。すると、空データで再レンダリングされてしまい、せっかくサーバ側で吐き出したデータが消えてしまいます。

これに対処するには、サーバ側のデータをクライアントが受け取れるようにします。具体的な方法としては、データを JSON 化して HTML に埋め込みます。クライアント側はその JSON データを取得し、それを使って再レンダリングを行います。これにより、サーバ側で取得したデータをクライアント側で再利用することができます。

## サーバーとクライアントの処理

throw promise によるコンポーネントの評価順を制御することで、データが出揃うのを待つコンポーネントを作ることが出来ます。このコンポーネントでデータの JSON 化してレンダリングすることでサーバ側の出力は完了です。

クライアントは、サーバ側で出力された JSON データを取得し、初期データとして設定します。その後、クライアント側で再レンダリングを行います。この時、初期データがあるため、再レンダリング時にデータが消えることはありません。

# React Query を SSR 化する

前述の内容を踏まえて、React Query を SSR 化する方法を紹介します。私の認識では React Query は多機能な非同期データキャッシュの管理ライブラリです。このデータキャッシュ機構を利用して、SSR 化させてみます。

こちらが npm に公開しているライブラリです
https://www.npmjs.com/package/react-query-ssr

サーバ上では React Query で発生した Promise 完了を待ってキャッシュが完成するのを待ち、dehydrate で取り出したデータを初期 HTML で書き出します。そしてクライアント側で HTML 上からデータを受け取り、hydrate して React Query のキャッシュに送ります。

```tsx
"use client";
import {
  isServer,
  dehydrate,
  hydrate,
  useQueryClient,
} from "@tanstack/react-query";
import React, { ReactNode } from "react";
import { FC, useRef } from "react";

const DATA_NAME = "__REACT_QUERY_DATA_PROMISE__";

type PropertyType = {
  finished?: boolean;
  promises?: Promise<unknown>[];
};

const DataTransfer: FC<{ property: PropertyType }> = ({ property }) => {
  const queryClient = useQueryClient();
  const promises = queryClient
    .getQueryCache()
    .getAll()
    .flatMap(({ promise }) => (promise ? [promise] : []));
  if (isServer && !promises.every((p) => property.promises?.includes(p))) {
    property.promises = promises;
    throw Promise.all(promises);
  }
  const value = dehydrate(queryClient);
  return (
    <script
      id={DATA_NAME}
      type="application/json"
      dangerouslySetInnerHTML={{
        __html: JSON.stringify(value).replace(/</g, "\\u003c"),
      }}
    />
  );
};

export const SSRProvider: FC<{ children: ReactNode }> = ({ children }) => {
  const queryClient = useQueryClient();
  const property = useRef<PropertyType>({}).current;
  if (!isServer && !property.finished) {
    const node = document.getElementById(DATA_NAME);
    if (node) {
      const value = JSON.parse(node.innerHTML);
      hydrate(queryClient, value);
    }
    property.finished = true;
  }
  return (
    <>
      {children}
      <DataTransfer property={property} />
    </>
  );
};

export const enableSSR = { suspense: isServer };
```

# 実装例

- Vercel でのデモ
  <https://next-react-query-ssr.vercel.app/>
- GitHub
  <https://github.com/SoraKumo001/next-react-query-ssr>

ポケモンの情報を表示するサンプルです。初回アクセス時はデータをサーバ側で処理して SSR し、その後の UI 操作によるアクションはクライアント側でデータを取得しています。

通常の React Query に追加する作業は、SSRProvider を挟み込むのと、useQuery に enableSSR オプションを追加するだけです。

## app/Provider.tsx

React Query の Provider を作成します。staleTime を設定しないと、サーバで作ったデータがクライアントで破棄されてしまうので注意してください。さらに先程作った SSRProvider を差し込んで、サーバで作ったデータをクライアントに転送する機能を追加します。

```tsx
"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { FC, ReactNode, useState } from "react";
import { SSRProvider } from "react-query-ssr";

export const Provider: FC<{ children: ReactNode }> = ({ children }) => {
  const [queryClient] = useState(
    () =>
      new QueryClient({ defaultOptions: { queries: { staleTime: 60 * 1000 } } })
  );
  return (
    <QueryClientProvider client={queryClient}>
      <SSRProvider>{children}</SSRProvider>
    </QueryClientProvider>
  );
};
```

## app/Layout.tsx

Provider を使ってページをラップします。

```tsx
import { Provider } from "./Provider";

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <Provider>{children}</Provider>
      </body>
    </html>
  );
}
```

## src/app/[page]/page.tsx

ポケモンの一覧を表示するサンプルです。普通に useQuery を使っているだけのように見えますが、これだけで SSR 化されます。サーバ・クライアント間のデータ共有は自動で行われます。

追加事項はオプションに enableSSR を追加していることです。これを入れなかった場合、サーバ側ではデータが取得されなくなります。React Query には元々こんなオプションはありません。実際に何をやっているのかというと、サーバ側では suspense フラグを有効にして、クライアントでは無効にしています。ReactQuery@5 では、useQuery の suspense フラグ自体が型情報から削除されていますが実際は使えます。

React@19 からはタイトルやメタ情報をコンポーネントの中に書いても、SSR 時に<head>に移動してくれる機能が追加されました。これにより、フレームワークの力を借りなくとも、React の標準機能だけ<head>内の情報を管理することが可能になりました。

```tsx
"use client";
import { useQuery } from "@tanstack/react-query";
import { enableSSR } from "react-query-ssr";

import Link from "next/link";
import { useParams } from "next/navigation";

type PokemonList = {
  count: number;
  next: string;
  previous: string | null;
  results: { name: string; url: string }[];
};

const pokemonList = (page: number): Promise<PokemonList> =>
  fetch(`https://pokeapi.co/api/v2/pokemon/?offset=${(page - 1) * 20}`).then(
    (r) => r.json()
  );

const Page = () => {
  const params = useParams();
  const page = Number(params["page"] ?? 1);
  const { data } = useQuery({
    // `useQuery` with this option.
    ...enableSSR,
    queryKey: ["pokemon-list", page],
    queryFn: () => pokemonList(page),
  });

  if (!data) return <div>loading</div>;
  return (
    <>
      <title>Pokemon List</title>
      <div style={{ display: "flex", gap: "8px", padding: "8px" }}>
        <Link
          href={page > 1 ? `/${page - 1}` : ""}
          style={{
            textDecoration: "none",
            padding: "8px",
            boxShadow: "0 0 8px rgba(0, 0, 0, 0.1)",
          }}
        >
          ⏪️
        </Link>
        <Link
          href={page < Math.ceil(data.count / 20) ? `/${page + 1}` : ""}
          style={{
            textDecoration: "none",
            padding: "8px",
            boxShadow: "0 0 8px rgba(0, 0, 0, 0.1)",
          }}
        >
          ⏩️
        </Link>
      </div>
      <hr style={{ margin: "24px 0" }} />
      <div>
        {data.results.map(({ name }) => (
          <div key={name}>
            <Link href={`/pokemon/${name}`}>{name}</Link>
          </div>
        ))}
      </div>
    </>
  );
};
export default Page;
```

## src/app/pokemon/[name]/page.tsx

こちらは、ポケモンの詳細を表示するサンプルです。こちらも enableSSR を追加しています。

```tsx
"use client";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { enableSSR } from "../../react-query-ssr";

type Pokemon = {
  abilities: { ability: { name: string; url: string } }[];
  base_experience: number;
  height: number;
  id: number;
  name: string;
  order: number;
  species: { name: string; url: string };
  sprites: {
    back_default: string;
    back_female: string;
    back_shiny: string;
    back_shiny_female: string;
    front_default: string;
    front_female: string;
    front_shiny: string;
    front_shiny_female: string;
  };
  weight: number;
};

const pokemon = (name: string): Promise<Pokemon> =>
  fetch(`https://pokeapi.co/api/v2/pokemon/${name}`).then((r) => r.json());

const Page = () => {
  const params = useParams();
  const name = String(params["name"]);
  const { data } = useQuery({
    // `useQuery` with this option.
    ...enableSSR,
    queryKey: ["pokemon", name],
    queryFn: () => pokemon(name),
  });

  if (!data) return <div>loading</div>;
  return (
    <>
      <title>{name}</title>
      <div style={{ padding: "8px" }}>
        <Link
          href="/1"
          style={{
            textDecoration: "none",
            padding: "8px 32px",
            boxShadow: "0 0 8px rgba(0, 0, 0, 0.1)",
            borderRadius: "8px",
          }}
        >
          ⏪️List
        </Link>
      </div>
      <hr style={{ margin: "24px 0" }} />
      <div
        style={{
          display: "inline-flex",
          flexDirection: "column",
          alignItems: "center",
          padding: "8px",
        }}
      >
        <img
          style={{ boxShadow: "0 0 8px rgba(0, 0, 0, 0.5)" }}
          src={data.sprites.front_default}
        />
        <div>{name}</div>
      </div>
    </>
  );
};
export default Page;
```

## 実行結果

初期 HTML にデータが含まれていることが確認できます。

![](/images/react-query-ssr/2024-12-08-20-57-02.png)
![](/images/react-query-ssr/2024-12-09-08-59-08.png)

# まとめ

React Router(Remix) や Next.js などのフレームワーク種類に関係なく、React の SSR にフレームワークの機能は必要ありません。React の標準機能だけで実現することが可能です。この記事では、throw promise を使ってコンポーネントの評価順を制御し、データの出力を行いました。また、データルーティングを行うことで、サーバ側のデータをクライアント側で再利用しています。

フレームワークの多機能化が進んでいますが、ベンダーロックインを防ぐためにも、標準機能でなんとかしていきたいところです。
