---
title: "apollo-server(v3系)は非推奨となったので、@apollo/server(v4系)に移行しましょう"
emoji: "📑"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [nextjs, graphql, apollo, typescript, react]
published: true
---

※こちらでも同じ記事を書いています
https://next-blog.croud.jp/contents/CtOK4fDpToThQ8Y2f9Um

# ApolloServer3 のサポート終了は 2023/10/22

以下公式サイトに`Apollo Server 3`の終了と、`Apollo Server 4` 移行の説明が載っています。

https://www.apollographql.com/docs/apollo-server/migration

現在使用しているパッケージが`apollo-server`だった場合は非推奨バージョンです。できるだけ早く準備を整えて`@apollo/server`に乗り換えましょう。

# 何が変わったのか

バラバラに散っていた機能が一つのパッケージに集約されました。その関係で切られる機能はバッサリ切られ、自分で書かなければならないコードが増えました。

# 情報が少ない

ネット上の記事はほぼ`Apollo Server 3`の頃のものばかりなので、公式以外の情報はあまり期待できません。こういう時に必要なのは、情報が少ないときほどワクワクする心を持つことです。新雪に最初に足跡を突っ込んでやるヒャッホーという気持ちこそが必要なのです。

# サンプルを作ってみる

Next.js の APIRoute からアクセス出来る GraphQL のエンドポイントを作ってみます。ただし、普通にやるだけなら公式を見れば良いだろうという話になってしまいます。なので、なぜか避けて通る人が多いファイルのアップロード機能を入れてみます。

# Next.js のサンプル

https://github.com/SoraKumo001/next-apollo-server

## API Route に GraphQL のエンドポイントを用意

`Apollo Server4`では、GraphQL の処理に executeHTTPGraphQLRequest を使用します。httpGraphQLRequest に適切な情報を載せて呼び出します。context は今回使用していませんが、とりあえず汎用的に使用しそうなものを送っています。適切な情報を作る部分は github にソースを載せているのでそちらを参照してください。

- src/pages/api/graphql

```tsx
import { gql } from "@apollo/client";
import { ApolloServer } from "@apollo/server";
import type { NextApiRequest, NextApiResponse } from "next";
import {
  createGraphQLRequest,
  createHeaders,
  createSearch,
} from "../../libs/apollo-tools";
import { File } from "formidable";
import { promises as fs } from "fs";

/**
 * GraphQLのType設定
 */
const typeDefs = gql`
  # 日付を返す
  scalar Date
  type Query {
    date: Date!
  }

  # ファイル情報を返す
  type File {
    name: String!
    type: String!
    value: String!
  }
  scalar Upload
  type Mutation {
    upload(file: Upload!): File!
  }
`;

/**
 * GraphQLのResolver
 */
const resolvers = {
  Query: {
    date: async () => new Date(),
  },
  Mutation: {
    upload: async (_: unknown, { file }: { file: File }) => {
      return {
        name: file.originalFilename,
        type: file.mimetype,
        value: await fs.readFile(file.filepath, { encoding: "utf8" }),
      };
    },
  },
};

/**
 * apolloServer
 */
const apolloServer = new ApolloServer({
  typeDefs,
  resolvers,
});
apolloServer.start();

/**
 * Next.js用APIRouteハンドラ
 */
const apolloHandler = async (req: NextApiRequest, res: NextApiResponse) => {
  //NextApiRequestをGraphQL用のbody形式に変換(multipart/form-data対応)
  const [body, removeFiles] = await createGraphQLRequest(req);
  try {
    const result = await apolloServer.executeHTTPGraphQLRequest({
      httpGraphQLRequest: {
        method: req.method ?? "",
        headers: createHeaders(req),
        search: createSearch(req),
        body,
      },
      context: async () => ({ req, res }),
    });
    if (result.body.kind === "complete") {
      res.end(result.body.string);
    } else {
      for await (const chunk of result.body.asyncIterator) {
        res.write(chunk);
      }
      res.end();
    }
  } finally {
    // multipart/form-dataで作成された一時ファイルの削除
    removeFiles();
  }
};

export default apolloHandler;

export const config = {
  api: {
    bodyParser: false,
  },
};
```

## フロント側の処理

- src/pages/\_app.tsx

createUploadLink で`Upload`タイプのパラメータを multipart 形式に変換させる必要があります。

```tsx
import type { AppType } from "next/app";
import { ApolloClient, ApolloProvider, InMemoryCache } from "@apollo/client";
import { createUploadLink } from "apollo-upload-client";
const endpoint = "/api/graphql";
const uri =
  typeof window === "undefined"
    ? `${
        process.env.VERCEL_URL
          ? `https://${process.env.VERCEL_URL}`
          : "http://localhost:3000"
      }${endpoint}`
    : endpoint;

const App: AppType = ({ Component, pageProps }) => {
  const client = new ApolloClient({
    cache: new InMemoryCache(),
    // Upload用
    link: createUploadLink({
      uri,
      headers: { "apollo-require-preflight": "true" },
    }),
  });

  return (
    <ApolloProvider client={client}>
      <Component {...pageProps} />
    </ApolloProvider>
  );
};

export default App;
```

- src/pages/index.tsx

アップロードの処理は variables に blob オブジェクトのデータを載せるだけなので簡単です。  
こちらのサンプルでは、ドラッグドロップされたデータをバックエンドに送って、内容を戻してもらい表示する実装になっています。
また、日付表示はおまけで、ファイルのアップロードとは関係ありません。

```tsx
import { gql, useMutation, useQuery } from "@apollo/client";

// 日付を取り出す
const QUERY = gql`
  query date {
    date
  }
`;

// ファイルをアップロードする
const UPLOAD = gql`
  mutation Upload($file: Upload!) {
    upload(file: $file) {
      name
      type
      value
    }
  }
`;

const Page = () => {
  const { data, refetch } = useQuery(QUERY);
  const [upload, { data: file }] = useMutation(UPLOAD);
  return (
    <>
      <a
        target="_blank"
        href="https://github.com/SoraKumo001/next-apollo-server"
        rel="noreferrer"
      >
        Source code
      </a>
      <hr />
      <button onClick={() => refetch()}>日付更新</button>{" "}
      {data?.date &&
        new Date(data.date).toLocaleString("ja-jp", { timeZone: "Asia/Tokyo" })}
      <div
        style={{
          height: "100px",
          width: "100px",
          background: "lightgray",
          marginTop: "8px",
          padding: "8px",
        }}
        onDragOver={(e) => {
          e.preventDefault();
        }}
        onDrop={(e) => {
          const file = e.dataTransfer.files[0];
          if (file) {
            upload({ variables: { file } });
          }
          e.preventDefault();
        }}
      >
        Upload Area
      </div>
      {file && <pre>{JSON.stringify(file, undefined, "  ")}</pre>}
    </>
  );
};

export default Page;
```

# まとめ

`Apollo Server 3`は非推奨パッケージなので、早々に`Apollo Server 4`への移行をお勧めします。

ちなみにこちらはクライアントに`urql`を使ったバージョンになります。urql の suspense 機能を使って、独自の Exchange を足しつつ SSR しています。こちらの解説記事は改めて書きます。
https://github.com/SoraKumo001/next-urql
