---
title: "[TypeScript/JavaScript] Promiseの終了を待たないawaitの利用方法"
emoji: "🐡"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [javascript,typescript,await,promise]
published: true
---

[こちら](https://next-blog.croud.jp/contents/YtwDZ9LsqMHPXcLTzz3N)にも同じ記事を書いています

# Promiseの終了を待たないawaitの利用方法

## Promiseは不便？

Promiseで非同期のプログラムを組む際、対象のPromiseはresolveを呼び出して実行を完了しているのか、それともまだ実行中なのかを判断したいことがあります。しかし単純にawaitで状態を確認しようとしても、終了まで処理がブロックされてしまいます。また、thenの実行時にフラグを操作すれば状態を確認することは可能ですが、それなりに書き方が冗長になります。

「await時にまだ処理が終了していなければ、ブロックせずに実行中であることを識別できる値を返す」というのが可能なら話は簡単です。実はこれ、かなり簡単に書くことが出来ます。


## ソースコード

```ts
const main = async () => {
    // ウエイト用
    const sleep = (msec: number) => new Promise(resolve => setTimeout(resolve, msec))
    // 1000ms後に終了するPromise
    const p = new Promise(resolve => setTimeout(() => resolve("end"), 1000))
    while (true) {
        // pが終了していなければ即座にundefinedが返り、終了したらendが返る
        const result = await Promise.race([p, undefined])
        console.log(result)
        if (result)
            break;
        // 100ms待つ
        await sleep(100);
    }
}
main()
```

## 実行結果

```txt
undefined
undefined
undefined
undefined
undefined
undefined
undefined
undefined
undefined
undefined
end
```

## 実行確認用

https://www.typescriptlang.org/ja/play?ssl=16&ssc=7&pln=1&pc=1#code/MYewdgzgLgBAtgQwJZhgXhgiBPMwYAUAlOgHwwDeAUDLTAPT0yBlDIBUMgJQyATDIBSuNdokWBAA2AU1EAHdITgRRwAFwwwAVzgAjUQCcSacmFEB3GAAUtIOEjkEtoiCGEA3UWRhyoAFSRxRIFVBs7B2cAGng5YCIiPlpGGABGAAZk2UAY-UBrBkAhX0AwuUBNBkBohjMLK1EYmAFoGCkMA2Miy2tbeycXPTdRT29ffwJiVybg0QIAIlEwABNhojCk5KiywwALJDFCKC0VURJqOl2GJglAGQYcwHUGQDMGQBEGQCsGQEUGQBiGQAcGFQnRADMUUXHDwBX4-LLdiqwJoqYSwDAIQzIWD1EoAOi0CGAQwA2hIws9xm8PuMALrRPb8cDNUSw4QgADmgQgIKg+IJMCQr0IwNBdPpdHUtgQAGsANz-OhxWayQCh+oATBgFtAhULcYkkBFmRH5uwAvlQ1YgUMQgA

## 解説

肝は`Promise.race`です。私は時々使うのですが、一般的なところでは滅多にお目にかかることはありません。この関数は、渡した値の中から待ちが発生していない値を返します。また、複数の処理が終了している場合は、先頭側の値を優先して返します。

この性質を利用して、目的のPromiseの後ろに待つ必要の無い値を入れます。するとPromiseが終了するまでは、そちらの値が返ってくるのです。そしてPromiseが終了した時点で、今度はPromiseが返した値に変化します。

## まとめ

`Promise.all`に比べると日の目を見ない`Promise.race`ですが、実はとても使えるヤツなので、忘れないであげてください。