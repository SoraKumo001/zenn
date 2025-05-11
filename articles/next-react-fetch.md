---
title: "ReactでuseEffectを使わずにfetchする"
emoji: "🐥"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [react, typescript, fetch, nextjs]
published: true
---

# useEffect について

React のコードを書くとき、useEffect は極力使わないことが推奨されています。では fetch でデータ取得の処理を行う場合はどうでしょう？結論として、使う必要はありません。

# 天気予報を useEffect なしで取得する

`useRef`で必要な処理やデータを揃えて、`useSyncExternalStore`に渡しています。`subscribe`で受け取っている`onStoreChange`がイベント発火のキーになるので、コンポーネントに渡したい値を書き換えたら呼び出してやるという流れです。

`useEffect` と違って、取得項目を変えて再 fetch する際、任意の処理を用意してクリックイベントなどから直接発火させることができます。これによって`useEffect`内で fetch を行うときのような、関連データのピタゴラスイッチを防げます。

ちなみに`useRef` + `useSyncExternalStore`の組み合わせで書いてますが`useSyncExternalStore`が特殊な hook というわけではないので、`useRef` + `useState`でも同じことは可能です。重要なのはデータ更新タイミングに合わせて、コンポーネントの再レンダリングを発火させることです。

https://github.com/SoraKumo001/next-fetch

![](/images/next-react-fetch/2025-05-10-11-21-35.webp)

```tsx
"use client";
import { useRef, useSyncExternalStore } from "react";

export interface WeatherType {
  publishingOffice: string;
  reportDatetime: string;
  targetArea: string;
  headlineText: string;
  text: string;
}

export default function Page() {
  const storeCtx = useRef({
    subscribe: (onStoreChange: () => void) => {
      storeCtx.onStoreChange = onStoreChange;
      storeCtx.request(storeCtx.defaultParam.id);
      return () => {
        storeCtx.controller.abort();
      };
    },
    request: async (id: number) => {
      const signal = storeCtx.controller.signal;
      storeCtx.result = {
        ...storeCtx.result,
        isLoading: true,
        isError: false,
        data: null,
      };
      storeCtx.onStoreChange();
      await new Promise((result) => setTimeout(result, 1000)); // Simulate network delay
      fetch(
        `https://www.jma.go.jp/bosai/forecast/data/overview_forecast/${id}.json`,
        { signal }
      )
        .then((r) => r.json())
        .then((r) => {
          storeCtx.result = { ...storeCtx.result, data: r };
        })
        .catch(() => {
          storeCtx.result = { ...storeCtx.result, isError: true };
        })
        .finally(() => {
          storeCtx.result = { ...storeCtx.result, isLoading: false };
          storeCtx.onStoreChange();
        });
    },
    onStoreChange: () => {},
    controller: new AbortController(),
    result: {
      isLoading: true,
      isError: false,
      data: null as WeatherType | null,
    },
    defaultParam: {
      id: 130000,
    },
  }).current;

  const result = useSyncExternalStore(
    storeCtx.subscribe,
    () => storeCtx.result,
    () => storeCtx.result
  );

  const areas = [
    [130000, "東京"],
    [120000, "千葉"],
    [140000, "神奈川"],
  ] as const;

  return (
    <div className="m-4 w-3xl">
      <div className="flex gap-1">
        {areas.map(([code, name]) => (
          <button
            key={code}
            className="text-white bg-blue-700 hover:bg-blue-800 focus:ring-4 focus:ring-blue-300 font-medium rounded-lg text-sm px-5 py-2.5 me-2 mb-2 dark:bg-blue-600 dark:hover:bg-blue-700 focus:outline-none dark:focus:ring-blue-800"
            onClick={() => storeCtx.request(code)}
          >
            {name}
          </button>
        ))}
      </div>
      <div className="p-4 border">
        {result.isLoading && <div className="text-blue-600">Loading</div>}
        {result.isError && <div className="text-red-600">Error</div>}
        {result.data && (
          <div className="whitespace-pre-wrap">
            {JSON.stringify(result.data, null, 4)}
          </div>
        )}
      </div>
    </div>
  );
}
```

# まとめ

React でコンポーネント内に単純にデータを保存したいときは`useRef`を使います。再レンダリングの発火を伴う State を管理したいときは`useState`を使います。タイミングを明確に操作したい場合や何らかのイベントを伴う場合は`useSyncExternalStore`を使うと良いでしょう。DOM にマウントが完了したあとに実行したい処理には`useEffect`です。それぞれの状況に応じて使い分けることで、より効率的なコードを書くことができます。

ただ一つ言えることは、既存のライブラリを使ったほうが早いということです。
