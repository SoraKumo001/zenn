---
title: "CloudflareD1へNode.jsのPrismaからアクセスする"
emoji: "👋"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [cloudflare, prisma, d1, typescript, workers]
published: true
---

# Prisma の D1 対応

下記の通り Prisma で Cloudflare の D1 がサポートされました。

https://www.prisma.io/blog/build-applications-at-the-edge-with-prisma-orm-and-cloudflare-d1-preview

ということで早速試してみます。
ただ、Prisma を使って 普通に Cloudflare 上から D1 にアクセスするのは誰でも簡単にできるので、世界で誰もやってなさそうな Node.js からアクセスする方法紹介します。

# Worker の作成

まずは Cloudflare 上に D1 にアクセスするための Worker を作成します。これは Node.js の Prisma からリモートアクセスさせるための Proxy です。QueryEngine だけ Workers 上で動かします。

https://github.com/SoraKumo001/prisma-accelerate-workers-d1

このプログラムを Workers にデプロイし、d1_databases をバインディング、シークレットを設定します。その後、以下のコマンドで API キーを作成します。これで準備完了です。

```sh
npx prisma-accelerate-local -s SECRET -m DB
```

ここで作った API キーと Workers の URL を使えば、Node.js 上の Prisma から D1 にアクセス出来るようになります。

余談ですが、prisma@5.12.0の D1 などの Adapter には以下の PR で混入した Node.js の`util`がバンドルされてしまう問題があって、本来は不要のはずの Node.js のランタイムを必要とします。

https://github.com/prisma/prisma/pull/23013

これがどういうことかというと、最初の記事で紹介されている Workers の設定の`nodejs_compat`(Workers 上のランタイムで 0 サイズ)では動かず、`node_compat`(Polyfill で容量を食う)の方が必要となります。これを回避する方法は前述の [こちら](https://github.com/SoraKumo001/prisma-accelerate-workers-d1) に記載しています。つまり公式の説明通りに実装すると、エラーを出して動きません。

# Node.js からのアクセス

https://github.com/SoraKumo001/prisma-d1-test

- prisma/schema.prisma

directUrl はマイグレーションファイルの生成に必要なのでダミーで指定しておきますが、実際に中にデータを入れることはありません。

```prisma
generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "sqlite"
  url       = env("DATABASE_URL")
  directUrl = "file:./dev.db"
}

model Role{
  id        String   @id @default(uuid())
  name      String   @unique
  users     User[]
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt
}

model User {
  id        String   @id @default(uuid())
  email     String   @unique
  name      String   @default("User")
  posts     Post[]
  roles     Role[]
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
```

- tools/migrate.ts

D1 に対して、リモートでマイグレーションを行うために適当に作ったコードです。Prisma のマイグレーションファイルを一つのフォルダに集約し、DB 名から UUID を取得して、その UUID を使ってマイグレーションを行います。手動でやると面倒なので、これを使って自動化します。

```ts
import fs from "fs";
import { exec } from "child_process";
import { promisify } from "util";
import path from "path";
import os from "os";

const srcPath = "prisma/migrations";
const distPath = fs.mkdtempSync(path.join(os.tmpdir(), "prisma-migrations"));
const DB = process.env.DB_NAME!;

const execAsync = promisify(exec);

type D1List = {
  uuid: string;
  name: string;
  version: string;
  created_at: string;
};

export const getD1List = async () => {
  const list = await execAsync("wrangler d1 list --json").then(
    ({ stdout }) => JSON.parse(stdout) as D1List[]
  );
  return list;
};

export const migrationD1 = async (dbName: string, dir: string) => {
  return execAsync(
    `wrangler d1 migrations apply --remote ${dbName} -c ${dir}/wrangler.toml`
  ).then(({ stdout, stderr }) => stderr || stdout);
};

const main = async () => {
  if (fs.existsSync(distPath)) {
    fs.rmSync(distPath, { recursive: true });
  }

  fs.mkdirSync(distPath, { recursive: true });
  const migrations = fs.readdirSync(srcPath, { withFileTypes: true });
  migrations
    .filter((v) => {
      return v.isDirectory();
    })
    .sort((a, b) => (a.name < b.name ? -1 : 1))
    .forEach(({ name }) => {
      const sql = fs.readFileSync(`${srcPath}/${name}/migration.sql`, "utf8");
      fs.writeFileSync(`${distPath}/${name}.sql`, sql);
    });

  const list = await getD1List();
  const uuid = list.find((v) => v.name === DB)?.uuid;
  if (uuid) {
    fs.writeFileSync(
      `${distPath}/wrangler.toml`,
      `[[d1_databases]]
binding = "DB"
database_name = "${DB}"
database_id ="${uuid}"
migrations_dir = "./"`
    );
  }
  const result = await migrationD1(DB, distPath);
  console.log(result);
  fs.rmSync(distPath, { recursive: true });
};

main();
```

- .env

Workers の URL と API キーを設定します。また、マイグレーションを行うための DB 名を設定します。こちらは先程のスクリプトで利用します。

```ts
# Address of installed Workers
DATABASE_URL=prisma://xxxxx.workers.dev?api_key=xxxxxx
# For Migration
DB_NAME=xxxx
```

- package.json

`yarn prisma:migrate`を実行すると、Prisma がマイグレーションファイルを作成し、それを Workers に送信してマイグレーションを行います。`next-exec`は環境変数を設定してから実行するためのツールです。

```json
{
  "name": "prisma-d1-test",
  "version": "1.0.0",
  "main": "index.js",
  "license": "MIT",
  "scripts": {
    "start": "next-exec -- tsx src",
    "prisma:migrate": "prisma migrate dev && next-exec -- tsx tools/migrate.ts && prisma generate --no-engine"
  },
  "dependencies": {
    "@prisma/client": "^5.12.0"
  },
  "devDependencies": {
    "@types/node": "^20.12.3",
    "next-exec": "^1.0.0",
    "prisma": "^5.12.0",
    "tsx": "^4.7.1",
    "typescript": "^5.4.3",
    "wrangler": "^3.44.0"
  }
}
```

- src/index.ts

こちらがメインのコードです。Prisma を使って D1 にアクセスしデータの読み書きをしています。通常の Node.js のコードと全く代わりません。DATABASE_URL に`prisma://xxxx`を指定している時点で、D1 の設定作業は終わっています。

```ts
import { PrismaClient } from "@prisma/client";

const formatNumber = (num: number) => {
  return num.toString().padStart(2, "0");
};

const main = async () => {
  const prisma = new PrismaClient();
  const roles = await prisma.role.count().then(async (count) => {
    if (!count) {
      return Promise.all(
        [
          {
            name: "ADMIN",
          },
          { name: "USER" },
        ].map((data) => {
          return prisma.role.create({
            data,
          });
        })
      );
    }
    return prisma.role.findMany();
  });

  if (roles === undefined) {
    throw new Error("roles is undefined");
  }
  const ROLES = Object.fromEntries(roles.map((v) => [v.name, v.id] as const));

  const users = await prisma.user.count().then(async (count) => {
    if (!count) {
      return Promise.all(
        [
          {
            name: "admin",
            email: "admin@example.com",
            roles: {
              connect: [
                {
                  id: ROLES["ADMIN"],
                },
                { id: ROLES["USER"] },
              ],
            },
          },
          {
            name: "example",
            email: "example@example.com",
            roles: { connect: [{ id: ROLES["USER"] }] },
          },
        ].map((data) => {
          return prisma.user.create({
            data,
          });
        })
      );
    }
    return prisma.user.findMany();
  });

  // add category
  const categories = await prisma.category.count().then(async (count) => {
    if (!count) {
      return Promise.all(
        Array(10)
          .fill(0)
          .map((_, i) => ({ name: `Category${formatNumber(i + 1)}` }))
          .map((data) =>
            prisma.category.create({
              data,
            })
          )
      );
    }
    return prisma.category.findMany();
  });

  // add post
  await prisma.post.count().then(async (count) => {
    if (!count) {
      for (let i = 0; i < 30; i++) {
        await prisma.post.create({
          data: {
            title: `Post${formatNumber(i + 1)}`,
            content: `Post${formatNumber(i + 1)} content`,
            authorId: users[1].id,
            published: i % 4 !== 0,
            categories: {
              connect: [
                { id: categories[i % 2].id },
                { id: categories[i % 10].id },
              ],
            },
          },
        });
      }
    }
  });

  console.log(
    JSON.stringify(
      await prisma.post.findMany({
        include: { author: true, categories: true },
      }),
      undefined,
      2
    )
  );
};
main();
```

- Cloudflare のコンソール上で確認

きちんとデータが入っています。

![](/images/prisma-d1/2024-04-04-09-02-59.png)

# まとめ

Prisma で D1 がサポートされたので、Node.js からアクセスする方法を紹介しました。これによって Cloudflare の D1 が、サーバーレスな DB となります。
