---
title: "Embedding Gemma 2 を C# から使用してマルチモーダル対応の検索アプリを作る"
emoji: "🦔"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: ["onnx", "directml", "dotnet", "winui", "embedding"]
published: true
---

画像・PDF・動画・テキストを「自然言語」や「画像」で横断検索できるデスクトップアプリを、完全ローカルで作りました。埋め込みモデルには Google DeepMind の EmbeddingGemma 2 の ONNX 版を使い、C#（WinUI 3）から ONNX Runtime + DirectML で直接動かしています。

「モデルを ONNX で動かす」だけなら公式のサンプルで済みますが、実際に作ってみると、前処理の移植、GPU（DirectML）で動かないグラフ、思ったほど速くならない原因の切り分け、実データ特有の検索ノイズなど、ハマりどころが多くありました。本記事では、その過程で分かったことを、計測値つきでまとめます。

先に結果だけ書いておきます。

| 項目 | 最初の実装 | 最終 |
|---|---|---|
| 画像 1 枚の埋め込み（直列） | 842 ms | 145 ms（4 並列） |
| GPU 使用率（平均） | 23% | 87% |
| 画像 967 枚の再インデックス | 822 秒 | 155 秒 |

※ 計測環境は Windows 11、NVIDIA GeForce RTX 4070 Ti、CPU 24 スレッド、ONNX Runtime 1.24.4（DirectML）です。画像は漫画のスキャン画像（jpg / png、大きいもので 4,300×6,000 px 程度）967 枚で、1 台の PC での結果です。環境やデータで数値は変わります。

---

## 1. 作ったもの

Windows上で動作します

https://github.com/SoraKumo001/embedding-search-viewer/releases

- 検索対象: 画像（jpg / png / webp / bmp）、PDF、動画（mp4 / wmv / avi / mov / webm / mkv / flv）
- 検索方法: 自然言語、画像（類似画像検索）、キーワード全文検索（SQLite FTS5）を併用
- 実行環境: 完全ローカル。クラウドの API は使いません（モデルは初回に Hugging Face からダウンロード）
- 技術: .NET / WinUI 3、ONNX Runtime（DirectML）、SkiaSharp、SQLite

```
[取り込み]                                  [検索]
フォルダ監視 / 手動                          クエリ（文章 or 画像）
   │                                           │
   ├─ 画像 ───────────────┐                    ▼
   ├─ PDF  → ページ画像 + テキスト ┤→ EmbeddingGemma 2 → 768 次元ベクトル
   └─ 動画 → 区間ごとのフレーム ────┘        │                │
                                          SQLite           コサイン類似度
                                    (ベクトル + FTS5) ──→  + FTS5（RRF で統合）
```

ポイントは、テキストも画像も同じ 768 次元の空間に埋め込まれることです。「赤い車」という文章と、赤い車の写真が、同じベクトル空間で比較できるため、種類の違うメディアを 1 つのインデックスで検索できます。

---

## 2. EmbeddingGemma 2 の ONNX 版の構成

使ったのは [`onnx-community/embeddinggemma-2-ONNX`](https://huggingface.co/onnx-community/embeddinggemma-2-ONNX) です。ライセンスは Apache-2.0 と表示されており、gated（利用許諾のクリックが必要な形式）ではないので、ログインなしでダウンロードできます（2026 年 10 月時点）。

```
onnx/
  model.onnx / model.onnx_data            言語モデル（テキストエンコーダ）  fp32 で 約 1.08 GB
  vision_encoder.onnx / .onnx_data        ビジョンエンコーダ               fp32 で 約 0.67 GB
  audio_encoder.onnx / .onnx_data         音声エンコーダ（今回は未使用）
  *_fp16 / *_q4 / *_quantized ...         精度違い
tokenizer.json, config.json, ...
```

### 2.1 2 段構成になっている

画像を埋め込むときは、1 つのモデルで完結しません。

```
画像 ──→ vision_encoder.onnx ──→ image_features [n, 512]   ← 画像を n 個の「ソフトトークン」に変換
                                        │
入力 ID: <bos> <|image> <|image|>×n <image|> <eos>
                                        │  ← <|image|> の位置に image_features が差し込まれる
                                        ▼
                                  model.onnx ──→ sentence_embedding [batch, 768]
```

`model.onnx`（言語モデル）の入力は次のとおりです（ONNX ファイルのヘッダを直接読んで確認しました）。

| 入力名 | 型・形状 | 内容 |
|---|---|---|
| `input_ids` | int64 `[batch, seq]` | トークン ID |
| `attention_mask` | int64 `[batch, seq]` | パディングのマスク |
| `image_features` | float `[n, 512]` | ビジョンエンコーダの出力（なければ `[0, 512]`） |
| `video_features` | float `[n, 512]` | 動画フレーム用（なければ `[0, 512]`） |
| `audio_features` | float `[n, 512]` | 音声用（なければ `[0, 512]`） |

出力の `sentence_embedding`（`[batch, 768]`）は、平均プーリングと L2 正規化まで済んでいます。使わない入力も、形状 `[0, 512]` の空テンソルを渡す必要があります。

ビジョンエンコーダの入力は `pixel_values`（float `[batch, パッチ数, 768]`）と `pixel_position_ids`（int64 `[batch, パッチ数, 2]`）で、出力は `image_features`（`[ソフトトークン数, 512]`）です。

### 2.2 テキストのプロンプト

用途ごとの接頭辞が決まっています（`config_sentence_transformers.json` の `prompts`）。

```csharp
const string QueryPrefix = "task: search result | query: ";   // 検索クエリ
// 文書側: $"title: {title} | text: {text}"（タイトルなしは "title: none | text: ..."）
// 画像には接頭辞をつけない
```

### 2.3 Matryoshka（MRL）

出力は 768 次元ですが、先頭から 512 / 256 / 128 次元に切り詰めて使えます。切り詰めたあとは L2 正規化をやり直す必要があります。

```csharp
static float[] PostProcess(float[] raw, int truncateDim)
{
    int dim = Math.Min(truncateDim, raw.Length);
    var result = raw.AsSpan(0, dim).ToArray();
    float norm = MathF.Sqrt(TensorPrimitives.SumOfSquares(result));
    if (norm > 0) for (int i = 0; i < result.Length; i++) result[i] /= norm;
    return result;
}
```

---

## 3. 画像の前処理を C# に移植する

ONNX にしても、前処理（リサイズ、パッチ分割）はモデルに含まれません。公式の実装は JavaScript（[transformers.js](https://github.com/huggingface/transformers.js) の `Gemma4ImageProcessor`）なので、これを C# に移植しました。README だけでは分からない仕様が多く、ソースを読むのが確実でした。

### 3.1 リサイズ: アスペクト比を保ち、48 の倍数にする

可変解像度で、縦横比を保ったまま「パッチ数の予算（280 トークン × 9 = 2,520 パッチ）」に収まるサイズに縮尺します。1 辺はパッチサイズ（16）× プーリングのカーネル（3）= 48 の倍数に切り捨てます。

```csharp
public static (int Height, int Width) GetTargetSize(int height, int width,
    int patchSize = 16, int maxPatches = 2520, int poolingKernelSize = 3)
{
    double targetPx = (double)maxPatches * patchSize * patchSize;
    double factor = Math.Sqrt(targetPx / ((double)height * width));
    int sideMult = poolingKernelSize * patchSize;   // 48

    int targetHeight = (int)(Math.Floor(factor * height / sideMult) * sideMult);
    int targetWidth  = (int)(Math.Floor(factor * width  / sideMult) * sideMult);
    // 極端な縦横比で片方が 0 になる場合の処理は省略
    return (targetHeight, targetWidth);
}
```

例えば 1000×1000 の画像は 768×768（48×48 = 2,304 パッチ、ソフトトークン 256 個）になります。リサンプリングは bicubic で、SkiaSharp の `SKCubicResampler.CatmullRom` を使いました。

### 3.2 パッチ分割と位置 ID

- 画素は 0〜1 に正規化するだけです（平均・標準偏差による正規化はなし）。
- 16×16 の領域ごとに、`(dy, dx, チャンネル)` の順で 768 要素に並べます。
- 位置 ID は `(列, 行)` の順で、余りのパッチは -1 で埋めます。
- ソフトトークンの数は `パッチ数 / 9` です（3×3 でプーリングされる）。

```csharp
// 位置 ID: meshgrid(arange(W), arange(H), indexing="xy") → [col, row]
var positions = new long[maxPatches * 2];
Array.Fill(positions, -1L);                      // パディングは -1
int idx = 0;
for (int row = 0; row < patchesH; row++)
    for (int col = 0; col < patchesW; col++)
    {
        positions[idx++] = col;
        positions[idx++] = row;
    }
```

アルファチャンネルのある PNG は、PIL の `convert("RGB")` と同じく、アルファを捨てて RGB だけを使います。SkiaSharp では、既定の「プリマルチプライ済み」で読み込むと色が変わってしまうので、`SKAlphaType.Unpremul` を指定して読みました。

### 3.3 言語モデルへの入力 ID

画像は、`<|image>` と `<image|>` で挟んだ `<|image|>` をソフトトークンの数だけ並べます。トークナイザーを通さず、ID を直接組み立てました（ID は `config.json` の `image_token_id` などから）。

```csharp
// <bos> <|image> <|image|> x n <image|> <eos>
var ids = new long[n + 4];
ids[0] = 2;                                    // <bos>
ids[1] = 255999;                               // <|image>
for (int i = 0; i < n; i++) ids[2 + i] = 258880;   // <|image|>
ids[n + 2] = 258882;                           // <image|>
ids[n + 3] = 1;                                // <eos>
```

`<|image|>` の数と `image_features` の行数が一致しないとエラーになります。

---

## 4. ONNX Runtime + DirectML で GPU に載せる

ここが一番時間を使ったところです。

### 4.1 そのままでは DirectML で動かない（`allowzero`）

ビジョンエンコーダを DirectML で実行すると、`Reshape` ノードで次のエラーになりました。

```
Non-zero status code returned while running Reshape node. Name:'node_view_1'
... DmlExecutionProvider ... 80070057 (パラメーターが間違っています)
```

fp16 でも fp32 でも、グラフ最適化レベルや、入力のパディング有無を変えても同じでした。ONNX のグラフを調べると、すべての `Reshape` に `allowzero=1` という属性が付いていました。DirectML はこの属性を受け付けないようです（手元の ORT 1.24.4 での挙動で、ほかの版は未確認です）。

このモデルでは、形状に 0 は含まれないので、`allowzero=0` にしても結果は変わりません。属性の値は 1 バイトなので、ファイルサイズも外部の重みファイルへの参照も変えずに、バイト列を書き換えるだけで直せます。

```csharp
// 属性名 "allowzero" に続く: field 3 (i) = 1、field 20 (type) = INT
static readonly byte[] AllowZeroOn  = Concat("allowzero"u8, new byte[] { 0x18, 0x01, 0xA0, 0x01, 0x02 });
static readonly byte[] AllowZeroOff = Concat("allowzero"u8, new byte[] { 0x18, 0x00, 0xA0, 0x01, 0x02 });
// モデル全体の中から AllowZeroOn を探して AllowZeroOff に置換（128 か所）
```

元のファイルは変更せず、隣に `*.dml2.onnx` というコピーを作って、DirectML のときだけそちらを読み込む形にしました。

### 4.2 動いたのに遅い: プロファイラでボトルネックを探す

パッチ後は動きましたが、ビジョン 1 回が約 450 ms かかり、GPU 使用率は 20% 台でした。推測で最適化する前に、ONNX Runtime のプロファイラで、どの演算がどのプロバイダ（GPU / CPU）で、どれだけ時間を使っているかを見ました。

```csharp
using var options = new SessionOptions();
options.AppendExecutionProvider_DML(0);
options.EnableProfiling = true;
options.ProfileOutputPathPrefix = prefix;
using var session = new InferenceSession(modelPath, options);
// 数回 Run してから
string json = session.EndProfiling();     // Chrome トレース形式の JSON
```

JSON のうち `cat == "Node"` のイベントは、`args.provider` と `args.op_name`、`dur`（マイクロ秒）を持っています。演算ごとに集計した結果（1 回の実行あたり、約 480 ms 中）は次のとおりです。

| 演算 | 実行場所 | 時間 |
|---|---|---|
| `MemcpyToHost`（19 ノード） | GPU → CPU のコピー | 257 ms |
| `MemcpyFromHost`（17 ノード） | CPU → GPU のコピー | 53 ms |
| `Gelu`（16 ノード） | CPU | 54 ms |
| `SimplifiedLayerNormalization` | GPU | 28 ms |
| `MatMul` ほか（行列計算） | GPU | 合計で数十 ms |

時間の約 75% が、GPU ↔ CPU のコピーと CPU の `Gelu` でした。行列計算そのものは速いのに、各層（16 層）で「GPU から取り出す → CPU で `Gelu` → GPU に戻す」という往復が発生していたことになります。

### 4.3 `Gelu` を `FastGelu` に置き換える

このモデルの `Gelu` は、標準の ONNX 演算子（opset 20）で `approximate="tanh"` です。DirectML 実行プロバイダがこの演算子を実装していないため、CPU に回されていました。

Microsoft の拡張演算子 `com.microsoft::FastGelu` は、同じ tanh 近似の式です。

```
FastGelu(x) = 0.5 · x · (1 + tanh(√(2/π) · (x + 0.044715 · x³)))
```

グラフを書き換えて、`Gelu` を `FastGelu` に置き換えました。文字列の長さが変わるので、今回は protobuf の構造を読んで書き直しています（ノードの `op_type` はフィールド 4、`attribute` は 5、`domain` は 7）。

```csharp
// NodeProto のうち op_type == "Gelu"、domain が空、approximate == "tanh" のものだけ
case 4: WriteBytesField(ms, 4, "FastGelu"u8.ToArray()); break;        // op_type を差し替え
case 5: break;                                                         // approximate 属性を削除
case 7: WriteBytesField(ms, 7, "com.microsoft"u8.ToArray()); break;    // domain を設定
```

モデルは `com.microsoft` の演算子セットをすでに import しています（`MultiHeadAttention` などを使っているため）。

書き換えが正しいかは、次の 2 つで確認しました。

1. 最小の ONNX モデルを組み立てて、元のモデルとパッチ後のモデルを ORT（CPU）で実行し、出力が一致する（単体テスト）。
2. 実モデルで、GPU（パッチ後）と CPU（元のモデル）の最終的な埋め込みを比較し、コサイン類似度が最小 0.999997。

結果は次のとおりです。

| | パッチ前 | パッチ後 |
|---|---|---|
| ビジョン 1 回（GPU） | 約 450 ms | 約 140 ms |
| 言語モデル（画像 1 枚分、約 264 トークン） | CPU で約 230 ms | GPU で約 30 ms |

言語モデルのほうにも `Gelu` が 48 個あり、同じ原因で GPU では遅かったのですが、パッチで一緒に解決しました。

### 4.4 DirectML は入力の形状が変わると遅い

もう 1 つ、実測で分かったことがあります。言語モデルに、長さを変えながらテキストを入れてみた結果です（fp32、1 件ずつ）。

| 条件 | CPU | DirectML |
|---|---|---|
| 同じ長さ（12 トークン）を繰り返す | 約 38 ms | 約 27 ms |
| 長さが毎回変わる | 37〜54 ms | 約 290〜350 ms |

同じ長さなら GPU のほうが速いのに、入力の形状が変わると 300 ms 前後のコストがかかります。DirectML は入力の形状ごとにグラフを準備し直している、と理解しています（内部の仕組みは確認していません）。なお、この表は `Gelu` を置換する前のモデルで測ったものです。同じモデルで「同じ長さ」と「長さが変わる」を比べた差なので、形状の変化によるコストだと判断しましたが、置換後のモデルで測り直してはいません。そこで次のように使い分けました。

- 短いテキストのクエリ（数十トークン）: CPU に任せる。約 40 ms で、GPU を占有しない。
- 画像の言語モデル: 長さを固定してパディングする（`280 + 4 = 284` トークン、マスクで無効化）。形状が 1 種類だけなので、準備し直しが起きない。
- ビジョンエンコーダ: 入力を常に最大パッチ数（2,520）に固定する（`-1` の位置 ID のパッチは無視される。CPU の結果と一致することを確認）。

```csharp
// 画像 1 枚あたり: <bos> <|image> + 最大 280 個 + <image|> <eos>
const int GpuImageSequenceLength = Gemma4ImagePreprocessor.MaxSoftTokens + 4;
```

### 4.5 同時実行はできない（排他制御）

DirectML のセッションは、同じセッションを複数のスレッドから同時に `Run` すると失敗しました（`MemcpyToHost` のエラー）。セッションごとにロックを持たせ、GPU の部分だけを直列にしています。

一方で、画像のデコード・リサイズ・パッチ分割（CPU）は、複数の画像を並行して処理できます。GPU が 1 枚を処理している間に、次の画像の前処理や、別の画像のテキスト側の計算を進める、という並行化です。

```csharp
Parallel.ForEach(images, new ParallelOptions { MaxDegreeOfParallelism = 4 },
    image => results[image.Index] = EncodeImage(image.Path, truncateDim, skipBlank: true));
```

同じ理由で、トークナイザー（Tokenizers.DotNet のネイティブライブラリ）も、複数スレッドからの同時呼び出しでプロセスごと異常終了しました。ロックで囲んで解決しています。

### 4.6 精度の選択: fp32 / fp16 / q8

CPU で、同じ 8 枚の画像と 10 個のテキストを使って比較しました（1 件あたりの時間と、fp32 の結果との一致度）。

| 精度 | テキスト | 画像 | fp32 との類似度（画像） | 備考 |
|---|---|---|---|---|
| fp32 | 37 ms | 3,059 ms | ― | |
| fp16 | 49 ms | 3,793 ms | 1.0000 | NaN なし |
| q8（量子化） | 597 ms | 4,691 ms | 最小 0.9948 | 遅い、精度も下がる |

q8 は CPU では速くならず、画像の上位 1 位がずれるケースも出たので、候補から外しました。fp16 はこのデータでは fp32 とほぼ同じでしたが、Gemma 系は fp16 で中間活性値がオーバーフローするという報告があり、全入力で安全とは言い切れません。そこで既定は fp32 にしました（text 1.08 GB + vision 0.67 GB の約 1.76 GB）。

### 4.7 結果

画像 40 枚（長辺が大きいスキャン画像）を、取り込みと同じ経路で処理した結果です。`nvidia-smi` で GPU 使用率を 150 ms ごとに採取しました。

| 構成 | 1 枚あたり | GPU 使用率（平均） |
|---|---|---|
| 直列（`allowzero` の修正のみ。`Gelu` は CPU のまま） | 842 ms | 23% |
| 直列、`Gelu` も置換 | 481 ms | 21% |
| 直列、さらに言語モデルも GPU | 268 ms | 50% |
| 2 並列 | 183 ms | 72% |
| 4 並列 | 145 ms | 87%（最大 100%） |

4 並列では、ビジョンの GPU 実行（約 140 ms）にほぼ張り付いていて、これ以上は、ビジョン自体を速くする（fp16、解像度の予算を下げるなど）必要があります。

---

## 5. 検索の仕組み

### 5.1 ベクトル + 全文検索を RRF で統合

- ベクトル検索: クエリを埋め込み、全チャンクとのコサイン類似度を計算（`TensorPrimitives.CosineSimilarity`）。
- 全文検索: SQLite の FTS5（ファイル名やテキストのスニペット）。
- 統合: Reciprocal Rank Fusion（RRF）。ベクトル側の順位を `1/(k + rank)`、全文側を `0.5/(k + rank)` として足し合わせます（k = 60）。

全チャンクを毎回 DB から読むと遅いので、メモリにキャッシュしています。DB に「データのバージョン」（保存・削除のたびに増える整数）を持たせ、バージョンが変わるまでキャッシュを使います。

### 5.2 同点の順位は「パス」で決める

RRF の順位計算は、ベクトルのスコアで並べ替えて順位を振ります。ところが、同じスコアのもの（後述の同一画像）の順位が、DB の格納順に依存して不安定でした。同点はファイルパスの順で決めるようにして、検索結果が毎回同じになるようにしました。

### 5.3 メタデータの絞り込みは「最終段」でもかける

期間・サイズ・フォルダ・メディア種別の絞り込みは、候補のチャンクに対してかけます。ここで 1 つバグを作りかけました。全文検索だけでヒットした項目は、候補一覧を通らないため、フィルタを素通りします。最終的な結果を作る段階でも、同じフィルタを再度かける必要があります（これを外すとテストが落ちるようにしてあります）。

---

## 6. 実データで見つけた問題

### 6.1 白紙のページが、一般的な検索語の上位に来る

インデックスを作ったあとに「a girl with long hair」「a red car」で検索すると、上位 5 件が別々のファイルなのに、まったく同じスコア（0.670、0.640）でした。調べると、埋め込みが完全に同一の画像が 7 枚あり、いずれも真っ白なページでした。

白紙のような画像は、「何も写っていない」ために、どんな一般的な文章に対しても、そこそこ似ている（類似度が中程度）という性質があります。ベクトル検索ではよく起きる現象（ハブネス）で、結果の上位を占領してしまいます。

そこで、ほぼ一色の画像はインデックスしないことにしました。判定には、輝度の標準偏差と、上位 1%〜下位 1% の幅を使います。

```csharp
public const double BlankStdDevMax = 5.0;
public const double BlankRangeMax  = 24.0;
public static bool IsBlank(double stdDev, double range) => stdDev < BlankStdDevMax && range < BlankRangeMax;
```

しきい値は、実データ 967 枚の分布から決めました（輝度の標準偏差の小さい順）。

| 標準偏差 | 1%〜99% の幅 | 内容 |
|---|---|---|
| 0.00（9 枚） | 0 | 真っ白なページ |
| 3.39 | 11 | ほぼ真っ暗な一色のページ（右下にページ番号だけ） |
| 10.42 | 58 | 文字のあるページ（内容がある中で一番「静か」なページ） |
| 13.57 以上 | 63 以上 | ふつうのページ |

3.39 と 10.42 の間に大きな隔たりがあるので、5.0 / 24 を境にしても、内容のあるページを誤って外すことはありませんでした。判定は、リサイズ後の画像（すでにデコード済み）で行うので、追加のデコードは不要です。さらに、ビジョンエンコーダを動かす前に判定して、白紙ならそこで打ち切ります。

埋め込みサービスのインターフェースには、「空の配列を返したら、埋め込まない（保存しない）」という約束を加えました。

### 6.2 同一の埋め込みは、検索結果で 1 件にまとめる

白紙以外にも、同じ画像のコピー（別のフォルダの同一ファイルなど）が、埋め込みも完全に同一になります。ファイル自体は別物なので、インデックスから消すのではなく、検索結果のときに代表の 1 件にまとめ、「同一画像 他 N 件」と表示します。

```csharp
// 埋め込みのバイト列の SHA-256 の先頭 8 バイトを「グループ ID」にする
var hash = SHA256.HashData(MemoryMarshal.AsBytes(chunk.Embedding.AsSpan()));
groups[chunk.Id] = BitConverter.ToUInt64(hash, 0) | 1UL;   // 0 は「埋め込みなし」の意味
```

結果を並べ替えたあと、グループごとに最上位のものだけを残し、残りのパスを代表に持たせます。件数の上限（TopK）の前にまとめるので、同一画像が 60 枚あっても、枠は 1 つしか使いません。

---

## 7. PDF と動画の取り込み

最初の実装は、PDF のページ抽出と動画のシーン抽出を Python のサイドカー（PyMuPDF、ffmpeg のコマンド呼び出し）に頼っていて、ONNX 単体のときは「ファイル名だけを埋め込む」処理になっていました。これを、すべて .NET の中で完結させました。

### 7.1 PDF: Windows 標準のレンダラ + PdfPig

- ページの描画: `Windows.Data.Pdf`（`PdfDocument.LoadFromFileAsync` → `PdfPage.RenderToStreamAsync`）。追加のネイティブファイルは不要です。
- テキストの抽出: PdfPig（純 .NET）。Windows の API にはテキスト抽出がありません。
- 1 ページごとに、画像のチャンクと、テキストが 20 文字を超えるページにはテキストのチャンクも作ります。

ハマった点として、出力ピクセル数が表示倍率で変わる問題がありました。150 DPI 相当（816×1056 DIP のページなら 1,275×1,650 px）を指定して描画したところ、出力は 1,594×2,063 でした。ちょうど 1.25 倍で、この PC の表示倍率（125%）です。`DestinationWidth` は DIP（論理ピクセル）として扱われ、表示倍率が掛かるようです。環境で解像度が変わるのは困るので、最初のページで実際の出力幅を測り、倍率を補正して描き直すようにしました。

```csharp
var (actual, requested) = await RenderPageAsync(document, index, imagePath, correction);
if (index == 0 && Math.Abs((double)actual / requested - 1.0) > 0.02)
{
    correction = (double)requested / actual;      // 以降のページはこの倍率で指定する
    await RenderPageAsync(document, index, imagePath, correction);
}
```

もう 1 つ、ページ数の多い PDF でメモリ不足になる問題がありました。349 ページの PDF で、テキストを全ページまとめて 1 回のバッチで言語モデルに渡したところ、`bad allocation`（メモリ確保の失敗）になりました。言語モデルは、トークンごとに、全 24 層分のバッファ（1 トークンあたり数十 KB）を持ちます。1 回の実行あたりのトークン数に予算（4,096）を設け、長さの近いものをまとめて分割しました。

```csharp
internal static List<int[]> PlanTextRuns(IReadOnlyList<int> lengths, int maxTokensPerRun = 4096, int maxSequencesPerRun = 32)
{
    // 長さの昇順に並べ、(件数 × 最長) が予算に収まる範囲でひとまとめにする
    ...
}
```

結果は、349 ページ（698 チャンク）で 263 秒、67 ページ（128 チャンク）で 58 秒でした（1 ページあたり約 0.75〜0.86 秒）。テキストの埋め込みが CPU 実行なので、これが律速になっていると見ています。

### 7.2 動画: 区間ごとの中央フレーム

動画は、15 秒ごとに（3 秒の重なりを持たせて）区間を切り、各区間の中央のフレームを 1 枚取り出して、画像と同じ経路で埋め込みます。

フレームの取り出しには 2 つの方法を用意し、順に試します。

1. FFmpegInteropX の `FrameGrabber`: webm / flv / HEVC なども読める。FFmpeg の DLL が x64 で約 43 MB 増える。
2. Windows 標準（`Windows.Media.Editing` の `MediaComposition.GetThumbnailAsync`）: 追加の配布物なし。

```csharp
public sealed class VideoSegmentExtractor : IVideoSegmentExtractor
{
    // 1 つ目で開けて、かつ 1 枚でもフレームが取れたらそれを採用。だめなら次へ
    ...
}
```

同じファイルで測ると、FFmpeg のほうが速かったので、FFmpeg を先にしています。

| ファイル | FFmpeg | Windows 標準 |
|---|---|---|
| AVI（30 秒、3 区間） | 0.1 秒 | 12.9 秒（初回） |
| mov（16 秒、2 区間） | 0.4 秒 | 1.0 秒 |

単体テストは、`MediaComposition` で赤・緑・青の動画（`MediaClip.CreateFromColor`）を生成し、区間の中央フレームが期待の色になることを確かめています。実際のエンコードと抽出を通すので、偽物ではなく本物の経路のテストになります。

---

## 8. モデルの初回ダウンロード

モデルは約 1.76 GB あるので、アプリに同梱せず、初回起動時に Hugging Face からダウンロードします。

- 固定リビジョン: URL に、コミットハッシュを含めて固定します（`/resolve/<commit>/<path>`）。モデルが更新されても、インデックスとの整合性が崩れません。
- サイズと SHA-256 の検証: 公開 API（`/api/models/<id>?blobs=true`）の `siblings[].lfs.sha256` を、マニフェストとして埋め込みました。ダウンロードしたファイルは、これと照合します。
- 途中再開: `name.part` に書き込み、中断後は `Range: bytes=N-` で再開します。サーバーが Range を無視して `200` を返したら、最初からやり直します。照合に成功してから、本来の名前に移動します。
- 空き容量の確認、リトライ（最大 4 回、待ち時間を 2 秒、4 秒、6 秒と段階的に延ばす）、進捗（ファイル、速度、残り時間）の表示。
- 再起動なしで切り替え: アプリ全体が使う埋め込みサービスを、ホスト（`EmbeddingServiceHost`）で包みます。モデルがないときは「利用不可」状態で起動し、ダウンロード完了後に本物のエンジンへ差し替えます。

```csharp
public sealed class EmbeddingServiceHost : IEmbeddingService
{
    public Task ReloadAsync() => Task.Run(() =>
    {
        var next = SafeCreate();                       // 失敗したら「理由つきの利用不可」を返す
        var previous = Interlocked.Exchange(ref _inner, next);
        (previous as IDisposable)?.Dispose();
        Changed?.Invoke();
    });
}
```

単体テストは、偽のサーバー（`HttpMessageHandler`）で、再開・Range 無視・破損の検出・リトライ・キャンセルを確認しています。さらに本物のサーバーに対して、約 33 MB の 3 ファイルで、途中キャンセル → 再開 → 検証が通ることも確認しました。

インデックスとモデルの対応: 別のモデルで作った埋め込みを混ぜると、検索結果が無意味になります。インデックスを作ったモデルの識別子（例: `embeddinggemma-2-onnx-fp32`）を保存しておき、違うモデルのインデックスが残っていたら、警告を出して再作成を促します。

---

## 9. ハマりどころのまとめ

| 症状 | 原因 | 対処 |
|---|---|---|
| DirectML でビジョンが `Reshape` で失敗 | `allowzero=1`（DirectML 非対応） | バイト列を書き換えて `allowzero=0` にしたコピーを使う |
| GPU に載せたのに遅い、GPU 使用率 20% | `Gelu` が CPU にフォールバックし、GPU↔CPU のコピーが往復 | プロファイラで特定し、`FastGelu` に置換 |
| 入力の長さが変わるたびに約 300 ms 遅い | DirectML が形状ごとにグラフを準備し直す | 長さを固定してパディング、短いクエリは CPU |
| 複数スレッドで GPU を使うと失敗 | DirectML のセッションは同時実行に非対応 | セッションごとにロック |
| トークナイザーでプロセスごと異常終了 | ネイティブライブラリが並行呼び出しに非対応 | ロック |
| 長い PDF で `bad allocation` | 全ページのテキストを 1 回で実行 | トークン数の予算でバッチを分割 |
| PDF の画像が環境で 1.25 倍になる | `DestinationWidth` に表示倍率が掛かる | 最初のページで測って補正 |
| 一般的な検索語で白紙が上位に | 白紙の埋め込みが、どの文章にも中程度に似る | ほぼ一色の画像をインデックスしない |
| 同点の順位が毎回変わる | 同一スコアの並びが DB の格納順に依存 | 同点はファイルパスで決める |
| 全文検索だけでヒットしたものが、絞り込みを素通り | 候補一覧を通らない | 最終段でも、同じフィルタをかける |

あと 1 つ、計測の方法として、次の 2 つが役に立ちました。

- ONNX Runtime のプロファイラ（`EnableProfiling`）: 演算ごと・プロバイダごとの時間が分かる。「GPU を使っているはずなのに遅い」ときの第一手です。
- `nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits -lms 150`: 実行中の GPU 使用率を、一定間隔で採取する。

---

## 10. まとめ

- EmbeddingGemma 2 の ONNX 版は、テキストと画像を同じ 768 次元の空間に埋め込めるので、1 つのインデックスで、画像・PDF・動画を横断検索できます。ただし、前処理（リサイズ、パッチ分割、プロンプトの組み立て）は自分で移植する必要があります。
- DirectML で動かすときは、グラフのどの演算が GPU 非対応かをプロファイラで調べるのが近道です。今回は、2 か所のグラフ修正（`allowzero`、`Gelu`）で、ビジョンが約 3 倍速くなり、全体では約 5.8 倍（842 → 145 ms/枚）になりました。
- 実データには、モデルの外側で対処すべきノイズ（白紙、同一画像）があります。

## 参考

- [onnx-community/embeddinggemma-2-ONNX（Hugging Face）](https://huggingface.co/onnx-community/embeddinggemma-2-ONNX)
- [transformers.js: `Gemma4ImageProcessor` と `EmbeddingGemma2Processor`](https://github.com/huggingface/transformers.js)
- [ONNX Runtime DirectML 実行プロバイダ](https://onnxruntime.ai/docs/execution-providers/DirectML-ExecutionProvider.html)
- [FFmpegInteropX](https://github.com/FFmpegInteropX/FFmpegInteropX)
- [PdfPig](https://github.com/UglyToad/PdfPig)
