---
title: "WebAssemblyとマルチスレッドによる環境に依存しない高速画像変換"
emoji: "😽"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [WebAssembly, Nextjs, ReactRouter, wasm, thread]
published: true
---

# 画像変換の WebAssembly 利用

本稿では、画像サイズ変更やフォーマット変換といった処理を WebAssembly で行う方法について紹介します。また、必要に応じてマルチスレッドを使用することで、処理を並列化し、より高速な実行を実現できます。

# なぜ画像変換を WebAssembly で行うのか

JavaScript は大量のビットデータの扱いには強くありませんが、WebAssembly は SIMD（Single Instruction, Multiple Data）などを使い、並列処理をサポートしています。これにより、画像変換のような重い計算を高速化できます。また、WebAssembly はブラウザだけでなく、Node.js や Deno など他の環境でも利用可能です。

今回は Emscripten を使用して C++でコンパイルを行います。WebAssembly に関して Rust の情報が多いですが、画像変換においては C++ の方が高速化しやすいという理由から、Emscripten をおすすめします。

# マルチスレッド処理

WebAssembly 自身はマルチスレッドに対応しておらず、並列処理を実現するためには、利用環境によって異なる方法が必要です。ブラウザ上で動作させる場合は Web Workers を使用し、Node.js の CLI 環境では worker_threads モジュールを利用できます。また、バックエンドサーバー環境ではマルチプロセスによる処理が有効です。

本稿では、以前開発した Web Worker ライブラリを活用し、worker_threads にも対応させました。これにより、既存の関数を簡単に非同期マルチスレッド化することが可能です。

https://www.npmjs.com/package/worker-lib

# 画像変換ライブラリ

今回は以下の画像変換ライブラリを使用します。このライブラリは Node.js、Deno、Cloudflare Workers などのバックエンド環境だけでなく、Next.js や React Router などのフロントエンド環境でも利用可能です。

https://www.npmjs.com/package/wasm-image-optimization

# wasm と WebWorkers 環境の問題

面倒なのが WebAssembly の wasm バイナリを実行するための動作が、環境によって異なるという問題があります。Cloudflare Workers は wasm を import で処理しなければならず、Next.js(WebPack) や React Router(Vite) でバイナリが素直にバンドルされません。それぞれの環境に合わせて色々調整しています。さらに WebWorkers の使用時に js ファイルが単独でバンドルされる必要があるため、その点でも注意が必要です。Vite に関しては node_module 内の調整ではどうにもならなかったので、敗北を受け入れ Vite 用のプラグインを作りました。

その関係で package.json の exports 設定がカオスです。ライブラリ利用者側は特に細かいことを考えなくとも使えます。

https://github.com/node-libraries/wasm-image-optimization/blob/master/package.json

# サンプル

以下では、画像サイズ変更やフォーマット変換を行うサンプルコードを紹介します。また、OGP 生成における SVG から PNG への変換も含めています。ただし SVG に関しては、使用しているライブラリが現時点でフィルターに対応していないため、textShadow 属性を使用するとその部分の出力ができません。

https://github.com/SoraKumo001/wasm-image-optimization-samples

# ブラウザ上で変換の効果を確認

サンプルコードにて、Next.js と React Router を利用してブラウザ上での画像変換を行います。フレームワーク依存性はほとんどなく、コードが非常にシンプルです。各形式（未変換、webp、jpeg、png、avif）の出力結果および、Web Workers を使用した非同期処理による UI ブロックの回避も確認できます。

https://next-image-convert.vercel.app/

![変換の様子](https://raw.githubusercontent.com/node-libraries/wasm-image-optimization/refs/heads/master/doc/image.webp)

ちなみに画像圧縮に関しては avif が圧倒的に縮みます。ただし高圧縮を望むと変換に時間がかかります。変換パラメータとして Speed 項目があるのですが、0 設定にすると 1024\*1024 の画像変換に 1 分ぐらいかかるので実用性は微妙なところです。9 や 10 設定にすると webp よりも変換が高速になりますが、圧縮率とクオリティが犠牲になります。このあたりのさじ加減は、実際に試してみると良いと思います。

また、WebAssembly の実行速度に関して Chrome と Firefox で試した結果、Firefox の方が二割ぐらい速い感じです。

Next.js で動作させるときの注意点として TurboPack を使うと動きません。Vercel はそろそろ TurboPack の開発に見切りを付けた方が良いのではと個人的には思っています。

## ブラウザ上での画像変換サンプルコード抜粋

### 変換用コンポーネント

Web Workers の並列処理数を setLimit 関数で指定可能です。デフォルトは 4 ですが、必要に応じて調整できます。また、launchWorker を使用して事前に Web Workers を準備します。このプロセスは必須ではありませんが、初回の変換時間を正確に測定するためには推奨です。

`optimizeImageExt`に画像データを放り込むと指定したフォーマットで結果が返ってきます。width や height を指定しなかった場合は、サイズ変更なしの変換を行います。フォーマットに`none`を指定した場合は、画像変換を行わず、元画像の情報だけを返します。`waitReady`で WebWorkers のキューに空きができるのを待っていますが、待たなくともキューが積まれるだけなので必須ではありません。しかしこのコードの場合、変換時間の測定をしているのでキューの空きを待たないと、キューに積まれた時間から変換終了の時間を測定してしまいます。

ちなみにキューの制御などは先に紹介した worker-lib を使用しています。

```tsx
setLimit(8); // Web Worker limit
launchWorker(); // Prepare Worker in advance.

const formats = ["none", "webp", "jpeg", "png", "avif"] as const;
const AsyncImage: FC<{
  file: File;
  format: (typeof formats)[number];
  quality: number;
  speed: number;
  size: [number, number];
}> = ({ file, format, quality, size, speed }) => {
  const [time, setTime] = useState<number>();
  const [image, setImage] = useState<OptimizeResult | null | undefined>(null);
  useEffect(() => {
    const convert = async () => {
      setImage(null);
      // Wait for WebWorkers to become available.
      // If you don't wait, they will still be loaded in the queue, but the conversion time will no longer be accurately measured.
      await waitReady();
      const t = performance.now();
      const image = await optimizeImageExt({
        image: await file.arrayBuffer(),
        format,
        quality,
        speed,
        width: size[0] || undefined,
        height: size[1] || undefined,
      });
      setTime(performance.now() - t);
      setImage(image);
    };
    convert();
  }, [file]);
  const src = useMemo(
    () =>
      image &&
      URL.createObjectURL(
        new Blob([image.data], {
          type: format === "none" ? file.type : `image/${format}`,
        })
      ),
    [image]
  );
  const filename =
    format === "none" ? file.name : file.name.replace(/\.\w+$/, `.${format}`);
  return (
    <div className="border border-gray-300 rounded-4 overflow-hidden relative w-64 h-64 grid">
      {image === undefined && <div>Error</div>}
      {src && image && (
        <>
          <a download={filename} href={src}>
            <img
              className="flex-1 object-contain block overflow-hidden"
              src={src}
            />
          </a>
          <div className="bg-white/80 w-full z-10 text-right p-0 absolute bottom-0 font-bold">
            <div>{filename}</div>
            <div>{time?.toLocaleString()}ms</div>
            <div>
              {format !== "none" ? "Optimize" : "Original"}:{" "}
              {image.width.toLocaleString()}x{image.height.toLocaleString()} -{" "}
              {Math.ceil(image.data.length / 1024).toLocaleString()}KB
            </div>
          </div>
        </>
      )}
      {image === null && (
        <div className="m-auto animate-spin h-10 w-10 border-4 border-blue-600 rounded-full border-t-transparent" />
      )}
    </div>
  );
};
```

### 画像アップロード用コンポーネント

この ImageInput コンポーネントは、コピー&ペースト、ドラッグドロップ、ファイル選択ダイアログに対応した`Dorp here`機能を提供します。これらの方法で受け取った File インスタンスを画像変換処理に渡すことができます。

```tsx
const ImageInput: FC<{ onFiles: (files: File[]) => void }> = ({ onFiles }) => {
  const refInput = useRef<HTMLInputElement>(null);
  const [focus, setFocus] = useState(false);
  return (
    <>
      <div
        className={classNames(
          "w-64 h-32 border-dashed border flex justify-center items-center cursor-pointer select-none m-2 rounded-4xl p-4",
          focus && "outline outline-blue-400"
        )}
        onDragOver={(e) => {
          e.preventDefault();
          e.stopPropagation();
        }}
        onDragEnter={(e) => {
          e.preventDefault();
          e.stopPropagation();
        }}
        onDoubleClick={() => {
          refInput.current?.click();
        }}
        onClick={() => {
          refInput.current?.focus();
        }}
        onDrop={(e) => {
          onFiles(Array.from(e.dataTransfer.files));
          e.preventDefault();
        }}
      >
        Drop here, copy and paste or double-click to select the file.
      </div>
      <input
        ref={refInput}
        className="absolute size-0"
        type="file"
        multiple
        accept=".jpg,.png,.gif,.svg,.avif,.webp"
        onFocus={() => setFocus(true)}
        onBlur={() => setFocus(false)}
        onPaste={(e) => {
          e.preventDefault();
          onFiles(Array.from(e.clipboardData.files));
        }}
        onChange={(e) => {
          e.preventDefault();
          if (e.currentTarget.files) onFiles(Array.from(e.currentTarget.files));
        }}
      />
    </>
  );
};
```

# Node.js の CLI での利用例

以下では、Node.js の CLI を使用して実行するサンプルコードを紹介します。images フォルダ内のファイルを幅 512px の webp、jpeg、png、avif 形式に変換し、image_output フォルダに出力します。worker_threads を変換ライブラリ内部で使用することによって、マルチスレッドを利用した高速な処理が可能です。ただし、worker プールが残存しないようには close 関数を呼び出さなければなりません。

Worker 側を終了させずに process.exit を使うコードを見かけますが、親スレッドを強制終了させるのではなく Worker を終了させるのが真っ当です。

## シングルスレッド

順番通りに変換されます。

![](https://github.com/SoraKumo001/wasm-image-optimization-samples/raw/master/node-image-convert/document/convert_single.webp)

```ts
import { promises as fs } from "node:fs";
import { optimizeImage } from "wasm-image-optimization";

const formats = ["webp", "jpeg", "png", "avif"] as const;

const main = async () => {
  const title = "Single thread";
  console.time(title);
  await fs.mkdir("./image_output", { recursive: true });
  const files = await fs.readdir("./images");
  for (const file of files) {
    await fs.readFile(`./images/${file}`).then(async (image) => {
      console.log(
        `${file} ${Math.ceil(image.length / 1024).toLocaleString()}KB`
      );
      for (const format of formats) {
        const label = `[${file}] -> [${format}]`;
        console.time(label);
        await optimizeImage({
          image,
          quality: 80,
          format,
          width: 512,
        }).then((encoded) => {
          if (encoded) {
            console.timeLog(
              label,
              `${Math.ceil(encoded.length / 1024).toLocaleString()}KB`
            );
            const fileName = file.split(".")[0];
            fs.writeFile(`image_output/${fileName}.${format}`, encoded);
          }
        });
      }
    });
  }
  console.timeEnd(title);
};
main();
```

## マルチスレッド

変換が並列化されるので変換順序が狂いますが、処理速度が向上します。

![](https://github.com/SoraKumo001/wasm-image-optimization-samples/raw/master/node-image-convert/document/convert_multi.webp)

```ts
import { promises as fs } from "node:fs";
import {
  optimizeImage,
  close,
  setLimit,
} from "wasm-image-optimization/node-worker";

const formats = ["webp", "jpeg", "png", "avif"] as const;

setLimit(4); // set worker limit

const main = async () => {
  const title = "Multi thread";
  console.time(title);
  await fs.mkdir("./image_output", { recursive: true });
  const files = await fs.readdir("./images");
  const p = files.map(async (file) => {
    return fs.readFile(`./images/${file}`).then((image) => {
      console.log(
        `${file} ${Math.floor(image.length / 1024).toLocaleString()}KB`
      );
      const p = formats.map((format) => {
        const label = `[${file}] -> [${format}]`;
        console.time(label);
        return optimizeImage({
          image,
          quality: 100,
          format,
          width: 512,
        }).then((encoded) => {
          if (encoded) {
            console.timeLog(
              label,
              `${Math.floor(encoded.length / 1024).toLocaleString()}KB`
            );
            const fileName = file.split(".")[0];
            fs.writeFile(`image_output/${fileName}.${format}`, encoded);
          }
        });
      });
      return Promise.all(p);
    });
  });
  await Promise.all(p);
  close(); // close worker
  console.timeEnd(title);
};
main();
```

# まとめ

WebAssembly や WebWorkers で高速化できるという話はあれど、なかなか具体的な活用事例が出てこないので、あらゆる環境で実際に動作するようにしました。実装コードやサンプルは一通り揃えました。
