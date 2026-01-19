---
title: "Drizzle ORM から PostgreSQL を使用する際に、環境変数からschemaを切り替える"
emoji: "📑"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [drizzle, prisma, postgresql, orm, database]
published: false
---

# PostgreSQL の schema 切り替え

PostgreSQL は DB 上に schema を作成して、テーブルをその配下に配置できます。デフォルトでは public という名前がついていますが、これを新しく作ることによってひとつの DB に複数の同名のテーブルを作ることが可能になります。

PostgreSQL でスキーマを指定は、テーブル名の前にスキーマ名を装飾するか、search_path にスキーマ名を設定することで行います。これが Prisma の Rust ネイティブのドライバだと、接続名のパラメータとして`?schema=xxxx`を付けることによって切り替えられます。これはあくまで Prisma の糖衣構文なので、その他の環境では動作しません。しかしこの機能が PostgreSQL の標準機能と誤解しており、この機能が動作しないと Issues に書き込んでいる人を見かけます。

今回は`?schema=xxxx`の機能を Drizzle から使えるように実装する方法を紹介します。drizzle-kit の対応がなされていない部分は、自分でコマンドを実装します。

## Schema Example

このプロジェクトは、**Drizzle ORM** と **PostgreSQL** を使用して、データベースのスキーマを `?schema=xxxxxx` で切り替えるサンプルです。

https://github.com/SoraKumo001/drizzle-pg-schema

## サンプル用データベーススキーマ

以下のモデル（テーブル）が定義されています（`src/db/schema.ts`）:

- **User**: ユーザー情報（ID, Email, Name, Roles）
- **Post**: 投稿記事（ID, Title, Content, Published, Author）
- **Category**: カテゴリー (ID, Name)
- **PostToCategory**: 投稿とカテゴリーの多対多リレーション

## セットアップ手順

### 1. 依存関係のインストール

```bash
pnpm install
```

### 2. 環境変数の設定

プロジェクトルートの `.env` ファイル内にある schema オプションを参照してスキーマを切り替えます。そもそものところで schema パラメータは Prisma の PostgreSQL の Rust エンジンで用いられる糖衣構文なので、他の ORM や DB ドライバなどではサポートされていません。これを Drizzle でサポート可能にするというのが今回の内容です。

```env
DATABASE_URL=postgres://postgres:password@localhost:5432/postgres?schema=xxxxxx
```

### 3. データベースの起動

Docker を使用して PostgreSQL コンテナを起動します。

```bash
pnpm run docker
```

### 4. マイグレーションとシーディング

データベーススキーマを適用し、初期データを投入します。

```bash
# マイグレーションの生成（スキーマ変更時）
pnpm run generate

# マイグレーションの実行（DBへの適用）
pnpm run migrate

# 初期データの投入
pnpm run seed
```

もしくは、以下のコマンドでデータベースをリセットして再構築できます。

```bash
pnpm run reset
```

## 実行

メインスクリプトを実行して、データベースからデータを取得しコンソールに表示します。

```bash
pnpm run dev
```

## 利用可能なスクリプト

`package.json` に定義されている主なコマンドです：

- `pnpm run dev`: アプリケーションのエントリーポイント (`src/index.ts`) を実行します。
- `pnpm run docker`: Docker Compose を使って PostgreSQL をバックグラウンドで起動します。
- `pnpm run generate`: Drizzle Kit を使用してスキーマ変更からマイグレーションファイルを生成します。
- `pnpm run migrate`: マイグレーションをデータベースに適用します。
- `pnpm run seed`: テストデータをデータベースに投入します。
- `pnpm run reset`: データベースをリセットし、マイグレーションを再適用します。

## プロジェクト構造

- `src/db/schema.ts`: Drizzle ORM のスキーマ定義
- `src/db/relations.ts`: リレーション定義（もし存在すれば）
- `src/index.ts`: サンプル実行コード
- `drizzle/`: マイグレーションファイルとスナップショット
- `tools/`: マイグレーションやシード用のユーティリティスクリプト
- `docker/`: Docker Compose 設定ファイル

## スキーマ切り替えの仕組み (`search_path`)

このプロジェクトでは、接続先の PostgreSQL スキーマ（`search_path`）を環境変数 `DATABASE_URL` のクエリパラメータで動的に切り替える仕組みを実装しています。これにより、同じデータベースインスタンス内で開発環境、テスト環境などを容易に分離できます。

### 1. 設定の読み込み (`drizzle.config.ts`)

`drizzle.config.ts` は `DATABASE_URL` を解析し、`?schema=xxx` パラメータが存在する場合はその値を、存在しない場合はデフォルトの `public` をスキーマとして採用します。そして`migrations.schema`にスキーマ名を指定します。

しかし`migrations.schema`を指定しても`migrate`の管理用テーブルの場所が指定できるだけで、肝心のテーブル自体は`public`に作られてしまいます。これに対する対処は、後述する自作`migrate`コマンドで対処します。

```typescript
// drizzle.config.ts
const url = new URL(connectionString);
const searchPath = url.searchParams.get("schema") ?? "public";

export default defineConfig({
  // ...
  migrations: {
    schema: searchPath, // マイグレーション対象のスキーマを指定
  },
});
```

### 2. ツール側の制御 (`tools/`)

`tools/` ディレクトリ内のスクリプト（`migrate.ts`, `seed.ts`, `reset.ts`）は、この `drizzle.config.ts` の設定を読み込んで動作します。

各ツールは、DB 接続時に `options: "--search_path=..."` を指定して、セッションのデフォルトスキーマを固定しています。これにより、その後のクエリがすべて指定されたスキーマに対して実行されます。

```typescript
// tools/migrate.ts 等の共通ロジック
const searchPath = config.migrations?.schema ?? "public";

const db = drizzle({
  connection: {
    connectionString: config.dbCredentials.url,
    // セッションレベルで search_path を設定
    options: `--search_path=${searchPath}`,
  },
});
```

#### 各ツールの詳細挙動

##### **`tools/migrate.ts`**:

`drizzle-orm/node-postgres/migrator` の `migrate` 関数を使用する際、`migrationsSchema` オプションに `search_path` を渡します。これにより、マイグレーション管理テーブル（`__drizzle_migrations`）や作成されるテーブルが正しいスキーマに配置されます。

`drizzle-kit`の CLI を使わずスクリプトを実装しているのは、CLI コマンドにスキーマを切り替えるパラメータを載せることが出来ないからです。マイグレーションをユーザースクリプトとして実装することによって、スキーマの切り替えが実現できます。

```ts
import config from "../drizzle.config";
import { drizzle } from "drizzle-orm/node-postgres";
import { migrate } from "drizzle-orm/node-postgres/migrator";

const main = async () => {
  if (config.dialect !== "postgresql")
    throw new Error("Only postgresql is supported");
  if (!("dbCredentials" in config) || !("url" in config.dbCredentials)) {
    throw new Error(
      "dbCredentials in drizzle.config.ts must have a 'url' property."
    );
  }
  const searchPath = config.migrations?.schema ?? "public";

  const db = drizzle({
    connection: {
      connectionString: config.dbCredentials.url,
      options: `--search_path=${searchPath}`,
    },
  });
  if (!config.out) throw new Error("out is not set");
  await migrate(db, {
    migrationsFolder: config.out,
    migrationsSchema: searchPath,
  });
  db.$client.end();
};

main();
```

##### **`tools/reset.ts`**:

データベース全体を初期化するため、指定されたスキーマ自体を `DROP SCHEMA ... CASCADE` コマンドで削除します。これにより、テーブルだけでなくスキーマごとクリーンアップされます。

`drizzle-kit`の CLI に欠けている機能です。

```ts
import config from "../drizzle.config";
import { drizzle } from "drizzle-orm/node-postgres";

const main = async () => {
  if (config.dialect !== "postgresql")
    throw new Error("Only postgresql is supported");
  if (!("dbCredentials" in config) || !("url" in config.dbCredentials)) {
    throw new Error(
      "dbCredentials in drizzle.config.ts must have a 'url' property."
    );
  }
  const searchPath = config.migrations?.schema ?? "public";
  const db = drizzle({
    connection: {
      connectionString: config.dbCredentials.url,
      options: `--search_path=${searchPath}`,
    },
  });
  // 対象スキーマの削除
  await db.execute(`drop schema ${searchPath} cascade`).catch(() => {});
  db.$client.end();
};

main();
```

##### **`tools/seed.ts`**:

データの投入前に既存データをクリアします。`drizzle-seed` の標準機能ではスキーマ指定時の挙動がプロジェクトの要件と合わない場合があるため、明示的に `TRUNCATE TABLE ... CASCADE` を発行してテーブルを空にしてから、`seed` 関数でデータを投入しています。

`drizzle-seed`の`reset`は使用せずに、テーブル内容のクリアを行っています。`drizzle-seed`の`reset`は、スキーマ名が設定されていない場合、勝手にテーブル名に`public`のスキーマ名を付け加えたうえで`truncate`意味不明な仕様になっており実用不能でした。

```ts
import config from "../drizzle.config";
import { drizzle } from "drizzle-orm/node-postgres";
import { seed } from "drizzle-seed";
import path from "path";
import { pathToFileURL } from "node:url";
import { sql } from "drizzle-orm";
import { getTableConfig, type PgTable } from "drizzle-orm/pg-core";
import { isTable } from "drizzle-orm";

const main = async () => {
  if (config.dialect !== "postgresql")
    throw new Error("Only postgresql is supported");
  if (!("dbCredentials" in config) || !("url" in config.dbCredentials)) {
    throw new Error(
      "dbCredentials in drizzle.config.ts must have a 'url' property."
    );
  }
  const searchPath = config.migrations?.schema ?? "public";

  const db = drizzle({
    connection: {
      connectionString: config.dbCredentials.url,
      options: `--search_path=${searchPath}`,
    },
  });
  if (!config.schema) throw new Error("schema is not set");
  const schema = await Promise.all(
    (Array.isArray(config.schema) ? config.schema : [config.schema]).map((s) =>
      import(pathToFileURL(path.resolve(s)).href).then((v) => v)
    )
  );
  const s = Object.assign({}, ...schema);
  await db.transaction(async (tx) => {
    // drizzle-seedのresetはスキーマ名が巻き込まれるため、相当のものを独自に実装
    await db.execute(
      sql.raw(
        `truncate ${Object.values(s)
          .filter((t) => isTable(t))
          .map((t) => `"${getTableConfig(t as PgTable).name}"`)
          .join(",")} cascade;`
      )
    );
    await seed(tx, s);
  });
  await db.$client.end();
};
main();
```

### 利用例

`migrate`/`seed`をスキーマ切り替えに対応させたので、あとは普通に利用するだけです。`drizzle`のインスタンス作成時に`search_path`を設定することによって、対象のスキーマに接続できます。

```ts
import "dotenv/config";
import { relations } from "./db/relations.js";
import { drizzle } from "drizzle-orm/node-postgres";

const connectionString = process.env.DATABASE_URL;
if (!connectionString) throw new Error("DATABASE_URL is not set");

const url = new URL(connectionString);
const searchPath = url.searchParams.get("schema") ?? "public";

const db = drizzle({
  connection: {
    connectionString,
    options: `--search_path=${searchPath}`,
  },
  relations,
});

const main = async () => {
  console.log(
    await db.query.posts.findMany({ with: { author: true, categories: true } })
  );
  db.$client.end();
};

main();
```

## まとめ

Drizzle で PostgreSQL のスキーマを設定するには pgSchema を使って、固定でスキーマ名を設定することが前提になっています。しかしテストや開発時に、動的にスキーマを切り替えたいというニーズが完全に無視されており、とても不便です。今回紹介したように CLI のコマンドや関連パッケージの一部機能を自作して回避すれば対応は可能です。
