---
title: "情報処理技術者試験1.2万問をpgvector × Workers AIで類似検索化する（設計からUI、コスト実績まで）"
emoji: "🔍"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: ["cloudflare", "postgresql", "pgvector", "drizzle", "hono"]
published: true
---

情報処理技術者試験（基本情報技術者試験や応用情報技術者試験など）の過去問を解いていると、「この問題、数年前の過去問とほぼ同じだな」「この用語に関連する類題をまとめて演習したいな」と感じることが多々あります。

現在開発・運用している過去問対策Webサービス （問題数 約12,800問）

https://it.lerning.croud.jp/

において、Cloudflare Workers + Workers AI + PostgreSQL (pgvector) + Drizzle ORM を組み合わせ、類似問題の検索・レコメンド機能を実装しました。

本記事では、ゼロから類似検索を設計・本番投入するにあたり考慮したアーキテクチャ選定、埋め込み前処理の工夫、資格試験データ特有の「焼き直し問題」の壁とその解決策、そして1.2万問の全件ベクトル化でかかったコスト実績についてまとめます。

---

## 1. システム構成と技術スタック

本アプリの基本スタックは以下の通りです。エッジで完結するモダンな構成を採用しています。

- バックエンド / API: Cloudflare Workers + Hono
- フロントエンド: React + TanStack Router / Query + Tailwind CSS
- データベース: PostgreSQL (Supabase) + Drizzle ORM (Hyperdrive経由)
- AI / 埋め込みモデル: Cloudflare Workers AI (`@cf/baai/bge-m3`)
- 問題データ規模: Markdownベースの過去問 12,884件

```
[クライアント (React / TanStack)]
          │
          │ GET /api/questions/:id/similar
          ▼
[Cloudflare Workers (Hono)]
   ├── Workers AI: @cf/baai/bge-m3 (クエリのベクトル化)
   └── Hyperdrive ──► [PostgreSQL (Supabase + pgvector)]
                         ├── questions (問題メタデータ)
                         └── question_embeddings (1024次元ベクトル)
```

---

## 2. アーキテクチャ選定とデータモデル設計

### なぜ Cloudflare Vectorize ではなく PostgreSQL (pgvector) なのか？

Cloudflare環境でベクトル検索を組む場合、選択肢としてCloudflare Vectorizeと既存PostgreSQLへのpgvector拡張があります。今回はpgvectorを採用しました。

主な理由は以下の通りです。

1. メタデータ結合とアクセス権（認可）の一元管理:
   問題データには「公開/非公開フラグ（`isPublic`）」「下書き」「作成者権限」「所属試験」など厳密な可視性フィルタが必要です。独立したVector DBでは「ベクトル検索でTop-K取得 → RDBで可視性チェックして除外 → 結果が足りなくなる（不足問題）」が起こりがちですが、pgvectorであればSQLの`WHERE`句で1クエリかつトランザクション安全に解決できます。
2. トランザクション整合性:
   問題の削除（CASCADE削除）や更新時の整合性をRDB側の外部キー制約で自然に担保できます。

### 埋め込みモデルの選定: `@cf/baai/bge-m3`

モデルにはWorkers AIで利用可能な `@cf/baai/bge-m3`（1024次元）を採用しました。
日本語の技術用語や略語（RAID, CIDR, SQL, MTBFなど）に対する表現力が高く、多言語・密ベクトル検索において安定した精度を発揮します。

### スキーマ設計（Drizzle ORM）

`questions` テーブル本体にベクトル列を追加するのではなく、別テーブル `question_embeddings` として切り出しました。

```typescript
// app/db/schema.ts
import { pgTable, uuid, text, timestamp, vector } from 'drizzle-orm/pg-core';
import { questions } from './questions';

export const questionEmbeddings = pgTable('question_embeddings', {
  questionId: uuid('question_id')
    .primaryKey()
    .references(() => questions.id, { onDelete: 'cascade' }),
  model: text('model').notNull(), // 例: '@cf/baai/bge-m3'
  embedTextHash: text('embed_text_hash').notNull(), // SHA-256ハッシュ
  embedding: vector('embedding', { dimensions: 1024 }).notNull(),
  createdAt: timestamp('created_at', { withTimezone: true }).defaultNow().notNull(),
  updated_at: timestamp('updated_at', { withTimezone: true }).defaultNow().notNull(),
});
```

設計上のポイントは以下の2点です。

- `model` 列の保持: 将来モデルを刷新・移行する際、旧モデルと新モデルを共存させて無停止切り替えができるようにします。
- `embedTextHash` 列: 後述する差分更新・完全一致検知のためのSHA-256ハッシュです。

### インデックス戦略: 1万件規模ならHNSWインデックスを「あえて作らない」

pgvectorといえばHNSWインデックスやIVFFlatインデックスが定番ですが、初期フェーズではインデックスをあえて作成していません。

- 1万件程度（1024次元）であれば、PostgreSQLのシーケンシャルスキャンでも数ミリ秒〜十数ミリ秒で走査可能です。
- HNSWインデックスはメモリ（RAM）消費が大きく、ビルドやVACUUMのオーバーヘッドがあります。
- 初期のSupabaseのサーバースペックやメモリ圧迫リスクを抑え、まずは不要な最適化を避ける（YAGNI原則）判断をしました。

---

## 3. 埋め込みテキストの整形と差分更新パイプライン

### テキスト整形（`buildEmbedText`）の工夫

埋め込みモデルにどのようなテキストを渡すかは、類似検索の精度を左右する最重要ポイントです。

```typescript
// tools/lib/buildEmbedText.ts（概要）
export function buildEmbedText(body: string, choices: { text: string; originalIndex?: number }[]): string {
  // 1. MarkdownやLaTeX記法を除去・正規化
  const cleanBody = normalizeMarkdown(body);
  
  // 2. 選択肢をoriginalIndex順（元々の出題順）でソートし、ラベル（ア・イ・ウ・エ）や正誤フラグは除外
  const sortedChoices = [...choices].sort((a, b) => (a.originalIndex ?? 0) - (b.originalIndex ?? 0));
  const cleanChoices = sortedChoices.map(c => normalizeMarkdown(c.text));
  
  // 3. 問題文 + 選択肢テキストを連結（上限2000文字で安全にクリップ）
  return [cleanBody, ...cleanChoices].join('\n').slice(0, 2000);
}
```

#### なぜ「解説文」を含めないのか？
当初は「解説（explanation）も含めた方が情報量が増えて精度が上がるのでは？」と考えがちですが、解説は意図的に除外しています。

資格試験の解説には「〜とは関係がない」「誤答である理由」「関連する他のIT用語の補足」などノイズとなる情報が大量に含まれます。これらを含めると、問題自体のテーマではなく解説文にたまたま登場した共通用語にベクトルの類似度が引っ張られてしまうため、問題文と選択肢のみに絞るのが最も検索精度が高くなりました。

また、選択肢のラベル（「ア」「イ」）や正誤情報を含めず純粋なテキストのみを元の出題順でソートして結合することで、選択肢のシャッフル等によるテキスト揺れを防いでいます。

### トランザクション分離（2相同期設計）

問題の更新時（`PATCH /api/questions/:id`）やMarkdownの一括インポート時、DBトランザクションの中で外部AI API（Workers AI）を直接呼び出してはいけません。

外部APIのレイテンシや一時的な障害でDBトランザクションが長時間ロックされ、コネクション枯渇を引き起こすためです。

```
[悪い例: 1トランザクション]
BEGIN → DB更新 → Workers AI呼び出し (数秒ブロック・障害リスク) → COMMIT

[良い例: 2相同期設計]
Phase 1: BEGIN → DB更新 → COMMIT (即座に確定)
Phase 2: commit後に非同期で差分判定 → Workers AI呼び出し → 埋め込みテーブルをUpsert
          (万が一AIが失敗しても、更新ログ出力のみで本体処理は成功させる)
```

この2相同期アプローチにより、AIサービスのダウンタイム時でもコアのデータ更新機能が巻き込まれて落ちるのを防ぎます。

---

## 4. 全件バックフィルと驚異のコスト実績

### バックフィルスクリプトの実装

既存の過去問12,884件をすべてベクトル化するため、並列実行と指数バックオフを備えたスクリプトを用意しました。

```typescript
// tools/backfill-embeddings.ts（処理フロー）
// 1. question_embeddings にレコードが存在しない問題、
//    または embedTextHash が不一致（テキスト更新あり）の問題を抽出
// 2. 3並列でWorkers AIを呼び出し、question_embeddings にUPSERT
// 3. レートリミット（429）時は指数バックオフで自動リトライ
```

### 1.2万件投入のコスト実績: まさかの「完全無料」

ここで驚くべき結果が出ました。

全12,884件の問題文・選択肢を一括でWorkers AI（`@cf/baai/bge-m3`）に投げてベクトル化した際、消費されたWorkers AIリソースは約4,000ニューロン程度でした。

Cloudflare Workers AIの無料枠は1日あたり10,000ニューロンです。
つまり、1.2万件という巨大なデータセットの全件埋め込みが、1日の無料枠の半分未満で、追加費用0円（完全無料）で完了しました。

個人開発やスタートアップにとって、外部Embedding API（OpenAI等）を大量に叩く際のコスト懸念を完全に払拭できる素晴らしいコストパフォーマンスです。

---

## 5. 類似検索APIの実装とセキュリティ・開発環境の考慮

### コサイン距離による検索クエリ

Drizzle ORMの `cosineDistance` 関数を利用して、コサイン距離の昇順でクエリします。

```typescript
// app/api/similar.ts（抜粋）
import { cosineDistance } from 'drizzle-orm/sql/functions/vector';
import { and, eq, ne, sql } from 'drizzle-orm';

// 1. クエリテキストの埋め込み取得 (5秒タイムアウト)
const queryVector = await embedQuery(env, baseQuestionText);

// 2. ベクトル類似検索
const candidates = await db
  .select({
    id: questions.id,
    questionNumber: questions.questionNumber,
    body: questions.body,
    embedTextHash: questionEmbeddings.embedTextHash,
    distance: cosineDistance(questionEmbeddings.embedding, queryVector),
    exam: {
      name: exams.name,
      type: exams.type,
      year: exams.year,
      term: exams.term,
    },
  })
  .from(questionEmbeddings)
  .innerJoin(questions, eq(questionEmbeddings.questionId, questions.id))
  .leftJoin(exams, eq(questions.examId, exams.id))
  .where(
    and(
      eq(questionEmbeddings.model, '@cf/baai/bge-m3'),
      ne(questions.id, baseQuestion.id), // 自分自身を除外
      visibilityCondition(user)           // 認可・公開フラグチェック (IDOR防止)
    )
  )
  .orderBy(asc(sql`distance`))
  .limit(25); // 後述する「焼き直し分離」のため多めに取得
```

### 認可（IDOR）とフォールバック設計

- セキュリティ（IDOR対策）:
  検索元の問題と検索候補の問題の双方に対して、同一の可視性条件（`isPublic = true` または 自身が作成者）を適用します。非公開の問題がベクトル検索の類似度上位として漏洩するのを確実に防ぎます。
- フォールバック機構:
  Workers AIの呼び出しがタイムアウト（5秒）した場合やオフライン環境では、エラー画面を表示するのではなく、同一カテゴリの新着問題をフォールバックとして返却します。

### ローカル開発（Vite）でのハマりどころ: `RemoteSessionAuthenticationError`

Cloudflare Viteプラグイン（`@cloudflare/vite-plugin`）を使ってローカル開発を行う際、`cloudflare.config.ts` に `AI: bindings.ai()` を追加すると、`pnpm dev` 起動時に以下のような認証エラーが発生しました。

```
RemoteSessionAuthenticationError: This Worker uses bindings that need to run remotely, even when developing locally, but the remote session could not be authenticated.
CLOUDFLARE_API_TOKEN may be invalid or lack permissions...
```

Workers AIはローカルシミュレータが存在しないため、Vite起動時に自動的にCloudflareのリモート開発セッションを開始しようとします。しかし、ローカル環境でAPIトークンの権限が不足していたり環境変数が分かれていたりすると開発サーバー自体が起動しなくなってしまいます。

対策として、`vite.config.ts` で `remoteBindings` を通常時は無効化（`false`）し、明示的な環境フラグがある場合のみリモート接続するように設定しました。

```typescript
// vite.config.ts
export default defineConfig({
  plugins: [
    cloudflare({
      // ローカル開発時はリモートセッションを張らない
      // AIバインディングは未接続となり、API側のフォールバック（カテゴリ新着）が動くため安全
      remoteBindings: process.env.IT_LERNING_REMOTE_AI === 'true',
    }),
  ],
});
```

これにより、開発者は特別なCloudflareトークンを持っていなくても `pnpm dev` で即座にアプリを動かすことができます。

---

## 6. 過去問ドメイン特有の壁 — 「同一・焼き直し問題」の分離

1.2万件のバックフィルが完了し、テスト検索を行った際に実務上の大きな課題に直面しました。

### 類似上位が「全く同じ問題」で埋まってしまう現象

情報処理技術者試験では、過去の午前問題が数年後にそのまま再出題（いわゆる焼き直し問題）されることが頻繁にあります。

たとえば「平成21年秋期 問56（パイロット移行方式）」の類似問題を検索すると、Top 5のうち4問が「令和元年 問55」「平成26年春 問55」といった一言一句違わない同一の出題で埋め尽くされてしまいました。

```
[従来の検索結果]
基準: H21秋 問56 (パイロット移行方式)
- 1位: R01秋 問55 (パイロット移行方式) 類似度 0.999  ← まったく同じ問題
- 2位: H26春 問55 (パイロット移行方式) 類似度 0.998  ← まったく同じ問題
- 3位: H23秋 問54 (パイロット移行方式) 類似度 0.995  ← まったく同じ問題
- 4位: H19秋 問55 (パイロット移行方式) 類似度 0.994  ← まったく同じ問題
- 5位: H28春 問57 (一斉移行方式)       類似度 0.820  ← 本来見たかった類題！
```

ベクトル検索の精度としては完璧（距離0付近に同一文章が来ている）なのですが、学習者のUXとしては「同じ問題ばかり並んでいて、他の類題（段階移行や一斉移行など）が見られない」という好ましくない状態になります。

### 解決策: しきい値 `0.04` によるサーバサイド2分割

この問題を解決するため、API側で候補を多め（25件）に取得し、「同一問題グループ（再出題）」と「類似問題」に分割して返却する構造に改修しました。

```typescript
// app/api/similar.ts（2分割ロジック）
const SAME_GROUP_DISTANCE = 0.04; // コサイン距離 0.04（類似度 0.96相当）

const sameGroup: typeof candidates = [];
const similar: typeof candidates = [];

for (const item of candidates) {
  // ハッシュ完全一致、またはコサイン距離が0.04未満（極めて高い類似度）の場合
  const isSame = item.embedTextHash === baseHash || item.distance < SAME_GROUP_DISTANCE;

  if (isSame) {
    sameGroup.push(item);
  } else {
    similar.push(item);
  }
}

return c.json({
  fallback: false,
  groupKey: baseHash,
  sameGroup,                 // 過去の再出題・同一問題リスト
  similar: similar.slice(0, 5), // 本当の「類題」Top 5
});
```

1024次元の `bge-m3` モデルにおいて、一般的な類題（関連する技術用語や別の移行方式）の類似度は `0.70〜0.85`（距離 `0.15〜0.30`）付近に分布します。
一方、同一問題や選択肢の微小な表記揺れは類似度 `0.96以上`（距離 `0.04未満`）に集中するため、`0.04` を境界値とすることで極めて高い精度で分離できました。

### UIでの出し分け

フロントエンド側（Reactコンポーネント `RelatedQuestions.tsx`）では、この2分割データを直感的に表示できるようにしました。

```
┌────────────────────────────────────────────────────────┐
│ 🔄 過去の同一出題 (再出題) : 3件                       │
│  ・応用情報技術者 令和元年秋期 問55 [表示]             │
│  ・他2件の出題を展開 ▼                                │
└────────────────────────────────────────────────────────┘
┌────────────────────────────────────────────────────────┐
│ 💡 類似した問題 (類題演習)                              │
│  1. 応用情報技術者 平成28年春期 問57 (類似度: 82%)    │
│     「システムの移行方式のうち、一斉移行方式の特徴は…」│
│  2. 基本情報技術者 令和3年免除 問15 (類似度: 79%)     │
│     ...                                                │
└────────────────────────────────────────────────────────┘
```

- 同一問題: 「過去にも同じ問題が出ている」という事実がひと目でわかり、アコーディオンで過去の出題回を確認できる。
- 類似問題: 同一問題に埋もれることなく、周辺知識の補強につながる類題をスムーズに連続演習できる。

学習アプリとしての実用性が格段に向上しました。

---

## 7. まとめ

今回の取り組みを通じて得られた知見は以下の通りです。

1. pgvectorのシンプルさと堅牢さ:
   Cloudflare Workers環境であっても、認可やメタデータ結合を重視するならRDB直結のpgvectorは極めて扱いやすい。
2. Workers AIの圧倒的なコスパ:
   1.2万問の全件ベクトル化が約4,000ニューロン（デイリー無料枠10,000の範囲内）で収まり、運用コスト0円で高精度な埋め込み環境が手に入る。
3. ドメイン固有の課題とデータ分割:
   ベクトル検索を実プロダクトに組み込むと「近すぎるデータ（完全一致・再出題）」がノイズになる場合がある。コサイン距離のしきい値（今回は `0.04`）を用いたグルーピングを行うことで、UXを劇的に改善できる。

今回実装した類似問題検索・同一問題グルーピング機能は、以下のWebサービスで実際に稼働しています。基本情報・応用情報などの資格取得を目指している方は、ぜひ触ってみてください！

- 🌐 情報処理技術者試験 過去問対策システム: [https://it.lerning.croud.jp/](https://it.lerning.croud.jp/)

Cloudflare WorkersとPostgreSQLでベクトル検索やRAGの導入を検討している方の参考になれば幸いです！
