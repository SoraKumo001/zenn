---
title: "🚻 Next.jsによるGraphQLに入門させないGraphQL入門"
emoji: "🚻"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [nextjs, graphql, pothos, react, prisma]
published: true
---

# ソースコードと実働環境

- Vercel に設置した動作確認環境

https://next-graphql-five.vercel.app/

- ソースコード

https://github.com/SoraKumo001/next-graphql

# 最終的に出来ること

Prisma スキーマを設定するだけで、GraphQL スキーマやリゾルバを自動生成し、対応する GraphQL クエリも自動的に作って、React コンポーネントから使える Hooks を自動生成し、普通にコンポーネントを作るときちんと SSR で動作し、JavaScript を切ったとしてもページジェネレーションぐらいまでは表示できるようになります。

# 今回使うもの一覧

| 種類              | Package        |
| ----------------- | -------------- |
| DB                | PostgreSQL     |
| ORM               | Prisma         |
| GraphQL Server    | GraphQL Yoga   |
| GraphQL Framework | Pothos GraphQL |
| GraphQL Client    | Urql           |

GraphQL Server は Apollo と Yoga の二択で、入門用により簡単に使える Yoga を今回は選択しています。
GraphQL Framework は Nexus と Pothos の二択で、Prisma との連携をカスタマイズする上で便利な Pothos を選びました。
GraphQL Client は ApolloClient と Urql の二択で、Mutation 時のキャッシュ管理が楽な Urql を利用しています。

# Next.js の利用方法

| 種類         | 内容          |
| ------------ | ------------- |
| App Router   | GraphQL Yoga  |
| Pages Router | 各 Components |

App Router を GraphQL のバックエンド専用、Pages Router をフロント用に利用しています。コンポーネントは App Router 側には置きませんが、コンポーネント上でデータ取得用の hooks を使うだけで完全な SSR を行います。データ取得専用の命令をコンポーネント外に書く必要はありません。

# GraphQL でアプリケーションを作るまでの道のり

Next.js で GraphQL を使ったアプリケーションを作ろうと思ったとき、少々長い道のりを経ることになります。例えば、バックエンドに PostgreSQL を用いて ORM に Prisma を選択した場合、フロントの実装に至るまで以下のようになります。

- 1.PostgreSQL の環境構築(Docker もしくは外部サービス)
- 2.Prisma スキーマの作成
- 3.Prisma の DB へのマイグレーション
- 4.Prisma のバックエンド API 用ジェネレーション
- 5.GraphQL 用 API サーバの準備
- 6.GraphQL スキーマの作成とリゾルバの実装
- 7.GraphQL クエリの作成
- 8.GraphQL クエリを graphql-codegen などで、フロントで実装しやすい形に変換

ということで、やることはそれなりにあります。順番にやっていきましょう。

# 自動変換までの流れ

## PostgreSQL の環境構築

Docker の例です。

_docker\docker-compose.yml_

```yml
version: "3.7"
services:
  postgres:
    container_name: next-pothos-postgres
    image: postgres:alpine
    environment:
      POSTGRES_DB: postgres
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: password
    volumes:
      - next-graphql-vol:/var/lib/postgresql/data
    ports:
      - "5432:5432"
volumes:
  next-graphql-vol:
```

package.json の scripts に以下のコマンドを追加しておくと便利です。-p のプロジェクト名設定は、アプリケーションに合わせた任意のものにしてください。設定しなくても問題ありませんが、Docker を並行して利用している場合は区別がつきやすくなります。

```json
{
  "scripts": {
    "dev:docker": "docker compose -p next-graphql -f docker/docker-compose.yml up -d"
  }
}
```

.env に DB への接続情報を設定しておきます。外部サービスを使う場合は、Docker の設定を行わず、接続情報だけ設定します。Docker インスタンスで複数の schema に切り替えたいときは schema の名前を変更してください。

また、外部サービスで Supabase などを使用する場合も、schema を切り替えると複数のアプリケーションに対応できます。

```sh
DATABASE_URL="postgresql://postgres:password@localhost:5432/postgres?schema=test"
```

これで

- 1.PostgreSQL の環境構築(Docker もしくは外部サービス)

が完了です。

## Prisma スキーマの作成

タイトルとコンテンツ情報を持ったテーブルを作成します。リレーションの実験が出来るように複数のカテゴリを関連付けられるようにします。

_prisma/schema.prisma_

```prisma
// This is your Prisma schema file,
// learn more about it in the docs: https://pris.ly/d/prisma-schema

generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}


model Post {
  id          String     @id @default(uuid())
  published   Boolean    @default(false)
  title       String     @default("New Post")
  content     String     @default("")
  categories  Category[]
  createdAt   DateTime   @default(now())
  updatedAt   DateTime   @updatedAt
  publishedAt DateTime   @default(now())
}

model Category {
  id        String   @id @default(uuid())
  name      String
  posts     Post[]
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt
}
```

package.json の scripts に以下のコマンドを突っ込んでおくと便利です。

```json
{
  "scripts": {
    "prisma:migrate": "prisma format && prisma migrate dev",
    "prisma:generate": "prisma generate"
  }
}
```

これで

- 2.Prisma スキーマの作成
- 3.Prisma の DB へのマイグレーション
- 4.Prisma のバックエンド API 用ジェネレーション
  が完了です。

## GraphQL 用 API サーバの準備

GraphQL 用のフレームワークに Pothos、サーバに GraphQL Yoga を使い、Next.js の AppRouter で処理を行います。

Pothos には標準的なプラグインの他に、追加で以下のプラグインを入れています

- Prisma スキーマから GraphQL スキーマとリゾルバ作成するプラグイン

https://www.npmjs.com/package/pothos-prisma-generator

- GraphQL スキーマから GraphQL クエリを作成するプラグイン

https://www.npmjs.com/package/pothos-query-generator

- GraphQL スキーマをファイルに出力するプラグイン

https://www.npmjs.com/package/pothos-schema-exporter

_src/app/schema.tsx_

```ts
import path from "path";
import SchemaBuilder from "@pothos/core";
import PrismaPlugin from "@pothos/plugin-prisma";
import PrismaUtils from "@pothos/plugin-prisma-utils";
import { PrismaClient } from "@prisma/client";
import PothosPrismaGeneratorPlugin from "pothos-prisma-generator";
import PothosQueryGeneratorPlugin from "pothos-query-generator";
import PothosSchemaExporterPlugin from "pothos-schema-exporter";

const prismaClient = new PrismaClient();

/**
 * Create a new schema builder instance
 */
export const builder = new SchemaBuilder<{
  // PrismaTypes: PrismaTypes; //Not used because it is generated automatically
}>({
  plugins: [
    PrismaPlugin,
    PrismaUtils,
    PothosPrismaGeneratorPlugin,
    PothosSchemaExporterPlugin,
    PothosQueryGeneratorPlugin,
  ],
  prisma: {
    client: prismaClient,
  },
  pothosSchemaExporter: {
    output:
      process.env.NODE_ENV === "development" &&
      path.join(process.cwd(), "graphql", "schema.graphql"),
  },
  pothosQueryGenerator: {
    output:
      process.env.NODE_ENV === "development" &&
      path.join(process.cwd(), "graphql", "query.graphql"),
  },
});

export const schema = builder.toSchema({ sortSchema: false });
```

_src/app/route.tsx_

```ts
import { createYoga } from "graphql-yoga";
import { schema } from "./schema";

const { handleRequest } = createYoga<{}>({
  schema,
  fetchAPI: { Response },
});

export { handleRequest as POST, handleRequest as GET };
```

pakcage.json には以下のコマンドを追加します。

```json
{
  "scripts": {
    "dev:next": "next"
  }
}
```

実行後、<http://localhost:3000/graphql>にアクセスすると、Yoga の Explorer が起動します。

これで

- 5.GraphQL 用 API サーバの準備
- 6.GraphQL スキーマの作成とリゾルバの実装
- 7.GraphQL クエリの作成

が完了です。

graphql フォルダに[schema.graphql](https://github.com/SoraKumo001/next-graphql/blob/master/graphql/schema.graphql)と[query.graphql](https://github.com/SoraKumo001/next-graphql/blob/master/graphql/query.graphql)が自動生成されています。

Query から Mutation まで必要なものはだいたい揃っています。これでデータの取得、作成、更新、削除が全て行えます。抽出条件の設定やソート、件数制限などの機能も備わっています。

## GraphQL クエリを graphql-codegen などで、フロントで実装しやすい形に変換

schema.graphql と query.graphql から Urql 用の Hooks を作成します。

_codegen/codegen.ts_

```ts
import { CodegenConfig } from "@graphql-codegen/cli";

const config: CodegenConfig = {
  schema: "graphql/schema.graphql",
  overwrite: true,
  documents: "graphql/query.graphql",
  generates: {
    "src/generated/graphql.ts": {
      plugins: ["typescript", "typescript-operations", "typescript-urql"],
      config: { scalars: { DateTime: "string" } },
    },
  },
};

export default config;
```

pakcage.json には以下のコマンドを追加します。

```json
{
  "scripts": {
    "graphql:codegen": "graphql-codegen --config codegen/codegen.ts"
  }
}
```

src/generated/graphql.ts に型付で必要な hooks が用意されました。バックエンドに接続するための作業は以上になります。あとはフロントを書いていくだけです。

生成されるファイルは以下のようになります。  
[graphql.ts](https://github.com/SoraKumo001/next-graphql/blob/master/src/generated/graphql.ts)

これで

- 8.GraphQL クエリを graphql-codegen などで、フロントで実装しやすい形に変換

が完了です。

# フロントの実装

## 準備作業

今回は認証などの処理は入れていませんが、SSR 時に認証情報が必要になったときに備えて Cookie で渡せるようにしてあります。また、アプリケーションをデプロイした先の URL を SSR 時に認識できるように、ホスト名の引き渡しも行っています。Vercel に置いた場合や Nginx でプロキシした場合など、汎用的に対応可能です。

- Urql によるクエリを使ったコンポーネントを SSR にするプラグイン

https://www.npmjs.com/package/@react-libraries/next-exchange-ssr

上記を使って pages にコンポーネントを配置すれば、SSR 対応のアプリケーションになります。

\_src/global.css

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

_src/pages/\_app.tsx_

```tsx
import "../global.css";
import { AppContext, AppProps } from "next/app";
import { UrqlProvider } from "@/components/Provider/UrqlProvider";
import { getHost } from "@/libs/getHost";

const App = ({
  Component,
  pageProps,
}: AppProps<{ host?: string; cookie?: string }>) => {
  const { cookie, host } = pageProps;
  return (
    <UrqlProvider host={host} cookie={cookie} endpoint="/graphql">
      <Component {...pageProps} />
    </UrqlProvider>
  );
};

App.getInitialProps = async (context: AppContext) => {
  // ホスト名とクッキーを渡す
  const req = context?.ctx?.req;
  const host = getHost(req);
  return {
    pageProps: {
      cookie: req?.headers?.cookie,
      host,
    },
  };
};

export default App;
```

_src\components\Provider\UrqlProvider.tsx_

```tsx
import {
  NextSSRProvider,
  createNextSSRExchange,
} from "@react-libraries/next-exchange-ssr";
import { ReactNode, useMemo } from "react";
import { cacheExchange, Client, fetchExchange, Provider } from "urql";

const isServerSide = typeof window === "undefined";

export const UrqlProvider = ({
  host,
  cookie,
  endpoint,
  children,
}: {
  host?: string;
  cookie?: string;
  endpoint: string;
  children: ReactNode;
}) => {
  const client = useMemo(() => {
    const nextSSRExchange = createNextSSRExchange();
    const url = isServerSide ? `${host}${endpoint}` : endpoint;
    return new Client({
      url,
      fetchOptions: {
        headers: {
          "apollo-require-preflight": "true",
          cookie: cookie ?? "",
        },
      },
      suspense: isServerSide,
      exchanges: [cacheExchange, nextSSRExchange, fetchExchange],
    });
  }, [host, cookie]);
  return (
    <Provider value={client}>
      <NextSSRProvider>{children}</NextSSRProvider>
    </Provider>
  );
};
```

_src/libs/getHost.ts_

```ts
import type { IncomingMessage } from "http";

export const getHost = (req?: Partial<IncomingMessage>) => {
  const headers = req?.headers;

  const host = headers?.["x-forwarded-host"] ?? headers?.["host"];
  if (!host) return undefined;
  const proto =
    headers?.["x-forwarded-proto"]?.toString().split(",")[0] ?? "http";
  return headers ? `${proto}://${host}` : undefined;
};
```

## カテゴリ入力機能

graphql-codegen で生成した hook を呼び出し、Category テーブルの中身を操作します。データ取得時は name をキーに昇順にソートさせています。自動生成された hooks は、prisma の関数名に近い名前になっています。検索条件、ソート、件数制限なども利用可能です。

_src/pages/category.tsx_

```tsx
import Link from "next/link";
import {
  OrderBy,
  useCreateOneCategoryMutation,
  useFindManyCategoryQuery,
} from "@/generated/graphql";

// GraphQLのadditionalTypenamesを設定する
const context = {
  additionalTypenames: ["Category"],
};

const Page = () => {
  const [{ data: dataCategory }] = useFindManyCategoryQuery({
    context,
    variables: { orderBy: { name: OrderBy.Asc } },
  });
  // カテゴリ一覧を取得
  const [{ fetching: fetchingCategory }, createCategory] =
    useCreateOneCategoryMutation();
  // カテゴリの作成
  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const target = e.target as typeof e.target & {
      name: { value: string };
    };
    // 新しいカテゴリを作成する
    if (target.name.value) {
      createCategory({
        input: {
          name: target.name.value,
        },
      });
      // フォームをリセットする
      e.currentTarget.reset();
    }
  };
  return (
    <>
      <div className="max-w-2xl m-auto py-4">
        <Link className="underline text-blue-500" href="/">
          投稿一覧
        </Link>
        {/* カテゴリフォーム */}
        <form
          className="grid border-gray-400 border-solid"
          onSubmit={handleSubmit}
        >
          <label htmlFor="flex-1">Category</label>
          <input className="border p-1" type="text" name="name" />
          <button
            className="shadow bg-blue-500 hover:bg-blue-400 focus:shadow-outline focus:outline-none text-white font-bold py-2 px-4 rounded m-1 disabled:opacity-30 disabled:cursor-not-allowed"
            type="submit"
            disabled={fetchingCategory}
          >
            Create Category
          </button>
        </form>
        <hr className="m-2" />

        {/* カテゴリ一覧 */}
        <div>
          {dataCategory?.findManyCategory.map((category) => (
            <div key={category.id} className="mt-5 p-1 border rounded">
              <div className="flex-1">{category.name}</div>
            </div>
          ))}
        </div>
      </div>
    </>
  );
};

export default Page;
```

_実行画面_

![](/images/next-graphql/2023-10-15-22-42-18.png)

## 投稿の作成と表示

1 ページの表示件数を 5 件に設定して、ページジェネレーションを付けています。また、別ページで作成したカテゴリを設定する機能も付けています。Query や Mutation で使用するパラメータは Prisma に近い形のものが使用できます。

_src/pages/index.tsx_

```tsx
import Link from "next/link";
import { useRouter } from "next/router";
import {
  OrderBy,
  useCountPostQuery,
  useCreateOnePostMutation,
  useDeleteOnePostMutation,
  useFindManyCategoryQuery,
  useFindManyPostQuery,
} from "@/generated/graphql";

// GraphQLのadditionalTypenamesを設定する
const context = {
  additionalTypenames: ["Post", "Category"],
};

// 1ページに表示する投稿の数
const PageLimit = 5;

const Page = () => {
  const router = useRouter();
  // ページ番号を取得する
  const page = Number(router.query.page) || 1;
  // useFindManyPostQueryフックを使用して、投稿を取得する(updatedAtを降順)
  const [{ data: dataPost }] = useFindManyPostQuery({
    variables: {
      orderBy: { updatedAt: OrderBy.Desc },
      categoriesOrderBy: { name: OrderBy.Asc },
      limit: 5,
      offset: (page - 1) * PageLimit,
    },
    context,
  });
  const [{ data: dataCategory }] = useFindManyCategoryQuery({
    variables: { orderBy: { name: OrderBy.Asc } },
  });
  // 投稿の総数を取得する
  const [{ data: dataPostCount }] = useCountPostQuery({ context });
  // 新しい投稿を作成する
  const [{ fetching: fetchingCreatePost }, createPost] =
    useCreateOnePostMutation();
  // 投稿を削除する
  const [, deletePost] = useDeleteOnePostMutation();

  // 投稿フォームが送信されたときに呼び出される関数
  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const target = e.target as typeof e.target & {
      title: { value: string };
      content: { value: string };
      category: RadioNodeList;
    };
    // カテゴリIDを取り出す
    const categories = Array.from(target.category).flatMap((category) =>
      category instanceof HTMLInputElement && category.checked
        ? [category.value]
        : []
    );
    // 新しい投稿を作成する
    createPost({
      input: {
        title: target.title.value || "タイトルなし",
        content: target.content.value || "内容なし",
        categories: {
          connect: categories.map((id) => ({
            id,
          })),
        },
      },
    });
    // フォームをリセットする
    e.currentTarget.reset();
  };

  // 投稿の総数を取得する
  const postCounts = dataPostCount?.countPost ?? 0;
  // 投稿の総ページ数を計算する
  const postPages = Math.ceil(postCounts / PageLimit);
  return (
    <>
      <div className="max-w-2xl m-auto py-4">
        <Link className="underline text-blue-500" href="/category">
          カテゴリの追加
        </Link>
        {/* 投稿フォーム */}
        <form
          className="grid border-gray-400 border-solid"
          onSubmit={handleSubmit}
        >
          <label htmlFor="flex-1">Title</label>
          <input className="border p-1" type="text" name="title" />
          <label htmlFor="content">Content</label>
          <textarea className="border p-2 rounded" rows={5} name="content" />
          {/* カテゴリ一覧 */}
          <div className="flex gap-2 flex-wrap p-2">
            {dataCategory?.findManyCategory.map((category) => (
              <label
                key={category.id}
                className="border border-blue-400 rounded p-2"
              >
                <input type="checkbox" name="category" value={category.id} />{" "}
                {category.name}
              </label>
            ))}
          </div>
          <button
            className="shadow bg-blue-500 hover:bg-blue-400 focus:shadow-outline focus:outline-none text-white font-bold py-2 px-4 rounded m-1 disabled:opacity-30 disabled:cursor-not-allowed"
            type="submit"
            disabled={fetchingCreatePost}
          >
            Create Post
          </button>
        </form>
        <hr className="m-2" />
        {/* ページネーション */}
        <div className="flex gap-2 items-center">
          <div>最大5件表示</div>
          <div>
            Page {page}/{postPages}
          </div>
          <Link
            className={`border p-1 rounded ${
              page <= 1 ? "opacity-30 cursor-not-allowed" : ""
            }`}
            href={`/?page=${page <= 1 ? page : page - 1}`}
          >
            ←
          </Link>
          <Link
            className={`border p-1 rounded ${
              page >= postPages ? "opacity-30 cursor-not-allowed" : ""
            }`}
            href={`/?page=${page >= postPages ? page : page + 1}`}
          >
            →
          </Link>
          All:{postCounts}
        </div>

        {/* 投稿一覧 */}
        <div>
          {dataPost?.findManyPost.map((post) => (
            <div key={post.id} className="mt-5 p-1 border rounded">
              <div className="flex gap-2">
                <div className="flex-1">{post.title}</div>
                <div>[{post.id}]</div>
                <div>
                  {new Date(post.updatedAt).toLocaleString("ja-JP", {
                    timeZone: "Asia/Tokyo",
                  })}
                </div>
                <button
                  className="border p-px rounded bg-red-500 hover:bg-red-400 focus:shadow-outline focus:outline-none text-white font-bold px-px"
                  onClick={() => deletePost({ where: { id: post.id } })}
                >
                  Del
                </button>
              </div>
              <div className="whitespace-pre-wrap">{post.content}</div>
              <div className="flex flex-wrap gap-1">
                {post.categories.map((category) => (
                  <div key={category.id} className="bg-slate-100 px-1">
                    {category.name}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="text-center">
        <div>
          <Link className="underline text-blue-500" href="/explorer">
            動作確認用 Apollo Explorer
          </Link>
        </div>
        <div>
          <Link
            className="underline text-blue-500"
            href="https://github.com/SoraKumo001/next-graphql"
          >
            ソースコード
          </Link>
        </div>
      </div>
    </>
  );
};

export default Page;
```

_実行画面_

Urql に SSR 用のプラグインを入れているため、結果はページを読み込んだ時点で HTML に挿入されています。CreatePost でデータを追加するとクライアント側で再レンダリングされます。コンポーネントのレンダリングは AppRouter ではなく PagesRouter を使っているので、ServerComponents 特有の制限はありません。

また、JavaScript を OFF にしても、表示系機能はページジェネレーションを含め動作します。このあたりは Next.js の標準機能として存在しているので、きちんと SSR させているかが重要になります。

![](/images/next-graphql/2023-10-15-22-42-40.png)

# おまけ ApolloExplorer を使う

GraphQL クエリを作成・テストするときに ApolloExplorer があると便利です。Yoga にも実装されているのですが、ApolloExplorer の方が使い勝手が良いのです。ApolloServer を使っている場合は、標準で使えるのですが、Yoga を使っている場合は自分でコンポーネントを組み込む必要があります。

_src/components/GraphQLExplorer_

```tsx
import { ApolloExplorer } from "@apollo/explorer/react";
import { FC } from "react";

export const GraphQLExplorer: FC<{ schema: string }> = ({ schema }) => {
  return (
    <ApolloExplorer
      className="fixed inset-0"
      schema={schema}
      endpointUrl="/graphql"
      persistExplorerState={true}
      handleRequest={(url, option) =>
        fetch(url, { ...option, credentials: "same-origin" })
      }
    />
  );
};
```

_src/pages/explorer.tsx_

```tsx
import { printSchema } from "graphql";
import { GetStaticProps, NextPage } from "next";
import { schema } from "@/app/graphql/schema";
import { GraphQLExplorer } from "@/components/GraphQLExplorer";

const Page: NextPage<{ schema: string }> = ({ schema }) => {
  return <GraphQLExplorer schema={schema} />;
};

// Schemaを渡すのに使用、これでIntrospectionクエリが不要となる
export const getStaticProps: GetStaticProps = async () => {
  return {
    props: { schema: printSchema(schema) },
  };
};

export default Page;
```

_実行画面_

![](/images/next-graphql/2023-10-15-22-42-52.png)

# まとめ

GraphQL に入門するのが難しい理由は、ほとんどの部分が自動生成されるためです。GraphQL スキーマを作成する必要も、GraphQL クエリを書く必要もありません。

今後必要なことは、データ構造を追加した場合などに`prisma.schema`に追記していくことです。そうすることで、`prisma generate`を実行した後に<http://localhost:3000/graphql>にアクセスするだけで、新しいクエリが自動生成されます。

ただし、実際に運用する場合には問題があります。`query.graphql`に記述されているデータの範囲が大きいため、必要のないデータまで取得してしまうことがあります。最終的には、データの取得範囲を調整するために自分で修正することをオススメします。

また、今回は認証や権限管理に関して特に何もしていません。これらの処理は、`schema.prisma`にディレクティブを設定することで、自動生成されるリゾルバに権限管理を付加できます。詳しくは、[こちらの記事](https://next-blog.croud.jp/contents/6139cb73-f402-4523-a26f-2e9341299415)の後半を参照してください。

内容的にはしれっと SSR させています。AppRouter の ServerComponents を使わなくとも、Urql の Suspense を Pages 上で SSR させるのは、Urql にプラグインを入れるだけで非常に簡単に実現可能です。
