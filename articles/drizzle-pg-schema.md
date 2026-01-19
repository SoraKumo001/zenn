---
title: "Drizzle ORM から PostgreSQL を使用する際に、環境変数からschemaを切り替える"
emoji: "📑"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [drizzle, prisma, postgresql, orm, database]
published: true
---

# はじめに

PostgreSQL には **Schema（スキーマ）** という概念があり、1 つのデータベース内に「名前空間」を作ってテーブルを管理できます。デフォルトでは `public` スキーマが使われますが、これを切り替えることで、たとえば「テナントごとにスキーマを分ける」「テスト実行時だけ隔離されたスキーマを使う」といった運用が可能になります。

Prisma ユーザーにはおなじみですが、PostgreSQL の接続 URL に `?schema=my_schema` というパラメータを付けるだけで、接続先スキーマを切り替えられる機能があります。
しかし、これはあくまで Prisma が独自に実装している機能（糖衣構文）であり、PostgreSQL のドライバ標準の仕様ではありません。そのため、他の ORM やツールでは同様に記述しても無視されてしまいます。

**Drizzle ORM** も例外ではなく、通常の方法（`pgSchema` でのハードコーディング）では動的なスキーマ切り替えが困難です。本記事では、Drizzle ORM において環境変数（接続 URL）から動的にスキーマを切り替える実装方法を紹介します。

## サンプルプロジェクト

本記事で解説するコードの完成形は、以下のリポジトリで公開しています。

[https://github.com/SoraKumo001/drizzle-pg-schema](https://github.com/SoraKumo001/drizzle-pg-schema)

### 使用技術

- **Drizzle ORM / Drizzle Kit**: ORM およびマイグレーションツール
- **PostgreSQL**: データベース
- **Docker**: 実行環境

---

## 課題：なぜ標準機能だけでは足りないのか

Drizzle ORM で特定のスキーマを利用する場合、通常はスキーマ定義ファイル内で `pgSchema("my_schema")` を使って固定的に記述する必要があります。しかし、これでは開発・テスト・本番でスキーマ名を柔軟に変えたいニーズに対応できません。

PostgreSQL 自体には `search_path` という設定があり、これをセッション接続時に指定することでデフォルトのスキーマを変更できます。今回はこの `search_path` を活用しつつ、Drizzle Kit の CLI コマンド（`migrate` や `push`）では対応しきれない部分を**カスタムスクリプト**で補うことで解決します。

---

## 実装のポイント

実装の核となるのは以下の 3 点です。

1. **`drizzle.config.ts`**: 環境変数からスキーマ名を読み取る。
2. **App 接続設定**: `search_path` オプションを付与して接続する。
3. **カスタムスクリプト**: マイグレーションやシード実行時にスキーマを明示的に指定する。

### 1. 設定ファイル (`drizzle.config.ts`)

まず、`DATABASE_URL` から `?schema=xxx` パラメータを解析し、Drizzle Kit に伝える設定を行います。

```typescript:drizzle.config.ts
import { defineConfig } from "drizzle-kit";
import "dotenv/config";

const connectionString = process.env.DATABASE_URL!;
const url = new URL(connectionString);
// クエリパラメータから schema を取得。なければ public
const searchPath = url.searchParams.get("schema") ?? "public";

export default defineConfig({
  dialect: "postgresql",
  schema: "./src/db/schema.ts",
  out: "./drizzle",
  dbCredentials: {
    url: connectionString,
  },
  migrations: {
    // マイグレーション管理テーブル（__drizzle_migrations）の作成先を指定
    schema: searchPath,
  },
});

```

### 2. アプリケーションコードでの接続

アプリケーションから DB に接続する際、PostgreSQL ドライバのオプションとして `search_path` を渡します。これにより、発行される SQL にスキーマ名が明記されていなくても、自動的に指定したスキーマがターゲットになります。

```typescript:src/index.ts
import "dotenv/config";
import { drizzle } from "drizzle-orm/node-postgres";
import { relations } from "./db/relations.js";

const connectionString = process.env.DATABASE_URL;
if (!connectionString) throw new Error("DATABASE_URL is not set");

const url = new URL(connectionString);
const searchPath = url.searchParams.get("schema") ?? "public";

const db = drizzle({
  connection: {
    connectionString,
    // セッションレベルで search_path を設定
    // これにより、以降のクエリはこのスキーマに対して実行される
    options: `--search_path=${searchPath}`,
  },
  relations,
});

// 使用例
const main = async () => {
  const result = await db.query.posts.findMany({
    with: { author: true, categories: true }
  });
  console.log(result);
  db.$client.end();
};

main();

```

---

## 運用ツールの自作（Migrate, Seed, Reset）

Drizzle Kit の CLI (`drizzle-kit migrate` 等）は便利ですが、動的なスキーマ切り替えや、環境ごとのクリーンアップを行うには柔軟性が足りない場合があります。そこで、Node.js スクリプトとして各コマンドを実装します。

これらのスクリプトは `tools/` ディレクトリに配置し、`drizzle.config.ts` の設定を読み込んで動作させます。

### A. マイグレーション実行 (`tools/migrate.ts`)

CLI の代わりに `drizzle-orm` の `migrate` 関数を使用します。ここで重要なのが `migrationsSchema` オプションです。これを指定することで、マイグレーション履歴の管理テーブルも指定スキーマ内に作成されます。

```typescript:tools/migrate.ts
import config from "../drizzle.config";
import { drizzle } from "drizzle-orm/node-postgres";
import { migrate } from "drizzle-orm/node-postgres/migrator";

const main = async () => {
  // ... (接続チェック省略) ...

  const searchPath = config.migrations?.schema ?? "public";

  const db = drizzle({
    connection: {
      connectionString: config.dbCredentials.url,
      options: `--search_path=${searchPath}`,
    },
  });

  if (!config.out) throw new Error("out is not set");

  // スキーマを指定してマイグレーションを実行
  await migrate(db, {
    migrationsFolder: config.out,
    migrationsSchema: searchPath,
  });

  await db.$client.end();
};

main();

```

### B. データベースリセット (`tools/reset.ts`)

開発中、DB を完全にクリーンな状態に戻したい場合があります。`drizzle-kit` にはこの機能が不足しているため、指定されたスキーマごと削除（`DROP SCHEMA ... CASCADE`）するスクリプトを用意します。

```typescript:tools/reset.ts
// ... (imports) ...

const main = async () => {
  // ... (config読み込み) ...
  const searchPath = config.migrations?.schema ?? "public";

  const db = drizzle({
    connection: {
      connectionString: config.dbCredentials.url,
      options: `--search_path=${searchPath}`,
    },
  });

  // スキーマごと削除してカスケード
  await db.execute(`DROP SCHEMA IF EXISTS "${searchPath}" CASCADE`);

  // スキーマを再作成（必要に応じて）
  await db.execute(`CREATE SCHEMA IF NOT EXISTS "${searchPath}"`);

  await db.$client.end();
};

main();

```

### C. シーディング (`tools/seed.ts`)

`drizzle-seed` を使用しますが、ここにも注意点があります。標準の `reset` 機能を使うと、スキーマ名が正しく扱われず `public` などを誤って参照してしまう挙動（バグまたは仕様）が見られました。
そのため、手動で `TRUNCATE` を行ってからデータを投入します。

```typescript:tools/seed.ts
import config from "../drizzle.config";
import { drizzle } from "drizzle-orm/node-postgres";
import { seed } from "drizzle-seed";
import { sql, isTable } from "drizzle-orm";
import { getTableConfig, type PgTable } from "drizzle-orm/pg-core";
import * as schema from "../src/db/schema"; // スキーマ定義をインポート

const main = async () => {
  // ... (config読み込み) ...
  const searchPath = config.migrations?.schema ?? "public";

  const db = drizzle({
    connection: {
      connectionString: config.dbCredentials.url,
      options: `--search_path=${searchPath}`,
    },
  });

  await db.transaction(async (tx) => {
    // 全テーブルを動的に取得して TRUNCATE する
    const tables = Object.values(schema)
      .filter((t) => isTable(t))
      .map((t) => `"${getTableConfig(t as PgTable).name}"`)
      .join(", ");

    if (tables.length > 0) {
      await tx.execute(sql.raw(`TRUNCATE TABLE ${tables} CASCADE;`));
    }

    // データの投入
    await seed(tx, schema);
  });

  await db.$client.end();
};

main();

```

---

## 実行方法

`package.json` に以下のようにスクリプトを定義しておくとスムーズに運用できます。

```json
{
  "scripts": {
    "dev": "tsx src/index.ts",
    "docker": "docker compose up -d",
    "generate": "drizzle-kit generate",
    "migrate": "tsx tools/migrate.ts",
    "seed": "tsx tools/seed.ts",
    "reset": "tsx tools/reset.ts"
  }
}
```

### ワークフロー

1. **.env の設定**: URL にターゲットスキーマを指定します。

```env
DATABASE_URL=postgres://user:pass@localhost:5432/db?schema=test_schema

```

2. **DB 起動**: `pnpm run docker`
3. **マイグレーション生成**: `pnpm run generate` (スキーマ変更時）
4. **適用 & データ投入**:

```bash
pnpm run migrate # 指定したスキーマにテーブル作成
pnpm run seed    # 指定したスキーマにデータ投入

```

5. **アプリ実行**: `pnpm run dev`

これで、`test_schema` 配下にデータが作られ、アプリもそこを参照して動くようになります。環境変数を書き換えるだけで、コードを変更することなく接続先スキーマをスイッチ可能です。

---

## まとめ

Drizzle ORM で動的なスキーマ切り替えを実現するには、標準の `pgSchema` 定義ではなく、以下の組み合わせが有効です。

1. PostgreSQL 標準の `search_path` を接続オプションで利用する。
2. `drizzle-kit` の CLI に頼らず、`migrate` や `seed` をプログラム（スクリプト）から実行し、その際にスキーマ情報を注入する。

このアプローチにより、Prisma のような手軽さで、開発・テスト・本番環境のスキーマ分離を Drizzle でも実現できます。ぜひ試してみてください。
