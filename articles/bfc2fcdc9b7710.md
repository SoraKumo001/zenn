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

以下公式サイトに`Apollo Server 3`の終了と、`Apollo Server 4` 移行をお勧めする説明が載っています。

https://www.apollographql.com/docs/apollo-server/migration

現在使用しているパッケージが`apollo-server`だった場合は非推奨バージョンです。できるだけ早く準備を整えて`@apollo/server`に乗り換えましょう。

# 何が変わったのか

バラバラに散っていた機能が一つのパッケージに集約されました。その関係で切られる機能はバッサリ切られ、自分で書かなければならないコードが増えました。

# 情報が少ない

ネット上の記事はほぼ`Apollo Server 3`の頃のものばかりなので、公式以外の情報はあまり期待できません。こういう時に必要なのは、情報が少ないときほどワクワクする心を持つことです。新雪に最初に足跡を突っ込んでやるヒャッホーという気持ちこそが必要なのです。

# サンプルを作ってみる

Next.js の APIRoute からアクセス出来る GraphQL のエンドポイントを作ってみます。ただし、普通にやるだけなら公式を見れば良いだろうという話になってしまいます。ということで今回は`Apollo Server 4`になってから情報が壊滅したファイルアップロードの機能をサンプルに加えます。

# Next.js のサンプル

https://github.com/SoraKumo001/next-apollo-server

## API Route に GraphQL のエンドポイントを用意

`Apollo Server4`では、GraphQL の処理に executeHTTPGraphQLRequest を使用します。httpGraphQLRequest に適切な情報を載せて呼び出します。context は今回使用していませんが、とりあえず汎用的に使用しそうなものを設定しています。

必要な機能は`@react-libraries/next-apollo-server`に集約させてあります。使い方は以下の通りです。

- src/pages/api/graphql

```tsx
import { promises as fs } from "fs";
import { ApolloServer } from "@apollo/server";
import {
  executeHTTPGraphQLRequest,
  FormidableFile,
} from "@react-libraries/next-apollo-server";
import type { IResolvers } from "@graphql-tools/utils";
import type { NextApiHandler, NextApiRequest, NextApiResponse } from "next";

/**
 * Type settings for GraphQL
 */
const typeDefs = `
  # Return date
  scalar Date
  type Query {
    date: Date!
  }
  # Return file information
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
 * Set Context type
 */
type Context = { req: NextApiRequest; res: NextApiResponse };

/**
 * Resolver for GraphQL
 */
const resolvers: IResolvers<Context> = {
  Query: {
    date: async (_context, _args) => new Date(),
  },
  Mutation: {
    upload: async (_context, { file }: { file: FormidableFile }) => {
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
const apolloServer = new ApolloServer<Context>({
  typeDefs,
  resolvers,
});
apolloServer.start();

/**
 * APIRoute handler for Next.js
 */
const handler: NextApiHandler = async (req, res) => {
  // Convert NextApiRequest to body format for GraphQL (multipart/form-data support).
  return executeHTTPGraphQLRequest({
    req,
    res,
    apolloServer,
    context: async () => ({ req, res }),
    options: {
      //Maximum upload file size set at 10 MB
      maxFileSize: 10 * 1024 * 1024,
    },
  });
};

export default handler;

export const config = {
  api: {
    bodyParser: false,
  },
};
```

## フロント側の処理

- src/pages/\_app.tsx

createUploadLink で`Upload`タイプのパラメータを multipart 形式に変換させる必要があります。ヘッダーには`apollo-require-preflight`が必要です。

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

// Date retrieval
const QUERY = gql`
  query date {
    date
  }
`;

// Uploading files
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
      {/* SSRedacted data can be updated by refetch. */}
      <button onClick={() => refetch()}>Update date</button>
      {
        /* Dates are output as SSR. */
        data?.date &&
          new Date(data.date).toLocaleString("en-US", { timeZone: "UTC" })
      }
      {/* File upload sample from here down. */}
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
      {/* Display of information on returned file data to check upload operation. */}
      {file && <pre>{JSON.stringify(file, undefined, "  ")}</pre>}
    </>
  );
};
```

## 変換パッケージのコード

変換そのものは formidable がやっているので、あとは適切にデータを配るだけです。

```tsx
import { promises as fs } from "fs";
import { parse } from "url";
import formidable from "formidable";
import type {
  ApolloServer,
  BaseContext,
  ContextThunk,
  GraphQLRequest,
  HTTPGraphQLRequest,
} from "@apollo/server";
import type { NextApiRequest, NextApiResponse } from "next";

/**
 * Request parameter conversion options
 */
export type FormidableOptions = formidable.Options;

/**
 * File type used by resolver
 */
export type FormidableFile = formidable.File;

/**
 * Converting NextApiRequest to Apollo's Header
 * Identical header names are overwritten by later values
 * @returns Header in Map format
 */
export const createHeaders = (req: NextApiRequest) =>
  new Map(
    Object.entries(req.headers).flatMap<[string, string]>(([key, value]) =>
      Array.isArray(value)
        ? value.flatMap<[string, string]>((v) => (v ? [[key, v]] : []))
        : value
        ? [[key, value]]
        : []
    )
  );

/**
 *  Retrieve search from NextApiRequest
 * @returns search
 */
export const createSearch = (req: NextApiRequest) =>
  parse(req.url ?? "").search ?? "";

/**
 * Make GraphQL requests multipart/form-data compliant
 * @returns [body to be set in executeHTTPGraphQLRequest, function for temporary file deletion]
 */
export const createBody = (
  req: NextApiRequest,
  options?: formidable.Options
) => {
  const form = formidable(options);
  return new Promise<[GraphQLRequest, () => void]>((resolve, reject) => {
    form.parse(req, async (error, fields, files) => {
      if (error) {
        reject(error);
      } else if (!req.headers["content-type"]?.match(/^multipart\/form-data/)) {
        resolve([fields, () => {}]);
      } else {
        if (
          "operations" in fields &&
          "map" in fields &&
          typeof fields.operations === "string" &&
          typeof fields.map === "string"
        ) {
          const request = JSON.parse(fields.operations);
          const map: { [key: string]: [string] } = JSON.parse(fields.map);
          Object.entries(map).forEach(([key, [value]]) => {
            value.split(".").reduce((a, b, index, array) => {
              if (array.length - 1 === index) a[b] = files[key];
              else return a[b];
            }, request);
          });
          const removeFiles = () => {
            Object.values(files).forEach((file) => {
              if (Array.isArray(file)) {
                file.forEach(({ filepath }) => {
                  fs.rm(filepath);
                });
              } else {
                fs.rm(file.filepath);
              }
            });
          };
          resolve([request, removeFiles]);
        } else {
          reject(Error("multipart type error"));
        }
      }
    });
  });
};

/**
 * Creating methods
 * @returns method string
 */
export const createMethod = (req: NextApiRequest) => req.method ?? "";

/**
 * Execute a GraphQL request
 */
export const executeHTTPGraphQLRequest = async <Context extends BaseContext>({
  req,
  res,
  apolloServer,
  options,
  context,
}: {
  req: NextApiRequest;
  res: NextApiResponse;
  apolloServer: ApolloServer<Context>;
  context: ContextThunk<Context>;
  options?: FormidableOptions;
}) => {
  const [body, removeFiles] = await createBody(req, options);
  try {
    const httpGraphQLRequest: HTTPGraphQLRequest = {
      method: createMethod(req),
      headers: createHeaders(req),
      search: createSearch(req),
      body,
    };
    const result = await apolloServer.executeHTTPGraphQLRequest({
      httpGraphQLRequest,
      context,
    });
    result.status && res.status(result.status);
    result.headers.forEach((value, key) => {
      res.setHeader(key, value);
    });
    if (result.body.kind === "complete") {
      res.end(result.body.string);
    } else {
      for await (const chunk of result.body.asyncIterator) {
        res.write(chunk);
      }
      res.end();
    }
    return result;
  } finally {
    removeFiles();
  }
};
```

# まとめ

`Apollo Server 3`は非推奨パッケージなので、早々に`Apollo Server 4`への移行をお勧めします。

ちなみにこちらはクライアントに`urql`を使ったバージョンになります。urql の suspense 機能を使って、独自の Exchange を足しつつ Next.js で SSR しています。withUrqlClient のような余計なものを書かずに、コンポーネント上に配置した hook が自動で SSR 対応になります。こちらの解説記事は改めて書きます。

https://github.com/SoraKumo001/next-urql
