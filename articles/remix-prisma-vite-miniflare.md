---
title: "Vite@6 で Remix + Prisma が動く Cloudflare の HMR 対応開発環境を作る"
emoji: "🙌"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [vite, remix, cloudflare, workerd, prisma]
published: true
---

# 現在の開発環境

Remix を使った Cloudflare 向けの開発環境では、Vite が Node.js 上で動作し、開発コードも Node ランタイムで実行されています。しかし、Cloudflare は Workerd ランタイムで動作するため、開発時とデプロイ時で動作方法や呼び出すモジュールに違いが生じます。

この問題を解決する最良の方法は、開発時にも Workerd ランタイムでコードを実行することです。しかし、通常この方法を取ると、開発用のコードをすべてビルドしてから実行する必要があり、Vite の HMR が利用できなくなるため、開発効率が低下してしまいます。

では、どうすればよいのでしょうか？それは、Vite 自体は Node ランタイムで実行し、開発コードを Workerd ランタイムで動作させることです。このアプローチはすでに進行中で、Vitest ではある程度機能する段階まで来ています。

この記事では Vite プラグインを作成し、Remix を Workerd ランタイム上で動作させ、Prisma で DB を操作するところまでを解説します。

動作サンプルは以下のリポジトリで確認できます。

https://github.com/SoraKumo001/remix-prisma-vite-miniflare/

# Vite + Miniflare で開発コードを Workerd ランタイムで動作させるたのめ概略図

![](/images/remix-prisma-vite-miniflare/2024-09-30-09-03-33.png)

開発コードを Vite Environments で HMR 対応の形式に変換し、Workerd 上に組み込んだ Module Runner で動作させるという流れになります。

# Miniflare

Miniflare は、Workerd ランタイムををローカルでエミュレートするためのツールです。Miniflare を使うことで、Cloudflare Workers/Pages の開発をローカルで行うことができます。Vite で読み込んだコードを Miniflare で実行することで、開発時にも Workerd ランタイムで動作することができます。それだけ言うと、とても簡単なことのように思えますが、実際にはいくつかの苦難が待ち受けています。

- Miniflare 上で重要な機能

| 機能                        | 説明                                                                    |
| --------------------------- | ----------------------------------------------------------------------- |
| modules                     | Workerd 上にあらかじめ組み込んでおくモジュールを設置                    |
| unsafeEvalBinding           | テキスト状態のコードを Workerd 側で実行可能な状態に変換する関数名を設定 |
| serviceBindings             | Workerd 側とやり取りする値や関数を設置                                  |
| unsafeModuleFallbackService | Workerd 側が要求したモジュールを返す                                    |

https://github.com/SoraKumo001/remix-prisma-vite-miniflare/blob/master/vitePlugin/miniflare.ts

## ModuleRunner

modules に組み込むコードは「ModuleRunner」という名前で、Vite 側が用意しています。この ModuleRunner によって、Workerd ランタイムと Node.js 上の Vite が連携して動作するようになります。

- ModuleRunner の重要機能

| 機能                          | 説明                                                                                                     |
| ----------------------------- | -------------------------------------------------------------------------------------------------------- |
| ModuleRunner:transport        | Workerd 側が開発コードを要求し、Node.js 側の Vite からビルド済みコードを取り出す                         |
| ModuleRunner:runInlinedModule | Vite の形式で変換されたコードを Workerd 側で実行可能な状態に変換し実行                                   |
| fetch                         | Vite から渡されたファイル名(Remix の初期実行コード)を元に、Remix を実行下の状態にして Request を処理する |

https://github.com/SoraKumo001/remix-prisma-vite-miniflare/blob/master/vitePlugin/miniflare_module.ts

## @remix-run/cloudflare

ModuleRunner が実行する Remix の基本コードでは、クライアントからのリクエストを受け取り、Remix の処理を適切に振り分けます。

https://github.com/SoraKumo001/remix-prisma-vite-miniflare/blob/master/vitePlugin/server.ts

## unsafeModuleFallbackService

外部モジュールを Workerd 側に返すための関数は、非常に手間がかかる部分です。要求されたモジュールを Workerd で実行可能なコードに変換する必要があります。

まず大前提として、Workerd は ESM（ECMAScript モジュール）形式を使用しています。unsafeModuleFallbackService からは一応、CommonJS 形式を明示してモジュールを返すことも可能ですが（その場合も require は使えません）、実際にはまともに動作しないことが多いです。結局、CommonJS のモジュールは ESM に変換する必要があります。

https://github.com/SoraKumo001/remix-prisma-vite-miniflare/blob/master/vitePlugin/unsafeModuleFallbackService.ts

require は createRequire を使って互換関数を生成しています。これにより、ある程度の動作は可能になります。しかし、変換を頑張って行っても、依存パッケージの中に CommonJS から ESM を require しているコードが含まれている場合、うまく連結できないと致命的な問題が発生します。

さらに、ESM から CommonJS を import している場合、エクスポートされた名前が取り出せなかったりと、状況は非常にカオスになります。このため、モジュールの互換性を保つことが難しく、開発において多くの課題が生じることになります。

# プラグイン作成

## Miniflare を統合する

Miniflare に必要なパラメータを設定して作成したら、それを Vite プラグインとして呼び出せるようにします。これにより、Vite のビルドプロセスに Miniflare の機能を統合し、開発時によりスムーズな体験を提供することができます。具体的には、Miniflare の設定を Vite プラグインとして組み込むことで、ローカル環境でのテストやデバッグが容易になります。

https://github.com/SoraKumo001/remix-prisma-vite-miniflare/blob/master/vitePlugin/index.ts

## unsafeModuleFallbackService で変換不能コードに白旗を上げる

Remix 単体での動作には問題ありませんが、Prisma を使用する際に必要なモジュールの中で、@prisma/adapter-pg-worker と@prisma/driver-adapter-utils の 2 つは unsafeModuleFallbackService で変換できませんでした。これらのモジュールは、vite.config.ts でバンドルして結合させることで動作させる必要があります。

https://github.com/SoraKumo001/remix-prisma-vite-miniflare/blob/master/vite.config.ts

最終的に、モジュールの呼び出しに失敗したパッケージを検出して、実行時に noExternal に放り込むという方法で対処しました。ただ、この検出作業で起動時間が遅くなるので、最初から記述しておいたほうがスムーズです。

# Remix で Prisma を使う

Workerd ランタイム上でしか動かない `@prisma/adapter-pg-worker` と `@prisma/pg-worker` が、開発モードで動くようになりました。

https://github.com/SoraKumo001/remix-prisma-vite-miniflare/blob/master/app/routes/_index.tsx

# まとめ

Vite@6 で Workerd ランタイムが簡単に動くという噂を聞いて試してみたところ、実際には prisma まで動くレベルのものは存在しませんでした。仕方なく自分で実装を試みましたが、モジュール関連の問題が深刻で、非常に面倒な状況になっています。

なんとか動く状態まで持っていきましたが、そのうちもっと適切な実装をしたプラグインが登場するはずなので、もうしばらく待ちましょう。
