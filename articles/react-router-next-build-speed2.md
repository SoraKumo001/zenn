---
title: "ビルド速度が劇的に向上した Next.js@16 と React Routerとのビルド速度と比較する"
emoji: "🔖"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [reactrouter, nextjs, react, typescript, javascript]
published: true
---

# Next.js@16 の登場

2025/10/21 に`Next.js 16`がリリースされました。ビルド速度が向上したとのことなので早速確認してみます。

# ビルドに使うリポジトリ

マークダウンエディタの作り方を解説する記事で使っていた、ほぼ同じ動作をするコードを`Next.js`用と`React Router`用で利用しています。

https://github.com/SoraKumo001/next-unified

https://github.com/SoraKumo001/react-router-markdown

# 測定結果

手元の環境でビルドさせてみた結果

Next.js は React Router のビルドと同じ条件になるように`ignoreBuildErrors: true`を追加して、TypeCheck を省いています。lint を行わないというオプションは廃止され、最初から無効になっているようです。

| フレームワーク | バージョン | バンドラ                    |   速度 |
| -------------- | ---------- | --------------------------- | -----: |
| Next.js        | 16.0.0     | turbopack                   |  6.61s |
| Next.js        | 16.0.0     | webpack                     | 19.66s |
| Next.js        | 15.5.3     | turbopack                   | 12.88s |
| Next.js        | 15.5.3     | webpack                     | 16.72s |
| React Router   | 7.8.2      | rolldown-vite(NativePlugin) |  3.03s |
| React Router   | 7.8.2      | rolldown-vite               |  4.16s |
| React Router   | 7.8.2      | vite                        |  5.19s |

- Next.js のビルド

![](/images/react-router-next-build-speed/2025-10-23-19-38-44.png)

- React Router のビルド

![](/images/react-router-next-build-speed/2025-09-13-15-07-13.png)

# まとめ

Next.js が React Router のビルド速度にだいぶ近づいてきました。ただ、webpack を指定すると以前より遅くなるという謎の挙動なので、互換性重視で Next.js を webpack でビルドする場合は気をつけてください。
