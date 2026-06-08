---
title: "Remix3 を非同期コンポーネント対応に魔改造、簡単 SSR フレームワーク化"
emoji: "🐈"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: ["remix", "react", "ssr", "typescript", "cloudflare"]
published: true
---

# Demoに関して

- Demoリポジトリ(Remix3のUIパッケージだけ利用しています)
  https://github.com/SoraKumo001/remix3-fork
- Demoサンプルのトップ部分(非同期コンポーネントの使い方)
  https://github.com/SoraKumo001/remix3-fork/blob/main/demos/remix3-sample01/src/routes/index.tsx
- Demo
  https://remix3-fork-sample01.mofon001.workers.dev/

Demo は Remix3 の UI パッケージを改造して実装しています。その他の Remix3 のパッケージは使用しておらず、Vite + Hono + Tailwind + Cloudflare という構成になっています。

# Remix3とSSR

Remix3はSSRで非同期で取得したデータをシームレスに統合する機能を持っておらず、現在の機能でそれを実装しようとすると、別URLや別ファイルからUI断片を読み込んで差し込むためのFrame機能を使って強引にやるしかありません。この問題を解決するため、@remix-run/uiのコードを変更して、通常コンポーネントを非同期に対応させる実験を行いました。

# ReactとRemix3の違い

| 観点                 | React                                                                                                  | Remix3                                                                                                         |
| -------------------- | ------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------- |
| ステートの保持方法   | Fiberやdispatcherを通じて、Hooksの呼び出し順に対応するステートを管理します。                           | コンポーネントのセットアップ関数内で作られたローカル変数を、返されたレンダー関数のクロージャとして保持します。 |
| コンポーネントの形   | コンポーネント関数が直接UIを返します。                                                                 | セットアップ関数がレンダー関数を返す2層構造です。                                                              |
| 呼び出し順序への依存 | Hooksの呼び出し順序が変わらないことが重要です。                                                        | ステートはローカル変数としてコンポーネントインスタンスに閉じ込められます。                                     |
| 標準の非同期手段     | RSCのサーバーコンポーネントでは `async` コンポーネントを扱えますが、クライアントステートは使えません。 | Frameを使うと外部コンテンツを非同期に組み込めます。                                                            |

この違いにより、Remix3ではセットアップ処理を非同期化しても、Reactの通常コンポーネントよりステートの対応関係を壊しにくい構造になっています。セットアップフェーズだけを `async` 化し、解決後にレンダー関数へ進む形にできるためです。一方で、どちらも標準機能だけでは、通常コンポーネント上に自由にデータ取得とステートを同居させる形には制約があります。

たとえばRemix3では、セットアップ関数内で作った `let count = 0` のようなローカル変数が、返されたレンダー関数のクロージャに残ります。レンダー関数が再実行されてもセットアップ関数は毎回実行されないため、コンポーネントインスタンスごとの状態として扱えます。この性質が、セットアップフェーズで非同期処理を待ってからレンダー関数を返す、という改造の土台になります。

# Remix3の標準の非同期コンポーネント

Remix3の標準機能としてFrameコンポーネントを事実上の非同期コンポーネントとして扱うことができます。ただし本来の使用目的は、実行中に外部ファイルからコンポーネントを取ってきて、それをツリー上に組み込むためのものです。そのためFrameに用意されている引数は、対象コードのアドレスを渡すためのsrcを指定するというのが前提になり、通常コンポーネントのようにパラメータを複数設定してレンダリングを行うような用途は前提とされていません。

ただ、Remix3のコードを見てみると、Frameの処理に関してはasync/awaitが使用されており、通常コンポーネントのレンダリング処理もその近くにあります。実装の入口はかなり近い場所にあり、通常コンポーネントの非同期化も試せそうだと想像できます。

# Remix3の通常コンポーネントの非同期化

通常コンポーネントを非同期（`async/await`）に対応させるため、今回は以下の魔改造を加えました。

1. **通常コンポーネントを async で定義可能にする**
2. **通常コンポーネントの初期化 Promise を保持して、解決後に再描画する**
3. **通常コンポーネントの handle に非同期データ保持機能を追加する**
4. **保持した非同期データをハイドレーション後に利用できるように転送する**

これにより、コンポーネントの初期化（セットアップ）フェーズで非同期データ取得がシームレスに行えるようになります。

主に変更した場所は以下です。

| ファイル                                                               | 役割                                                                                                                 |
| ---------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `packages/ui/src/runtime/component.ts`                                 | 通常コンポーネントが `Promise<RenderFn>` を返せるようにし、`handle.async` と非同期リソースのキャッシュを追加します。 |
| `packages/ui/src/server/stream.ts`                                     | SSR時に非同期コンポーネントやブロッキングFrameの解決を待ってからHTMLを組み立てます。                                 |
| `packages/ui/src/runtime/frame.ts` / `packages/ui/src/runtime/vdom.ts` | `__REMIX_DATA__` からハイドレーション用データを読み込み、クライアント側のランタイムに渡します。                      |

---

## 1. 通常コンポーネントを async/await 対応にする仕組み

### セットアップフェーズとレンダーフェーズの分離

Remix3 (fork) のコンポーネントは、以下のように「初回初期化時のセットアップ」と「更新ごとのレンダー」という2つのフェーズに分かれた2層構造をしています。

```tsx
function MyComponent(handle: Handle<Props>) {
  // 1. セットアップフェーズ (インスタンス生成時に1回だけ実行)
  let count = 0;

  return () => {
    // 2. レンダーフェーズ (初回描画および更新ごとに実行)
    return <div>Count: {count}</div>;
  };
}
```

このセットアップフェーズであるコンポーネント関数自体を `async` で定義できるようにし、`Promise<RenderFn>` を返せるようにランタイムを改造します。

### `ComponentRuntime` での Promise 制御

コンポーネントの描画ライフサイクルを司る `ComponentRuntime.render` メソッド（`packages/ui/src/runtime/component.ts`）において、コンポーネント関数が `Promise` を返した際のハンドリングを追加します。

```typescript
let result = this.#config.type(this.#handle);

if (result instanceof Promise) {
  this.initPromise = result;
  result
    .then((resolvedRenderFn) => {
      if (typeof resolvedRenderFn !== "function") {
        throw new Error("Must return a render function");
      }
      if (this.#removed) return;
      // 解決されたレンダリング関数を格納
      this.#renderFn = resolvedRenderFn;
      // 再描画をスケジュール
      this.#scheduleUpdate();
    })
    .catch((error) => {
      // エラーハンドリング
    });

  // 非同期待ちの間は null を返して描画
  return [null, this.#dequeueTasks()];
}
```

セットアップ関数が Promise を返した場合、それを `initPromise` に格納します。通常のクライアント描画では解決するまで `null` を返しておき、Promise が解決した段階で `this.#scheduleUpdate()` をトリガーしてレンダーフェーズ（`RenderFn`）へと移行させます。SSRでは後述する `resolveBlocking` 側でこの Promise の解決を待ってからHTMLを組み立てます。

---

## 2. 非同期データ取得 `handle.async` の Thenable の動作

非同期コンポーネントでデータを取得する上で課題となるのが、**「SSR（サーバーサイド）ではHTML出力前にデータを待ち合わせ、CSR（クライアントサイド）では非同期に描画をブロックせず pending 状態の UI を表示させる」** という挙動の二面性をどう両立するかです。

これを解決するのが `handle.async` ヘルパーです。

`handle.async` は通常の `Promise<T>` ではなく、現在の読み込み状態を持った `AsyncResource<T>` を返します。セットアップ関数内では `await handle.async(...)` と書けますが、実際に手元に残るのは値そのものではなく、以下のような操作用オブジェクトです。

| プロパティ / メソッド | 役割                                                                             |
| --------------------- | -------------------------------------------------------------------------------- |
| `value`               | 最後に解決された値です。初回読み込み前や `clear()` 後は `undefined` になります。 |
| `pending`             | 現在読み込み中かどうかを表します。ローディングUIの出し分けに使います。           |
| `error`               | 最後の読み込みで発生したエラーです。                                             |
| `refresh()`           | 非同期処理を再実行し、解決後にキャッシュ値を更新します。                         |
| `clear()`             | キャッシュと現在値を消します。                                                   |

### Thenable オブジェクトによる待機・即時返却の切り替え

`handle.async` の戻り値である `AsyncResource` は、`then` メソッドを実装した **Thenable**（Promiseライク）オブジェクトになっています。

```typescript
let resource = {
  ...view,
  then(onfulfilled, onrejected) {
    let ready =
      behavior.await === "immediate" || entry.status === "resolved"
        ? Promise.resolve(view)
        : entry.status === "rejected"
          ? Promise.reject(entry.error)
          : refresh().then(() => view);

    return ready.then(onfulfilled, onrejected);
  },
};
```

この `then` メソッドの挙動は、実行環境（サーバーかクライアントか）によって変化します。

- **サーバーサイド (SSR)**:
  `behavior.await` が `'block'` になります。これにより、セットアップ関数内で `let data = await handle.async(...)` と await すると、アクションの実行（`refresh()`）が完了するまで待機します。その結果、サーバーでデータ取得を完了した状態でHTMLを出力できます。
- **クライアントサイド (CSR/Live)**:
  `behavior.await` が `'immediate'` になります。これにより、セットアップ関数内で `await handle.async(...)` しても、**即座に解決される Promise が返るため await が即座に通り抜け**、未解決状態の `resource` が返されます。コンポーネントはブロックされることなく即座にレンダー関数を返し、`resource.pending` に応じたローディング画面（Skeletonなど）を描画できます。

クライアントサイドで未解決のリソースが作られた場合は、`handle.async` の内部で `resource.refresh()` が自動的に開始されます。つまりコンポーネント側では `await handle.async(...)` と書くだけで、初回描画では `pending` を見てローディングUIを出し、取得完了後にランタイム側の更新によって `value` を使った表示へ切り替えられます。

---

## 3. シリアライズとハイドレーション

サーバーサイドで `handle.async` によってHTML出力前に解決されたデータは、そのままHTMLドキュメントの末尾に JSON データとしてシリアライズされ、クライアントに転送されます。

```html
<script type="application/json" id="__REMIX_DATA__">
  {"async:hn:item:123": {"story": {...}, "comments": [...]}}
</script>
```

クライアントサイドでのハイドレーション時、ランタイムはこの埋め込まれた JSON からサーバーで解決済みのデータを抽出し、`handle.async` で同じキーが指定された際にキャッシュからデータを即時返却します。
これにより、ハイドレーション中にクライアントが同一の API に対して余計な重複リクエストを送ることを防いでいます。

キャッシュの扱いは `cache` オプションで切り替えます。

| `cache`     | 挙動                                                                                                                                 |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `'page'`    | ページ内のランタイムキャッシュに保持します。同じキーの `handle.async` は解決済みデータを再利用できます。デフォルトはこのモードです。 |
| `'hydrate'` | サーバーからクライアントへのハイドレーションには使いますが、ページ内キャッシュとしては保持しません。                                 |
| `'none'`    | ハイドレーションデータにもページキャッシュにも保持しません。常に再取得したい処理向けです。                                           |

---

## 4. サーバーサイド・ストリーミングにおける `resolveBlocking`

サーバーサイドで HTML をストリーミング送出する際（`renderToStream`）、非同期コンポーネントの初期化や、フォールバックを持たないFrameの解決を完了させてから最初のチャンクを送出する必要があります。

`packages/ui/src/server/stream.ts` では、ツリー内のブロッキング要素の Promise がすべて解決するのを待ち合わせる `resolveBlocking` 関数が定義されています。

```typescript
async function resolveBlocking(segment: Segment): Promise<void> {
  if (segment.kind === "frame") {
    if (segment.pending) {
      await segment.pending;
      segment.pending = undefined;
    }
    if (segment.content) await resolveBlocking(segment.content);
    return;
  }
  if (segment.kind === "async-component") {
    await segment.pending;
    if (segment.content) await resolveBlocking(segment.content);
    return;
  }
  if (segment.kind === "composite") {
    for (let part of segment.parts) {
      await resolveBlocking(part);
    }
  }
}
```

この処理により、ストリーミング SSR であっても、初期HTMLに含めるべき非同期コンポーネントやFrameの内容が解決した状態でHTMLやシリアライズデータが組み立てられ、出力されます。

---

## 5. 実践的なコード例

以下は、非同期コンポーネントを用いて Hacker News の記事詳細とコメントを取得・描画するコンポーネントの具体的な実装例です。

この例で見るポイントは以下の3つです。

1. セットアップフェーズで `await handle.async(...)` を呼び、SSRではHTML出力前にデータを解決する
2. CSRでは `detail.pending` と `detail.value` を見てローディング表示と取得済み表示を切り替える
3. 更新ボタンでは `detail.refresh()` と `handle.update()` を組み合わせ、読み込み中と取得後の2回表示を更新する

```tsx
import { type Handle, on } from "@remix-run/ui";
import { useParams } from "../provider/RouterProvider";

interface Story {
  id: number;
  title: string;
  by: string;
  score: number;
  time: number;
  kids?: number[];
}

interface HNComment {
  id: number;
  by: string;
  text: string;
  type: "comment";
  deleted?: boolean;
  dead?: boolean;
}

interface ItemDetail {
  story: Story;
  comments: HNComment[];
}

export default async function ItemDetailRoute(handle: Handle) {
  const { id } = useParams(handle);

  // 1. handle.async を使って非同期データをロードする
  const detail = await handle.async<ItemDetail>(
    async () => {
      const storyRes = await fetch(
        `https://hacker-news.firebaseio.com/v0/item/${id}.json`,
      );
      if (!storyRes.ok) throw new Error("Failed to fetch story details");
      const story = (await storyRes.json()) as Story;

      const kids = story.kids || [];
      const commentPromises = kids.slice(0, 15).map(async (kidId) => {
        const commentRes = await fetch(
          `https://hacker-news.firebaseio.com/v0/item/${kidId}.json`,
        );
        if (!commentRes.ok) return null;
        return commentRes.json() as Promise<HNComment>;
      });

      const commentsRaw = await Promise.all(commentPromises);
      const comments = commentsRaw.filter(
        (c): c is HNComment =>
          c !== null && c.type === "comment" && !c.deleted && !c.dead,
      );
      return { story, comments };
    },
    {
      key: `hn:item:${id}`,
      cache: "page", // ページ遷移時もキャッシュを維持する
    },
  );

  // 2. レンダー関数を返す (この関数が更新時に繰り返し呼ばれる)
  return () => {
    const value = detail.value;

    return (
      <main>
        {detail.pending && !value ? (
          <p>データを読み込み中...</p>
        ) : (
          value && (
            <article>
              <h1>{value.story.title}</h1>
              <p>
                by {value.story.by} / {value.story.score} points
              </p>

              <button
                type="button"
                disabled={detail.pending}
                mix={on("click", async () => {
                  const refresh = detail.refresh();
                  await handle.update(); // ローディング状態（pending: true）へ更新
                  await refresh;
                  await handle.update(); // 取得後のデータで描画を更新
                })}
              >
                {detail.pending ? "更新中..." : "データを更新する"}
              </button>

              <h2>コメント</h2>
              <div>
                {value.comments.map((comment) => (
                  <div key={comment.id}>
                    <p>{comment.by}</p>
                    <div innerHTML={comment.text} />
                  </div>
                ))}
              </div>
            </article>
          )
        )}
      </main>
    );
  };
}
```

HN APIのコメント本文はHTML文字列として返ってくるため、このデモでは `innerHTML` で表示しています。外部入力をそのままHTMLとして描画する形になるので、本番用途ではサニタイズや許可タグの制限を検討してください。

# SSRが簡単になる

非同期コンポーネントによって、コンポーネント単位で非同期データを取得してレンダリングできます。しかもサーバー専用コードではなく、クライアントでも動作するコードとして作ることができます。SSR時はサーバーで、その後のCSRではブラウザからデータを取得するという部分のコードが共通化できます。しかもRSCのような境界を考慮した実装がいらないので、データ取得とレンダリングをコンポーネント上に書くだけで好きなように動かすことができます。

ただ、コンポーネント単位で非同期処理を行うと、非同期データを必要とするコンポーネントがネストしたときに、SSRの処理が完遂されるまで時間がかかるという問題が発生します。簡単にはなりますが、そのあたりの考慮を忘れると全体のパフォーマンスが落ちます。

また、この方式は万能ではありません。ブラウザから直接アクセスできないDBや内部APIを使う場合は、別途サーバー側のAPIやBFFを用意する必要があります。さらに、非同期処理のエラーをどこで表示するか、ページ遷移やコンポーネント削除時に進行中の処理をどう扱うか、といった設計も必要になります。今回の実装は「通常コンポーネントに非同期データ取得を自然に書けるようにする」ことを目的にした実験であり、プロダクション向けにはエラー境界やキャンセル、キャッシュ破棄のルールをもう少し詰める必要があります。

# DPUとの親和性

Chromeで実験的な実装が行われているDPU(Declarative Partial Updates)を使えば、非同期コンポーネントのネストの問題をブラウザ側のHTML更新プリミティブで扱える可能性があります。RSCのようなストリーミングUI更新に近い用途を、フレームワーク専用のプロトコルだけでなくHTMLの部分更新として扱えるかもしれません。いずれこのあたりを活用した強力なフレームワークが登場することでしょう。

# 非同期コンポーネントの将来性

非同期コンポーネントの実装ができそうなのでやってみました。結果として、想定通り動作するものになりました。そして無茶苦茶便利です。ただ個人的には、本家のRemix3に入る類の機能ではないと思っています。どこか資金力と人材のある組織が、こんな感じのライブラリやフレームワークを作ってくれると良いなと思うばかりです。
