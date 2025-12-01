---
title: "Next.js から WebGPU を使用する"
emoji: "💭"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [nextjs, webpgu, typescript]
published: true
---

# サンプルリポジトリ

https://github.com/SoraKumo001/next-web-gpu

# CPU と GPU

一般的な CPU と GPU、どちらの演算速度が速いかというと、圧倒的に CPU です。ではなぜ色々な演算に GPU が用いられているかというと、その理由は並列数にあります。個別の速度ではなく、圧倒的な物量でその優位性を発揮します。

プログラムの基本動作は CPU で行われるわけですが、大量のデータに対して特定の演算を行いたい場合に GPU を利用すると優位性を発揮する場合があるのです。ただ、大量のデータを演算しなければならないというケースが限られているため、Web アプリケーションなどで利用することは稀です。

# 簡単なサンプルを Next.js で作る

本当に必要なケースを想定して作ると、プログラムの規模た大きくなり解説に不向きになるので、配列の中の値を足すだけという非常に単純なコードを作ってみます。素の Node.js は WebGPU をサポートしていないため、バックエンド側では実行できないので注意してください。

## types の追加

TypeScript で利用する場合は、WebGPU の型定義が必要になります

- tsconfig.json

```json
{
  "compilerOptions": {
    "types": ["@webgpu/types"]
  }
}
```

## 配列内の数値を足すサンプル

下準備が面倒です

- デバイスの取得
- 入力用バッファの作成
- 入力バッファにデータを転送
- 出力用バッファの作成
- シェダーやバッファをリソースとして投入
- 実行
- 読み込み用バッファの作成
- 実行結果を転送

という作業が必要になります。GPU がアクセスできるのは VRAM 上のデータなので、メインメモリとのやり取りが回りくどくなります。またシェーダーを使って動作手順を指定する必要があります。

- app/libs/addAll.ts

```ts
//最大並列数
const MaxThread = 64;

export async function addAll(targets: number[], value: number) {
  // デバイスの取得
  const device = await navigator.gpu
    .requestAdapter()
    .then((adapter) => adapter?.requestDevice());
  if (!device) throw "No device found";
  // バッファサイズの計算
  const bufferSize = targets.length * Float32Array.BYTES_PER_ELEMENT;

  // 入力用バッファ
  const inputBuffer = device.createBuffer({
    size: bufferSize,
    usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST,
    mappedAtCreation: true,
  });
  new Float32Array(inputBuffer.getMappedRange()).set(targets);
  inputBuffer.unmap();

  // 出力用バッファ
  const outputBuffer = device.createBuffer({
    size: bufferSize,
    usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_SRC,
  });

  // 加算用シェーダ
  const shaderCode = `
    @group(0) @binding(0) var<storage, read> inputBuffer : array<f32>;
    @group(0) @binding(1) var<storage, read_write> outputBuffer : array<f32>;
    @compute @workgroup_size(${MaxThread})
    fn main(@builtin(global_invocation_id) index : vec3<u32>) {
      let idx = index.x;
      outputBuffer[idx] = inputBuffer[idx] + ${value};
    }
  `;

  // リソースの準備
  const shaderModule = device.createShaderModule({ code: shaderCode });
  const pipeline = device.createComputePipeline({
    layout: "auto",
    compute: {
      module: shaderModule,
    },
  });
  const bindGroup = device.createBindGroup({
    layout: pipeline.getBindGroupLayout(0),
    entries: [
      { binding: 0, resource: { buffer: inputBuffer } },
      { binding: 1, resource: { buffer: outputBuffer } },
    ],
  });

  // 実行処理
  const commandEncoder = device.createCommandEncoder();
  const passEncoder = commandEncoder.beginComputePass();
  passEncoder.setPipeline(pipeline);
  passEncoder.setBindGroup(0, bindGroup);
  passEncoder.dispatchWorkgroups(Math.ceil(targets.length / MaxThread));
  passEncoder.end();

  // 読み出し用バッファ
  const readBuffer = device.createBuffer({
    size: bufferSize,
    usage: GPUBufferUsage.COPY_DST | GPUBufferUsage.MAP_READ,
  });
  commandEncoder.copyBufferToBuffer(outputBuffer, 0, readBuffer, 0, bufferSize);

  // 実行の確定と処理街
  device.queue.submit([commandEncoder.finish()]);

  // 実行結果を取り出す
  await readBuffer.mapAsync(GPUMapMode.READ);
  const resultArray = new Float32Array(readBuffer.getMappedRange().slice(0));
  readBuffer.unmap();
  return Array.from(resultArray);
}
```

## Next.js から呼び出す

実行すると配列の内容に所定の値を加算して結果を表示します。GPU を使う必要があるかというと、まったくありません。普通にループで計算したほうが速いです。

```tsx
"use client";

import { useState } from "react";
import { addAll } from "./libs/addAll";

const srcValues = [10, 20, 30, 40, 50];

export default function Home() {
  const [value, setValue] = useState(100);
  const [result, setResult] = useState<number[]>([]);
  return (
    <div className="p-4 grid gap-2 w-3xl">
      <input
        className="input"
        type="number"
        value={value}
        onChange={(e) => setValue(Number.parseFloat(e.target.value))}
      />
      <button
        type="button"
        className="btn w-16"
        onClick={() => addAll(srcValues, value).then(setResult)}
      >
        Add
      </button>
      <pre className="p-2 border">{JSON.stringify(srcValues)}</pre>
      <pre className="p-2 border">{JSON.stringify(result)}</pre>
    </div>
  );
}
```

## 実行結果

https://next-web-gpu.vercel.app/

![](/images/next-web-gpu/2025-12-01-09-05-16.webp)

# まとめ

ブラウザの WebGPU のサポートがひととおり行われたため、気軽に使えるようになりました。ただ、大量のデータとそれに対する演算をぶん回さないといけないケースが一般的なアプリケーションではほとんど発生しないため、ほとんどの人に使い道がないという状況です。
