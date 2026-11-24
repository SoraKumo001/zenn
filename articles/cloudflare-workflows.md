---
title: "Cloudflare Workflows を使って、時間のかかる処理をすっきりと記述する"
emoji: "🗂"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: ["cloudflare", "cloudflareworkers", "workflows", "typescript", "ai"]
published: true
---

# はじめに

AI を使ったアプリケーションを作っていると、「1 回の HTTP リクエストに収まらない時間のかかる処理」をどう組むかが課題になりがちです。

現在開発を進めている小説執筆支援アプリ「ノベクリ（Novel Creator）」では、アイデア 1 行から小説を自動生成する自律執筆（オートパイロット）機能の実装を追加しました。

https://novel-creator.croud.jp/

この処理では、内部で次のような多段パイプラインが順番に、かつ章・節の数だけループしながら動きます。

1. 構想・登場人物・世界観のブートストラップと詳細構想の推敲
2. 全体の章構成（プロット）と伏線の生成
3. ユーザーによるプロット確認・修正指示（承認待ち）
4. 章ごとの節（シーン）の分割設計
5. 各節の本文執筆（LLM ストリーミング生成）
6. 執筆後のダイジェスト生成・事実／記憶抽出・ベクトルインデックス反映・整合確認

1 作品あたり合計で数分〜十数分かかる処理になるため、通常の HTTP API や SSE 接続のまま回すと、実行時間制限・ブラウザのタブ閉じや通信断・途中失敗時のやり直しがネックになります。

かといって Cloudflare Queues だけで組もうとすると、ステップごとの状態遷移テーブル、重複実行の制御、承認待ちからの再開スケジューリング、リトライ管理を自前で作り込むことになり、業務ロジックより制御コードのほうが膨らみやすくなります。

| 方式 | 長時間・多段実行 | 自動リトライ | 承認待ち（Human-in-the-loop） | 実装の見通し |
| :--- | :--- | :--- | :--- | :--- |
| **HTTP / SSE 同期実行** | 接続断・実行上限に弱い | クライアント側でやり直しが必要 | 接続を維持できず別 API で再開が必要 | 単発処理向き |
| **Queues + 自前状態管理** | メッセージ連鎖で可能 | キュー単位の再配信あり | 一時停止〜再開の状態機械を自前実装 | 制御コードが肥大化しやすい |
| **Cloudflare Workflows** | `step.do` の連鎖で長時間実行に対応 | ステップ単位で設定可能 | `step.waitForEvent` で待機コスト 0 の休止 | `for` / `await` の流れで素直に書ける |

本記事では、ノベクリに Cloudflare Workflows を導入した実例をもとに、**「実行の耐久性を Workflows に任せ、業務状態の正を DB に寄せる」** 設計パターンと、実際に書いてみて分かったハマりどころを整理します。

---

# 全体アーキテクチャ：Workflows と DB の責務分離

Cloudflare Workflows でコードがすっきり書けるかどうかは、「Workflow インスタンスに何を持たせ、DB に何を持たせるか」の切り分けで決まります。

ノベクリでは以下のルールを徹底しました。

- Workflow に渡すペイロードは `{ jobId }` だけにする
- 進捗・設定・トークン予算・ステップログ・一時停止理由の正（Source of Truth）は PostgreSQL に置く
- Workflows は「次の 1 ステップを耐久性付きで進めるオーケストレーター」に徹する

全体の処理フローは次のようになります。

```html-embed
<div class="wf-flow" role="region" aria-label="AutopilotWorkflow の全体処理フロー">
  <div class="wf-col">
    <div class="wf-phase-label">1. 初期化・プロット生成</div>

    <div class="wf-node wf-node-start">
      <div class="wf-node-head">開始 API</div>
      <div class="wf-node-desc">DB にジョブ作成 &amp; <code>workflow.create({ id, params: { jobId } })</code></div>
    </div>
    <div class="wf-arrow" aria-hidden="true">↓</div>

    <div class="wf-node">
      <div class="wf-node-head"><code>bootstrap_concept</code></div>
      <div class="wf-node-desc">構想・人物・世界観の生成と詳細化</div>
    </div>
    <div class="wf-arrow" aria-hidden="true">↓</div>

    <div class="wf-node">
      <div class="wf-node-head"><code>plan_plot</code></div>
      <div class="wf-node-desc">章構成と伏線を生成</div>
    </div>
    <div class="wf-arrow" aria-hidden="true">↓</div>

    <div class="wf-decision">
      <div class="wf-decision-title">自動実行モード?</div>
      <div class="wf-branches">
        <div class="wf-branch wf-branch-wait">
          <span class="wf-badge wf-badge-amber">plot_approval</span>
          <div class="wf-node wf-node-wait">
            <div class="wf-node-desc"><code>step.waitForEvent('plot-approval')</code> で休止</div>
          </div>
          <span class="wf-branch-note"><span class="wf-dir-pc">→ 2. へ</span><span class="wf-dir-sp">↓</span> 承認 / 修正指示あり</span>
        </div>
        <div class="wf-branch wf-branch-auto">
          <span class="wf-badge wf-badge-blue">full_auto</span>
          <div class="wf-branch-direct">承認待ちをスキップして 2. へ <span class="wf-dir-pc">→</span><span class="wf-dir-sp">↓</span></div>
        </div>
      </div>
    </div>
  </div>

  <div class="wf-col">
    <div class="wf-phase-label">2. 章・節ループと完了</div>

    <div class="wf-loop wf-loop-chapter">
      <div class="wf-loop-tag">章ループ（未設計の章あり? → Yes で反復）</div>

      <div class="wf-node">
        <div class="wf-node-head"><code>plan_chapter_sections</code></div>
        <div class="wf-node-desc">章ごとの節設計</div>
      </div>
      <div class="wf-arrow" aria-hidden="true">↓</div>

      <div class="wf-loop wf-loop-section">
        <div class="wf-loop-tag">節ループ（未執筆の節あり? → Yes で反復）</div>
        <div class="wf-node">
          <div class="wf-node-head"><code>write_section</code></div>
          <div class="wf-node-desc">節の本文執筆</div>
        </div>
        <div class="wf-arrow" aria-hidden="true">↓</div>
        <div class="wf-node">
          <div class="wf-node-head"><code>post_process_section</code></div>
          <div class="wf-node-desc">要約・記憶・事実・埋め込み更新</div>
        </div>
      </div>

      <div class="wf-arrow-label">↓ 未執筆の節あり: No</div>

      <div class="wf-node">
        <div class="wf-node-head"><code>finalize_chapter</code></div>
        <div class="wf-node-desc">章まとめ・整合確認</div>
      </div>
    </div>

    <div class="wf-arrow-label">↓ 未設計の章あり: No</div>

    <div class="wf-node wf-node-end">
      <div class="wf-node-head"><code>complete</code></div>
      <div class="wf-node-desc">完了</div>
    </div>
  </div>
</div>

<style>
  .wf-flow {
    --wf-bg: #f8fafc;
    --wf-surface: #ffffff;
    --wf-border: #cbd5e1;
    --wf-text: #0f172a;
    --wf-muted: #475569;
    --wf-accent: #0284c7;
    --wf-accent-bg: #e0f2fe;
    --wf-amber: #b45309;
    --wf-amber-bg: #fef3c7;
    --wf-amber-border: #f59e0b;
    --wf-green: #15803d;
    --wf-green-bg: #dcfce7;
    --wf-green-border: #22c55e;
    --wf-loop-bg: #f1f5f9;
    box-sizing: border-box;
    display: grid;
    grid-template-columns: 1fr 1.12fr;
    gap: 14px;
    padding: 14px;
    background: var(--wf-bg);
    color: var(--wf-text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-size: 12px;
    line-height: 1.45;
  }

  [data-theme="dark"] .wf-flow {
    --wf-bg: #0f172a;
    --wf-surface: #1e293b;
    --wf-border: #334155;
    --wf-text: #f1f5f9;
    --wf-muted: #cbd5e1;
    --wf-accent: #38bdf8;
    --wf-accent-bg: #0c4a6e;
    --wf-amber: #fcd34d;
    --wf-amber-bg: #451a03;
    --wf-amber-border: #d97706;
    --wf-green: #86efac;
    --wf-green-bg: #052e16;
    --wf-green-border: #16a34a;
    --wf-loop-bg: #162032;
  }

  .wf-flow *,
  .wf-flow *::before,
  .wf-flow *::after {
    box-sizing: border-box;
  }

  .wf-col {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .wf-phase-label {
    font-size: 12px;
    font-weight: 700;
    color: var(--wf-accent);
    margin-bottom: 8px;
    letter-spacing: 0.02em;
  }

  .wf-node {
    background: var(--wf-surface);
    border: 1.5px solid var(--wf-border);
    border-radius: 8px;
    padding: 7px 10px;
    min-width: 0;
    overflow-wrap: anywhere;
  }

  .wf-node-start {
    border-color: var(--wf-accent);
    background: var(--wf-accent-bg);
  }

  .wf-node-wait {
    border-color: var(--wf-amber-border);
    background: var(--wf-amber-bg);
    width: 100%;
  }

  .wf-node-end {
    border-color: var(--wf-green-border);
    background: var(--wf-green-bg);
    text-align: center;
  }

  .wf-node-head {
    font-weight: 700;
    font-size: 12px;
    color: var(--wf-text);
  }

  .wf-node-desc {
    font-size: 12px;
    color: var(--wf-muted);
    margin-top: 2px;
  }

  .wf-node-start .wf-node-desc,
  .wf-node-end .wf-node-head {
    color: var(--wf-text);
  }

  .wf-flow code {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 12px;
    padding: 0 3px;
    border-radius: 4px;
    background: rgba(148, 163, 184, 0.18);
  }

  .wf-arrow {
    text-align: center;
    color: var(--wf-accent);
    font-weight: 700;
    font-size: 13px;
    line-height: 1.25;
    padding: 2px 0;
  }

  .wf-arrow-label {
    text-align: center;
    color: var(--wf-muted);
    font-weight: 600;
    font-size: 12px;
    padding: 3px 0;
  }

  .wf-decision {
    border: 1.5px dashed var(--wf-accent);
    border-radius: 8px;
    padding: 8px;
    background: var(--wf-surface);
  }

  .wf-decision-title {
    font-weight: 700;
    text-align: center;
    margin-bottom: 6px;
    color: var(--wf-text);
  }

  .wf-branches {
    display: grid;
    grid-template-columns: 1.2fr 1fr;
    gap: 8px;
  }

  .wf-branch {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
    min-width: 0;
  }

  .wf-badge {
    display: inline-block;
    font-size: 12px;
    font-weight: 700;
    padding: 1px 7px;
    border-radius: 999px;
  }

  .wf-badge-amber {
    background: var(--wf-amber-bg);
    color: var(--wf-amber);
    border: 1px solid var(--wf-amber-border);
  }

  .wf-badge-blue {
    background: var(--wf-accent-bg);
    color: var(--wf-accent);
    border: 1px solid var(--wf-accent);
  }

  .wf-branch-note,
  .wf-branch-direct {
    font-size: 12px;
    color: var(--wf-muted);
    text-align: center;
  }

  .wf-branch-direct {
    margin-top: 6px;
  }

  .wf-dir-sp {
    display: none;
  }

  .wf-loop {
    border: 1.5px solid var(--wf-accent);
    border-radius: 10px;
    padding: 8px 10px;
    background: var(--wf-loop-bg);
  }

  .wf-loop-section {
    border-style: dashed;
    background: var(--wf-bg);
    margin-top: 2px;
  }

  .wf-loop-tag {
    font-size: 12px;
    font-weight: 700;
    color: var(--wf-accent);
    margin-bottom: 6px;
  }

  @media (max-width: 640px) {
    .wf-flow {
      grid-template-columns: 1fr;
      padding: 10px;
      gap: 12px;
    }

    .wf-branches {
      grid-template-columns: 1fr;
    }

    .wf-dir-pc {
      display: none;
    }

    .wf-dir-sp {
      display: inline;
    }
  }
</style>
```

業務データを Workflows のイベントペイロードやステップ戻り値に抱え込まないようにしたことで、以下のメリットが得られました。

1. UI からの状態参照（進捗バー・ステップログ・直近生成した節のプレビュー）は DB を読むだけで完結する
2. 承認待ちのあいだにユーザーが「修正指示を差し込む」「予算を引き上げて再開する」といった操作をしても、すべて DB 上のジョブ状態として一貫して扱える
3. Workflow インスタンスが万一期限切れや終了状態になっても、新しいインスタンスに同じ `{ jobId }` を渡すだけで途中から再開できる

---

# 実装のポイント

ここからは、実際のコードベースに沿って 4 つの実装ポイントを順番に整理します。

## 1. エントリーポイントと設定（`WorkflowEntrypoint` / `cloudflare.config.ts`）

Cloudflare Workflows では、`cloudflare:workers` の `WorkflowEntrypoint` を継承したクラスを Worker のエントリーポイントファイルからエクスポートします。ノベクリでは `src/server.ts` に `AutopilotWorkflow` クラスを定義しています。

```ts
// src/server.ts（抜粋）
import {
  WorkflowEntrypoint,
  type WorkflowEvent,
  type WorkflowStep,
} from "cloudflare:workers";
import type { WorkerEnv } from "./server/worker-env.js";

export class AutopilotWorkflow extends WorkflowEntrypoint<
  WorkerEnv,
  { jobId: string }
> {
  async run(
    event: Readonly<WorkflowEvent<{ jobId: string }>>,
    step: WorkflowStep
  ): Promise<void> {
    const { buildWorkerContext } = await import("./server/worker-env.js");
    const { runAutopilotWorkflow } = await import(
      "./server/core/autopilot/workflow-runner.js"
    );
    const context = buildWorkerContext(this.env);
    await runAutopilotWorkflow(
      {
        ai: context.ai,
        db: context.db,
        embedding: context.embedding,
        env: context.env,
        llm: context.llm,
        vectorStore: context.vectorStore,
      },
      event.payload.jobId,
      step
    );
  }
}
```

ここで地味に効いているのが `run()` 内部での動的 `import()` です。開発時の `vite dev`（workerd）起動ではエントリーポイントから静的 import されているモジュール群が一括評価されます。Workflow 実行時だけ必要な重いサーバーモジュール・AI SDK 依存を `run()` 内の動的 `import()` に逃がしておくことで、開発サーバーの起動時間への悪影響を抑えています。

バインディングと Export の宣言は、このプロジェクトで使っている `cloudflare.config.ts` 側に記載しています。一般的な `wrangler.jsonc` で書く場合は、`workflows` 配列に `name`・`binding`・`class_name` を並べる形に相当します。

```ts
// cloudflare.config.ts（抜粋）
// wrangler.jsonc の場合:
// "workflows": [{ "name": "novel-creator-autopilot", "binding": "AUTOPILOT_WORKFLOW", "class_name": "AutopilotWorkflow" }]
exports: {
  AutopilotWorkflow: exports.workflow({
    concurrency: { limit: 10 },
    name: "novel-creator-autopilot",
  }),
},
bindings: {
  AUTOPILOT_WORKFLOW: bindings.workflow({
    exportName: "AutopilotWorkflow",
    name: "novel-creator-autopilot",
    worker: "novel-creator",
  }),
}
```

API 側からは `env.AUTOPILOT_WORKFLOW.create({ id: instanceId, params: { jobId } })` でインスタンスを起動し、`env.AUTOPILOT_WORKFLOW.get(instanceId)` で既存のインスタンスハンドルを取得できます。

## 2. ループ型ステートマシンを `step.do` で回す

多段パイプラインを記述するとき、各工程ごとに `step.do("step-1", ...)` → `step.do("step-2", ...)` と直列に書き並べる方法もありますが、小説生成のように「章数 × 節数ぶん繰り返す」「中断・承認・スキップが挟まる」処理では、固定上限ループの中で `step.do` を回すステートマシン型が非常に相性が良かったです。

```ts
// src/server/core/autopilot/workflow-runner.ts（概念抜粋）
const MAX_WORKFLOW_ITERATIONS = 500;

type StepOutcome = {
  action: "continue" | "stop" | "wait_approval";
};

export async function runAutopilotWorkflow(
  base: SharedBaseDeps,
  jobId: string,
  step: AutopilotWorkflowStep,
  deps: AutopilotWorkflowDeps = {}
): Promise<void> {
  const store = deps.store ?? createDbAutopilotWorkflowStore(base.db);

  for (let iter = 0; iter < MAX_WORKFLOW_ITERATIONS; iter += 1) {
    const outcome = await step.do<StepOutcome>(
      `autopilot-step-${iter}`,
      {
        retries: {
          backoff: "exponential",
          delay: "5 seconds",
          limit: 2,
        },
      },
      async () => {
        const existing = await store.getById(jobId);
        if (
          existing === null ||
          isAutopilotTerminalStatus(existing.status) ||
          existing.status === "paused"
        ) {
          return { action: "stop" };
        }
        if (existing.status === "waiting_approval" && !existing.plotApproved) {
          return { action: "wait_approval" };
        }

        // プラン権限・トークン予算（maxTotalTokens）・ステップ上限のチェック
        // 超過時は例外を投げず DB を paused（pauseReason: "budget_reached" 等）に更新して stop
        // ...

        const claimed = await store.markRunning(existing.id);
        if (claimed === null) {
          return { action: "stop" };
        }

        const result = await stepRunner(claimed.currentStep, {
          ctx: jobCtx.ctx,
          job: claimed,
          reportProgress,
        });

        // ステップログ保存 & 次のアクションに応じて DB 更新
        if (result.waitForApproval) {
          await store.park({ /* status: "waiting_approval", ... */ });
          return { action: "wait_approval" };
        }
        if (result.nextStep === "complete") {
          await store.succeed({ /* ... */ });
          return { action: "stop" };
        }
        await store.advance({ nextStep: result.nextStep, /* ... */ });
        return { action: "continue" };
      }
    );

    if (outcome.action === "stop") {
      return;
    }

    if (outcome.action === "wait_approval") {
      // 次の「step.waitForEvent」節で解説
    }
  }
}
```

この構成で特に意識した点は次の 3 つです。

1. ステップ名は反復ごとに一意にする（`autopilot-step-${iter}`）
   Cloudflare Workflows は実行済みステップの結果をステップ名単位で永続化・リプレイするため、ループ内で同じ名前を再利用できません。`iter` を埋め込むことで各反復が独立したチェックポイントになります。
2. ステップの戻り値は `{ action: "continue" | "stop" | "wait_approval" }` だけにする
   小説本文や章配列のような大きなデータを `step.do` の戻り値に乗せる必要はありません。実データは DB に書き込み、Workflow のループ制御に必要な最小限のフラグだけを返すことで、状態サイズが常に一定に保たれます。
3. 1 回の起動で無限ループしないよう `MAX_WORKFLOW_ITERATIONS` と予算上限で安全停止する
   プロンプトの暴走や無限ループで LLM トークンを溶かさないよう、各ステップ実行前に `tokensUsed >= config.maxTotalTokens` と `stepsExecuted >= config.maxSteps` を検査し、上限到達時は `failed` ではなく `paused`（`pauseReason: "budget_reached"`）として安全停止します。また、Cloudflare Workflows には 1 インスタンスあたり 1,024 ステップの上限があるため、`MAX_WORKFLOW_ITERATIONS = 500` で余裕を持って区切る意図もあります。UI 側からは予算を追加してそのまま続きから再開できます。

## 3. `step.waitForEvent` で待機コスト 0 の Human-in-the-loop を書く

自律執筆機能には、全自動モード（`full_auto`）のほかに「プロット（章立て・伏線）ができた時点で一度立ち止まり、人間が確認・修正指示をしてから本文執筆へ進む」モード（`plot_approval`）があります。

人間がプロットを確認して承認ボタンを押すまでには、数分〜数日かかることもあります。これをポーリングやキューの再投入で待つのではなく、`step.waitForEvent` を使って休止します。

```html-embed
<div class="seq-wrap" role="region" aria-label="承認待ちと再開のシーケンス図">
  <div class="seq-actors" aria-hidden="true">
    <div class="seq-actor">ユーザー</div>
    <div class="seq-actor">UI</div>
    <div class="seq-actor">Hono API</div>
    <div class="seq-actor">PostgreSQL</div>
    <div class="seq-actor">Workflow</div>
  </div>

  <div class="seq-body">
    <div class="seq-row">
      <div class="seq-mobile-route">Workflow → PostgreSQL</div>
      <div class="seq-msg seq-c4-5 seq-left">
        <span class="seq-step-num">1</span>
        <code>park(status="waiting_approval")</code>
      </div>
    </div>

    <div class="seq-row">
      <div class="seq-mobile-route">Workflow（待機）</div>
      <div class="seq-msg seq-c5-5 seq-self">
        <span class="seq-step-num">2</span>
        <code>step.waitForEvent("plot-approval", timeout="7 days")</code> で休止
      </div>
    </div>

    <div class="seq-row">
      <div class="seq-mobile-route">ユーザー → UI</div>
      <div class="seq-msg seq-c1-2 seq-right">
        <span class="seq-step-num">3</span>
        プロット確認 &amp; 承認クリック（任意で指示文付き）
      </div>
    </div>

    <div class="seq-row">
      <div class="seq-mobile-route">UI → Hono API</div>
      <div class="seq-msg seq-c2-3 seq-right">
        <span class="seq-step-num">4</span>
        <code>POST /approve { instruction }</code>
      </div>
    </div>

    <div class="seq-row">
      <div class="seq-mobile-route">Hono API → PostgreSQL</div>
      <div class="seq-msg seq-c3-4 seq-right">
        <span class="seq-step-num">5</span>
        <code>approveAutopilotJobByUser(plotApproved=true, nextStep="plan_chapter_sections")</code>
      </div>
    </div>

    <div class="seq-row">
      <div class="seq-mobile-route">Hono API → Workflow</div>
      <div class="seq-msg seq-c3-5 seq-right">
        <span class="seq-step-num">6</span>
        <code>workflow.get(instanceId).sendEvent({ type: "plot-approval", payload })</code>
      </div>
    </div>

    <div class="seq-alt seq-alt-ok">
      <div class="seq-alt-title">分岐 A: sendEvent 成功</div>
      <div class="seq-row">
        <div class="seq-mobile-route">Workflow → PostgreSQL</div>
        <div class="seq-msg seq-c4-5 seq-left">
          <span class="seq-step-num">7a</span>
          <code>confirmApproval()</code>
        </div>
      </div>
      <div class="seq-row">
        <div class="seq-mobile-route">Workflow（継続）</div>
        <div class="seq-msg seq-c5-5 seq-self">
          <span class="seq-step-num">8a</span>
          次ループの <code>step.do</code> で <code>plan_chapter_sections</code> を実行
        </div>
      </div>
    </div>

    <div class="seq-alt seq-alt-fb">
      <div class="seq-alt-title">分岐 B: sendEvent 失敗（旧インスタンス終了・失効など）</div>
      <div class="seq-row">
        <div class="seq-mobile-route">Hono API → Workflow</div>
        <div class="seq-msg seq-c3-5 seq-right">
          <span class="seq-step-num">7b</span>
          <code>workflow.create({ id: jobId + "-a" + timestamp, params: { jobId } })</code>
        </div>
      </div>
      <div class="seq-row">
        <div class="seq-mobile-route">Workflow → PostgreSQL</div>
        <div class="seq-msg seq-c4-5 seq-left">
          <span class="seq-step-num">8b</span>
          DB の <code>plotApproved=true</code> を読んで続きから再開
        </div>
      </div>
    </div>
  </div>
</div>

<style>
  .seq-wrap {
    --sq-bg: #f8fafc;
    --sq-surface: #ffffff;
    --sq-border: #cbd5e1;
    --sq-line: #e2e8f0;
    --sq-text: #0f172a;
    --sq-muted: #475569;
    --sq-accent: #0284c7;
    --sq-accent-bg: #e0f2fe;
    --sq-ok: #15803d;
    --sq-ok-bg: #dcfce7;
    --sq-ok-border: #22c55e;
    --sq-fb: #b45309;
    --sq-fb-bg: #fef3c7;
    --sq-fb-border: #f59e0b;
    box-sizing: border-box;
    padding: 12px;
    background: var(--sq-bg);
    color: var(--sq-text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-size: 12px;
    line-height: 1.35;
  }

  [data-theme="dark"] .seq-wrap {
    --sq-bg: #0f172a;
    --sq-surface: #1e293b;
    --sq-border: #334155;
    --sq-line: #273449;
    --sq-text: #f1f5f9;
    --sq-muted: #cbd5e1;
    --sq-accent: #38bdf8;
    --sq-accent-bg: #0c4a6e;
    --sq-ok: #86efac;
    --sq-ok-bg: #052e16;
    --sq-ok-border: #16a34a;
    --sq-fb: #fcd34d;
    --sq-fb-bg: #451a03;
    --sq-fb-border: #d97706;
  }

  .seq-wrap *,
  .seq-wrap *::before,
  .seq-wrap *::after {
    box-sizing: border-box;
  }

  .seq-actors {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 6px;
    margin-bottom: 8px;
  }

  .seq-actor {
    background: var(--sq-accent-bg);
    border: 1.5px solid var(--sq-accent);
    color: var(--sq-text);
    font-weight: 700;
    text-align: center;
    padding: 5px 4px;
    border-radius: 6px;
    font-size: 12px;
  }

  .seq-body {
    display: flex;
    flex-direction: column;
    gap: 5px;
  }

  .seq-row {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 6px;
    align-items: center;
  }

  .seq-mobile-route {
    display: none;
  }

  .seq-msg {
    background: var(--sq-surface);
    border: 1px solid var(--sq-border);
    border-radius: 6px;
    padding: 4px 8px;
    min-width: 0;
    overflow-wrap: anywhere;
    position: relative;
  }

  .seq-right {
    border-left: 3px solid var(--sq-accent);
  }

  .seq-left {
    border-right: 3px solid var(--sq-accent);
  }

  .seq-self {
    border-left: 3px dashed var(--sq-accent);
    background: var(--sq-accent-bg);
  }

  .seq-c1-2 { grid-column: 1 / 3; }
  .seq-c2-3 { grid-column: 2 / 4; }
  .seq-c3-4 { grid-column: 3 / 5; }
  .seq-c3-5 { grid-column: 3 / 6; }
  .seq-c4-5 { grid-column: 4 / 6; }
  .seq-c5-5 {
    grid-column: 4 / 6;
    justify-self: end;
    width: 68%;
  }

  .seq-step-num {
    display: inline-block;
    font-weight: 700;
    color: var(--sq-accent);
    margin-right: 4px;
  }

  .seq-wrap code {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 12px;
    padding: 0 3px;
    border-radius: 4px;
    background: rgba(148, 163, 184, 0.18);
  }

  .seq-alt {
    border-radius: 8px;
    padding: 6px 8px;
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin-top: 2px;
  }

  .seq-alt-ok {
    background: var(--sq-ok-bg);
    border: 1.5px solid var(--sq-ok-border);
  }

  .seq-alt-fb {
    background: var(--sq-fb-bg);
    border: 1.5px solid var(--sq-fb-border);
  }

  .seq-alt-title {
    font-weight: 700;
    font-size: 12px;
  }

  .seq-alt-ok .seq-alt-title {
    color: var(--sq-ok);
  }

  .seq-alt-fb .seq-alt-title {
    color: var(--sq-fb);
  }

  @media (max-width: 640px) {
    .seq-wrap {
      padding: 10px;
    }

    .seq-actors {
      display: none;
    }

    .seq-row {
      display: flex;
      flex-direction: column;
      align-items: stretch;
      gap: 2px;
    }

    .seq-mobile-route {
      display: block;
      font-weight: 700;
      font-size: 12px;
      color: var(--sq-accent);
    }

    .seq-c1-2,
    .seq-c2-3,
    .seq-c3-4,
    .seq-c3-5,
    .seq-c4-5,
    .seq-c5-5 {
      grid-column: auto;
      justify-self: auto;
      width: auto;
    }
  }
</style>
```

Workflow 側のコードは見通しよく書けます。

```ts
// src/server/core/autopilot/workflow-runner.ts（抜粋）
if (outcome.action === "wait_approval") {
  try {
    const approvalEvent = await step.waitForEvent<{
      instruction?: string;
    }>(`wait-plot-approval-${iter}`, {
      timeout: "7 days",
      type: "plot-approval",
    });

    await step.do(
      `confirm-approval-${iter}`,
      {
        retries: {
          backoff: "constant",
          delay: "2 seconds",
          limit: 2,
        },
      },
      async () => {
        await store.confirmApproval({
          instruction: approvalEvent.payload?.instruction,
          jobId,
        });
        return true;
      }
    );
  } catch {
    // 7 日タイムアウト等で待機に失敗したら paused に倒して安全終了
    const latest = await store.getById(jobId);
    if (latest && !isAutopilotTerminalStatus(latest.status)) {
      await store.park({
        jobId,
        pauseReason: "approval_required",
        progress: {
          ...latest.progress,
          stageLabel: "承認待ちタイムアウトにより一時停止",
        },
        status: "paused",
        tokensDelta: 0,
      });
    }
    return;
  }
}
```

（なお、`catch` ブロック内の `store.park` はタイムアウト終了直前のベストエフォート更新として直接呼んでいますが、リトライによる確実性を優先する場合はこの更新処理も `step.do` で囲むと安全です。）

ポイントは、API 側（承認エンドポイント）に「まず DB 上で承認済みに更新し、次に `sendEvent` を試し、万一 `sendEvent` に失敗したら継続用インスタンスを新しく `workflow.create` する」フォールバックを入れている点です。

```ts
// src/server/core/autopilot/service.ts（抜粋）
const instanceId = updated.runToken ?? updated.id;
try {
  const instance = await workflow.get(instanceId);
  await instance.sendEvent({
    payload: instruction ? { instruction } : {},
    type: "plot-approval",
  });
  return { dispatch: "queued", job: updated };
} catch (err) {
  appLogger.warn(
    "[autopilot] workflow sendEvent failed, spawning continuation instance",
    { err, instanceId, jobId: updated.id }
  );
  const fallbackId = `${updated.id}-a${Date.now()}`;
  const triggered = await triggerWorkflowInstance(
    ctx.db,
    workflow,
    updated.id,
    fallbackId
  );
  // ...
}
```

前述のとおり「業務状態の正は DB」に寄せてあるため、フォールバックで別インスタンスが起動しても、`step.do` 冒頭で DB から `currentStep = "plan_chapter_sections"` と `plotApproved = true` を読み取り、何事もなかったかのように本文執筆フェーズへ進めます。また、各ステップの実行前に DB 側で `markRunning`（および `runToken` の一致確認）によるクレーム処理を行っているため、万一旧インスタンスと新インスタンスが一時的に重なっても二重実行にはならず、片方は即座に `stop` します。

## 4. 長時間ステップ中の「待ち時間」を可視化する

`step.do` はステップ単位のチェックポイントとしては優秀ですが、LLM で 1 節分の小説本文（2,000〜4,000 字）をストリーミング生成するステップでは、1 つの `step.do` の中だけで数十秒〜1 分以上かかることがあります。ステップ完了時まで DB が変わらないと、ユーザー画面がずっと同じ表示のままフリーズしたように見えてしまいます。

そこで、各ステップ関数に `reportProgress` コールバックを渡し、DB の `progress` JSONB カラムへ中間進捗をベストエフォートで書き出すようにしました。

- **ステップ開始時**: `stepStartedAt`（経過時間タイマー用）と `activeSubstage`（例: 「シーン割り・各節のあらすじを構成しています...」）を書き込む
- **本文生成中**: LLM ストリーミングチャンクを受信しつつ、DB 負荷を抑えるため約 2.5 秒スロットルで現在の生成文字数と末尾スニペット（`livePreviewText`）を更新する
- **ステップ完了／停止時**: `settledProgress` で `activeSubstage`・`livePreviewText`・`stepStartedAt` を `null` にクリアする

フロントエンド側はジョブ実行中 2.5 秒間隔でステータス API をポーリングするだけで、「今どのフェーズの何をしているか」「リアルタイムにどのくらいの文が書かれているか」を滑らかに表示できます。`reportProgress` の失敗は `try / catch` で握りつぶすベストエフォート設計にしているため、進捗通知の都合で本体の生成ステップが失敗・リトライされることはありません。

---

# 実際に使って分かったハマりどころと設計ノウハウ

実装とローカル実機（Miniflare）での検証を通じて得た知見をまとめます。

## 1. リトライさせたいエラーとさせたくないエラーを切り分ける

`step.do` に `retries: { limit: 2, ... }` を設定すると、コールバック内で未捕捉の例外を投げた際に自動で再実行されます。これはネットワークの一瞬の揺らぎには有効ですが、プランの月次上限超過や 429 レート制限、モデル設定不備などをそのまま `throw` すると無駄なリトライが走ってしまいます。

そのためノベクリでは `step.do` の `try / catch` 内でエラーを分類し、次のように振る舞いを分けています。

- **クォータ／プラン制限・429**: `paused`（`pauseReason: "plan_limit"`）に倒して `{ action: "stop" }` を返す（Workflow のリトライを回さない）
- **トークン予算上限・最大ステップ上限**: 実行前にチェックして `paused`（`pauseReason: "budget_reached"`）で安全停止する
- **それ以外の致命的失敗**: ログ内の認証キー等を `sanitizeAutopilotErrorMessage` でマスクしたうえで `failed` を記録し、`{ action: "stop" }` を返す

あえて「Workflows のリトライに任せる一時エラー」と「アプリ側でハンドリングして綺麗に止めるエラー」の境界を自前で握っておくと、失敗時の挙動が予測しやすくなります。

## 2. 一時停止・キャンセル・再開の二重ガード

API から「一時停止（`pause`）」や「キャンセル（`cancel`）」が呼ばれたとき、まず DB 上のステータスを更新したうえで `workflow.get(instanceId)` に対して `instance.pause()` や `instance.terminate()` を呼びます。

ただし、ステップ実行のちょうど境目などでタイミングが前後する可能性があるため、各 `step.do` の冒頭でも必ず DB 上の最新ステータスを確認し、`paused` や終了ステータスになっていれば即 `{ action: "stop" }` を返す二重ガードにしています。

また、一時停止や失敗からの再開（`resume`）は `instance.resume()` に一本化せず、既存インスタンスがすでに終了／期限切れになっていても確実に動くよう、DB の状態を `queued` に戻したうえで `${job.id}-r${Date.now()}` の新しいインスタンス ID で `workflow.create()` を呼び出す形に揃えました。この統一モデルのおかげで、承認後タイムアウトからの再開・予算引き上げ後の再開・エラー修正後の再開がすべて同じ経路で動きます。

## 3. クライアント同居構成（TanStack Start / Vite）での `cloudflare:workers` 型定義

少し特殊な事情ですが、ノベクリは TanStack Start による SSR / クライアントコードと、Cloudflare Workers / Workflows のサーバーコードが同じアプリパッケージ（`apps/app`）に同居しています。

この構成で `@cloudflare/workers-types` をグローバル型としてそのまま読み込むと、Workers 側の `Response` 型拡張などがブラウザ・DOM 前提のクライアント側の型チェックと衝突して大量の型エラーを引き起こします。

そこで今回は次のように型境界を切り離しました。

- `src/server/cloudflare-workers.d.ts`: `cloudflare:workers` モジュールのうち、`WorkerEntrypoint`・`WorkflowEntrypoint`・`WorkflowEvent`・`WorkflowStep` の必要な最小面だけを宣言
- `src/server/worker-env.ts` / `workflow-runner.ts`: 実ランタイムのバインディングや `WorkflowStep` と構造的に互換な最小インターフェース（`AutopilotWorkflowBinding` / `AutopilotWorkflowStep`）を定義

この「構造的部分型で受ける」アプローチは、次のテスト容易性にもそのまま活きました。

## 4. テスト容易性（Vitest 単体テスト + ローカル Miniflare 検証）

`runAutopilotWorkflow` が Cloudflare ランタイムの具象クラスに直接依存せず、`AutopilotWorkflowStep` と `AutopilotWorkflowStore` を DI できる純粋な関数になっているため、普段の Vitest 単体テストではインメモリのフェイク `step` とモックストアを差し込むだけで高速にテストできます。

実際、次のシナリオを数ミリ秒〜数十ミリ秒のユニットテストで網羅しています。

- 複数ステップの連続実行と `maxSteps` / `maxTotalTokens` 到達時の安全停止
- `plot_approval` での `waitForEvent` 待機・指示付き承認・タイムアウト時の一時停止
- API キー等を含むエラーメッセージのサニタイズと `failed` 記録
- 各ステップ（構想推敲・プロット生成・節設計・本文執筆・章終了時のベクトル整合修復）の単体検証

そのうえで、開発サーバー（Vite + Miniflare）上では設定した実 Cloudflare Workflows バインディングと PostgreSQL を使って、実際の承認停止〜ブラウザからの承認操作〜完走までをそのまま E2E で動かして確認できました。ローカル開発環境と本番環境で同じ Workflow ランタイムモデルが動く点は大きな安心感につながります。

---

# まとめ

ノベクリの自律執筆機能を題材に、Cloudflare Workflows を使った長時間・多段処理の設計と実装を紹介しました。

- 実行の耐久性とリトライ・長時間の待機は Cloudflare Workflows（`step.do` / `step.waitForEvent`）に任せる
- 進捗・予算・承認状態・ログといった業務状態の正は DB に置き、Workflow には `{ jobId }` だけを渡す
- 継続再開は新規インスタンス起動のフォールバックを前提にしておくと、タイムアウト・予算超過・失敗リカバリをすべて同じ仕組みで扱える

時間のかかる AI パイプラインは、状態をキューでたらい回しにし始めると途端に全体の見通しが悪くなりますが、Cloudflare Workflows と「状態の正を DB に置く」割り切りを組み合わせることで、処理の流れを素直な `for` ループと `await` としてすっきり記述できるようになりました。

同じように「LLM を使った複数ステップの自動実行」や「途中で人間の確認を挟むバックグラウンド処理」を Cloudflare Workers 上で組み立てたい方の参考になれば幸いです。
