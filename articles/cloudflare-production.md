---
title: "Cloudflare Workers / Pages のデプロイで気をつけること"
emoji: "😊"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [react, remix, cloudflare, typescript, wrangler]
published: true
---

# NODE_ENV に注意

Cloudflare Workers / Pages にデプロイする時 `wrangler deploy` を使用します。この時、内部では esbuild が実行され、依存している node_modules がバンドルされます。ここで気をつけなければならないのが、コマンド実行時点で `NODE_ENV` が `production` になっている必要があるということです。特に React を使っている場合、`NODE_ENV`が`production`になっていないと開発用のコードがバンドルされ、ビルド後のサイズが肥大化し、パフォーマンスも落ちます。

# どのぐらい違うのか

試しに、Remix + Prisma を使用したプログラムをビルドしてみます。

https://github.com/SoraKumo001/remix-global-prisma

ちなみにこのプログラムは、Cloudflare Workers 上の prisma インスタンスを env のバケツリレー無しで使用するサンプルです。

## package.json

`next-exec`は指定した env ファイルを読み込んでコマンドを実行するツールです。

```json
{
  "scripts": {
    "size-test:development": "wrangler deploy --dry-run",
    "size-test:production": " next-exec -c deploy -- wrangler deploy --dry-run"
  }
}
```

## env.deploy

```env
NODE_ENV=production
```

## 実行結果

- size-test:development

  ```txt
  ⛅️ wrangler 3.80.1 (update available 3.83.0)
  -------------------------------------------------------

  Total Upload: 2902.99 KiB / gzip: 1061.40 KiB
  ```

- size-test:production

  ```txt
  ⛅️ wrangler 3.80.1 (update available 3.83.0)
  -------------------------------------------------------

  Total Upload: 2563.51 KiB / gzip: 958.48 KiB
  ```

NODE_ENV を設定するだけで、サイズが約 100KB 減りました。

# まとめ

Cloudflare Workers / Pages の無料プランは gzip 時のサイズが 1MB までという制限があるので、Remix + Prisma のような構成でなにも設定しないと、問答無用でデプロイを却下されます。

デプロイ時の環境変数設定は忘れないようにしましょう。
