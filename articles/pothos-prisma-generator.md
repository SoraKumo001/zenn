---
title: "PrismaのスキーマをからPothosのGraphQLオペレーションを全自動で生成"
emoji: "💤"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [graphql, pothos, nextjs, typescript, react]
published: true
---

# GraphQL Nexus と Pothos GraphQL

GraphQL をコードファーストで構築する場合、GraphQL Nexus を使うことが多いと思います。しかし、Nexus の開発が停滞しているようで、別のツールに切り替える必要が出てきました。Pothos はその候補の一つです。

Nexus では nexus-prisma というパッケージを使って TypeScript と Prisma を統合できました。Pothos でも Prisma との連携は可能ですが、Prisma 側で設定されている方をそのまま持っていきたい場合に nexus-prisma ほど便利ではありません。Pothos のドキュメントにはいくつかのサンプルがありますが、プラグインとして簡単に導入できるものではありません。

prisma-generator-pothos-codegen というパッケージもありますが、私が試したときは prisma@5 に対応していませんでした。その後、対応がされたようですが、すでに Pothos を使ってコードを書いていたので、そのまま開発を続けることにしました。

そして、よく使う操作を自動化するプラグインを作成しました。

# 作成したもの

開発した Pothos のジェネレータを紹介します。Pothos はこれまで使ったことがなかったので、開発は完全にゼロからでした。

## npm パッケージ

https://www.npmjs.com/package/pothos-prisma-generator

## サンプルアプリ

### Next.js

- ソースコード(Next.js + GraphQL-Yoga + Apollo-Explorer)

https://github.com/SoraKumo001/next-pothos

- Vercel にデプロイしたもの

https://next-pothos.vercel.app/

### NestJS

- ソースコード(NextJS + Apollo/Server4)

https://github.com/SoraKumo001/nest-pothos

- Render.com したもの

https://nest-pothos.onrender.com

### Blog システム

以前 Nexus で作っていたブログシステムを Pothos+今回作ったジェネレータに置き換えました。

https://github.com/SoraKumo001/md-blog

- VPS 上の Docker で動作

https://next-blog.croud.jp/

# 基本的な使い方

## Pothos の Builder 作成

まず、plugins に PothosPrismaGenerator を設定します。このプラグインは、Prisma スキーマから GraphQL スキーマを生成するために必要です。また、plugin-prisma と plugin-prisma-utils も併用します。これらのプラグインは、Prisma クライアントと GraphQL リゾルバを連携させるために必要です。

Pothos の設定はこれだけで完了です。次に、Apollo Server などの GraphQL サーバーに Builder で作ったスキーマを投入します。以下のコードは、TypeScript で書かれた例です。

```ts
import SchemaBuilder from "@pothos/core";
import PrismaPlugin from "@pothos/plugin-prisma";
import PrismaUtils from "@pothos/plugin-prisma-utils";
import PothosPrismaGenerator from "pothos-prisma-generator";
import { Context, prisma } from "./context";

/**
 * Create a new schema builder instance
 */
export const builder = new SchemaBuilder<{
  Context: Context;
}>({
  plugins: [PrismaPlugin, PrismaUtils, PothosPrismaGenerator],
  prisma: {
    client: prisma,
  },
});
```

## Prisma のスキーマ作成

ここでは、サンプル用に適当な Prisma のスキーマを用意してみましょう。以下のコードは、ユーザー、投稿、カテゴリーという 3 つのモデルと、ユーザーの役割を表す列挙型を定義しています。各モデルには、id や名前などのフィールドや、他のモデルとの関係を示すリレーションがあります。

このスキーマを保存したら、`prisma generate`コマンドで@prisma/client を生成します。これで、GraphQL のオペレーションが使えるようになりました。プラグインはこのとき prisma が作成する DMMF を参照します。

```prisma
generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}

model User {
  id        String   @id @default(uuid())
  email     String   @unique
  name      String   @default("User")
  posts     Post[]
  roles     Role[]   @default([USER])
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt
}

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

model Category {
  id        String   @id @default(uuid())
  name      String
  posts     Post[]
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt
}

enum Role {
  ADMIN
  USER
}
```

## 出力結果

以下のように Prisma のモデルに対応した Query と Mutation が作成されます。プラグインを追加するだけで、モデルに対応したオペレーションの全機能が動きます。

ラクチン！

![](/images/pothos-prisma-generator/2023-09-26-09-03-08.png)

![](/images/pothos-prisma-generator/2023-09-26-09-03-25.png)

## 作成可能なクエリの例

![](/images/pothos-prisma-generator/2023-09-26-09-00-50.png)

クエリの引数として filter,orderBy,limit,offset の指定が可能です。また、リレーション先に対しても同様の指定が可能です。
これらの機能を手動で作った場合、リレーション先を含めるとかなり複雑になります。

以下、クエリのサンプルです。リレーションのリレーションまでは書いていませんが、どこまでもたどれます。リレーションに関しては件数取得機能もフィールド上に追加されるので、limit や offset と組み合わせてページングも行えます。

クエリに関しては手動で書かなければならないのですが、テンプレート的なものを自動生成しようかと思案中です。

```graphql
fragment user on User {
  id
  email
  name
  roles
  createdAt
  updatedAt
}

fragment category on Category {
  id
  name
  createdAt
  updatedAt
}

fragment post on Post {
  id
  published
  title
  content
  authorId
  updatedAt
  publishedAt
}

query CountUser($filter: UserFilter) {
  countUser(filter: $filter)
}

query CountPost($filter: PostFilter) {
  countPost(filter: $filter)
}

query CountCategory($filter: CategoryFilter) {
  countCategory(filter: $filter)
}

query FindUniqueUser(
  $filter: UserUniqueFilter!
  $postFilter: PostFilter
  $postOrderBy: [PostOrderBy!]
  $postLimit: Int
  $postOffset: Int
) {
  findUniqueUser(filter: $filter) {
    ...user
    posts(
      filter: $postFilter
      orderBy: $postOrderBy
      limit: $postLimit
      offset: $postOffset
    ) {
      ...post
    }
    postsCount(filter: $postFilter)
  }
}

query FindUniquePost(
  $filter: PostUniqueFilter!
  $categoryFilter: CategoryFilter
  $categoryOrderBy: [CategoryOrderBy!]
  $categoryLimit: Int
  $categoryOffset: Int
) {
  findUniquePost(filter: $filter) {
    ...post
    author {
      ...user
    }
    categories(
      filter: $categoryFilter
      orderBy: $categoryOrderBy
      limit: $categoryLimit
      offset: $categoryOffset
    ) {
      ...category
    }
    categoriesCount(filter: $categoryFilter)
  }
}

query FindUniqueCategory(
  $filter: CategoryUniqueFilter!
  $postFilter: PostFilter
  $postOrderBy: [PostOrderBy!]
  $postLimit: Int
  $postOffset: Int
) {
  findUniqueCategory(filter: $filter) {
    ...category
    posts(
      filter: $postFilter
      orderBy: $postOrderBy
      limit: $postLimit
      offset: $postOffset
    ) {
      ...post
    }
    postsCount(filter: $postFilter)
  }
}

query FindFirstUser(
  $filter: UserFilter
  $orderBy: [UserOrderBy!]
  $postFilter: PostFilter
  $postOrderBy: [PostOrderBy!]
  $postLimit: Int
  $postOffset: Int
) {
  findFirstUser(filter: $filter, orderBy: $orderBy) {
    ...user
    posts(
      filter: $postFilter
      orderBy: $postOrderBy
      limit: $postLimit
      offset: $postOffset
    ) {
      ...post
    }
    postsCount(filter: $postFilter)
  }
}

query FindFirstPost(
  $filter: PostFilter
  $orderBy: [PostOrderBy!]
  $categoryFilter: CategoryFilter
  $categoryOrderBy: [CategoryOrderBy!]
  $categoryLimit: Int
  $categoryOffset: Int
) {
  findFirstPost(filter: $filter, orderBy: $orderBy) {
    ...post
    author {
      ...user
    }
    categories(
      filter: $categoryFilter
      orderBy: $categoryOrderBy
      limit: $categoryLimit
      offset: $categoryOffset
    ) {
      ...category
    }
    categoriesCount(filter: $categoryFilter)
  }
}

query FindFirstCategory(
  $filter: CategoryFilter
  $orderBy: [CategoryOrderBy!]
  $postFilter: PostFilter
  $postOrderBy: [PostOrderBy!]
  $postLimit: Int
  $postOffset: Int
) {
  findFirstCategory(filter: $filter, orderBy: $orderBy) {
    ...category
    posts(
      filter: $postFilter
      orderBy: $postOrderBy
      limit: $postLimit
      offset: $postOffset
    ) {
      ...post
    }
    postsCount(filter: $postFilter)
  }
}

query FindManyUser(
  $filter: UserFilter
  $orderBy: [UserOrderBy!]
  $limit: Int
  $offset: Int
  $postFilter: PostFilter
  $postOrderBy: [PostOrderBy!]
  $postLimit: Int
  $postOffset: Int
) {
  findManyUser(
    filter: $filter
    orderBy: $orderBy
    limit: $limit
    offset: $offset
  ) {
    ...user
    posts(
      filter: $postFilter
      orderBy: $postOrderBy
      limit: $postLimit
      offset: $postOffset
    ) {
      ...post
    }
    postsCount(filter: $postFilter)
  }
}

query FindManyPost(
  $filter: PostFilter
  $limit: Int
  $offset: Int
  $orderBy: [PostOrderBy!]
  $categoryFilter: CategoryFilter
  $categoryOrderBy: [CategoryOrderBy!]
  $categoryLimit: Int
  $categoryOffset: Int
) {
  findManyPost(
    filter: $filter
    orderBy: $orderBy
    limit: $limit
    offset: $offset
  ) {
    ...post
    author {
      ...user
    }
    categories(
      filter: $categoryFilter
      orderBy: $categoryOrderBy
      limit: $categoryLimit
      offset: $categoryOffset
    ) {
      ...category
    }
    categoriesCount(filter: $categoryFilter)
  }
}

query FindManyCategory(
  $filter: CategoryFilter
  $orderBy: [CategoryOrderBy!]
  $limit: Int
  $offset: Int
  $postFilter: PostFilter
  $postOrderBy: [PostOrderBy!]
  $postLimit: Int
  $postOffset: Int
) {
  findManyCategory(
    filter: $filter
    orderBy: $orderBy
    limit: $limit
    offset: $offset
  ) {
    ...category
    posts(
      filter: $postFilter
      orderBy: $postOrderBy
      limit: $postLimit
      offset: $postOffset
    ) {
      ...post
    }
    postsCount(filter: $postFilter)
  }
}

mutation CreateOneUser($input: UserCreateInput!) {
  createOneUser(input: $input) {
    ...user
  }
}

mutation CreateOnePost($input: PostCreateInput!) {
  createOnePost(input: $input) {
    ...post
  }
}

mutation CreateOneCategory($input: CategoryCreateInput!) {
  createOneCategory(input: $input) {
    ...category
  }
}

mutation CreateManyUser($input: [UserCreateInput!]!) {
  createManyUser(input: $input)
}

mutation CreateManyPost($input: [PostCreateInput!]!) {
  createManyPost(input: $input)
}

mutation CreateManyCategory($input: [CategoryCreateInput!]!) {
  createManyCategory(input: $input)
}

mutation UpdateOneUser($where: UserUniqueFilter!, $data: UserUpdateInput!) {
  updateOneUser(where: $where, data: $data) {
    ...user
  }
}

mutation UpdateOnePost($where: PostUniqueFilter!, $data: PostUpdateInput!) {
  updateOnePost(where: $where, data: $data) {
    ...post
  }
}

mutation UpdateOneCategory(
  $where: CategoryUniqueFilter!
  $data: CategoryUpdateInput!
) {
  updateOneCategory(where: $where, data: $data) {
    ...category
  }
}

mutation UpdateManyUser($where: UserFilter!, $data: UserUpdateInput!) {
  updateManyUser(where: $where, data: $data)
}

mutation UpdateManyPost($where: PostFilter!, $data: PostUpdateInput!) {
  updateManyPost(where: $where, data: $data)
}

mutation UpdateManyCategory(
  $where: CategoryFilter!
  $data: CategoryUpdateInput!
) {
  updateManyCategory(where: $where, data: $data)
}

mutation DeleteOneUser($where: UserUniqueFilter!) {
  deleteOneUser(where: $where) {
    ...user
  }
}

mutation DeleteOnePost($where: PostUniqueFilter!) {
  deleteOnePost(where: $where) {
    ...post
  }
}

mutation DeleteOneCategory($where: CategoryUniqueFilter!) {
  deleteOneCategory(where: $where) {
    ...category
  }
}

mutation DeleteManyUser($where: UserFilter!) {
  deleteManyUser(where: $where)
}

mutation DeleteManyPost($where: PostFilter!) {
  deleteManyPost(where: $where)
}

mutation DeleteManyCategory($where: CategoryFilter!) {
  deleteManyCategory(where: $where)
}
```

# 使い方詳細

## 権限制御

初期状態だと Query から Mutation まで全て動いてしまいます。このままでは使い物になりません。
とりあえず Mutation にアクセス制御をかけてみます。

まずは Builder に authority 設定を追加し、権限を返す機能を追加します。

```ts
import SchemaBuilder from "@pothos/core";
import PrismaPlugin from "@pothos/plugin-prisma";
import PrismaUtils from "@pothos/plugin-prisma-utils";
import PothosPrismaGenerator from "pothos-prisma-generator";
import { Context, prisma } from "./context";

/**
 * Create a new schema builder instance
 */
export const builder = new SchemaBuilder<{
  Context: Context;
}>({
  plugins: [PrismaPlugin, PrismaUtils, PothosPrismaGenerator, ScopeAuthPlugin],
  prisma: {
    client: prisma,
  },
  pothosPrismaGenerator: {
    // Set the following permissions
    /// @pothos-generator any {authority:["ROLE"]}
    authority: ({ context }) => context.user?.roles ?? [],
  },
});
```

USER 権限をもったユーザのみ mutation 系の命令を使えるようにするため、
`/// @pothos-generator executable {include:["mutation"],authority:["USER"]}`
を Prisma の各モデルに設定し、`prisma generate`を実行します。

```prisma
generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}

/// @pothos-generator executable {include:["mutation"],authority:["USER"]}
model User {
  id        String   @id @default(uuid())
  email     String   @unique
  name      String   @default("User")
  posts     Post[]
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt
}

/// @pothos-generator executable {include:["mutation"],authority:["USER"]}
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

これで createOneUser などを実行する際は、認証を通していないと動作しなくなります。

## 書き込みデータに介入

例えば Post に書き込んだユーザを Prisma 側のデータに与えたい場合、以下のように書きます。

```ts
export const builder = new SchemaBuilder<{
  Context: Context;
}>({
  plugins: [PrismaPlugin, PrismaUtils, PothosPrismaGenerator],
  prisma: {
    client: prisma,
  },
  pothosPrismaGenerator: {
    // Replace the following directives
    // /// @pothos-generator input {data:{author:{connect:{id:"%%USER%%"}}}}
    replace: { "%%USER%%": ({ context }) => context.user?.id },
  },
});
```

```prisma
/// @pothos-generator input-data {data:{author:{connect:{id:"%%USER%%"}}}}
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
```

これで書き込んだ人のユーザ情報が author に入ります。

## 権限による出力データの制御

認証されていないユーザには published:false のデータを見せたくない場合、以下のように書きます。

```ts
export const builder = new SchemaBuilder<{
  Context: Context;
}>({
  plugins: [PrismaPlugin, PrismaUtils, PothosPrismaGenerator],
  prisma: {
    client: prisma,
  },
  pothosPrismaGenerator: {
    authority: ({ context }) => context.user?.roles ?? [],
  },
});
```

```prisma
/// @pothos-generator where {include:["query"],where:{},authority:["USER"]}
/// @pothos-generator where {include:["query"],where:{published:true}}
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
```

where に介入して、権限によって出力条件を変えています。これで見せたくないデータを隠すことが出来ます。

# まとめ

このパッケージは、Prisma を使って GraphQL の API を簡単に作成できるようにするものです。主な機能は以下のとおりです。

- Prisma のスキーマに基づいて、CRUD 操作やフィルタリング、ページネーションなどのリゾルバを自動生成します。
- リレーションやネストされたオブジェクトに対応した入力型や出力型を自動生成します。
- 認証や認可などのカスタムロジックを追加するための Builder パターンを提供します。

詳細な使い方や設定方法は、パッケージの README をご覧ください。このパッケージは、Prisma のスキーマがファーストになるというコンセプトで作られています。つまり、GraphQL のスキーマではなく、Prisma のスキーマに従って API が生成されます。また、実行時にリゾルバや型を動的に生成するため、コードの出力はありません。

このように、人間が書くコードを最小限にすることで、バグを減らすことができます。もちろん、ジェネレータ自体にバグがある場合は別ですが。

以上が、このパッケージの概要です。GraphQL と Prisma を使って API 開発をしたいけれど、バックエンド側を楽に書きたいという場合に活用できます。
