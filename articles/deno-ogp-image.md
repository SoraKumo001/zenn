---
title: "Deno Deploy でOGP画像生成"
emoji: "👋"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: []
published: false
---

# Deno Deployの新料金体系

以前のDeno DeployはDeno Deploy Classicという名称に変わり、2026年7月20日でサービスが終了することになりました。そして、Deno Deploy(v2)の新しい料金体系が発表されました。

https://deno.com/deploy/pricing

Deno Deployの無料プラン（Freeプラン）では、個人開発や小規模なプロジェクトには十分すぎるほどのリソースが提供されています。主な無料枠の内容は以下の通りです。

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

全体的に非常に制限が緩く設定されており、小規模なAPIサーバーの運用や、今回のようなOGP画像生成の用途であれば、無料で十分にまかなうことができます。ただしクレジットカードを登録しないと大幅に制限が厳しくなるので注意が必要です。

新料金プランの利点は、以前はCPU時間が１アクセスごとに50msに制限されていたのが、月間15時間に緩和されたことです。これにより、画像の変換処理などの重い処理を制限を受けずに行うことが出来ます。Cloudflareの無料プランの10ms制限よりも安心して使うことが出来ます。

また、新システムに移行してからはDeno以外のプラットフォームも扱えるようになりました。Next.jsのようなNode.jsベースのフレームワークも動かすことが出来ます。Vercelと同様に、GitHubと連携して自動ビルドとデプロイが可能になっています。ただ、デプロイ中のビルド時間がCPU時間の計算に含まれるので、節約するならビルド済みの内容をデプロイした方が良いでしょう。

利点 CPU時間の大幅な緩和
欠点 リージョンがアメリカとヨーロッパにしか無い

# OGP画像生成とキャッシュ構成

CPU時間制限が緩和されたので、OGP画像生成のような重い処理をDeno Deployで行うことが容易になりました。ただし、リージョンが2つしか無い上に、日本から遠いので、応答速度の面では優位性はありません。しかしこれには解決策があります。ドメイン名が必要になりますが、CloudflareのDNS設定で、DenoDeployのアプリケーションをプロキシさせるように設定すれば、CloudflareのCDNのキャッシュ機能を利用することが出来ます。これにより、一度生成したOGP画像はCloudflareのCDNにキャッシュされるため、二度目以降のアクセスは非常に高速になります。しかもキャッシュから配信される場合はDenoDeployのCPU時間は消費されない上に、Cloudflare側のCDN利用料金は無料です。この構成だと、ある程度大規模なサービスでもそうそう足が出ることはありません。

# OGP画像生成のプログラム

OGP画像の作成だとVercelのSatoriが有名ですが、今回はAIをぶん回して作ったSatoruを使います。

https://www.npmjs.com/package/satoru-render

Satoriが限定されたFlexbox上でイメージを作るのに対し、SatoruはHTML全般が使えます。CSSのレイヤーやグラデーション、最近の規格までサポートしています。縦書きもサポートしています。そのため、複雑なデザインのOGP画像も簡単に作ることが出来ます。


サンプルプログラムをGitHubに上げました。以下のようなOGP画像が生成されます。

![](/images/deno-ogp-image/2026-04-06-22-17-49.png)

https://github.com/SoraKumo001/satoru-deno-ogp-image

```tsx
import { toHtml } from "satoru-render/preact";
import { render } from "satoru-render";
import { createCSS } from "satoru-render/tailwind";

Deno.serve(async (request) => {
  const url = new URL(request.url);
  if (url.pathname !== "/") {
    return new Response(null, { status: 404 });
  }

  const name = url.searchParams.get("name") ?? "Name";
  const title = url.searchParams.get("title") ?? "Title";
  const image = url.searchParams.get("image");

  const isDev =
    Deno.env.get("DENO_ENV") === "development" || url.hostname === "localhost";
  const cache = await caches.open("satoru-ogp2");
  const cacheKey = new Request(url.toString());

  if (!isDev) {
    const cachedResponse = await cache.match(cacheKey);
    if (cachedResponse) return cachedResponse;
  }

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
          {/* Background Decorative Elements with Glow */}
          <div className="absolute -left-25 -top-25 flex size-150 rounded-full bg-indigo-600/20 blur-[100px]" />
          <div className="absolute -bottom-37.5 right-25 flex size-175 rounded-full bg-purple-600/15 blur-[120px]" />

          {/* Main Content Area */}
          <div className="z-10 flex size-full flex-row items-center justify-between p-15">
            {/* Left Content Card with Backdrop Filter (Glassmorphism) */}
            <div className="flex w-[62%] flex-col rounded-[48px] border border-white/10 bg-white/5 p-12 shadow-2xl backdrop-blur-2xl">
              <div className="mb-8 flex items-center">
                <div className="mr-5 h-1.5 w-16 rounded-full bg-linear-to-r from-indigo-500 to-purple-500 shadow-[0_0_20px_rgba(99,102,241,0.6)]" />
                <div className="flex text-xl font-bold uppercase tracking-[0.25em] text-indigo-300 drop-shadow-md">
                  Insight & Technology
                </div>
              </div>

              {/* Title with strong Drop Shadow */}
              <div className="mb-8 flex wrap-break-word text-[76px] font-black leading-[1.1] text-white drop-shadow-[0_12px_12px_rgba(0,0,0,0.6)]">
                {title}
              </div>

              {/* Subtitle with subtle Drop Shadow */}
              <div className="flex -rotate-4 underline decoration-wavy underline-offset-8 text-[30px] font-medium leading-relaxed text-slate-300 opacity-90 drop-shadow-lg">
                {name}
              </div>

              <div className="mt-12 flex items-center gap-4">
                <div className="flex rounded-2xl border border-indigo-500/30 bg-indigo-500/20 px-6 py-2.5 text-sm font-bold uppercase tracking-widest text-indigo-100 shadow-inner">
                  Cloudflare
                </div>
                <div className="flex rounded-2xl border border-purple-500/30 bg-purple-500/20 px-6 py-2.5 text-sm font-bold uppercase tracking-widest text-purple-100 shadow-inner">
                  OGP Generator
                </div>
              </div>
            </div>

            {/* Right Image Container with Drop Shadow and Layering */}
            <div className="relative flex w-[33%] items-center justify-center">
              {/* Outer Glow Ring */}
              <div className="absolute flex size-115 rounded-full bg-indigo-500/10 blur-[50px]" />

              {/* Image Frame with multiple shadows */}
              <div className="flex size-105 rotate-3 overflow-hidden rounded-[56px] border-4 border-white/20 shadow-[0_35px_60px_-15px_rgba(0,0,0,0.9)] drop-shadow-[0_20px_20px_rgba(0,0,0,0.5)]">
                {image && (
                  <img
                    className="size-full scale-110 object-cover"
                    src={image}
                    alt=""
                  />
                )}
              </div>

              {/* Decorative Floating Icon with Glass effect */}
              <div className="absolute -bottom-7.5 -right-2.5 flex size-28 -rotate-12 items-center justify-center rounded-4xl shadow-2xl backdrop-blur-md">
                <div className="flex text-5xl font-bold text-white drop-shadow-lg">
                  ⭐️
                </div>
              </div>
            </div>
          </div>

          {/* Bottom Branding with Backdrop Filter */}
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
  // Render to PNG with automatic font resolution
  const png = await render({
    value: html,
    css: await createCSS(html),
    width: 1200,
    height: 630,
    format: "png",
  });
  const response = new Response(png as BodyInit, {
    headers: {
      "Content-Type": "image/png",
      "Cache-Control": isDev
        ? "no-cache"
        : "public, max-age=31536000, immutable",
      date: new Date().toUTCString(),
    },
  });
  if (!isDev) {
    await cache.put(cacheKey, response.clone());
  }
  return response;
});

```
