---
title: "Cloudflare Workers + Hono + Vite + React で SSR を実現する"
emoji: "🦁"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [cloudflare, hono, vite, react, miniflare]
published: true
---

# React と SSR

React で SSR を行う場合は Next.js や Remix などのフロントエンドフレームワークを使うのが一般的です。しかし今回は Vite 用の Hono プラグインを使って、ほぼ素の React で 実現していきます。

Cloudflare へのデプロイに関しては Pages ではなく Workers を使用しています。Static Assets が使えるようになった現在、Pages を使用する必要性が無くなりました。

また、最後におまけで Miniflare を使って Workerd の VM 上で開発中のコードを動かす方法も紹介します。

# Workers と Hono

このサンプルはバックエンドに Hono を使い、React コンポーネント上で非同期処理を行った上で SSR を行います。他の方が作ったサンプルを当たってみたら、データ取得の非同期処理が Hono 側で完結してしまっていて、かなり用途が限定されていたので、もう少し自由度が高いものを作りました。

フロントエンド部分に関しては HMR 対応です。バックエンド側の修正は自動リロードはさせていないので、必要なら手動でブラウザのリロードをかける必要があります。

実行結果は以下のリンクから確認できます。

https://hono-ssr-react.mofon001.workers.dev/

## 実行内容

![](/images/hono-ssr-react/2024-10-24-14-39-06.png)

## サンプル解説

### package.json

構造が単純なので、開発モードの起動やビルドはシンプルです。ちなみに Vite@6 を使っていますが、この後に解説する Miniflare を使う場合に必要なので入れているだけなので@5 でも問題ありません。Workspace に複数バージョンの Vite を入れると、型定義が競合してエラーが出るのでバージョンを @6 で揃えています。

https://github.com/SoraKumo001/hono-ssr-react/blob/master/packages/hono-ssr-react/package.json

### vite.config.ts

Vite で Hono を使う場合は、`vite.config.ts` に`@hono/vite-dev-server`と`@vitejs/plugin-react`プラグインを追加します。どちらも開発モードで必要になります。

`@hono/vite-dev-server`で`injectClientScript: false`を設定していますが、これは Hono のプラグインが最後尾に`<script type="module" src="/@vite/client" />`を追加するのを阻止するためです。この方法だとこの後使う renderToReadableStream で stream を返す時に問題が起こるのと、正常に追加されたとしても HMR が適用されずフルリロードになってしまうので、処理を止めています。

また、Vite のビルド対象ファイルに関してはクライアント側の指定のみになります。デプロイ時に wrangler がバックエンド側をビルドします。

https://github.com/SoraKumo001/hono-ssr-react/blob/master/packages/hono-ssr-react/vite.config.ts

### wrangler.toml

`assets = { directory = "./dist"}`で Static Assets を設定し、クライアント側にファイルを渡せるようにします。また、`main = "./dist/index.js"`で Workers の起動ファイルを指定します。

https://github.com/SoraKumo001/hono-ssr-react/blob/master/packages/hono-ssr-react/wrangler.toml

### src/server.ts

`renderToReadableStream`を使って React のコンポーネントを stream で返します。この関数はコンポーネント内で`throw promise`が発生すると、その promise が解決されるまで待機し、解決後にコンポーネントを再評価します。この機能を利用して SSR を実現しています。

また、開発モード時に HMR を行うため`@react-refresh`を呼び出しています。そして`src/client.tsx`によって、Vite 側にクライアント側のコードを要求しています。

https://github.com/SoraKumo001/hono-ssr-react/blob/master/packages/hono-ssr-react/src/server.tsx

### src/client.tsx

Server 側で送った HTML 上にコンポーネントを Hydrate しています。これでクライアント側で React が動きます。

https://github.com/SoraKumo001/hono-ssr-react/blob/master/packages/hono-ssr-react/src/client.tsx

### src/App.tsx

`next-ssr`を利用しています。このパッケージは renderToReadableStream 上で発生した非同期データをクライアントに転送するためのものです。元々 Next.js 用に作ったものですが、React の標準機能しか使っていないので、Remix やフレームワーク無しの状態でも使えます。

https://github.com/SoraKumo001/hono-ssr-react/blob/master/packages/hono-ssr-react/src/App.tsx

- src/page/index.tsx

天気予報データを取得して表示しています。SSR で作られたデータはクライアント側でキャッシュされ、Reload しない限りは Client 側では fetch されません。

https://github.com/SoraKumo001/hono-ssr-react/blob/master/packages/hono-ssr-react/src/page/index.tsx

# Routing を追加する

単純に 1 ページだけだとサンプルとしての実用性が皆無なので、Routing を追加します。

実行結果は以下のリンクから確認できます。

https://hono-ssr-react-routing.mofon001.workers.dev/

## 実行内容

![](/images/hono-ssr-react/2024-10-24-14-41-05.png)
![](/images/hono-ssr-react/2024-10-24-14-41-38.png)

## サンプル解説

### src/server.tsx

Html コンポーネントを作って内容を移しています。また、SSR 時にどの path にアクセスされたかを取得して、出来るように url をコンポーネントに渡しています。

https://github.com/SoraKumo001/hono-ssr-react/blob/master/packages/hono-ssr-react-routing/src/server.tsx

### src/Components/Html.tsx

基本的に先程の server.tsx の内容と同じです。ただし、こちらは新たに`RouterProvider`を追加して、ルーティングの準備をしています。

https://github.com/SoraKumo001/hono-ssr-react/blob/master/packages/hono-ssr-react-routing/src/Components/Html.tsx

### src/Components/RouterProvider.tsx

外部ライブラリを使わずルーティングを行うため、`popstate`などのイベント処理を行っています。アドレスの変更を Context で渡します。

https://github.com/SoraKumo001/hono-ssr-react/blob/master/packages/hono-ssr-react-routing/src/Components/RouterProvider.tsx

### src/App.tsx

必要最小限で書いているので読みにくいですが、パスパラメータを取得して、それに応じたコンポーネントを返すようにしています。何もない場合は例外を返し、Hono 側がそれを受け取ったら 404 のステータスを返します。

https://github.com/SoraKumo001/hono-ssr-react/blob/master/packages/hono-ssr-react-routing/src/Components/App.tsx

### src/page/index.tsx

天気予報の都道府県一覧を返します。

https://github.com/SoraKumo001/hono-ssr-react/blob/master/packages/hono-ssr-react-routing/src/pages/index.tsx

### src/page/weather.tsx

天気予報を返します。

https://github.com/SoraKumo001/hono-ssr-react/blob/master/packages/hono-ssr-react-routing/src/pages/weather.tsx

# Miniflare を使って Workerd の VM で開発コードを動かす

おまけで Vite@6 の Environment API を使って、開発中のコードを Workerd の VM 上で動かしてみます。通常は Vite の開発モードでは Node.js ランタイム上で動きます。Node.js 環境上でも Service Binding は getPlatformProxy という機能である程度補えるのですが、cache 系などの機能は再現できません。そこで、Miniflare を使って Workers の VM 上で動かすことで、開発中のコードをより正確に再現できるようにします。

今回の内容は Cache API でカウントが増える様子を確認できます

## Vite Plugin の作成

この内容だと `@hono/vite-dev-server` では対応できないので、新しく Vite Plugin を作成します。少々複雑なので、以下のリンクからコードを確認してください。

https://github.com/SoraKumo001/hono-ssr-react/blob/master/packages/hono-ssr-react-miniflare/vitePlugin/index.ts
https://github.com/SoraKumo001/hono-ssr-react/blob/master/packages/hono-ssr-react-miniflare/vitePlugin/miniflare.ts
https://github.com/SoraKumo001/hono-ssr-react/blob/master/packages/hono-ssr-react-miniflare/vitePlugin/miniflare_module.ts
https://github.com/SoraKumo001/hono-ssr-react/blob/master/packages/hono-ssr-react-miniflare/vitePlugin/unsafeModuleFallbackService.ts
https://github.com/SoraKumo001/hono-ssr-react/blob/master/packages/hono-ssr-react-miniflare/vitePlugin/utils.ts

実行結果は以下のリンクから確認できます。

https://hono-ssr-react-routing.mofon001.workers.dev/

## 実行内容

![](/images/hono-ssr-react/2024-10-24-14-43-27.png)
![](/images/hono-ssr-react/2024-10-24-14-43-48.png)

## サンプル解説

- vite.config.ts

先程作った Vite Plugin を追加します。Worked 上でのモジュールの解決が面倒なので、Entry ファイルの段階で全て bundle しています。

https://github.com/SoraKumo001/hono-ssr-react/blob/master/packages/hono-ssr-react-miniflare/vite.config.ts

- src/server.tsx

Cache API を使ってカウンタを作っています。もちろん、本来こういう使い方をするものではありません。

https://github.com/SoraKumo001/hono-ssr-react/blob/master/packages/hono-ssr-react-miniflare/src/server.tsx

- src/Components/Count.tsx

先ほど作った API からカウントを取得して表示するコンポーネントです。CloudflareWorkers は`.workers.dev`にデプロイした時、自己の API を SSR 時に呼び出すのが少々面倒で、自分自身を ServiceBinding しないといけません。カスタムドメインを使った場合はその必要はありません。

https://github.com/SoraKumo001/hono-ssr-react/blob/master/packages/hono-ssr-react-miniflare/src/Components/Count.tsx

- src/Components/RouterProvider.tsx

自己参照 URL を作るための処理を追加しています。

https://github.com/SoraKumo001/hono-ssr-react/blob/master/packages/hono-ssr-react-miniflare/src/Components/RouterProvider.tsx

# まとめ

フロントエンドフレームワークを利用せずに、React で SSR を行う方法を紹介しました。また、自分で Plugin を作れば、開発中のコードを Workers の VM 上で動かすことも可能です。
