---
title: "Next.jsで通信アプリを簡単にSSRする"
emoji: "🐙"
type: "tech"
topics: ["graphql", "nextjs", "react", "typescript", "ssr"]
published: true
---

※サンプルコード
<https://github.com/SoraKumo001/use-fetch-sample01>

# SSRは面倒くさい

外部からデータを引っ張ってくるプログラムでSSRを行うためには、サーバ側で処理したデータをクライアントに引き渡す処理を書かなければなりません。この引き渡し処理をデータ取得処理の種類ごとに容易しなければならないのです。

Next.jsの場合はgetInitialPropsやgetServerSidePropsを作成して通信処理を書き、受け取った結果をpropsに渡してSSRを行います。クライアントでリロード処理が生じる場合は、この通信部分のコードを別に書かなければなりません。

これを解決する手段としてGraphQL+Apolloを使うという手段があります。`App.getInitialProps`にSSR用データを自動で構築する仕組みを作ってしまえば、あとは普通にプログラムを書けば良いのです。通信処理を二重に書く必要はありません。ではGraphQL以外で、しかも簡単にやるにはにはどうしたらいいかという紹介していきます。

# サンプルの天気予報アプリ

`src/pages/[id]/index.tsx`

```tsx
import React from 'react';
import Link from 'next/link';
import { useRouter } from 'next/router';
import { useFetch } from '@react-libraries/use-fetch';
import { Weather } from '../../components/Weather';
import { WeatherType } from '../../types/weatherType';

export const Page = () => {
  const router = useRouter();
  const id = router.query['id'];
  const { data, error, isValidating, dispatch } = useFetch<WeatherType>(
    `https://weather.tsukumijima.net/api/forecast/city/${id}`,
    { skip: isNaN((id as unknown) as number) } //IDが数値以外なら実行しない
  );
  return (
    <>
      <style jsx>{`
        .button {
          margin-left: 16px;
        }
      `}</style>
      <div>
        <Link href="/">←(戻る)</Link>
        <button
          className="button"
          onClick={() => {
            dispatch();
          }}
        >
          再読み込み
        </button>
      </div>

      {isValidating && <div>読み込み中</div>}
      {error && <div>エラー{String(error)}</div>}
      {data && <Weather value={data} />}
    </>
  );
};

export default Page;
```

天気予報のデータを`https://weather.tsukumijima.net/api/forecast/city/[ID]`から拾ってきて表示するプログラムです。データの取得状況が変化するごとにuseFetchがキーになってデータのキャッシュとコンポーネントの再描画を行います。これだけなら有名どころの[useSWR](https://swr.vercel.app/)と同じような動作です。

- スクリーンショット  
![](https://storage.googleapis.com/zenn-user-upload/a8fvzf7568qfwdhbrb6vwaxclv57)

## 自動SSR

通信データを利用してSSRを行うためのコードは以下のようになります。

`src/pages/_app.tsx`

```tsx
import { AppContext, AppProps } from 'next/app';
import { CachesType, createCache, getDataFromTree } from '@react-libraries/use-fetch';

const IS_SERVER = !process.browser;

const App = (props: AppProps & { cache: CachesType }) => {
  const { Component, cache } = props;
  !IS_SERVER && createCache(cache);
  return <Component />;
};
App.getInitialProps = async ({ Component, router, AppTree }: AppContext) => {
  const cache = IS_SERVER
    ? await getDataFromTree(<AppTree Component={Component} pageProps={{}} router={router} />)
    : {};
  return { cache };
};
export default App;
```

getDataFromTreeがPageコンポーネントを生成します。これはApolloと同じような動作となります。サーバ側のコンポーネントが作ったキャッシュデータを送って、クライアントでキャッシュデータを再生成しています。

App.getInitialPropsにこの流れを書く利点は、これだけ書いておけばどこでuseFetchを使っても、自動的にSSRされるようになることです。

SSRから引き渡されたキャッシュに存在していないデータは、SPA時に通信が行われ取りに行くようになっています。このあたりは[useSWR](https://swr.vercel.app/)と同じ動きになります。

## 楽ちん

面倒な記述が省略され、SSRのプログラムが楽ちんで作れるようになりまた。ちなみにuseFetchはキャッシュデータの管理にReduxやContextAPIで必須のProviderやStore的なものを必要としません。楽ちんです。