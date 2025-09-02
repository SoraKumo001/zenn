---
title: "Honoで作るバックエンドサーバ"
emoji: "🙆"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: []
published: false
---

# 無料で作るバックエンドサーバ

今回は DB に PostgreSQL を使い、GraphQL の API を提供するバックエンドサーバを Hono と Pothos、Prisma を使って構築します。すべて無料で利用できます。

## インフラの構成

今回使うインフラは無料大好きユーザー御用達の以下のサービスを使用します

- [Cloudflare Workers](https://www.cloudflare.com/ja-jp/developer-platform/products/workers/)
- [Supabase](https://supabase.com/)

## 使用するライブラリなど

### [Hono](https://hono.dev/)

Hono は Web フレームワークです。プラグインを使うことで、GraphQL サーバとして動作させることもできます。

### [Pothos](https://pothos-graphql.dev/)

Pothos GraphQL スキーマを構築するためのライブラリです。プラグインを追加することで、Prisma との連携が簡単に行えます。

### [Prisma](https://www.prisma.io/)

Prisma はデータベース ORM です。

## バックエンド API に GraphQL の利点

GraphQL の利点は、Prisma と相性が良いという部分が大きいです。もともと Prisma は内部エンジンに GraphQL を使用していた時代があり、JavaScript 側から使用する場合の構文もかなり近い書き方となっています。このおかげで GraphQL を通して Prisma を呼び出す際に、構文やフォーマットの変換が最小限で済みます。自動変換するためのコードを書くことも容易にできるのです。

# Hono + Pothos + Prisma のサンプルコード

Prisma のスキーマを定義し、Pothos で GraphQL のスキーマを定義、Hono で GraphQL のアクセス要求を受け取るサンプルコードです。Cloudflare Workers 上で動作することを前提としています。

Prisma スキーマから GraphQL スキーマへの変換は、プラグインを使って自動で行います。各テーブルに対する Query や Mutation は自動的に生成されるので、自分で書く必要はありません。

- `count`
- `findUnique`
- `findFirst`
- `findMany`
- `createOne`
- `createMany`
- `updateOne`
- `updateMany`
- `deleteOne`
- `deleteMany`

上記操作は自動生成です。また、リレーションも自動的に生成されるので、フィールド上で他のテーブルのデータを参照することもできます。

## 大まかな流れ

1. Prisma でデータベースのスキーマを定義
2. Pothos で GraphQL のスキーマを定義
3. Hono で GraphQL のアクセス要求を受け取る
4. JWT で認証を行う
5. 認証されたユーザ情報を GraphQL のコンテキストに設定

## コードの解説

### prisma/schema.prisma

カテゴリーを指定して、投稿を保存するスキーマを定義しています。  
`/// @pothos-generator`の部分は、GraphQL スキーマを自動生成するときに権限設定などを行っています。  
設定したものは`prisma generate`を行うと GraphQL のスキーマ自動生成の際に反映されます。

- 書き込み処理は USER 権限を持つもののみ

  - `/// @pothos-generator executable {include:["mutation"],authority:["USER"]}`

- 読み込み処理で USER 権限を持っている場合はすべてを、そうでない場合は publish が true のものだけ取り出すことができる

  - `/// @pothos-generator where {include:["query"],where:{},authority:["USER"]}`
  - `/// @pothos-generator where {include:["query"],where:{published:true}}`

- 書き込みは USER 権限を持つもののみ

  - `/// @pothos-generator executable {include:["mutation"],authority:["USER"]}`

- 書き込み時は強制的に authorId で、ユーザ情報が設定される

  - `/// @pothos-generator input-data {data:{authorId:"%%USER%%"}}`

- 書き込み時は author への直接の書き込みを禁止する

  - `/// pothos-generator input-field {include:["mutation"],fields:{exclude:["author"]}}`

- 書き込みは USER 権限を持つもののみ
  - `/// @pothos-generator executable {include:["mutation"],authority:["USER"]}`

Prisma のスキーマーで`prisma-dmmf.ts`を生成するための設定も含まれています。  
本来、Pothos にも dmmf を生成する機能があるのですが、enums が切り捨てられてしまうため、別機能を利用しています。

```prisma
generator client {
  provider     = "prisma-client-js"
  previewFeatures = ["driverAdapters","queryCompiler"]
  output       = "../node_modules/.prisma/client"
  moduleFormat = "esm"
}

datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}

generator pothos {
  clientOutput      = "@prisma/client"
  provider          = "prisma-pothos-types"
  output            = "../src/generated/pothos-types.ts"
}

generator prismaDmmfGenerator {
  provider = "pothos-prisma-generator"
  output   = "../src/generated/prisma-dmmf.ts"
}

enum Role {
  ADMIN
  USER
}

/// @pothos-generator executable {include:["mutation"],authority:["USER"]}
model User {
  id        String   @id @default(uuid())
  email     String   @unique
  name      String   @default("User")
  posts     Post[]
  roles     Role[]   @default([USER])
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt
}

/// @pothos-generator where {include:["query"],where:{},authority:["USER"]}
/// @pothos-generator where {include:["query"],where:{published:true}}
/// @pothos-generator executable {include:["mutation"],authority:["USER"]}
/// @pothos-generator input-data {data:{authorId:"%%USER%%"}}
/// @pothos-generator input-field {include:["mutation"],fields:{exclude:["author"]}}
model Post {
  id          String     @id @default(uuid())
  published   Boolean    @default(false)
  title       String     @default("New Post")
  content     String     @default("")
  author      User?      @relation(fields: [authorId], references: [id])
  authorId    String?
  categories  Category[]
  createdAt   DateTime   @default(now())
  updatedAt   DateTime   @updatedAt
  publishedAt DateTime   @default(now())
}

/// @pothos-generator executable {include:["mutation"],authority:["USER"]}
model Category {
  id        String   @id @default(uuid())
  name      String
  posts     Post[]
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt
}
```

### Hono で GraphQL のアクセス要求を受け取る部分

Hono で GraphQL のアクセス要求を受け取る部分です。

- GET リクエストで Apollo Explorer\(graphiql というエクスプローラが使いにくいので置き換えています\) を表示し、POST リクエストで GraphQL の処理を行う
- POST リクエストでは、JWT を使って認証を行い、認証されたユーザ情報を GraphQL のコンテキストに設定。この処理は一般的な GraphQL サーバでは、コンテキストのコールバック上で行われますが、Hono ではミドルウェアとして実装
- contextStorage を使って、Hono のコンテキストに Prisma クライアントを保存できるようにします

contextStorage は、リクエストごとにコンテキスト領域を確保するものです。ここに Prisma クライアントを動的に生成して保存することで、リクエストごとに異なる Prisma クライアントを使用できます。これは Cloudflare Workers の制限に対応するための方法です。同一インスタンスを別コネクションで使用すると、本番環境でエラーが発生します。

Node.js 版と同じように Cloudflare から GraphQL のオペレーションを document に設定しようとすると、サイズ超過で失敗するようです。一度、設定無しで表示すると 2 回目からはどうさするのですが、ここではコメントアウトしています。

#### src/index.ts

```ts
import { graphqlServer } from "@hono/graphql-server";
import { explorer } from "apollo-explorer/html";
// import { generate } from "graphql-auto-query";
import { Hono } from "hono";
import { contextStorage } from "hono/context-storage";
import { getCookie } from "hono/cookie";
import { createBuilder } from "./builder.js";
import { verifyJWT } from "./jwt.js";
import { prisma } from "./prisma.js";
import { initResolvers } from "./resolvers.js";
import type { Context } from "./context.js";

const builder = createBuilder();
// Initialize the resolvers for the GraphQL schema
initResolvers(builder);
const schema = builder.toSchema({ sortSchema: false });

const app = new Hono<{ Variables: Context }>();
app.use(contextStorage());

// Apollo Explorer
app.get("/", (c) => {
  return c.html(
    explorer({
      initialState: {
        // Set up sample GraphQL operations
        // document: generate(schema, 1),
      },
      endpointUrl: "/",
      introspectionInterval: 5000,
    })
  );
});

// Perform the initial setup required for GraphQL processing
app.post(async (c, next) => {
  const secret = process.env.SECRET ?? "";
  const token = getCookie(c, "session");
  const user = await verifyJWT<Pick<Context, "user">>(token, secret).then(
    (v) => v?.user
  );
  c.set("user", user);
  c.set("prisma", prisma);
  await next();
});

// Pass the process to the GraphQL server
app.post("/", (...params) =>
  graphqlServer({
    schema: schema,
  })(...params)
);

export default app;
```

### JWT のエンコードとデコード

セッションを管理するために JWT を使用しています。

#### src/jwt.ts

```ts
import { jwtVerify, SignJWT } from "jose";

export const verifyJWT = async <T>(
  token: string | undefined,
  secret: string
) => {
  if (!token) return undefined;
  const data = await jwtVerify(token, new TextEncoder().encode(secret)).catch(
    () => undefined
  );
  return data?.payload.data as T | undefined;
};

export const sighJWT = async <T>(data: T, secret: string) => {
  return await new SignJWT({ data })
    .setProtectedHeader({ alg: "HS256" })
    .sign(new TextEncoder().encode(secret));
};
```

### Prisma の初期化

Prisma クライアントの初期化を行います。  
Proxy を使用して、最初に Prisma を使用した時点でインスタンスを生成します。また、Hono のコンテキストストレージを使用して、リクエストごとに Prisma クライアントを共有します。

#### src/prisma.ts

```ts
import { PrismaPg } from "@prisma/adapter-pg";
import { PrismaClient } from "@prisma/client";
import { getContext } from "hono/context-storage";

const getAdapter = (datasourceUrl: string) => {
  const url = new URL(datasourceUrl);
  const schema = url.searchParams.get("schema") ?? undefined;
  return new PrismaPg({ connectionString: datasourceUrl }, { schema });
};

export const prisma: PrismaClient = new Proxy<PrismaClient>({} as never, {
  get(_target: unknown, props: keyof PrismaClient) {
    const context = getContext<{
      Variables: { _prisma: PrismaClient };
      Bindings: { database: { connectionString: string } };
    }>();

    if (!context.get("_prisma")) {
      const datasourceUrl =
        process.env.DATABASE_URL ?? context.env.database?.connectionString;
      if (!datasourceUrl) throw new Error("DATABASE_URL is not set");
      const adapter = getAdapter(datasourceUrl);
      const prisma = new PrismaClient({
        adapter,
        log: ["error"],
      });
      context.set("_prisma", prisma);
    }
    return context.get("_prisma")[props];
  },
});
```

### wrangler.jsonc の設定

```jsonc
{
  "$schema": "node_modules/wrangler/config-schema.json",
  "name": "hono-pothos-prisma-cloudflare",
  "compatibility_date": "2025-05-09",
  "compatibility_flags": [
    "nodejs_compat",
    "nodejs_compat_populate_process_env"
  ],
  "main": "./src/index.ts",
  "minify": true,
  "observability": {
    "enabled": true
  },
  "hyperdrive": [
    {
      "binding": "database",
      // The name of the binding is used to access the database in your code.
      "id": "",
      "localConnectionString": "postgresql://postgres:password@localhost:35432/postgres?schema=pothos-hono-postgres"
    }
  ]
}
```

### GraphQL のコンテキスト

GraphQL のコンテキストを定義します。  
このコンテキストには、Prisma クライアントと認証されたユーザ情報が含まれます。

#### src/context.ts

```ts
import type { prisma } from "./prisma";

export type Context = {
  prisma: typeof prisma;
  user?: { id: string; name: string; roles: string[] };
};
```

### Pothos のビルダー

Pothos のビルダーを作成します。

Prisma と連携するのに必要なプラグインを設定は以下のとおりです。

- `replace`では、schema.prisma で定義した`%%USER%%`を、認証されたユーザの ID に置き換え
- `authority`では、認証されたユーザのロールを取得し、権限を設定

#### src/builder.ts

Node.js 版との違いは、Prisma の DMMF を手動で指定している点です。  
Edge 環境用の構成を利用すると、Prisma が DMMF を中途半端にしか生成しなくなります。そのため Photos 側が DMMF を生成する機能を搭載したのですが、こちらも残念ながら中途半端なものを出力してしまいます。仕方がないので pothos-prisma-generator に DMMF の生成機能を付けて、そちらの DMMF を使用しています。

```ts
import SchemaBuilder from "@pothos/core";
import PrismaPlugin from "@pothos/plugin-prisma";
import PrismaUtils from "@pothos/plugin-prisma-utils";
import PothosPrismaGeneratorPlugin from "pothos-prisma-generator";
import { prismaDmmf } from "./generated/prisma-dmmf.js";
import { prisma } from "./prisma.js";
import type { Context } from "./context.js";
import type PrismaTypes from "@pothos/plugin-prisma/generated";
import type Hono from "hono";

// console.log(JSON.stringify(getDatamodel(), null, 2));

/**
 * Create a new schema builder instance
 */
export const createBuilder = () => {
  return new SchemaBuilder<{
    Context: Hono.Context<{ Variables: Context }>;
    PrismaTypes: PrismaTypes; //Not used because it is generated automatically
    Prisma: typeof prisma;
  }>({
    plugins: [PrismaPlugin, PrismaUtils, PothosPrismaGeneratorPlugin],
    prisma: {
      client: prisma,
      dmmf: prismaDmmf,
    },
    pothosPrismaGenerator: {
      // Replace the following directives
      // /// @pothos-generator input {data:{author:{connect:{id:"%%USER%%"}}}}
      replace: { "%%USER%%": ({ context }) => context.get("user")?.id },

      // Set the following permissions
      /// @pothos-generator any {authority:["ROLE"]}
      authority: ({ context }) => context.get("user")?.roles ?? [],
    },
  });
};

export type Builder = ReturnType<typeof createBuilder>;
```

### GraphQL のリゾルバ

GraphQL のリゾルバを定義します。  
基本的には Prisma のスキーマから自動生成されるので、必要な部分だけを追加しています。

- `signIn`でユーザのサインインを行い、JWT を生成してセッションを Cookie に保存
- `signOut`でセッションを Cookie から削除
- `me`で認証されたユーザの名前を取得
- `test`で投稿のタイトルに"Add-"を付けて返すカスタムフィールド\(実験用なので内容は適当\)
- `limit`ディレクティブを使用して、`findMany`の結果を 3 件に制限するカスタムディレクティブを追加

#### src/resolvers.ts

```ts
import { deleteCookie, setCookie } from "hono/cookie";
import { sighJWT } from "./jwt.js";
import type { Builder } from "./builder.js";
import type { Context } from "./context.js";

export const initResolvers = (builder: Builder) => {
  // Example of how to add a custom auth query
  builder.mutationType({
    fields: (t) => {
      return {
        // Example of how to add a custom auth query
        // This query will return true if the user is authenticated
        signIn: t.boolean({
          args: { email: t.arg({ type: "String", required: true }) },
          resolve: async (_root, { email }, ctx) => {
            const prisma = ctx.get("prisma");
            const { id, name, roles } = await prisma.user.findUniqueOrThrow({
              where: { email },
            });
            const secret = process.env.SECRET ?? "";
            const user: Context["user"] = { id, name, roles };
            const token = await sighJWT({ user: user }, secret);
            setCookie(ctx, "session", token, {
              path: "/",
              httpOnly: true,
              sameSite: "strict",
              expires: new Date(Date.now() + 1000 * 60 * 60 * 24 * 7),
            });
            return true;
          },
        }),
        // Example of how to add a custom auth query
        // and will clear the session cookie
        signOut: t.boolean({
          resolve: (_root, _args, ctx) => {
            deleteCookie(ctx, "session", {
              path: "/",
            });
            return true;
          },
        }),
        me: t.string({
          resolve: (_root, _args, ctx) => {
            return ctx.get("user")?.name;
          },
        }),
      };
    },
  });
  // Example of how to add a custom query
  builder.addModelFields("Post", {
    test: (t) =>
      t.string({
        resolve: (parent) => {
          return `Add-${parent.title}`;
        },
      }),
  });
  // Example of directive operation
  builder.addSchemaGenerator((c) => {
    c.generator.addModelDirectives("Post", "limit", {
      include: ["findMany"],
      limit: 3,
    });
  });
};
```

## 動作確認

1. 環境変数を設定します。`.env`ファイルを作成し、以下の内容を記述します。

```dotenv
DATABASE_URL="postgresql://postgres:password@localhost:35432/postgres?schema=pothos-hono-postgres"
SECRET="test"
```

2. 開発モードの実行

```bash
pnpm run dev
```

3. ブラウザで`http://localhost:3000/`にアクセスします。Apollo Explorer が表示されます。

![](./document/image.webp)

Prisma スキーマをもとにして GraphQL の操作がひととおり行えることが確認できます。Fragment,Query,Mutation などの GraphQL のオペレーションも自動生成されているので、必要なものを選択して実行できます。

### 認証の確認をする

#### user アカウントでの操作

- signIn

````graphql
# - variables
# {
#  "email": "user@example.com"
# }
mutation SignIn($email: String!) {
  signIn(email: $email)
}

# - result
# ```json
# {
#  "data": {
#    "signIn": true
#  }
# }
````

- 現在のユーザの確認

```graphql
mutation Mutation {
  me
}
# - result
# {
#   "data": {
#     "me": "user"
#   }
# }
```

- 投稿の作成

```graphql
# - variables
# {
#   "input": {
#     "title":"Title",
#     "content":"Content"
#   }
# }

mutation CreateOnePost($input: PostCreateInput!) {
  createOnePost(input: $input) {
    id
    title
    content
    createdAt
    updatedAt
    author {
      id
      name
    }
  }
}

# - result
# {
#   "data": {
#     "createOnePost": {
#       "id": "0bd1241a-67e3-48c1-b78c-2b89ed198a0d",
#       "title": "Title",
#       "content": "Content",
#       "createdAt": "2025-06-15T07:45:35.707Z",
#       "updatedAt": "2025-06-15T07:45:35.707Z",
#       "author": {
#         "id": "a86a54e5-73c6-491f-b010-0fe20ded3129",
#         "name": "user"
#       }
#     }
#   }
# }
```

#### admin アカウントでの操作

- signIn

```graphql
# - variables
# {
#  "email": "admin@example.com"
# }
mutation SignIn($email: String!) {
  signIn(email: $email)
}

# - result
# {
#   "data": {
#     "signIn": true
#   }
# }
```

- 現在のユーザの確認

```graphql
mutation Mutation {
  me
}
# - result
# {
#   "data": {
#     "me": "user"
#   }
# }
```

- 投稿の作成

```graphql
# - variables
# {
#   "input": {
#     "title":"Title",
#     "content":"Content"
#   }
# }

mutation CreateOnePost($input: PostCreateInput!) {
  createOnePost(input: $input) {
    id
    title
    content
    createdAt
    updatedAt
    author {
      id
      name
    }
  }
}

# - result
# {
#   "data": {
#     "createOnePost": {
#       "id": "99ce12db-2b46-4b2b-8ee2-d316a1f540ed",
#       "title": "Title",
#       "content": "Content",
#       "createdAt": "2025-06-15T06:45:19.160Z",
#       "updatedAt": "2025-06-15T06:45:19.160Z",
#       "author": {
#         "id": "e5f9e67a-e6d9-4b91-9bb5-3766cb2472e3",
#         "name": "admin"
#       }
#     }
#   }
# }
```

#### 未認証の場合の確認

認証されていないユーザで操作を行うと、書き込みができないことを確認します。

- signOut

```graphql
mutation Mutation {
  signOut
}
# - result
# {
#   "data": {
#     "signOut": true
#   }
# }
```

```graphql
query Query {
  me
}
# - result
# {
#   "data": {
#     "me": null
#   }
# }
```

- 投稿の作成

```graphql
# - variables
# {
#   "input": {
#     "title":"Title",
#     "content":"Content"
#   }
# }

mutation CreateOnePost($input: PostCreateInput!) {
  createOnePost(input: $input) {
    id
    title
    content
    createdAt
    updatedAt
    author {
      id
      name
    }
  }
}

# - result
# {
#   "errors": [
#     {
#       "message": "\nInvalid `prisma.post.create()` invocation:\n\n\nForeign key constraint violated on the constraint: `Post_authorId_fkey`",
#       "locations": [
#         {
#           "line": 9,
#           "column": 3
#         }
#       ],
#       "path": [
#         "createOnePost"
#       ]
#     }
#   ]
# }
```

# deploy

あらかじめ、Hyper Drive に Postgres の設定しておく必要があります。Hyper Drive はなくても DB を使うことは可能ですが、Supabase の pooler よりも倍早いです。設定したら、wrangler.jsonc 内の id を設定します。

設定が完了したら下記のコマンドでデプロイできます。secret は認証セッション用の JWT のシークレットキーを設定します。

```sh
pnpm deploy
pnpm deploy:secret
```

また、本番 DB の初期化は、.env.production に DATABASE_URL を設定し、以下のコマンドを実行します。

```sh
pnpm production:setup
```

## まとめ

このサンプルでは、Hono を使って GraphQL サーバを構築し、Prisma と Pothos を組み合わせて GraphQL スキーマを定義しました。認証とセッションの作成、ユーザごとのデータ操作など、アプリケーションを構築するための基本的な機能を実装しています。
