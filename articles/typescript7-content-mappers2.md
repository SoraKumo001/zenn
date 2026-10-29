---
title: "TypeScript 7.1 の新機能 Content Mappers で実現する新時代、脱 Codegenの 開発体験"
emoji: "🚀"
type: "tech"
topics: ["typescript", "graphql", "nextjs", "vite", "react"]
published: true
---

# はじめに

TypeScript 7.1 で導入された新機能、Content Mappers（コンテンツマッパー）。
前回の記事では、Next.js プロジェクト内で Content Mapper を自作し、`.graphql` ファイルを直接インポートして型を付ける実験を紹介しました。

https://zenn.dev/sorakumo001/articles/typescript7-content-mappers

前回のプロトタイプ実装でも「物理ファイルを生成せずに `.graphql` をインポートする」という目的自体は達成できていましたが、実用にあたってはいくつか課題が残っていました。

1. プロジェクトごとに Content Mapper を自作・管理する必要がある
2. 内部で `@graphql-codegen/cli` を呼び出していたため依存パッケージが 170 個を超え、初回起動や変換が重い
3. 重複する型定義の正規表現による除去や、標準出力（`stdout`）のミュートなど、不安定なワークアラウンドが多かった
4. ランタイム側で `graphql-tag/loader`（CommonJS 出力）と正規表現の Enum 抽出に頼っていたため、Vite などのネイティブ ESM バンドラで扱いづらかった
5. スキーマパスやスカラー設定がハードコードされていた

そこで今回、これらの課題を解消し、パッケージを追加するだけで使える汎用ライブラリ `graphql-content-mapper` を作って npm に公開しました。

https://www.npmjs.com/package/graphql-content-mapper
https://github.com/SoraKumo001/graphql-content-mapper

このライブラリでは `@graphql-codegen` や `graphql-tag` への依存を撤廃し、`graphql` 標準の AST 解析のみで「仮想 TypeScript 型定義の生成」と「純粋な ES Modules コードへの変換」を行っています。

本記事では、TypeScript 7.1 の Content Mappers の仕組みのおさらいから、`graphql-content-mapper` の導入方法、脱 Codegen を実現した内部アーキテクチャ、そして Next.js 本番ビルド時の注意点までを紹介します。

---

# 1. TypeScript 7.1 Content Mappers とは？

Content Mappers は、TypeScript コンパイラ（`tsc`）や Language Server（LSP）が未知の拡張子（`.graphql`, `.sql`, `.css` など）のインポートに遭遇した際、指定された外部プロセス（JSON-RPC 2.0 over stdio）を呼び出し、メモリ上で仮想の TypeScript コードを受け取って型解決を行う仕組みです。

```
[クライアントコード (.tsx)]
       │ import { FindBooks, OrderBy } from "./query.graphql"
       ├───► [TypeScript 7.1 コンパイラ / LSP]
       │         │ 未知の拡張子 .graphql を検出
       │         │ JSON-RPC 2.0 (stdio) で openProject / transform を送信
       │         ▼
       │     [graphql-content-mapper (型解決エンジン)]
       │         │ schema.graphql と query.graphql を AST 解析
       │         └─► メモリ上で仮想の TypeScript 型定義を返却
       │
       └───► [バンドラ (Next.js / Vite / Webpack)]
                 │
                 ▼
             [graphql-content-mapper (ランタイム変換)]
                 └─► AST から純粋な ES Modules (export const ...) を出力
```

### 従来の手法との比較

| 項目 | アンビエント宣言 (`*.d.ts`) | 従来の `graphql-codegen` | TypeScript 7.1 Content Mapper |
| :--- | :--- | :--- | :--- |
| 型の精度 | `any` や固定型のみ（クエリ内容と連動しない） | 完全型安全（クエリ個別） | 完全型安全（クエリ個別） |
| ファイル生成 | なし | `src/generated/...` の出力が必須 | 不要（ディスク書き込みゼロ） |
| watch プロセス | 不要 | codegen の常駐プロセスが必須 | 不要（LSP / tsc がオンデマンド実行） |
| Git のコミット差分 | 影響なし | 自動生成ファイルで差分が肥大化 | 影響なし（生成ファイルゼロ） |

物理ファイルが一切生成されないため、Git リポジトリが自動生成コードで汚れることがなく、ブランチ切り替えやスキーマ変更のたびに codegen コマンドを叩き直す手間もなくなります。

:::message alert
Content Mappers は外部プロセスを起動してコード変換を行うため、セキュリティ機構として CLI 実行時には `--runExternalCode` フラグ、VS Code 上では `"js/ts.contentMappers.enabled": true` の明示的な許可が必須となっています。
:::

---

# 2. `graphql-content-mapper` の導入手順

前回のように自前でマッパーやローダーを書く必要はありません。必要なパッケージは `graphql-content-mapper` と `graphql` の 2 つだけです。

### 1. インストール

```bash
# pnpm
pnpm add -D graphql-content-mapper graphql

# npm
npm install -D graphql-content-mapper graphql
```

### 2. `tsconfig.json` の設定（一元管理）

TypeScript 7.1 の `contentMappers` フィールドを設定します。
TypeScript 7.1 では `contentMappers` の各エントリに任意の `options` を記述でき、JSON-RPC の `openProject` リクエスト時にマッパーへ渡されます。

```jsonc:tsconfig.json
{
  "compilerOptions": {
    "moduleResolution": "bundler",
    "strict": true
    // その他の compilerOptions
  },
  "contentMappers": [
    {
      "package": "graphql-content-mapper",
      "extensions": [".graphql", ".gql"],
      "options": {
        "schema": "./graphql/schema.graphql",
        "scalars": {
          "DateTime": "string",
          "JSON": "Record<string, unknown>"
        },
        "skipTypename": false
      }
    }
  ],
  "include": [
    "src/**/*",
    "graphql/**/*.graphql"
  ]
}
```

:::message
`graphql-content-mapper` のバンドラ用プラグイン（Next.js / Vite / Webpack）も、この `tsconfig.json` の `contentMappers[].options` を自動的に読み取ります。そのため、型解決とバンドラの設定を `tsconfig.json` 1箇所に集約できます（環境変数 `GRAPHQL_SCHEMA_PATH` や `.graphqlrc`、プラグイン引数での個別上書きにも対応しています）。
:::

### 3. バンドラの設定

#### Next.js (App Router / Pages Router, Turbopack & Webpack 対応)
`next.config.js` を `graphql-content-mapper/next` でラップするだけで、Turbopack と Webpack の両方のローダー設定が自動構成されます。

```js:next.config.js
const withGraphQL = require("graphql-content-mapper/next");

/** @type {import('next').NextConfig} */
const nextConfig = {
  typescript: {
    // Next.js 内蔵の型チェックは '--runExternalCode' を渡せないためスキップし、
    // ビルドスクリプト側で 'tsc --runExternalCode --noEmit' を実行する（詳細は第6章）
    ignoreBuildErrors: true,
  },
};

module.exports = withGraphQL(nextConfig);
```

#### Vite の場合
`vite.config.ts` に `graphql-content-mapper/vite` プラグインを追加します。`schema.graphql` の変更監視（HMR）も自動で行われます。

```ts:vite.config.ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import graphql from "graphql-content-mapper/vite";

export default defineConfig({
  plugins: [
    react(),
    graphql(),
  ],
});
```

### 4. VS Code の設定

TypeScript 7.1 は Go 製ネイティブバイナリおよび新 LSP アーキテクチャへ移行しているため、VS Code で動かすには以下の設定を行います。

1. Microsoft 公式プレビュー拡張機能 [TypeScript 7](https://marketplace.visualstudio.com/items?itemName=TypeScriptTeam.native-preview)（`TypeScriptTeam.native-preview`）をインストール
2. `.vscode/settings.json` に以下を追加：
   ```json:.vscode/settings.json
   {
     "js/ts.tsdk.path": "node_modules/typescript",
     "js/ts.tsdk.additionalLocations": [
       "node_modules/typescript"
     ],
     "js/ts.contentMappers.enabled": true
   }
   ```
3. ステータスバーの `TypeScript Language Server` から `Use Custom Version` (7.1.0-beta - node_modules/typescript) を選択


この設定後はVSCodeが状態を認識して、FindManyCategoryにカーソルを合わせた場合に、以下のように完全に型情報が取れた状態になります。

```ts
import {
  CountPost,
  CreateOnePost,
  DeleteOnePost,
  FindManyCategory,
  FindManyPost,
  OrderBy,
} from "../../graphql/query.graphql";
```

![](/images/typescript7-content-mappers2/2026-10-29-10-25-43.png)

---

# 3. 実際の開発体験

以下のように、Fragment や Enum を使用した `.graphql` ファイルを用意します。

```graphql:graphql/query.graphql
fragment BookFields on Book {
  id
  title
  createdAt
}

query FindBooks($order: OrderBy) {
  books(orderBy: $order) {
    ...BookFields
  }
}

mutation CreateBook($title: String!) {
  createBook(title: $title) {
    ...BookFields
  }
}
```

あとは `.tsx` / `.ts` ファイルから、`.graphql` ファイルを直接 Named Import するだけです。

```tsx:src/app/BookList.tsx
"use client";

import { useQuery, useMutation } from "urql";
import {
  FindBooks,      // TypedDocumentNode<FindBooksQuery, FindBooksQueryVariables>
  CreateBook,     // TypedDocumentNode<CreateBookMutation, CreateBookMutationVariables>
  OrderBy,        // Enum (値 { Asc: "Asc", Desc: "Desc" } としても型としても利用可能)
} from "../graphql/query.graphql";

export function BookList() {
  const [{ data, fetching }] = useQuery({
    query: FindBooks,
    variables: {
      order: OrderBy.Asc, // variables も完全型安全
    },
  });

  const [, createBook] = useMutation(CreateBook);

  if (fetching) return <div>Loading...</div>;

  return (
    <ul>
      {data?.books.map((b) => (
        <li key={b.id}>{b.title}</li>
      ))}
    </ul>
  );
}
```

`.graphql` ファイルを編集して保存すると、watch プロセスを介さずにその場で型定義が更新され、存在しないフィールドの参照や変数型の不一致があれば即座にエディタおよび `tsc --runExternalCode --noEmit` で検出されます。

---

# 4. アーキテクチャ刷新：なぜ `@graphql-codegen` と `graphql-tag` を捨てたのか？

前回のプロトタイプからライブラリ化するにあたり、内部設計をゼロから作り直しました。

### 1. 型生成の脱 `@graphql-codegen` 化（Pure AST 型ジェネレータ）
前回は JSON-RPC サーバー内部で `@graphql-codegen/cli` の `executeCodegen` を呼び出していましたが、これには大きな問題がありました。

- 依存ツリーが巨大: `@graphql-codegen/cli` とプラグイン群を入れるだけで 170 個以上の依存パッケージが追加される
- 起動と変換のオーバーヘッド: 動的インポートやファイルローダーの初期化に数百ミリ秒を要する
- 不安定なワークアラウンド: 重複宣言を削る正規表現ハックや、Codegen のコンソール出力で JSON-RPC の stdio ストリームが破損するのを防ぐ `process.stdout.write` のミュート処理が必要だった

そもそも Content Mapper が返すべき仮想 TypeScript コードは、以下の要素だけです。

1. ベース型: `TypedDocumentNode`, `Maybe`, `InputMaybe`, `Exact`
2. スカラー型 (`Scalars`): 組み込みスカラーと `options.scalars` のマッピング
3. Enum 型: スキーマの `EnumTypeDefinition` から生成（`enumsAsTypes` オプションにも対応）
4. Input オブジェクト型: スキーマの `InputObjectTypeDefinition` から再帰的に生成
5. Operation / Fragment の型: スキーマの `Query` / `Mutation` / `Subscription` や型定義をインデックス化し、クエリの `selectionSet`（ネストしたフィールド、`...fragmentSpread`、`... on InlineFragment`、Union / Interface）を走査してレスポンス型と `Variables` 型を合成

これらはすべて、`graphql` パッケージ標準の `parse()` による AST 走査だけで完結します。
さらに、`schema.graphql` のパース結果をファイルの更新日時（`mtimeMs`）でインメモリキャッシュすることで、2回目以降の `transform` リクエストは 1ms 未満で応答できるようになりました。

### 2. ランタイム変換の脱 `graphql-tag` ＆ Pure ESM 化
前回はバンドラ側のローダーに `graphql-tag/loader` を使い、さらに正規表現（`/enum\s+(\w+)\s*\{([^}]+)\}/g`）でスキーマから Enum を抜き出して `module.exports` に継ぎ足していました。
しかし、`module.exports` 形式は Vite（Rollup）の ES Modules バンドルや Tree-shaking と相性が悪く、正規表現による Enum 抽出もコメントやディレクティブで壊れるリスクがありました。

新しい `compiler.ts` では、ランタイム側も `graphql` の `parse({ noLocation: true })` で AST 解析を行い、以下の純粋な ES Modules コードを直接生成します。

- 各 Operation が参照している Fragment（多段ネストした Fragment を含む）を依存グラフ探索で自動収集し、自己完結した `DocumentNode` として `export const FindBooks = { ... };` を出力
- 各 Fragment 単体も `export const BookFields = { ... };` として出力
- スキーマの `EnumTypeDefinition` から抽出した Enum も `export const OrderBy = { ... };` として出力

これにより、Next.js（Turbopack / Webpack）と Vite の双方で、不要なクエリがバンドルから除外される Tree-shaking が効くようになりました。

---

# 5. URQL 以外のクライアントでも使えるのか？

あらゆる GraphQL クライアントでそのまま使えます。

`graphql-content-mapper` が出力する型は、GraphQL エコシステムの事実上の標準規格である `TypedDocumentNode<Result, Variables>` に準拠しています。

```ts
export interface TypedDocumentNode<
  Result = { [key: string]: any },
  Variables = { [key: string]: any },
> extends DocumentNode {
  __apiType?: (variables: Variables) => Result;
}
```

特定のクライアントライブラリに依存するコードは一切含まれていないため、以下のような主要なライブラリすべてで自動型推論が機能します。

### Apollo Client (`@apollo/client`)
```tsx
import { useQuery, useMutation } from "@apollo/client";
import { FindBooks, CreateBook, OrderBy } from "./query.graphql";

export function BookList() {
  const { data, loading } = useQuery(FindBooks, {
    variables: { order: OrderBy.Asc },
  });

  const [createBook] = useMutation(CreateBook);

  if (loading) return <div>Loading...</div>;
  return <div>{data?.books.map((b) => b.title)}</div>;
}
```

### graphql-request (Next.js Server Components / Node.js)
```ts
import { request } from "graphql-request";
import { FindBooks, OrderBy } from "./query.graphql";

// data は自動的に FindBooksQuery 型として推論される
const data = await request("https://example.com/graphql", FindBooks, {
  order: OrderBy.Asc,
});
```

### TanStack Query (React Query) + graphql-request
```tsx
import { useQuery } from "@tanstack/react-query";
import { request } from "graphql-request";
import { FindBooks, OrderBy } from "./query.graphql";

export function useBooks() {
  return useQuery({
    queryKey: ["books", OrderBy.Asc],
    queryFn: () =>
      request("/api/graphql", FindBooks, {
        order: OrderBy.Asc,
      }),
  });
}
```

### ネイティブ `fetch` (Server Actions / Route Handlers)
クライアントライブラリを使わず、生成された型（`FindBooksQuery`, `FindBooksQueryVariables`）と `graphql` の `print()` を組み合わせて標準の `fetch` で呼び出すことも可能です。

```ts
import { print } from "graphql";
import {
  FindBooks,
  type FindBooksQuery,
  type FindBooksQueryVariables,
  OrderBy,
} from "./query.graphql";

const variables: FindBooksQueryVariables = { order: OrderBy.Asc };

const res = await fetch("https://example.com/graphql", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    query: print(FindBooks),
    variables,
  }),
});

const { data } = (await res.json()) as { data: FindBooksQuery };
```

---

# 6. 実践ノウハウ：Next.js 本番ビルド時の `TS18068` エラーと対処法

Next.js で `next build` を実行する際、必ず押さえておくべきポイントがあります。

### 発生する事象
`next.config.js` に何も設定せずに `next build` を実行すると、ビルド内の TypeScript チェック工程で以下のエラーが発生します。

```text
tsconfig.json(27,3): error TS18068: Content mappers require the '--runExternalCode' command line flag to be enabled.
src/app/Home.tsx(12,8): error TS2307: Cannot find module '../../graphql/query.graphql' or its corresponding type declarations.
Failed to type check.
```

### なぜ起きるのか？
前述の通り、TypeScript 7.1 の Content Mappers はセキュリティ保護のため `--runExternalCode` フラグが指定されたときのみ外部プロセスを起動します。
しかし、現行の `next build` が内部で実行する型チェッカーは、Next.js が直接 TypeScript Compiler API を呼び出しており、この `--runExternalCode` に相当するオプションをまだ渡していません。結果として Content Mapper の起動がブロックされ、`.graphql` モジュールが解決できずにエラーとなります。

### 解決策：型安全性を維持したビルド構成
以下の 2 つを組み合わせるのが確実です。

1. `next.config.js` で Next.js 内蔵の（`--runExternalCode` 非対応な）型チェックをスキップする：
   ```js:next.config.js
   const withGraphQL = require("graphql-content-mapper/next");

   module.exports = withGraphQL({
     typescript: {
       ignoreBuildErrors: true,
     },
   });
   ```

2. `package.json` の `build` スクリプトで、`next build` の直前に `tsc --runExternalCode --noEmit` を明示的に実行する：
   ```json:package.json
   {
     "scripts": {
       "typecheck": "tsc --runExternalCode --noEmit",
       "build": "npm run typecheck && next build"
     }
   }
   ```

これにより、型エラーがある場合は前段の `npm run typecheck` で確実にビルドが止まり、型チェックを通過したコードのみが `next build` へ進むため、型安全性を損なうことなく本番ビルドを行えます。

---

# おわりに

TypeScript 7.1 の Content Mappers は、「巨大なコード生成ツールを常駐させるか、型安全性を諦めるか」というこれまでのジレンマを解消する仕組みです。

今回公開した `graphql-content-mapper` を使えば、`graphql-codegen` の設定ファイルや生成コードに悩まされることなく、`.graphql` ファイルを TypeScript のファーストクラスなモジュールとしてそのままインポートできます。

前回の記事で紹介したサンプルリポジトリ（Next.js 16 + Pothos + Prisma + Urql）も、すでに npm 版の `graphql-content-mapper` を使う構成にアップデート済みです。ぜひ手元で動かして、その軽快さを試してみてください。

- npm パッケージ: [graphql-content-mapper](https://www.npmjs.com/package/graphql-content-mapper)
- ライブラリ (GitHub): [SoraKumo001/graphql-content-mapper](https://github.com/SoraKumo001/graphql-content-mapper)
- Next.js サンプル (GitHub): [SoraKumo001/next-graphql](https://github.com/SoraKumo001/next-graphql)
