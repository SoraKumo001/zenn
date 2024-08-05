---
title: "Remixでmetaをエクスポートせずにheadの内容を書き換えてSSR"
emoji: "💭"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [remix, react, helmet, typescript]
published: true
---

# Remix の head の内容制御

Remix では Head の内容を設定するには、routes に配置したファイルから meta 変数をエクスポートする形で行うのが公式の方法です。ただ、この方法を使うと、各コンポーネント内から柔軟に内容を設定するようなことが出来ません。とんでもなく不便です。なぜこのような構造になっているかというと、各コンポーネントの評価が行われるよりも前に、head タグの評価が終了しているため、後から変更しようとしても出来ないからです。

しかし実は React はコンポーネントの実行順序を動的に変更する機能が標準で用意されています。それを使えば、各コンポーネント内で head に出力する内容を設定し、後から head の内容を出力することが可能になります。

# コンポーネントの評価順序の変更方法

## throw promise

やり方は簡単です。現在のタイミングでレンダリングをスキップしたいときに`throw promise`を実行するだけです。この機能、非同期処理を待つ機能だと思われていますが、正確にはコンポーネントの評価を一旦スキップする機能です。必要なデータが出揃ってスキップしたコンポーネントを再評価したい場合は、promise の resolve を呼び出します。

# 実際にやってみる

## パッケージ

こちらに一連の処理をパッケージ化したものを用意しました。中で使われている原理は先ほど紹介したとおりです。

https://www.npmjs.com/package/remix-head

## 実装例

https://github.com/SoraKumo001/remix-helmet

以下の内容でコンポーネントで指定した`title`が SSR 時に出力されます。

- route.tsx

`RemixHeadProvider`と`RemixHeadRoot`を設置します。

```tsx
import {
  Links,
  Meta,
  Outlet,
  Scripts,
  ScrollRestoration,
} from "@remix-run/react";
import { Analytics } from "@vercel/analytics/react";
import { RemixHeadProvider, RemixHeadRoot } from "remix-head";

export function Layout({ children }: { children: React.ReactNode }) {
  return (
    <RemixHeadProvider>
      <html lang="en">
        <head>
          <meta charSet="utf-8" />
          <meta name="viewport" content="width=device-width, initial-scale=1" />
          <Meta />
          <Links />
          <RemixHeadRoot />
        </head>
        <body>
          {children}
          <ScrollRestoration />
          <Scripts />
          <Analytics />
        </body>
      </html>
    </RemixHeadProvider>
  );
}

export default function App() {
  return <Outlet />;
}
```

- routes/\_index.tsx

`RemixHead`内に head に配置したい内容を設定します。ただしここに配置するタグのパラメータには制限があります。クライアント側に内容を引き渡す必要があるので、関数などでイベントを仕込むことは出来ません。最終的にテキストや数値に展開されるパラメータのみが設定可能です。

RemixHead は子階層のコンポーネントに設置しても構いません。また、useLoaderData で受け取った値を利用することも可能です。

```tsx
import { Link } from "@remix-run/react";
import { RemixHead } from "remix-head";

export default function Index() {
  return (
    <div>
      <RemixHead>
        <title>Top</title>
      </RemixHead>
      <div>Top</div>
      <div style={{ display: "grid" }}>
        <Link to="test01">test01</Link>
        <Link to="test02">test02</Link>
      </div>
    </div>
  );
}
```

# まとめ

以前に https://github.com/SoraKumo001/cloud-blog でブログシステムを Next.js から Remix+Cloudflare に移植した際、該当機能がなかったため実装した機能なのですが、SSR 時に同等の事ができるライブラリがなかったので、npm パッケージとして切り出しました。React の標準機能の`throw promise`によるレンダリング順序の制御は、色々なことに応用が効きます。
