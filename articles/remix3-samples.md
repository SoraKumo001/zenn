---
title: "Remix 3 を実際に動かしてみる"
emoji: "👌"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [remix, remix3, react, typescript, rolldown]
published: true
---

# Remix3 とは

Remix 3 は、React から脱却し、Web 標準に基づいた新しいフルスタック Web フレームワークとして再設計されました。Remix 3 は鋭意開発中ですが、この記事では React 代替に相当する部分を部分的に動かして、実際に動作を検証してみます。

# サンプルコードのリポジトリ

https://github.com/SoraKumo001/remix3-sample01

# 環境の準備

SPA アプリケーションとして動作させるための環境を用意します。今回はビルドに rolldown を使用します。

## rolldown の設定

普通にビルドすれば依存パッケージのバンドルが行われるのですが、`react/jsx-runtime`に関しては`@remix-run/dom/jsx-runtime`に変換する設定が必要になります。

- rolldown.config.ts

```ts
import { defineConfig } from "rolldown";

export default defineConfig({
  input: "src/index.tsx",
  output: {
    file: "public/bundle.js",
  },
  resolve: {
    alias: {
      "react/jsx-runtime": "@remix-run/dom/jsx-runtime",
      "react/jsx-dev-runtime": "@remix-run/dom/jsx-dev-runtime",
    },
  },
});
```

## typescript の設定

Remix3 の jsx の形式を有効にするため、`jsxImportSource`を`@remix-run/dom`にする必要があります。

- tsconfig.json

```json
{
  "compilerOptions": {
    "strict": true,
    "lib": ["ES2024", "DOM", "DOM.Iterable"],
    "module": "ES2022",
    "moduleResolution": "Bundler",
    "target": "ESNext",
    "allowImportingTsExtensions": true,
    "rewriteRelativeImportExtensions": true,
    "verbatimModuleSyntax": true,
    "skipLibCheck": true,
    "jsx": "react-jsx",
    "jsxImportSource": "@remix-run/dom"
  }
}
```

# サンプルプログラム

## カウントを回すだけ

まずはボタンを押して、カウントを表示するプログラムです。  
これを見るとわかりますが、React との違いはステートが存在しないということです。React を初期から使っている人なら気がつくと思いますが、クラスコンポーネントのような動作を関数で行っています。再レンダリングの指示は`this.render()`で能動的に呼び出します。  
そして Remix3 ではイベントはすべて`on`に集約されており、そこでイベントを受け取ることになります。`press`という、あらかじめ定義されているものを使っていますが、自分で定義することも可能です。

```tsx
import { createRoot, type Remix } from "@remix-run/dom";
import { press } from "@remix-run/events/press";

function App(this: Remix.Handle) {
  let count = 0;
  return () => (
    <button
      on={press(() => {
        count++;
        this.render();
      })}
    >
      Count: {count}
    </button>
  );
}

createRoot(document.body).render(<App />);
```

## マウント、アンマウントの使い方

動作確認用に Test というコンポーネントを作って、ボタンを押したら消滅するようにします。  
これを動かすと、マウント時に`connect`が、アンマウント時に`disconnect`が呼び出されます。  
そして現時点で未実装なのか、ref が動作していません。

```tsx
import { createRoot, type Remix } from "@remix-run/dom";
import { press } from "@remix-run/events/press";
import { connect, disconnect } from "@remix-run/dom";

function Test() {
  return (
    <div
      ref={(n) => {
        console.log(n);
      }}
      on={[
        connect(() => {
          console.log("mount");
        }),
        disconnect(() => {
          console.log("unmount");
        }),
      ]}
    >
      Test
    </div>
  );
}

function App(this: Remix.Handle) {
  let count = 0;
  return () => (
    <>
      <button
        on={press(() => {
          count++;
          this.render();
        })}
      >
        Count: {count}
      </button>
      {count === 0 && <Test />}
    </>
  );
}

createRoot(document.body).render(<App />);
```

## その他のイベントの使い方

その他のイベントの使い方です。ここでの注意点ですが、Test コンポーネントは関数を戻しています。こうしないと、再レンダリングごとに`mouseState`が初期化されてしまうので気をつけてください。

```tsx
import { createRoot, type Remix } from "@remix-run/dom";
import { press } from "@remix-run/events/press";
import { dom } from "@remix-run/events";

function Test(this: Remix.Handle) {
  let mouseState = "mouseOut";
  return ({ value }: { value: string }) => (
    <div
      on={[
        dom.mouseover(() => {
          mouseState = "mouseOver";
          this.render();
        }),
        dom.mouseout(() => {
          mouseState = "mouseOut";
          this.render();
        }),
      ]}
    >
      {value}:{mouseState}
    </div>
  );
}

function App(this: Remix.Handle) {
  let count = 0;

  return () => (
    <>
      <button
        on={[
          press(() => {
            count++;
            this.render();
          }),
        ]}
      >
        Count: {count}
      </button>
      <Test value="test" />
    </>
  );
}

createRoot(document.body).render(<App />);
```

# まとめ

取り急ぎ、動くものを作って動作を確認してみました。興味のある人は是非いじってみてください。
