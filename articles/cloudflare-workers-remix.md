---
title: "Static Assets を使って Cloudflare Workers で Remix を動かす"
emoji: "🐡"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [remix, cloudflare, workers, react, typescript]
published: true
---

# Cloudflare Workers の Static Assets

https://developers.cloudflare.com/workers/static-assets/

Cloudflare Workers の Static Assets 対応によって、Cloudflare Pages を使わなくとも、静的コンテンツ配布時にリクエスト回数を消費せずに済むようになりました。これによって Remix を Cloudflare で使用する場合に、Pages を使わなければならない理由が減りました。対応機能の面で見れば、Pages から Workers に移行するメリットが増えたと言えるでしょう。

# Cloudflare 公式の Remix テンプレートを使うと二重ビルドが発生する

https://developers.cloudflare.com/workers/frameworks/framework-guides/remix/

上記の Cloudflare の公式テンプレートを使うと、Remix を Vite でビルドした後、さらに Pages 用のコードを Workers に変換するため二重にビルドする処理が生成されます。そもそものところで、最初から Workers 用のコードを作っておけばこの処理は不要です。今回は、最初から Workers 対応のコードを作る形で進めます。

# Workers で Remix を動かす

- wrangler.toml

公式のテンプレートを使うと`main = "./build/worker/index.js"`という記述になっています。これは一度 vite でビルドし、さらに wrangler で `[[path]].ts` をビルドして生成するものです。今回は`[[path]].ts`を直接呼び出すようにしています。正確に言うと直接呼び出しているように見えるファイルも、実際には wrangler が内部で esbuild していますが、そこはスルーしてください。

https://github.com/cloudflare/workers-sdk/blob/main/packages/create-cloudflare/templates-experimental/remix/templates/wrangler.toml

重要な点としては、`assets = { directory = "./build/client" }`で静的コンテンツのディレクトリを指定しています。これによって、静的コンテンツを Workers で配布することができます。

```toml
#:schema node_modules/wrangler/config-schema.json
name = "cloudflare-workers-remix"
compatibility_date = "2024-09-25"
main = "./functions/[[path]].ts"
assets = { directory = "./build/client" }

[observability]
enabled = true
```

- functions/[[path]].ts

ファイル名は wrangler.toml の main に指定したファイル名と一致させれば、この名前である必要はありません。
公式テンプレートだと `@remix-run/cloudflare-pages` を使っており、これをさらにビルドする方式になっているので、`@remix-run/cloudflare` の方を使用して、`fetch` をエクスポートすることにより `./functions/[[path]].ts` を wrangler から直接呼び出せるようにしています。

getLoadContext の処理を行う場合は、handler 実行直前の位置に置けば同様の結果が得られます。

```ts
import {
  AppLoadContext,
  createRequestHandler,
  ServerBuild,
} from "@remix-run/cloudflare";
import * as build from "../build/server";

const handler = createRequestHandler(build as ServerBuild);

const fetch = async (
  request: Request,
  env: AppLoadContext,
  ctx: ExecutionContext
) => {
  return handler(request, {
    cloudflare: {
      env,
      ctx: {
        waitUntil: ctx.waitUntil ?? (() => {}),
        passThroughOnException: ctx.passThroughOnException ?? (() => {}),
      },
      cf: request.cf!,
      caches,
    } as never,
  });
};

export default {
  fetch,
};
```

- package.json の scripts

公式テンプレートだと二重ビルドしていますが、今回は vite のビルド一回だけで済んでいます。

```json
  "scripts": {
    "build": "remix vite:build",
    "deploy": "pnpm run build && wrangler deploy",
    "dev": "remix vite:dev",
    "start": "wrangler dev",
  },
```

# まとめ

既存のプロジェクトの場合も必要な場所だけ置き換えれば、比較的簡単に Pages から Workers へ移行することが可能です。今後の開発では機能的メリットを考えると、 Pages を使う理由は少なそうです。
