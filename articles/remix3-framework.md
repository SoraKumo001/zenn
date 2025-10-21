---
title: "Remix3 を Vite で勝手に俺俺フレームワーク化して、Cloudflare にデプロイする"
emoji: "🗂"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [remix, remix3, cloudflare, react, vite]
published: true
---

# Remix3 の現在

開発有のパッケージが npm で配布されているものの、日本ではほとんど使ってみたという人が出てきません。情報もほとんどありません。周辺ライブラリもほぼ皆無です。なにかやろうとすると色々なものを自作することになります。得意分野が車輪の再発明の人間しかやってられません。

Remix3 に関して、現時点でこちらに関連リポジトリっぽいものがあります。

https://github.com/remix-run/remix

中を確認すると、Remix3 自体のコードは含まれておらず、使い方を示すサンプル集のような意味合いのリポジトリになっています。ただ、Vite で開発するようなコードは含まれておらず、今回この中で使ったのはパッケージは`route-pattern`だけです。ファイルベースルーティングの Vite Plugin を作るために利用しています。

# Vite で開発環境を整える

## サンプルリポジトリ

今回はこちらの、remix3-sample06 をベースに記事を書いています。

https://github.com/SoraKumo001/remix3-samples

## 前提条件

SPA で多少動かすだけなら小一時間でできたので、以下の条件で開発環境を構築します

- SSR で非同期データのやり取りができる
- Tailwind が使える
- Hono を使う
- HMR でフルリロードせずにホットリロードが使える
- ファイルベースベースルーティングができる
- Cloudflare にデプロイできる

## vite.config.ts の作成

- ビルドファイルの設定
- Hono プラグインによって開発モードと実起動の entry ファイルの共通化
- HMR 用のリロードプラグインを入れる
- Tailwind プラグインの組み込み
- ファイルベースルーティング用のプラグインの組み込み

```ts
import { defineConfig, type ViteDevServer } from "vite";
import devServer, { defaultOptions } from "@hono/vite-dev-server";
import tailwindcss from "@tailwindcss/vite";
import { remixRoutes } from "./vite-plugin/remix-routes";
export default defineConfig(({ isSsrBuild }) => {
  return {
    build: {
      outDir: isSsrBuild ? "./dist" : "./dist/assets",
      ssr: isSsrBuild,
      rolldownOptions: {
        input: isSsrBuild ? "./worker/app.ts" : "./src/client.tsx",
        output: {
          entryFileNames: (chunkInfo) => {
            if (chunkInfo.name === "app") {
              return "index.js";
            }
            return "[name].js";
          },
        },
      },
    },
    publicDir: isSsrBuild ? false : undefined,
    plugins: [
      devServer({
        entry: "worker/app.ts",
        exclude: [
          ...defaultOptions.exclude,
          /\.(ts|tsx|webp|png|svg|css)(\?.*)?$/,
        ],
      }),
      {
        name: "reload",
        handleHotUpdate({ server }: { server: ViteDevServer }) {
          server.moduleGraph.getModuleByUrl("/src/client.tsx").then((mod) => {
            if (mod) server.reloadModule(mod);
          });
        },
      },
      tailwindcss(),
      remixRoutes(),
    ],
  };
});
```

## ファイルベースルーティング用の Vite プラグインを作成

現時点において Remix3 に Vite 経由のファイルベースルーティング機能はありません。不便なので`./src/routes`にあるファイルリストを元にルーティングを行う仮想モジュールのプラグインを自作します。使い方は`React Router`に寄せてあります。

- vite-plugin/remix-routes.ts

```ts
import * as fs from "fs";
import * as path from "path";
import { type Plugin } from "vite";

const VIRTUAL_MODULE_ID = "virtual:routes";
const RESOLVED_VIRTUAL_MODULE_ID = "\0" + VIRTUAL_MODULE_ID;

export function remixRoutes(options?: { dir?: string }): Plugin {
  const dir = options?.dir ?? "./src/routes";
  let routesDir: string;

  return {
    name: "vite-plugin-remix-routes",
    config(config) {
      return {
        resolve: {
          alias: {
            "@": path.resolve(config.root || process.cwd(), dir),
          },
        },
      };
    },
    configResolved(resolvedConfig) {
      routesDir = path.join(resolvedConfig.root, dir);
    },
    resolveId(id) {
      if (id === VIRTUAL_MODULE_ID) {
        return RESOLVED_VIRTUAL_MODULE_ID;
      }
      return null;
    },
    load(id) {
      if (id === RESOLVED_VIRTUAL_MODULE_ID) {
        if (!routesDir) {
          throw new Error("routesDir has not been initialized.");
        }

        const routeFiles = fs.readdirSync(routesDir);
        const imports: string[] = [];
        const routeDefinitions: string[] = [];
        const routeMap: { [key: string]: string } = {};

        routeFiles.forEach((file, index) => {
          const fileName = path.parse(file).name;
          const importPath = `@/${fileName}`;

          imports.push(`import route${index} from "${importPath}";`);

          let routePath = fileName
            .replace(/\.(tsx|ts)$/, "")
            .split(".")
            .map((segment) => {
              if (segment.startsWith("$")) {
                return `:${segment.substring(1)}`;
              }
              return segment;
            })
            .join("/");

          if (routePath === "index") {
            routePath = "";
          }
          routePath = `/${routePath}`;
          routeMap[routePath] = `route${index}`;
        });

        Object.entries(routeMap).forEach(([routePath, componentName]) =>
          routeDefinitions.push(`  "${routePath}": ${componentName}`)
        );

        return `
${imports.join("\n")}
export const route = {
${routeDefinitions.join(",\n")}
};`;
      }
      return null;
    },
  };
}
```

## Entry ファイルの設置

Vite の開発モードと Cloudflare にデプロイするときに使う共通ファイルです。`../dist/index.js`は Vite から呼び出す場合は、`./src/server.tsx`に切り替わります。

- worker/app.ts

```ts
import { Hono } from "hono";
import handler from "../src/server.tsx";

const app = new Hono();
app.get("*", async (c) => {
  return handler(c.req.url);
});

export default app;
```

## Server 用ファイル

renderToStream で SSR を行う部分です。`resolveFrame`という Remix3 特有の機能を使っています。これが SSR の肝になる部分です。Remix3 には`<Frame>`という特別なコンポーネントがあり、仮想 DOM のツリー状に Frame を見つけると、resolveFrame を非同期で呼び出します。ここで Frame の中身を別のコンポーネントに変換して返すことができます。非同期で呼び出されるということは、外部データをコンポーネントに乗せたうえで送り返すことができるのです。この機能を使えば何でもありで SSR が使えます。

```tsx
import { renderToStream } from "@remix-run/dom/server";
import { Layout } from "./root";
import {
  resolveFrame,
  SSRProvider,
  type SSRProps,
} from "./provider/SSRProvider";
import { RouterProvider } from "./provider/RouterProvider";

const handler = (url: string) => {
  const storage: SSRProps = { states: {} };
  return new Response(
    renderToStream(
      <RouterProvider url={url}>
        <SSRProvider storage={storage}>
          <Layout />
        </SSRProvider>
      </RouterProvider>,
      {
        resolveFrame: (src) => resolveFrame(src, storage.states),
      }
    ),
    {
      headers: {
        "Content-Type": "text/html",
      },
    }
  );
};

export default handler;
```

## Client 用ファイル

クライアント側で DOM をハイドレーションさせています。Remix3 は React と違って`<HTML>`に対するハイドレーション機能を提供していません。仕方がないので body 配下にマウントさせています。

その他、 HMR 用に細工を入れています。

- src/client.tsx

```tsx
import { createRoot } from "@remix-run/dom";
import { App } from "./App";
import { SSRProvider } from "./provider/SSRProvider";
import { RouterProvider } from "./provider/RouterProvider";

const Render = (
  <RouterProvider>
    <SSRProvider>
      <App />
    </SSRProvider>
  </RouterProvider>
);

if (document.body) {
  createRoot(document.body).render(Render);
} else {
  window.addEventListener(
    "DOMContentLoaded",
    () => {
      createRoot(document.body).render(Render);
    },
    { once: true }
  );
}

if (import.meta.hot) {
  import.meta.hot.accept(() => {});
}
```

## レイアウト指定コンポーネント

ページ全体の記述をするファイルです。Remix3 が`<HTML>`自体をマウントできないので、現在はサーバ側でしか使っていませんが、本来はクライアントと共用したい部分です。開発モードかどうかで、呼び出すスクリプトファイルを切り替えています。

- root.tsx

```tsx
import type { Remix } from "@remix-run/dom";
import { App } from "./App";
import css from "./index.css?inline";

export function Layout(this: Remix.Handle) {
  return (
    <html lang="ja">
      <head>
        <meta charSet="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <style type="text/css">{css}</style>
        <script
          type="module"
          src={
            /\.(tsx|ts)$/.test(import.meta.url)
              ? "/src/client.tsx"
              : "/client.js"
          }
        />
        <title>Remix3 Test</title>
      </head>
      <body>
        <App />
      </body>
    </html>
  );
}
```

## Tailwind 用 CSS

おなじみ、Tailwind 用の CSS ファイルです。

- src/index.css

```css
@import "tailwindcss";

a {
  @apply underline text-blue-600 hover:text-blue-800 visited:text-purple-900;
}
```

## ルーティング用ファイル

現時点でルーティング用の機能が提供されていないので自分で作ります。サーバ側で URL をコンポーネントに渡したり、クライアントで URL の切り替えを検知して再レンダリングの指示を出します。また`<Link>`タグを作って、JavaScript がブラウザで制限されている場合の対処も含めてコンポーネント化します。

また、さきほど作った仮想モジュールを使ってファイルベースルーティング用のコンポーネント`Outlet`も用意します。このコンポーネントを設置した場所に、ファイルベースルーティングしたコンポーネントが差し込まれます。

- src/provider/RouterProvider.tsx

```ts
import { type Remix } from "@remix-run/dom";
import { dom } from "@remix-run/events";
import { RoutePattern, type RouteMatch } from "@remix-run/route-pattern";
import { route } from "virtual:routes";

const isServer = typeof window === "undefined";

export function RouterProvider(
  this: Remix.Handle<{
    serverUrl: string;
    navigate: (url: string) => void;
    params?: RouteMatch<string>;
  }>
) {
  const context = {
    serverUrl: "",
    navigate: (url: string) => {
      history.pushState({}, "", url);
      this.render();
    },
  };
  this.context.set(context);

  const handlePopState = () => {
    this.render();
  };
  if (!isServer) {
    addEventListener("popstate", handlePopState);
  }
  return ({ url, children }: { url?: string; children: Remix.RemixNode }) => {
    if (isServer && url) {
      context.serverUrl = url;
    }
    return <>{children}</>;
  };
}

export const useLocation = (inst: Remix.Handle) => {
  if (isServer) {
    const url = new URL(inst.context.get(RouterProvider).serverUrl);
    return url.pathname;
  }
  return location.pathname;
};

export const useFullLocation = (inst: Remix.Handle) => {
  if (isServer) {
    const url = new URL(inst.context.get(RouterProvider).serverUrl);
    return url.href;
  }
  return location.href;
};

export const useNavigate = (inst: Remix.Handle) => {
  return inst.context.get(RouterProvider).navigate;
};

export const useParams = <T extends Record<string, unknown>>(
  inst: Remix.Handle
) => {
  const p = inst.context.get(RouterProvider).params;
  if (!p) throw "error params";
  return p.params as T;
};

export function Link(this: Remix.Handle) {
  const navigate = useNavigate(this);
  return (props: Remix.Props<"a">) => {
    return (
      <a
        {...props}
        on={dom.click((e) => {
          e.preventDefault();
          if (props.href) {
            navigate(props.href);
          }
        })}
      >
        {props.children}
      </a>
    );
  };
}

export type RouteType = Record<string, Remix.Component>;

export const useRouter = (inst: Remix.Handle, route: RouteType) => {
  const location = useFullLocation(inst);

  for (const [pattern, content] of Object.entries(route)) {
    const p = new RoutePattern(pattern);
    const match = p.match(location);
    if (match) {
      inst.context.get(RouterProvider).params = match;
      return content;
    }
  }
  return <></>;
};

export function Outlet(this: Remix.Handle) {
  const Route = useRouter(this, route);
  return <Route />;
}
```

## SSR 制御機能

Remix3 で SSR させるための機能を実装しています。非同期通信用コンポーネント内で`<Frame>`を作っています。そしてサーバでレンダリングを行う際に、非同期データを保存したコンポーネントと入れ替えています。また、データをクライアントに渡すため、情報を JSON に変換して SSR で生成される HTML に挿入します。クライアント側では、最初にそのデータを受け取って、各コンポーネントのレンダリングが始まります。

```tsx
import { Frame, type Remix } from "@remix-run/dom";

const isServer = typeof window === "undefined";
const SSR_DATA_NAME = "__REMIX3_SSR__";

type SSRResult<T = unknown> = {
  state: "idle" | "loading" | "finished";
  value?: T;
};

type SSRState<T = unknown> = SSRResult<T> & {
  children: Remix.RemixNode;
  promise: Promise<T>;
};

export type SSRProps = {
  states: Record<string, SSRState>;
};

export function SSRProvider(this: Remix.Handle<SSRProps>) {
  return ({
    storage,
    children,
  }: {
    storage?: SSRProps;
    children: Remix.RemixNode;
  }) => {
    if (isServer) {
      this.context.set(
        storage ?? {
          states: {},
        }
      );
    } else {
      const node = document.getElementById(SSR_DATA_NAME);
      const states = JSON.parse(node?.innerText ?? "{}");
      this.context.set(
        storage ?? {
          states: Object.fromEntries(
            Object.entries(states).map(([key, v]) => [
              key,
              {
                state: "finished",
                promise: Promise.resolve(v),
                value: v,
                children: undefined,
              },
            ])
          ),
        }
      );
    }
    return (
      <>
        {children}
        {isServer && <Frame src="ssr-data:" />}
      </>
    );
  };
}

export function SSRData(this: Remix.Handle<SSRResult>) {
  return ({
    value,
    state,
    children,
  }: {
    value: unknown;
    state: "idle" | "loading" | "finished";
    children: Remix.RemixNode;
  }) => {
    this.context.set({ value, state });
    return children;
  };
}

export function SSRFetch<T>(
  this: Remix.Handle,
  {
    name,
    action,
    children,
  }: {
    name: string;
    action: () => Promise<T>;
    children: Remix.RemixNode;
  }
) {
  const context = this.context.get(SSRProvider);
  if (!context) return undefined;
  const frameName = `ssr:${name}`;
  if (!context.states[frameName]) {
    const promise = action();
    const state: SSRState<T> = {
      promise,
      state: "loading",
      value: undefined,
      children,
    };
    context.states[frameName] = state;
    promise.then((v) => {
      context.states[frameName].state = "finished";
      context.states[frameName].value = v;
      if (!isServer) this.render();
    });
  }
  if (isServer) {
    return <Frame src={frameName} />;
  } else {
    const state = context.states[frameName];
    return (
      <SSRData value={state.value} state={state.state}>
        {children}
      </SSRData>
    );
  }
}

export const useSSR = <T,>(inst: Remix.Handle) => {
  return inst.context.get(SSRData) as SSRResult<T>;
};

export const resolveFrame = async (
  src: string,
  states: Record<string, SSRState>
) => {
  if (src === "ssr-data:") {
    let length = 0;
    while (length !== Object.values(states).length) {
      await Promise.all(Object.values(states).map((v) => v.promise));
      length = Object.values(states).length;
    }
    const values: Record<string, unknown> = {};
    for (const [key, p] of Object.entries(states)) {
      values[key] = await p.promise;
    }
    return (
      <script type="application/json" id={SSR_DATA_NAME}>
        {JSON.stringify(values)}
      </script>
    );
  }
  const state = states[src];
  const children = state.children;
  const value = await state.promise;
  state.value = value;
  return (
    <SSRData value={value} state={state.state}>
      {children}
    </SSRData>
  );
};
```

## アプリケーションの起点を作る

ファイルベースルーティングで取得したコンポーネントを差し込みます。

- src/App.tsx

```tsx
import { type Remix } from "@remix-run/dom";
import { Outlet } from "./provider/RouterProvider";

export function App(this: Remix.Handle) {
  return <Outlet />;
}
```

# 天気予報表示アプリの作成

## エリア情報

気象庁のサイトから地域名の一覧を取得してリンクを作成しています。さきほど作った SSR 機能を使っているので、サーバサイドでデータを取得し HTML 化します。また、ルーティングのページ遷移で飛んできた場合は、クライアント側で fetch が行われます。

- src/routes/index.tsx

```tsx
import { type Remix } from "@remix-run/dom";
import { SSRFetch, useSSR } from "../provider/SSRProvider";
import { Link } from "../provider/RouterProvider";

interface Center {
  name: string;
  enName: string;
  officeName?: string;
  children?: string[];
  parent?: string;
  kana?: string;
}
interface Centers {
  [key: string]: Center;
}
interface Area {
  centers: Centers;
  offices: Centers;
  class10s: Centers;
  class15s: Centers;
  class20s: Centers;
}

export default function (this: Remix.Handle) {
  return (
    <SSRFetch
      name="area-list"
      action={() =>
        fetch("https://www.jma.go.jp/bosai/common/const/area.json").then((v) =>
          v.json()
        )
      }
    >
      <List />
    </SSRFetch>
  );
}

function List(this: Remix.Handle) {
  const { value, state } = useSSR<Area>(this);
  return (
    <div className="p-2">
      {state === "loading" && <div>Loading...</div>}
      {value &&
        Object.entries(value.offices).map(([code, { name }]) => (
          <div key={code}>
            <Link href={`/weather/${code}`}>{name}</Link>
          </div>
        ))}
    </div>
  );
}
```

## 天気の情報表示

パスパラメータから ID を取得して、対象の天気情報を取得し表示します。このページを直接ブラウザで開いた場合は SSR、遷移してきた場合はクライアント fetch になります。

- src/routes/wether.$id.tsx

```tsx
import { type Remix } from "@remix-run/dom";
import { SSRFetch, useSSR } from "../provider/SSRProvider";
import { Link, useParams } from "../provider/RouterProvider";

interface Weather {
  publishingOffice: string;
  reportDatetime: Date;
  targetArea: string;
  headlineText: string;
  text: string;
}

export default function (this: Remix.Handle) {
  const { id } = useParams(this);
  return (
    <SSRFetch
      name={`weather-${id}`}
      action={() =>
        fetch(
          `https://www.jma.go.jp/bosai/forecast/data/overview_forecast/${id}.json`
        ).then((v) => v.json())
      }
    >
      <WeatherItem />
    </SSRFetch>
  );
}

function WeatherItem(this: Remix.Handle) {
  const { value, state } = useSSR<Weather>(this);
  return (
    <div className="p-2">
      <div>
        <Link href="/">戻る</Link>
      </div>
      {state === "loading" && <div>Loading...</div>}
      {value && (
        <div className="max-w-4xl">
          <h1 className="text-2xl font-bold">{value.targetArea}</h1>
          <div>{new Date(value.reportDatetime).toLocaleString()}</div>
          <div>{value.headlineText}</div>
          <pre className="whitespace-pre-wrap">{value.text}</pre>
        </div>
      )}
    </div>
  );
}
```

## 出力結果

SSR での動作が確認できます。ただ Remix3 のバグでテキスト部分のハイドレーションエラーを起こしています。これはどうにもなりませんでした。

https://remix3-sample06.mofon001.workers.dev/

![](/images/remix3-framework/2025-10-21-09-33-37.png)

![](/images/remix3-framework/2025-10-21-09-34-02.png)

# まとめ

Remix3 の足りない機能を自作して、フレームワークっぽく動作させることができました。これで`React Router`に近い体験で開発を行えます。ただ、現時点での懸念点は Remix3 の HTML に対するハイドレーションがかなりバグってることです。複雑な HTML を出力してハイドレーションを行うと仮想 DOM のマウントに失敗し、ノードが二重になったり、適切にイベントが処理できなくなったりします。また、TypeScript による型づけが甘く、React のようにコンポーネントの関数に generics で型を付けようとすると、unknown に変換されるという洗礼を受けます。

現時点で Remix3 は開発中なので、あくまで遊びとして楽しんでください。
