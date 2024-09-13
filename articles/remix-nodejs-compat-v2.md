---
title: "Cloudflare の nodejs_compat_v2 を有効にし prisma から pg を使う"
emoji: "🙌"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [cloudflare, prisma, pg, nodejs_compat_v2, remix]
published: true
---

# nodejs_compat_v2

`nodejs_compat_v2` は Cloudflare Workers/Pages を扱う場合に、Node.js の機能と互換性を持たせることができます。nodejs_compat よりも対応する幅が増えました。compatibility_date の 2024-09-23 以降からは、v2 の機能が`nodejs_compat`に統合される予定です。

https://blog.cloudflare.com/more-npm-packages-on-cloudflare-workers-combining-polyfills-and-native-code/

ちなみに `nodejs_compat` は機能がランタイム側にあるため、利用してもデプロイ時のサイズに影響を与えないのですが、`nodejs_compat_v2`は デプロイ前に Polyfill が働くらしく、サイズ増加を覚悟する必要があります。

# さっそく pg を使ってみる

Node.js の互換性が上がったということは、 Polyfill を追加で指定せずに pg を使うことができるかもしれません。早速 Prisma から試してみました。`@prisma/adapter-pg` + `pg`の組み合わせで動作させてみます。ビルドはすんなり通るようで、実行までこぎつけました。

```bash
 [ERROR] TypeError: http://this.stream.once is not a function`
```

ということで実行はされるものの、機能不足でエラーです。

`@prisma/adapter-pg-worker` + `@prisma/adapter-pg-worker`の組み合わせを試してみます。

```bash
X [ERROR] TypeError: Illegal invocation: function called with incorrect `this` reference.
```

`@prisma/adapter-pg-worker` は `pg` に Polyfill を追加して動作させるように作られたパッケージですが、`nodejs_compat_v2` を有効にすると、こちらもエラーが出てしまいます。つまりこの機能が有効になると pg が完全に死にます。

# 動かす

ここで残念ながら動きませんでしたで終わらせるのはあまりにアホなので、`pg` を `nodejs_compat_v2` に対応させます。ということで、問題点を調べ修正を加え、パッチを作りました。pg の github 上のコードを見ると、一部修正されているのですが、まだ足りない部分がありました。

https://www.npmjs.com/package/pg-compat

これを`pg`と一緒にインストールするだけで、`pg`が`nodejs_compat_v2`で動作するようになります。

# サンプル

Remix + Prisma + PostgreSQL のサンプルを作りました。`nodejs_compat_v2`を有効にして動作させています。Prisma は `@prisma/adapter-pg` + `pg`の組み合わせで動作させています。これによって Node.js で動く開発環境と、Build 後の Wrangler 上の環境で、パッケージを切り替えずに動作させられます。

https://github.com/SoraKumo001/remix-nodejs_compat_v2

- wrangler.toml

```
compatibility_date = "2024-08-21"
compatibility_flags = ["nodejs_compat_v2"]
```

- app/routes/\_index.tsx

```tsx
import { LoaderFunctionArgs } from "@remix-run/cloudflare";
import { useLoaderData } from "@remix-run/react";
// @prisma/xxx-worker is not used
import pg from "pg";
import { PrismaPg } from "@prisma/adapter-pg";
import { PrismaClient } from "@prisma/client";

export default function Index() {
  const values = useLoaderData<string[]>();
  return (
    <div>
      {values.map((v) => (
        <div key={v}>{v}</div>
      ))}
    </div>
  );
}

export async function loader({
  context,
}: LoaderFunctionArgs): Promise<string[]> {
  const url = new URL(context.cloudflare.env.DATABASE_URL);
  const schema = url.searchParams.get("schema") ?? undefined;
  const pool = new pg.Pool({
    connectionString: context.cloudflare.env.DATABASE_URL,
  });
  const adapter = new PrismaPg(pool, { schema });
  const prisma = new PrismaClient({ adapter });
  await prisma.test.create({ data: {} });
  return prisma.test.findMany().then((r) => r.map(({ id }) => id));
}
```

# まとめ

とりあえずパッチを作って動くようにはしましたが、いずれ `pg` のバージョンアップでパッチが不要になることでしょう。また、compatibility_date の 2024-09-23 がやってきた後は、古いランタイムを使わないと `nodejs_compat`の状態で pg が死んでしまうので注意が必要です。
