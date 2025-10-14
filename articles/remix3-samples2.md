---
title: "Remix3 を Vite から HMR 対応で動かす"
emoji: "😺"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [remix, remix3, react, typescript, vite]
published: true
---

# 前回の記事

https://zenn.dev/sora_kumo/articles/remix3-samples

# 今回のリポジトリ

https://github.com/SoraKumo001/remix3-sample02

# Vite から Remix3 を使う

前回は rolldown でビルドして、html ファイルからスクリプトを呼び出して実行しました。今回は Vite から HMR 対応で動作させてみます。

## Vite の設定

### vite.config.ts

ファイルの変更を検知したら、スクリプトのトップのファイルを再読み込みさせるプラグインを作成します。また、前回同様 jsx のエイリアスを仕込みます。

```ts
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [
    {
      name: "reload",
      handleHotUpdate({ server }) {
        server.moduleGraph.getModuleByUrl("/src/main.tsx").then((mod) => {
          if (mod) server.reloadModule(mod);
        });
      },
    },
  ],
  base: "./",
  resolve: {
    alias: {
      "react/jsx-runtime": "@remix-run/dom/jsx-runtime",
      "react/jsx-dev-runtime": "@remix-run/dom/jsx-dev-runtime",
    },
  },
});
```

# サンプルプログラム

## main.tsx

起点になるファイルです。更新時にフルリロードされないように細工を入れます。

```tsx
import { App } from "./App";
import { createRoot } from "@remix-run/dom";

createRoot(document.getElementById("root")!).render(<App />);

if (import.meta.hot) {
  import.meta.hot.accept(() => {});
}
```

## App.tsx

前回使ったカウントボタンコンポーネントです。

```tsx
import { type Remix } from "@remix-run/dom";
import { dom } from "@remix-run/events";
import { Test } from "./Test";

export function App(this: Remix.Handle) {
  let count = 0;
  return () => (
    <>
      <button
        on={[
          dom.click(() => {
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
```

## Test.tsx

マウスオーバーイベントの確認用です。

```tsx
import { type Remix } from "@remix-run/dom";
import { dom } from "@remix-run/events";

export function Test(this: Remix.Handle) {
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
```

# HMR と保存されないステート

HMR 時にフルリロードは阻止し、html ファイルはそのままでスクリプトファイルのみを再読み込みの対象とすることは成功しました。ただ、根本的な問題があります。

各コンポーネントの React のステートに相当するデータ領域は関数内の変数です。しかし jsx の構造を修正した場合、戻り値としてその内容を返す必要があるため、関数の再実行は必須です。こうなると当然、変数の内容は初期化されます。つまり HMR 時に React のようにステートを維持する方法がないのです。

React はステートをどこに記憶しているのかというと、React 管理下の外部変数の中に順序を決めて放り込んでいます。このような構造をとっていない Remix3 は、現時点において状態を保持する機能を実装することができません。

# まとめ

Remix3 はまだ開発中なので、今後、仕様が大幅に修正される可能性が高いです。解決するべき問題が山積しているので、リリースされるのはかなりの未来になりそうな予感です。
