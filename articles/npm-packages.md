---
title: "Next.jsで対象ユーザのnpmパッケージリストを作成しSSRでOGPも作る"
emoji: "😽"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [npm, nextjs, react, typescript]
published: true
---

# npm のパッケージリスト

npm にパッケージを公開し続けていたら、気がつくと 50 を超えるパッケージを公開していました。これらのパッケージのダウンロード状態などを個別に把握するのは辛いので、一覧表示するページを作成しました。

https://next-npm.vercel.app/?name=sora_kumo&sort=3

![](/images/npm-packages/2024-07-31-09-09-57.png)

# データの取得方法

## npm パッケージの検索

以下のアドレスで GET リクエストを送ると、指定したユーザがメンテナしているパッケージの一覧を取得できます。

`https://registry.npmjs.org/-/v1/search?text=maintainer:${name}&size=1000`

## ユーザー情報の取得

以下のアドレスで GET リクエストを送ると、指定したユーザの情報を取得できます。

`https://www.npmjs.com/~${name}`

ただし普通にアクセスすると HTML で返ってくるので、JSON 形式で欲しい場合は以下のヘッダを追加します。

`headers: { "X-Spiferack": "1" }`

また、こちらは CORS が許可されていないので、バックエンド側で取得してからフロントに渡す必要があります。

# フロントの作成

## \_app.tsx

getHost でホスト名をヘッダから取得する機能を追加しています。フロントからバックエンドにリクエストを送る際に、ホスト名を指定するためです。また SSRProvider を加えています。これは SSR を行うための Provider です。これを入れておくだけで、Next.js の標準機能をスルーして SSR を行うことができます。

```tsx
import { IncomingMessage } from "http";
import { AppContext, AppProps } from "next/app";
import "./global.css";
import { SSRProvider } from "next-ssr";

const App = ({ Component, pageProps }: AppProps<{ host?: string }>) => {
  return (
    <SSRProvider>
      <Component {...pageProps} />
    </SSRProvider>
  );
};

App.getInitialProps = async (context: AppContext) => {
  const host = getHost(context?.ctx?.req);
  return {
    pageProps: {
      host,
    },
  };
};

export const getHost = (req?: Partial<IncomingMessage>) => {
  const headers = req?.headers;
  const host = headers?.["x-forwarded-host"] ?? headers?.["host"];
  if (!host) return undefined;
  const proto =
    headers?.["x-forwarded-proto"]?.toString().split(",")[0] ?? "http";
  return headers ? `${proto}://${host}` : undefined;
};

export default App;
```

## pages/index.tsx

`useSSR`を使うと、引数で指定した非同期処理で取得したデータが SSR されます。Next.js の getServerSideProps などは不要です。ServerComponents のような仕組みもいりません。コンポーネント上に非同期処理を書けば、それが SSR されます。

SSR 用に取得したデータは OGP 生成で利用しています。これでパッケージリストを SNS などに貼り付けたときに、カードが表示されます。

```tsx
import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";
import { useSSR } from "next-ssr";
import {
  FormEventHandler,
  MouseEventHandler,
  useDeferredValue,
  useEffect,
  useMemo,
  useState,
} from "react";
import { DateString } from "../libs/DateString";
import { NpmObject, NpmPackagesType } from "../types/npm";

const usePackages = (name: string, host?: string) => {
  const { data } = useSSR<[NpmPackagesType, string] | undefined>(
    () =>
      Promise.all([
        fetch(
          `https://registry.npmjs.org/-/v1/search?text=maintainer:${name}&size=1000`
        ).then((r) => r.json()),
        fetch(`${host ?? ""}/user/?name=${name}`).then((r) => r.text()),
      ]),
    { key: name }
  );
  return data;
};

const usePackageDownloads = (objects?: NpmObject[]) => {
  const [downloads, setDownloads] = useState<Record<string, number[]>>({});
  const downloadsDelay = useDeferredValue(downloads);
  useEffect(() => {
    if (objects) {
      objects.forEach((npm) => {
        const name = npm.package.name;
        setDownloads((v) => ({ ...v, [name]: Array(3).fill(undefined) }));
        const periods = ["last-year", "last-week", "last-day"] as const;
        periods.forEach((period, index) => {
          fetch(`https://api.npmjs.org/downloads/point/${period}/${name}`)
            .then((r) => r.json())
            .then((r) => {
              setDownloads((v) => {
                const d: number[] = v[name] ?? [];
                d[index] = r.downloads;
                return { ...v, [name]: d };
              });
            });
        });
      });
    }
  }, [objects]);
  return downloadsDelay;
};

export const NpmList = ({ host }: { host?: string }) => {
  const router = useRouter();
  const name =
    typeof router.query["name"] === "string" ? router.query["name"] : "";
  const value = usePackages(name, host);

  const downloads = usePackageDownloads(value?.[0].objects);
  const sortIndex = Number(router.query["sort"] || "0");

  const handleSubmit: FormEventHandler<HTMLFormElement> = (e) => {
    e.preventDefault();
    const query: Record<string, string | number> = {
      name: e.currentTarget.maintainer.value,
    };
    if (sortIndex) query["sort"] = sortIndex;
    router.push({ query });
  };
  const handleClick: MouseEventHandler<HTMLElement> = (e) => {
    const index = e.currentTarget.dataset["index"];
    router.replace({ query: { name, sort: index } });
  };
  const items = useMemo(() => {
    return value?.[0].objects
      .map((o) => o.package)
      .sort((a, b) => {
        switch (sortIndex) {
          default:
            return 0;
          case 1:
            return new Date(b.date).getTime() - new Date(a.date).getTime();
          case 2:
            return a.name < b.name ? -1 : 1;
          case 3:
          case 4:
          case 5:
            return (
              (downloads[b.name]?.[sortIndex - 3] ?? 0) -
              (downloads[a.name]?.[sortIndex - 3] ?? 0)
            );
        }
      });
  }, [value, sortIndex, downloads]);

  const title = name ? `${name} npm packages list` : "List of npm packages";
  const systemDescription = name
    ? `Number of npm packages is ${value?.[0].objects.length ?? 0}`
    : "System for listing npm packages";
  const imageUrl = value?.[1];

  return (
    <>
      <Head>
        <title>{`${name} npm list`}</title>
        <meta property="description" content={systemDescription} />
        <meta property="og:title" content={title} />
        <meta property="og:description" content={systemDescription} />
        <meta property="og:type" content="website" />
        <meta property="og:image" content={imageUrl} />
        <meta name="twitter:card" content={"summary"} />
      </Head>

      <form onSubmit={handleSubmit} className="flex items-center gap-2 p-1">
        <input
          name="maintainer"
          className="input input-bordered w-full max-w-xs"
          defaultValue={name}
        />
        <button className="btn" type="submit">
          設定
        </button>
        <Link
          href="https://github.com/SoraKumo001/next-npm"
          className="underline"
          target="_blank"
        >
          Source Code
        </Link>
      </form>

      <table className="table [&_*]:border-gray-300 [&_td]:border-x [&_td]:py-1 [&_th:hover]:bg-slate-100 [&_th]:border-x">
        <thead>
          <tr className="sticky top-0 cursor-pointer bg-white text-lg font-semibold">
            {["index", "date", "name", "year", "week", "day"].map(
              (v, index) => (
                <th key={v} onClick={handleClick} data-index={index}>
                  {v}
                </th>
              )
            )}
          </tr>
        </thead>
        <tbody className="[&_tr:nth-child(odd)]:bg-slate-200">
          {items?.map(({ name, date }, index) => (
            <tr key={name}>
              <td>{index + 1}</td>
              <td>{DateString(date)}</td>
              <td>
                <Link
                  href={`https://www.npmjs.com/package/${name}`}
                  target="_blank"
                >
                  {name}
                </Link>
              </td>
              {downloads[name]?.map((v, index) => (
                <td key={index}>{v}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
};
```

## app/user/route.ts

AppRoute 上に API を作成しています。こちらはユーザー情報を取得する API を使って、OPG 用の画像を取得しています。アドレスが JWT 形式になっているので、デコードしてから avatarURL を取得しています。ちなみに JWT はただの Base64 文字列なので、データを取り出すだけなら専用のライブラリは不要です。

```ts
import { NextRequest, NextResponse } from "next/server";
import { NpmUserType } from "../../types/npm";

export const GET = async (req: NextRequest): Promise<NextResponse> => {
  const url = new URL(req.url);
  const name = url.searchParams.get("name");
  if (!name) {
    return new NextResponse("name is required", { status: 400 });
  }
  const npmUser = await fetch(`https://www.npmjs.com/~${name}`, {
    headers: { "X-Spiferack": "1" },
  })
    .then((r) => r.json() as Promise<NpmUserType>)
    .catch(() => null);
  const img = npmUser?.scope?.parent.avatars.large;
  const token = img?.split("/")[2];
  const avatarURL = token && JSON.parse(atob(token.split(".")[1]))["avatarURL"];
  if (!avatarURL) return new NextResponse("Not Found", { status: 404 });
  return new NextResponse(avatarURL, { status: 404 });
};
```

# eslint の設定

## eslint.config.mjs

eslint を入れるとデフォルトで flat-config を使う形になったので設定例を紹介します。flat-config の趣旨としては、プラグインとルールの設定を種類ごとに分離してかけるようにしたのだろうと想像できるので、そのように設定しています。flat-config の情報はイマイチ情報が少ないです。

```mjs
/**
 * @type {import('eslint').Linter.FlatConfig[]}
 */
import { fixupPluginRules } from "@eslint/compat";
import eslint from "@eslint/js";
import eslintConfigPrettier from "eslint-config-prettier";
import importPlugin from "eslint-plugin-import";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import tailwind from "eslint-plugin-tailwindcss";
import tslint from "typescript-eslint";

export default [
  eslint.configs.recommended,
  ...tslint.configs.recommended,
  ...tailwind.configs["flat/recommended"],
  eslintConfigPrettier,
  {
    plugins: {
      react: fixupPluginRules(react),
    },
    rules: react.configs["jsx-runtime"].rules,
  },
  {
    plugins: {
      "react-hooks": fixupPluginRules(reactHooks),
    },
    rules: reactHooks.configs.recommended.rules,
  },
  {
    plugins: {
      import: importPlugin,
    },
    rules: {
      "@typescript-eslint/no-unused-vars": 0,
      "no-empty-pattern": 0,
      "no-empty": 0,
      "import/order": [
        "warn",
        {
          groups: [
            "builtin",
            "external",
            "internal",
            ["parent", "sibling"],
            "object",
            "type",
            "index",
          ],
          pathGroupsExcludedImportTypes: ["builtin"],
          alphabetize: {
            order: "asc",
            caseInsensitive: true,
          },
        },
      ],
    },
  },
];
```

# まとめ

最近 Next.js の AppRoute が話題になることが多いですが、その中でコンポーネント内に非同期処理を直書いて SSR 出来るという利点が語られることがあります。しかし今回やった通り、 PagesRouter でもそのまま書けます。もちろん ServerComponents は使う必要がありません。実は React 本体にコンポーネント内での非同期処理機能が搭載されているので、SSR にフレームワーク側の機能は不要なのです。
