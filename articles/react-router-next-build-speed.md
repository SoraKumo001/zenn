---
title: "React Router(rolldown-vite)とNext.js(turbo-pack)のビルド速度と比較する"
emoji: "🔖"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [reactrouter, nextjs, react, typescript, javascript]
published: true
---

# rolldown-vite とは

`rolldown-vite` は、Vite に Rust 製のバンドラー Rolldown を統合した実験的パッケージです。`React Router`のように Vite ベースのバンドラを使用している環境では、簡単に差し替えを行えます。対して、`Next.js`では Turbopack という Rust ベースのバンドラが使用可能です。それぞれ Rust 製ということもあり、その速度に興味が湧くところですが、ビルド速度を比較した情報を見かけないので、実際にやってみることにしました。

# ビルドに使うリポジトリ

ちょうどマークダウンエディタの作り方を解説する記事を書いていたので、ほぼ同じ動作をするコードを`Next.js`用と`React Router`用で作ってみました。

https://github.com/SoraKumo001/next-unified

https://github.com/SoraKumo001/react-router-markdown

# 測定結果

手元の環境でビルドさせてみた結果

Next.js は React Router のビルドと同じ条件になるように`--no-lint`オプションと`ignoreBuildErrors: true`を追加して、eslint と TypeCheck を省いています。

| フレームワーク | バージョン | バンドラ                    |   速度 |
| -------------- | ---------- | --------------------------- | -----: |
| Next.js        | 15.5.3     | Turbopack                   | 12.88s |
| Next.js        | 15.5.3     | webpack                     | 16.72s |
| React Router   | 7.8.2      | rolldown-vite(NativePlugin) |  3.03s |
| React Router   | 7.8.2      | rolldown-vite               |  4.16s |
| React Router   | 7.8.2      | vite                        |  5.19s |

- Next.js のビルド

![](/images/react-router-next-build-speed/2025-09-18-08-50-52.png)

- React Router のビルド

![](/images/react-router-next-build-speed/2025-09-13-15-07-13.png)

# まとめ

Next.js と React Router のビルド速度は、比較どうこうという以前に勝負になっていない結果となりました。Next.js の開発状況を鑑みるに、今後も劇的な改善は望めなさそうで、当分はこの状況が続くと見ています。

React のフレームワークとして圧倒的なシェアを誇る Next.js ですが、コード量が増えると一次関数的にビルド時間が増えます。大規模なプロジェクトだと、PR を出すときに発生する CI のチェック待ちが馬鹿になりません。Vercel にベンダーロックインしている状況ではない場合や、とくに新規プロジェクトの時は、別のフレームワークに切り替えることを検討したほうが良いかもしれません。
