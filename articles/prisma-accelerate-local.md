---
title: "Prisma Accelerate を Self Host して ローカルDBへアクセスする"
emoji: "🐷"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [prisma, edge, nextjs, database, cloudflare]
published: true
---

# Edge Runtime 上での Prisma Accelerate の必要性

Prisma を Edge-Runtime という制限された環境で使う場合、DB へクエリを発行する機能を持った PrismaEngine を直接動かすことが出来ません。これは PrismaEngine が Rust で書かれているためです。いずれは対応される可能性はありますが、現時点では動きません。このため、Edge-runtime 上で Prisma を使う場合は、PrismaEngine を切り離した状態で使う必要があります。

ここで登場するのが Prisma Accelerate という Prisma の公式サービスです。このサービスを使うと、PrismaClient 上で呼び出したクエリは、一旦 JsonProtocol に変換され、手元の PrismaEngine をスルーして、Prisma Accelerate へ送られます。そこで PrismaEngine が動作して各 DB にアクセスしクエリを実行します。これにより、Edge-Runtime 上で Prisma を使うことが出来るようになります。

# なぜ、Prisma Accelerate を Self Host する必要があるのか？

Prisma Accelerate は、予め登録された DB にアクセスできます。ここで問題になるのがローカルで開発している場合です。開発用では、 DB が localhost にあることが多いということです。Prisma Accelerate は、ローカル DB に直接アクセスすることが出来ません。設定次第で不可能ではありませんが面倒です。

こうなってくると問題になるのが、Prisma で Edge-runtime を使う書き方と、DB に直接接続するための書き方が異なるということです。さらに Next.js の場合は`export const runtime = 'edge'`を書いたり書かなかったりと、書き方が異なります。この`'edge'`部分、Next.js の Webpack の設定が手抜きになっているので変数が使えません。そのため環境変数でランタイムを気軽に切り替えられないので、開発環境と本番環境のコードに差異が生まれます。

開発環境と本番環境のコードを統一するには、Prisma から DB へのアクセス方法同じにする必要があります。そのために、Prisma Accelerate を Self Host する必要があるのです。

# Prisma Accelerate を Self Host する

ということで、早速 Prisma Accelerate を Self Host してみましょう。

使っているパッケージはこちらです。
https://www.npmjs.com/package/prisma-accelerate-local

以下のコマンドは PostgreSQL へのアクセスを想定の例です。

```sh
npx prisma-accelerate-local postgresql://postgres:password@localhost:5432/postgres -p 8000
```

これで Prisma Accelerate モドキが起動します。PrismaClient 側は、以下のような環境変数を設定します。

```js
DATABASE_URL="prisma://localhost:8000/?api_key=xxx"
NODE_TLS_REJECT_UNAUTHORIZED="0"
# To remove the NODE_TLS_REJECT_UNAUTHORIZED warning
NODE_NO_WARNINGS="1"
```

`NODE_TLS_REJECT_UNAUTHORIZED`は https でアクセスするために必要です。`NODE_NO_WARNINGS`は、NODE_TLS_REJECT_UNAUTHORIZED の警告を消すために必要です。起動オプションで認証済みの証明書のパスを設定すれば不要になります。

これで PrismaClient が Edge-runtime 上でもローカル DB にアクセスできるようになりました。基本的に Prisma Accelerate と同じような動きにしてあるので、prisma.schema は自動転送されます。また PrismaEngine も、対応バージョンをダウンロードして動くようにしています。

# まとめ

Prisma Accelerate が行っている処理に関しては情報が一切無かったので、間にプロキシを挟んでやり取りを確認しつつ、残りは Prisma のソースを見てなんとかしました。こういう開発に必要になるものは公式で用意してほしいところです。
