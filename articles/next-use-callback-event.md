---
title: "顧顧客が本当に必要だったものは useEffectEvent ではなく useCallbackEvent だったのでは？"
emoji: "🐷"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [react, typescript, nextjs]
published: true
---

※サンプルリポジトリ  
https://github.com/SoraKumo001/next-callback-event

# useEffectEvent の登場

React@19.2から useEffectEvent が追加されました。この Hook を使うと useEffect で関数を使うときに、依存する値としてその関数を含めずとも Linter の警告を回避できます。しかしこの機能は useEffect と対で使うことを前提としているので、たとえばメモ化したコンポーネントの再レンダリングの回避などには使えません。Linter の警告は回避できるものの、関数のインスタンスそのものは毎回新しく作成されるので、依存に含めればコールバック関数の再実行を起こします。

# useCallbackEvent を作る

useEffectEvent の情報を最初に目にした時、対象関数を useEffect の依存関係に含めても再実行を回避しつつ、実行時の変数の内容が更新される便利機能を想像した人がいるのではないでしょうか？そのつもりで useEffectEvent の説明を読んでみたら、結局は Linter を回避しているだけだと落胆した人もいることでしょう。ということで、最初の期待通りの Hook を作ってみます。

前提条件は以下の通りです

- useCallbackEvent の戻り値の関数インスタンスは常に同じものを返す
- コールバック内の変数は最新の状態を参照する

ということで、以下のようになりました。

ラッパー関数を固定して、常に最新の関数を呼ぶようにしているというシンプルな作りです。

```ts
import { useCallback, useImperativeHandle, useRef } from "react";

// Update the behavior of a function without changing its instance
export function useCallbackEvent<T extends (...args: unknown[]) => unknown>(
  callback: T
) {
  const property = useRef<{ callback: T }>(null);
  useImperativeHandle(property, () => ({ callback }));
  return useCallback((...args: Parameters<T>) => {
    if (!property.current) throw "callback is null";
    return property.current.callback(...args);
  }, []);
}
```

# 使い方

動作確認用に用意した、テキストボックスから入力された値を定期的に加算するというプログラムです。ぶっちゃけ、今回の機能を使用しなくてももっと効率的に書けるのですが、良いサンプルが思いつきませんでした。

useCallbackEvent で作成した handleAnswer は、valueA,valueB に依存しています。それを useEffect に含めています。

動作を確認すると、console.log で`effect`は一度だけ出力されます。その後の setInterval での定期的な加算実行は、最新の valueA,valueB が使われます。つまり関数のインスタンスを固定して、関数の実行内容自体は常に最新状態になります。

```ts
"use client";
import { useEffect, useState } from "react";
import { useCallbackEvent } from "./libs/use-callback-event";

const Page = () => {
  const [valueA, setValueA] = useState(10);
  const [valueB, setValueB] = useState(20);
  const [answer, setAnswer] = useState(0);

  // valueA,valueBを更新しつつ、関数のインスタンスは変えない
  const handleAnswer = useCallbackEvent(() => {
    setAnswer(valueA + valueB);
  });

  // handleAnswerのインスタンスは変更されないので、useEffectのコールバックはvalueA,valueBを更新しても呼ばれない
  useEffect(() => {
    const t = setInterval(() => {
      handleAnswer();
    }, 1000);
    console.log("effect");
    return () => clearInterval(t);
  }, [handleAnswer]);

  return (
    <div className="p-4">
      <div>
        A:
        <input
          className="outline p-1"
          type="number"
          value={valueA}
          onChange={(e) => setValueA(Number(e.target.value))}
        />
      </div>
      <div>
        B:
        <input
          className="outline p-1"
          type="number"
          value={valueB}
          onChange={(e) => setValueB(Number(e.target.value))}
        />
      </div>
      <div>Answer:{answer}</div>
    </div>
  );
};

export default Page;
```

- 実際の動作

https://next-callback-event.vercel.app/

# まとめ

今回紹介した useCallbackEvent は、メモ化したコンポーネントにコールバックを渡す場合などにも利用できます。関数の挙動を更新しても再レンダリングは発生しません。もちろん再レンダリングが発生しなければ困るケースもあるので、そういう場合は普通に useCallback を使って、依存する値を設定する必要があります。

技術的には簡単なので思いつきで作ってみましたが、あまり活用するケースは多くないように思います。
