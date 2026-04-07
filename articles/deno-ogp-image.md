---
title: "Deno Deploy + Cloudflare CDN で無料OGP画像生成"
emoji: "👋"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: ["deno", "ogp", "cloudflare", "typescript", "preact"]
published: true
---

この記事では、**Deno Deploy + Cloudflare CDN + Satoru** を組み合わせて、無料でOGP画像を動的に生成・配信する方法を紹介します。

# Deno Deployの新料金体系

以前のDeno DeployはDeno Deploy Classicという名称に変わり、2026年7月20日でサービスが終了することになりました。そして、Deno Deploy(v2)の新しい料金体系が発表されました。

https://deno.com/deploy/pricing

## 無料プランの内容

無料プラン（Freeプラン）では、個人開発や小規模なプロジェクトに十分なリソースが提供されています。

| 項目                     | 無料枠の上限   | 備考                               |
| ------------------------ | -------------- | ---------------------------------- |
| **リクエスト数**         | 月間 100万回   |                                    |
| **下り帯域幅 (Egress)**  | 月間 100GB     | 上りデータはカウントされません     |
| **CPU時間**              | 月間 15時間    |                                    |
| **メモリ時間**           | 月間 350 GB-h  |                                    |
| **アプリ (デプロイ) 数** | 最大 20個      | 同時にアクティブにできるデプロイ数 |
| **カスタムドメイン**     | 50個 / 組織    | ワイルドカードサブドメインは不可   |
| **チームメンバー数**     | 5人            |                                    |
| **Volume Storage**       | 1 GiB          |                                    |
| **KV Storage**           | 1 GiB          |                                    |
| **KV Read ユニット**     | 月間 450,000回 | 4KiB単位                           |
| **KV Write ユニット**    | 月間 300,000回 | 1KiB単位                           |

OGP画像生成のような用途であれば、無料枠で十分にまかなえます。ただし、クレジットカードを登録しないと大幅に制限が厳しくなるので注意が必要です。

## Classicからの主な変更点

新料金プランで最も大きな変更は **CPU時間の制限方式** です。

| 項目       | Classic（旧）         | v2（新）       |
| ---------- | --------------------- | -------------- |
| CPU時間    | **50ms / リクエスト** | **月間15時間** |
| 対応環境   | Denoのみ              | Node.jsも対応  |
| GitHub連携 | あり                  | あり           |

以前は1リクエストあたり50msというCPU時間制限があり、画像生成のような重い処理には不向きでした。新プランでは月間15時間のトータル制限に変わったため、1回のリクエストに数秒かかる処理でも問題なく実行できます。Cloudflare Workersの無料プランが10ms制限であることを考えると、かなり余裕があります。

また、Deno以外のランタイムにも対応し、Next.jsなどNode.jsベースのフレームワークも動かせるようになりました。Vercelと同様にGitHubと連携して自動デプロイが可能です。ただし、デプロイ時のビルド時間もCPU時間に含まれるため、節約するならビルド済みの内容をデプロイするのがおすすめです。

:::message
**唯一の弱点：** リージョンがアメリカとヨーロッパにしかありません。日本からのアクセスではレイテンシが大きくなりますが、次のセクションで紹介するCloudflare CDNとの連携で解決できます。
:::

# Cloudflare CDNによるキャッシュ構成

OGP画像のような「一度生成したら変わらないコンテンツ」は、CDNでキャッシュするのが効果的です。CloudflareのDNS設定でDeno Deployのアプリケーションをプロキシさせることで、CDNのキャッシュ機能を無料で利用できます。

```
ブラウザ/クローラー → Cloudflare CDN → Deno Deploy
                         ↑ キャッシュ済みなら
                         ここで返す（高速）
```

この構成のメリットは3つあります。

1. **高速な配信** — 初回生成後はCloudflareのエッジにキャッシュされ、二度目以降は高速に配信される
2. **CPU時間の節約** — キャッシュヒット時はDeno Deployのリソースを消費しない
3. **追加コスト0円** — Cloudflare CDNの利用料金は無料

ある程度大規模なサービスでもこの構成なら費用が嵩むことはほとんどありません。

# OGP画像生成の実装

## Satoruとは

OGP画像の動的生成ではVercelのSatoriが有名ですが、今回はSatoruを使います。AIをぶんまわして変換機能をC++でWebAssembly化したライブラリです。

https://www.npmjs.com/package/satoru-render

SatoriとSatoruの主な違いは以下の通りです。

| 項目             | Satori             | Satoru                    |
| ---------------- | ------------------ | ------------------------- |
| HTML/CSS対応範囲 | 限定的なFlexboxのみ | HTML/CSS全般              |
| グラデーション   | 制限あり           | フル対応                  |
| 縦書き           | 非対応             | 対応                      |
| CSSの複合レイヤー      | 非対応             | 対応                      |
| 入力形式         | JSX（React要素）   | HTML文字列（JSX変換も可） |

SatoruはHTML/CSSの幅広い機能をサポートしているため、複雑なデザインのOGP画像も簡単に作ることが出来ます。入力画像もWebPやAvifを標準サポートしています。

## 生成サンプル

サンプルプログラムをGitHubに用意しました。以下のようなOGP画像が生成されます。

![](/images/deno-ogp-image/2026-04-06-22-17-49.png)

https://github.com/SoraKumo001/satoru-deno-ogp-image

## コード解説

`Deno.serve`でHTTPサーバーを立ち上げ、クエリパラメータの`name`・`title`・`image`を受け取ってPNG画像を動的に生成します。

### 画像生成の核心部分

重要なのは、HTMLが文字列として`render`関数に渡される点です。HTMLを文字列として扱えれば、ReactでもVueでもSvelteでも対応可能です。フォントや画像は必要に応じてfetchで取得されます。

```tsx
  // HTMLをPNG画像にレンダリング（フォントは自動解決）
  const png = await render({
    value: html, // URL指定で外部のHTMLデータを読み込むことも可能
    css: await createCSS(html), // TailwindのCSSを生成(HTML側にCSSを書いてあれば、ここは不要)
    width: 1200,
    height: 630,
    format: "png",
  });

  // レスポンスを生成（本番はキャッシュヘッダ付き）
  const response = new Response(png as BodyInit, {
    headers: {
      "Content-Type": "image/png",
      "Cache-Control": isDev
        ? "no-cache"
        : "public, max-age=31536000, immutable",
      date: new Date().toUTCString(),
    },
  });
```

### コード全体

satoru-renderはHTMLをレンダリングするライブラリなので、JSXを使う場合は変換作業が必要になります。今回はPreactの`toHtml`とTailwind v4の`createCSS`ヘルパーを使っています。

```tsx
import { toHtml } from "satoru-render/preact";
import { render } from "satoru-render";
import { createCSS } from "satoru-render/tailwind";

Deno.serve(async (request) => {
  const url = new URL(request.url);
  if (url.pathname !== "/") {
    return new Response(null, { status: 404 });
  }

  // クエリパラメータからOGP画像の表示内容を取得
  const name = url.searchParams.get("name") ?? "Name";
  const title = url.searchParams.get("title") ?? "Title";
  const image = url.searchParams.get("image");

  // 開発環境かどうかの判定（開発時はキャッシュを無効化）
  const isDev =
    Deno.env.get("DENO_ENV") === "development" || url.hostname === "localhost";
  const cache = await caches.open("satoru-ogp2");
  const cacheKey = new Request(url.toString());

  // 本番環境ではキャッシュがあればそれを返す
  if (!isDev) {
    const cachedResponse = await cache.match(cacheKey);
    if (cachedResponse) return cachedResponse;
  }

  // JSXでOGP画像のレイアウトを定義し、HTMLに変換
  const html = toHtml(
    <html className="m-0 p-0">
      <head>
        <link
          href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@100..900&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="m-0 p-0 font-sans">
        <style>
          {`
          body {
            font-family: 'Noto Sans JP', 'emoji';
          }
          `}
        </style>
        <div className="relative flex h-157.5 w-300 overflow-hidden bg-[#0f172a]">
          {/* 背景の装飾（グロー効果） */}
          <div className="absolute -left-25 -top-25 flex size-150 rounded-full bg-indigo-600/20 blur-[100px]" />
          <div className="absolute -bottom-37.5 right-25 flex size-175 rounded-full bg-purple-600/15 blur-[120px]" />

          {/* メインコンテンツエリア */}
          <div className="z-10 flex size-full flex-row items-center justify-between p-15">
            {/* 左側：Glassmorphismスタイルのカード */}
            <div className="flex w-[62%] flex-col rounded-[48px] border border-white/10 bg-white/5 p-12 shadow-2xl backdrop-blur-2xl">
              <div className="mb-8 flex items-center">
                <div className="mr-5 h-1.5 w-16 rounded-full bg-linear-to-r from-indigo-500 to-purple-500 shadow-[0_0_20px_rgba(99,102,241,0.6)]" />
                <div className="flex text-xl font-bold uppercase tracking-[0.25em] text-indigo-300 drop-shadow-md">
                  Insight & Technology
                </div>
              </div>

              {/* タイトル */}
              <div className="mb-8 flex wrap-break-word text-[76px] font-black leading-[1.1] text-white drop-shadow-[0_12px_12px_rgba(0,0,0,0.6)]">
                {title}
              </div>

              {/* 名前 */}
              <div className="flex -rotate-4 underline decoration-wavy underline-offset-8 text-[30px] font-medium leading-relaxed text-slate-300 opacity-90 drop-shadow-lg">
                {name}
              </div>

              {/* タグ */}
              <div className="mt-12 flex items-center gap-4">
                <div className="flex rounded-2xl border border-indigo-500/30 bg-indigo-500/20 px-6 py-2.5 text-sm font-bold uppercase tracking-widest text-indigo-100 shadow-inner">
                  Cloudflare
                </div>
                <div className="flex rounded-2xl border border-purple-500/30 bg-purple-500/20 px-6 py-2.5 text-sm font-bold uppercase tracking-widest text-purple-100 shadow-inner">
                  OGP Generator
                </div>
              </div>
            </div>

            {/* 右側：画像コンテナ */}
            <div className="relative flex w-[33%] items-center justify-center">
              <div className="absolute flex size-115 rounded-full bg-indigo-500/10 blur-[50px]" />
              <div className="flex size-105 rotate-3 overflow-hidden rounded-[56px] border-4 border-white/20 shadow-[0_35px_60px_-15px_rgba(0,0,0,0.9)] drop-shadow-[0_20px_20px_rgba(0,0,0,0.5)]">
                {image && (
                  <img
                    className="size-full scale-110 object-cover"
                    src={image}
                    alt=""
                  />
                )}
              </div>
              <div className="absolute -bottom-7.5 -right-2.5 flex size-28 -rotate-12 items-center justify-center rounded-4xl shadow-2xl backdrop-blur-md">
                <div className="flex text-5xl font-bold text-white drop-shadow-lg">
                  ⭐️
                </div>
              </div>
            </div>
          </div>

          {/* 下部ブランディング */}
          <div className="absolute bottom-10 left-21.25 z-20 flex items-center">
            <div className="flex rounded-2xl border border-white/10 bg-slate-900/40 px-8 py-3 text-xl font-bold text-slate-100 shadow-xl backdrop-blur-xl">
              <span className="mr-2 flex text-indigo-400">@</span>
              satoru-cloudflare-ogp
            </div>
          </div>
        </div>
      </body>
    </html>,
  );

  // HTMLをPNG画像にレンダリング（フォントは自動解決）
  const png = await render({
    value: html,
    css: await createCSS(html),
    width: 1200,
    height: 630,
    format: "png",
  });

  // レスポンスを生成（本番はキャッシュヘッダ付き）
  const response = new Response(png as BodyInit, {
    headers: {
      "Content-Type": "image/png",
      "Cache-Control": isDev
        ? "no-cache"
        : "public, max-age=31536000, immutable",
      date: new Date().toUTCString(),
    },
  });

  // 本番環境ではWeb Cache APIにキャッシュを保存
  if (!isDev) {
    await cache.put(cacheKey, response.clone());
  }
  return response;
});
```

# まとめ

Deno Deploy v2の新料金体系により、CPU時間の制限が1リクエストあたり50msから月間15時間へと大幅に緩和されました。これにより、OGP画像生成のような比較的重い処理も無料プランで十分に運用できるようになっています。

リージョンが米国・欧州のみという弱点は、Cloudflare CDNをプロキシとして挟むことで解消できます。初回アクセスで生成した画像がCDNにキャッシュされるため、2回目以降は高速に配信され、Deno Deploy側のCPU時間も消費しません。

OGP画像の生成ライブラリとしては、Satoriの代替であるSatoruを紹介しました。SatoruはHTML/CSSの幅広い機能をサポートしており、Tailwind CSSやGoogleフォントと組み合わせることで、複雑なデザインのOGP画像も手軽に作成できます。

**Deno Deploy（無料） + Cloudflare CDN（無料） + Satoru** という構成で、コストをかけずに高品質なOGP画像生成サービスを構築できます。
