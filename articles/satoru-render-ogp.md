---
title: "satoru-render で OGPイメージの作成 ～ WebAssembly で複雑な HTML を画像変換 ～"
emoji: "🔖"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [nextjs, ogp, cloudflare, wasm, typescript]
published: true
---

# satoru-render の紹介と Playground

HTMLをSVG,PNG,WEBP,PDF形式に変換するためのJavaScriptパッケージを作りました。コア部分はWebAssemblyのため、あらゆる環境で動きます。Node.js,Deno Deploy,Cloudflare Workers,Webブラウザなどで動作を確認しています。

以下、Web上で動作確認するためのページを用意しました。複雑なレイアウトや、エフェクト類、カラーアイコン、合字、RLT対応のアラビア語、line-clampによる文字列省略処理などが確認できます。もはや何を求めているのかが自分でもわかりません。ヤケになって大量の機能に対応したものの、基本的なCSSの組み合わせなどの検証があまいので何が起こるかわかりません。

PlaygroundによるWebブラウザ上の動作はChromeだと問題ありませんが、FirefoxだとGoogleFontから取得するフォントデータがCORSの制限に引っかかてテキストが表示できません。また、CORSに引っかかるサイトの画像は読めません。

https://sorakumo001.github.io/satoru/master

ブラウザ\(左\)とSatoru\(右\)で変換内容を比較できます。

![](/images/satoru-render-ogp/2026-03-06-14-55-59.png)

# satori と satoruの比較

OGPイメージの作成というと有名どころではVercelのSatoriです。私もこれを使っていたのですが、一時期Cloudflareでwasmファイルの読み出し問題で動作不能の不具合が発生したため、自分で作ることにしました。Satoruと名付けて作成に一ヶ月ほどかけてC++で作りました。しかしその間にSatoriは不具合を修正しています。つまり存在価値に疑問符がついた形です。そうなってくると機能面で勝負するしかありません。以下が比較表になります。

| Feature            | Satori (Vercel)                    | **Satoru**                                          |
| ------------------ | ---------------------------------- | --------------------------------------------------- |
| **Engine**         | Yoga (Flexbox only)                | **litehtml (Full CSS Layout)**                      |
| **Renderer**       | Custom SVG Generator               | **Skia Graphics Engine**                            |
| **Output Formats** | SVG                                | **SVG, PNG, WEBP, PDF**                             |
| **CSS Support**    | Limited subset (Flexbox)           | **Extensive (Floats, Box-shadow, etc.)**            |
| **Images**         | External URLs, Base64, ArrayBuffer | **Embedded/Local/Url (PNG, JPEG, WebP, AVIF, GIF)** |
| **Font Formats**   | TTF, OTF, WOFF                     | **TTF, OTF, WOFF2, TTC**                            |
| **Typography**     | SVG Paths / Fonts                  | **Full Skia Typeface support**                      |
| **Performance**    | High (Lightweight)                 | **High (Wasm-accelerated Skia)**                    |
| **Edge Ready**     | Yes (Node/Edge/Cloudflare)         | **Yes (Wasm/Edge/Cloudflare)**                      |

SatoriがYogaによるFlexboxの部分的な機能で構成されているのに対し、Satoruはlitehtmlベースなので対応タグやCSSに制限はありません。追加で実装すれば可能性は無限大です。

グラフィックライブラリにはGoogle製のSkiaを使い、あらゆる描画に対応できるようにしました。画像フォーマットも望むだけ対応可能です。フォント形式に関してはFreeTypeを使ってWOFF2も対応。出力形式はSVG, PNG, WEBP, PDFが使えます。OGPイメージを作るのが目的だったはずなのに、完全に目的を見失ってやりたい放題です。そしてその代償はやってきます。

wasmサイズ約7MB、zip圧縮しても2.5MB。デケェよ！いや、一応CloudflareWorkersのFreeプランの3MB以内という条件は満たしています。まだ大丈夫。ちなみにavifのエンコード機能を付けたら、一気に圧縮サイズで850KBほど膨らんだため、この機能は無事に無かったことにされました。Avifはデコードのみ対応です。

# Example

各環境用のサンプルを用意しました。生のHTMLでの記述のほうが効率は良いのですが、Satoriユーザー用にJSX+Tailwindで記述しています。

- Cloudflare Workers  
  https://github.com/SoraKumo001/satoru-cloudflare-ogp
- Deno Deploy  
  https://github.com/SoraKumo001/satoru-deno-ogp-image
- Next.js(Vercel)  
  https://github.com/SoraKumo001/next-satoru

HTMLデータを内部で作ってOGP作成関連のイメージを作成するサンプルを並べています。さらにsatoru-renderは変換ソースにURLを指定することも可能です。たとえばNext.jsのサーバコンポーネントでOGP専用のHTMLを吐くページを用意して、satoru-renderにそのURLを読ませてpngに変換という手段もとれます。SSRでHTMLレンダリングが完了しているなら、HTMLはそこから持ってくる方法が使えます。

# 使い方

## 基本

HTMLタグを書いてrenderを呼び出すだけです。Node.js,Cloudflare,Deno,Webブラウザとあらゆるところで動きます。wasmの管理も環境によって動作を自動切り替えしているので、モジュールバンドラの種類などによる手動設定を不要にしています。基本的に利用者が余計なことを考える必要はありません。さらにpng出力が可能なので、いったんsvgで出して変換という必要もありません。フォントファイルの指定はGoogleFontのCSS2のAPIを指定することも可能です。CSSの内容を再帰的に解析してフォントを取りに行きます。ただ、やりとりにfetchが何度も必要になるので、必要なフォントを明確に指定するのが一番効率が良いです。厳密にフォントを管理する場合は、フォントのURLとfont-familyの指定を確実に一致させる必要があります。指定に矛盾があると、デフォルト設定のフォントを自動的に取りに行くようになっています。

外部データは自動でfetchされます。それを各環境用にキャッシュするためのコールバック機能も用意してありますが、それはまた別の機会に解説します。

```typescript
import { render } from "satoru-render";

const html = `
  <style>
    @font-face {
      font-family: 'Roboto';
      src: url('https://fonts.gstatic.com/s/roboto/v30/KFOmCnqEu92Fr1Mu4mxK.woff2');
    }
  </style>
  <div style="font-family: 'Roboto'; color: #2196F3; font-size: 40px;">
    Hello Satoru!
    <img src="logo.png" style="width: 50px;">
  </div>
`;

// Render from a URL directly
const png = await render({
  value: html,
  width: 1024,
  format: "png",
});
```

## マルチスレッド

マルチスレッドで動作させる場合の使い方です。対応環境はNode.jsとWebブラウザ上のみです。それぞれAPIが微妙に異なるのですが、そのあたりは自動切り替えで吸収するようにしてあるので、環境ごとの違いを書き分ける必要はありません。マルチスレッド版を使う利点は、メイン処理をブロックしなくなることです。とくにWebブラウザ上では、変換中にUIをブロックしなくなるという利点が大きいです。

```typescript
import { createSatoruWorker } from "satoru-render/workers";

// Create a worker proxy with up to 4 parallel instances
const satoru = createSatoruWorker({ maxParallel: 4 });

// Render with full configuration in one go
const png = await satoru.render({
  value: "<h1>Parallel Rendering</h1><img src='icon.png'>",
  width: 800,
  format: "png",
});
```

## JSX と Tailwind

JSXでの記述もサポートしています。Tailwind@4相当の記述も可能です。renderで変換する前にJSXをHTMLに変換するためのユーティリティを入れてありますが、この部分はSatoruを使わなくても好きな方法で対処できます。最終的にHTMLとCSSが揃っていればOKです。

- install

```bash
pnpm add preact preact-render-to-string @unocss/preset-wind4 satoru-render
```

- code

```tsx
/** @jsx h */
import { h, toHtml } from "satoru-render/preact";
import { createCSS } from "satoru-render/tailwind";
import { render } from "satoru-render";

// 1. Define your layout with Tailwind classes
const html = toHtml(
  <div className="w-[1200px] h-[630px] flex items-center justify-center bg-slate-900">
    <h1 className="text-6xl text-white font-bold">Hello World</h1>
  </div>,
);

// 2. Generate CSS from the HTML
const css = await createCSS(html);

// 3. Render to PNG
const png = await render({
  value: html,
  css,
  width: 1200,
  height: 630,
  format: "png",
});
```

- tsconfig.json

```json
{
  "compilerOptions": {
    "jsx": "preserve"
  }
}
```

# 技術的な色々

## Emscripten SDK による WebAssembly 開発

WebAssemblyというとRustでの開発が思う浮かぶと思いますが、ビルドサイズとグラフィックライブラリ関連の速度を考慮すると、最終的にC++で作るほうが妥当だという結論に至りました。ただ、C++でしかもWebAssembly向けとなると、関連ライブラリのエコシステムが苦難の道となります。vcpkg経由で簡単に持ってこられるものもある反面、SkiaやAvif関連は、必要な部分のコードを抽出してビルド方法を手動設定しないと動くところまで持っていけません。Avifは以前に画像最適化ライブラリを作ったときに使っていたので、その知識で簡単に組み込めました。しかしSkiaはかなり苦労しました。WebAssemblyでも使えると言われているものの、全然情報がありませんでした。

## litehtmlの魔改造

HTMLのレイアウトを読み取ってくれるlitehtmlですが、liteだけあって簡易的な機能しか対応していません。もともと簡易HTMLを自分のアプリに組み込んで表示するというのを前提としているので、昨今の複雑なCSSをアレコレしようとするのが間違いです。そのままだと対応できないCSS、とくにレイアウト計算が大量にあったため、コードを取り込んで直接修正する形にしました。そもそもの問題はレイアウトの計算方法がW3Cの規則に則っていないので、適切にスタイルを適用しようとしてもAの条件を満たすとBが壊れる、Bの条件を満たすとAが壊れるというジレンマが発生します。魔改造を繰り返した結果、レイアウト計算に関しては原型をとどめていません。

## Tailwindという強敵

CSSの検証のため、[自分のサイト](https://next-blog.croud.jp/)を実験用に使いました。完全にSSRされているページなので読み取りが可能です。このページはスタイルの記述に Tailwind + daisyUI を使っているのですが、昨今のTailwindは@layerによりCSSが多重構造になっています。また条件分岐や算術系の命令が散りばめられており、初期段階では何も出来ずに敗北しました。ひとつひとつ対応を行って、現在は17秒ほどかかりますがほぼ問題なく変換できます。

結果としてTailwindのCSSが読めるようになったので、追加機能としてTailwind@4をスタイリングで使用する追加機能を付けました。パッケージサイズを圧迫しないようにメインからは分離して、必要なときに使えるようにしてあります。

## SVGの苦難

もともとSatoriと同等のことができるようにという前提があって、svg出力からスタートしました。その後、wasmのファイルサイズが膨らみすぎて、svgを別のアプリで変換するぐらいならpng出力を付けるという形に方針転換しました。その名残でsvg出力が残っています。svg出力には利点があって、デバッグ時に出力コードの座標データから問題点の洗い出しができます。ただ、svgは万能ではなく、ラスターなら簡単に行えるドロップシャドウなどの機能がありません。色を重ねがけしてエミュレーションというむだな努力をしています。放射エフェクトはsvgの基本機能は諦めて、ラスターで作った画像を合成させています。バックドロップに関しては対応を諦めました。無理です。これもラスターで作って合成すれば良いのですが、そうなるとsvgを作るのに、一度、全体をラスター出力させてからベクターに組み入れるというわけのわからないことになるので勘弁してください。

## 環境に依存しないマルチスレッドの対応

マルチスレッド化に関しては以前、画像最適化ライブラリの作成時にすでに色々やっていました。[worker-lib](https://www.npmjs.com/package/worker-lib)を使って、処理をスレッド側に投げます。ただし、このマルチスレッド機能は1つの変換は1つのスレッドで、複数の変換を並列で走らせるというものです。複数の変換を同時に走らせるというケースはほとんどなさそうですが、ブラウザ上で動かすときはUIスレッドと分離されるので、変換中も表示や操作をブロックしないという利点が生まれます。

今回は画像変換ライブラリを作ったときと違って、C++側からメインスレッドのJSにfetch処理を要求するという双方向のやり取りが頻繁に発生します。worker-libでそこまでのデータのやり取りを想定していなかったのでライブラリを大幅修正しました。

## 多国語対応

多国語の文字は [harfbuzz](https://github.com/harfbuzz/harfbuzz) と [libunibreak](https://github.com/adah1972/libunibreak) によって処理していますが、ラスター情報を含むカラー絵文字、複数の文字が合体する合字、右から左に文字列が流れるアラビア語系、そして文字省略の計算、これらを滞り無く処理しなければなりません。これは地獄の一言です。やるだけはやりました。これだけやって表示できない文字は諦めます。

# まとめ

今回の内容は、もはや人間が単独でどうこうなる領域ではないので、AI（無課金）をぶん回しながらの作業でなんとか作りました。凡人が高難易度なものを作ろうと思えば作れてしまうという、なかなか恐ろしい時代になりました。
