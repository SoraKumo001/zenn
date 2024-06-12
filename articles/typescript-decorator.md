---
title: "TypeScriptの型を使って、実行時の挙動を変えてみる"
emoji: "😸"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [typescript]
published: true
---

TypeScript はトランスコンパイルを前提とする言語です。トランスコンパイルの結果は JavaScript と一対一で対応しているわけではなく、本質的に型が付与された JavaScript ではありません。トランスコンパイルの結果が実行時に影響を与えることをしっかり認識する必要があります。

# 型情報を実行時に使う

## 事前設定

`tsconfig.json`に以下の設定を追加します。特殊なコンパイラプラグインなどは必要ありません。

```json
{
  "compilerOptions": {
   "experimentalDecorators": true
   "emitDecoratorMetadata": true
  }
}
```

## サンプルコード

```ts
import "reflect-metadata";

//型のチェック
function isType(type: object, value: unknown) {
  switch (type) {
    case Number:
      if (typeof value !== "number") return false;
      break;
    case String:
      if (typeof value !== "string") return false;
      break;
    case Boolean:
      if (typeof value !== "boolean") return false;
      break;
    case Array:
      if (!(value instanceof Array)) return false;
      break;
    case Function:
      if (!(value instanceof Function)) return false;
      break;
  }
  return true;
}

function CHECK(target: any, name: string, descriptor: PropertyDescriptor) {
  const ptypes = Reflect.getMetadata(
    "design:paramtypes",
    target,
    name
  ) as object[];
  const rtype = Reflect.getMetadata(
    "design:returntype",
    target,
    name
  ) as object[];
  return {
    ...descriptor,
    value: function (...params: unknown[]) {
      if (ptypes.length !== params.length) throw "引数の数が不正";
      const flag = ptypes.reduce((a, b, index) => {
        return a && isType(b, params[index]);
      }, true);
      if (!flag) {
        throw "引数の型が不正";
      }
      const result = descriptor.value.apply(this, params);
      if (!isType(rtype, result)) throw "戻り値の型が不正";
      return result;
    },
  };
}

//テスト用クラス(型チェックなし)
class NoCheck {
  func01(a: number, b: string, c: boolean): number {
    console.log(a, b, c);
    return 0;
  }
  func02(a: number, b: string, c: boolean): string {
    console.log(a, b, c);
    return 0 as never; //戻り値の型が不正
  }
}

//テスト用クラス(型チェックあり)
class Check {
  @CHECK //これを付けると実行時に引数と戻り値の型がチェックされる
  func01(a: number, b: string, c: boolean): number {
    console.log(a, b, c);
    return 0;
  }
  @CHECK
  func02(a: number, b: string, c: boolean): string {
    console.log(a, b, c);
    return 0 as never; //戻り値の型が不正
  }
}

console.log("--- No Check ---");

//インスタンスの作成
const noCheck = new NoCheck();

//真っ当に実行
noCheck.func01(0, "A", true); //OK

//引数の型を間違える
try {
  noCheck.func01(0, 10 as never, true);
} catch (e) {
  console.error(e);
}

//戻り値が間違ったメソッドを呼び出す
try {
  noCheck.func02(0, "A", true);
} catch (e) {
  console.error(e);
}

console.log("--- Check ---");

//インスタンスの作成
const check = new Check();
//真っ当に実行
check.func01(0, "A", true); //OK

//引数の型を間違える
try {
  check.func01(0, 10 as never, true); //例外 "引数の型が不正"
} catch (e) {
  console.error(e);
}

//戻り値が間違ったメソッドを呼び出す
try {
  check.func02(0, "A", true); //例外 "戻り値の型が不正"
} catch (e) {
  console.error(e);
}
```

## 実行結果

`Check`の方は TypeScript の型情報を参照して、実行時に引数と戻り値の型をチェックしています。

```txt
--- No Check ---
0 A true
0 10 true
0 A true
--- Check ---
0 A true
引数の型が不正
0 A true
戻り値の型が不正
```

今回は TypeScript の Decorator を使って、実行時に引数と戻り値の型をチェックしてみました。このような Decorator を使っているパッケージで有名どころだと NestJS や TypeORM などが挙げられます。

# 設定変更による挙動の違い

これが注意点の一つです。設定次第で JavaScript の出力結果が変わるので、多機能トランスコンパイラだということをしっかり認識する必要があります。

- ソース

```ts
export class Test {
  a: number | undefined;
}

const test = new Test();
console.log(Object.keys(test));
```

- ES2015

```json
{
  "compilerOptions": {
    "target": "ES2015"
  }
}
```

```txt
[]
```

- ESNext

```json
{
  "compilerOptions": {
    "target": "ESNext"
  }
}
```

```txt
[ 'a' ]
```

# まとめ

TypeScript は JavaScript に型を付けただけのようなイメージがありますが、実体は多機能トランスコンパイラです。コンパイル後に生成されるコードは、単純に型だけが抜かれた状態ではありません。特に ESM や CJS の両対応パッケージを作る場合など、設定次第でモジュールをインポートするコードが大きく異なるので、このあたりで苦労している方も多いかと思います。出力コードの挙動には注意して使っていく必要があります。
