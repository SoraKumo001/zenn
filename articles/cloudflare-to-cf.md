---
title: "Cloudflare の CLI を wrangler から cf に移行する"
emoji: "🦔"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: ["cloudflare", "cloudflareworkers", "reactrouter", "vite", "typescript"]
published: true
---

## はじめに

Cloudflare から次世代の統合 CLI ツール **`cf`**（現在 v1.0.0-beta）が登場しました。
従来の `wrangler`（`wrangler.json` / `wrangler.jsonc` / `wrangler.toml`）から、TypeScript ベースの型安全な設定ファイル **`cloudflare.config.ts`** への移行が推奨されています。

公式には `cf migrate` という移行コマンドが用意されていますが、実行するだけでそのまま本番稼働できるわけではなく、いくつかの設定調整や実運用上のハマりどころが存在します。

この記事では、**React Router（v8 / Vite）+ Cloudflare Workers** のフルスタック構成や、キュー・バッチ Worker を含むマルチ Worker 構成を例に、`cf migrate` 実行から本番デプロイ成功までに必要だった全ステップと、実際に直面したエラーとその対処法を体系的に整理しました。

---

## なぜ今 `cf` に移行するのか？ 移行の 5 つのメリット

従来の `wrangler` から新 CLI `cf`（および `cloudflare.config.ts`）に移行することで、主に以下の 5 つの大きな恩恵が得られます。

### 1. TypeScript-first による強力な型安全性と補完
従来の `wrangler.jsonc` や `wrangler.toml` では、設定項目のタイポやバインディング定義の不備に気づくのはデプロイ時や実行時でした。
新設定 `cloudflare.config.ts` は完全な TypeScript 定義であり、IDE 上でリアルタイムに型チェックと補完が働きます。`bindings.hyperdrive()` や `bindings.assets()` などの専用ヘルパー関数が提供され、必須プロパティや利用可能なオプションがコーディング中に一目でわかります。

### 2. 設定ファイルとアプリケーションコードの完全な型同期
従来の `wrangler types` ではローカルの `.dev.vars` を元に曖昧に型生成されていましたが、`cf workers types` は `cloudflare.config.ts` の定義から直接型を逆算（`InferEnv`）します。
設定ファイルが「単一の真実のソース（Single Source of Truth）」となり、Worker 実装側の `env.database` や `env.SECRET_KEY` との型の乖離が一切なくなります。

### 3. Workers に留まらない Cloudflare 全リソースの統合 CLI
`wrangler` は Workers / Pages に特化したツールでしたが、新 CLI `cf` は Cloudflare 全体のプラットフォームを操作するための統合 CLI です。
DNS、R2、D1、Hyperdrive、Zero Trust、WAF、Images、Stream などの全サービスが同一の CLI から一貫したコマンド体系（`cf dns`, `cf r2`, `cf d1` 等）で操作可能になり、インフラ全体の管理が一本化されます。

### 4. モダンフレームワーク（Vite / React Router 等）とのネイティブ連携
Cloudflare の標準ビルド出力仕様（Build Output Specification: BOS）に基づいて設計されており、Vite や React Router との親和性が大幅に向上しています。
特に `cf dev` はフレームワークの開発サーバー（Vite）を自動検出し、事前ビルドなしでオンザフライな開発・高速な HMR（ホットリロード）を実現します。

### 5. AI エージェント（Agentic Coding）との親和性
`cf` は AI エージェント（Claude Code、Cursor、Antigravity など）による自動構成・コーディング支援を強く意識して設計されています。
AI が設定を変更する際も、TypeScript の型チェックによる即時フィードバックや、CLI の自己記述スキーマ（`cf schema`）を活用できるため、ハルシネーションによる誤設定を防ぎやすくなっています。

---

## 移行のロードマップ

移行作業は以下の流れで進めます。

```text
Step 1. 初期移行と設定ファイルの整備 (cf migrate / cloudflare.config.ts)
  ↓
Step 2. シークレット・環境変数と型定義 (cf workers types / tsconfig)
  ↓
Step 3. Vite / React Router との連携設定 (vite.config.ts)
  ↓
Step 4. スクリプトの更新 (package.json)
  ↓
Step 5. 実務・本番運用での落とし穴チェック (Windows・CLIフラグ・CI依存)
  ↓
Step 6. 最終動作検証と旧設定ファイルの整理
```

---

## Step 1: `cf migrate` の実行と `cloudflare.config.ts` の整備

まずはプロジェクトルートで移行コマンドを実行します。

```bash
pnpm dlx cf migrate
```

これにより以下の変更が自動で行われます：
- `package.json` の `devDependencies` に `"cf": "1.0.0-beta.x"` が追加
- `cloudflare.config.ts` が自動生成
- `.gitignore` に `.cloudflare` ディレクトリが追加

### 1-1. `cloudflare.config.ts` の `throw new Error` を解消する

生成された `cloudflare.config.ts` を開くと、以下のような TODO や例外スローが含まれている場合があります。

```typescript
// 移行直後のコード例
export default defineConfig({
  worker: {
    name: "my-app",
    compatibilityDate: "2026-09-04",
    compatibilityFlags: ["nodejs_compat"],
    entrypoint: "./workers/app.ts",
    // TODO: assets.directory is not supported in cloudflare.config.ts
    // throw new Error("assets.directory is not supported in cloudflare.config.ts");
    env: {
      ASSETS: bindings.assets(),
    },
  },
});
```

`cf` CLI では、Vite などのビルドツール経由でアセットが自動検出・配置されるため、設定ファイル側で静的アセットディレクトリ（旧 `assets.directory`）を明示する必要はありません。

Worker 内から静的ファイルを取得するための `ASSETS: bindings.assets()` が宣言されていれば十分ですので、**`throw new Error(...)` や TODO コメントは削除** します。

### 1-2. ブランチ・プレビュー環境（`previews`）の移行: `ctx.isPreview`

`wrangler.jsonc` で `previews: { vars: { ... } }` のようにブランチや PR プレビュー環境の設定を書いていた場合、`cf migrate` は自動的に**関数形式の `defineConfig((ctx) => { ... })`** に変換してくれます。

```typescript
import { bindings, defineConfig, triggers } from "cf/config";

export default defineConfig((ctx) => {
  // ブランチ / PR プレビュー環境の個別設定
  if (ctx.isPreview) {
    return {
      worker: {
        name: "my-app",
        compatibilityDate: "2026-09-04",
        compatibilityFlags: ["nodejs_compat"],
        entrypoint: "src/server.ts",
        env: {
          ENVIRONMENT: bindings.text("preview"),
          // プレビュー専用の R2 バケットや Rate Limit 等
          COVERS: bindings.r2({ name: "my-app-covers-preview" }),
          ASSETS: bindings.assets(),
        },
      },
    };
  }

  // 本番環境の設定
  return {
    worker: {
      name: "my-app",
      compatibilityDate: "2026-09-04",
      compatibilityFlags: ["nodejs_compat"],
      entrypoint: "src/server.ts",
      triggers: [
        triggers.queue({
          name: "my-app-jobs",
          deadLetterQueue: "my-app-jobs-dlq",
        }),
      ],
      env: {
        ENVIRONMENT: bindings.text("production"),
        COVERS: bindings.r2({ name: "my-app-covers" }),
        HYPERDRIVE: bindings.hyperdrive({ id: "xxxxxxxx" }),
        ASSETS: bindings.assets(),
      },
    },
  };
});
```

プレビュー環境では利用できないリソース（例えば Worker Previews で登録できない Queue Consumer など）をプレビュー側でのみ除外したり、バケットやレート制限の名前空間をプレビュー用に切り替えたりといった制御が、TypeScript の通常の `if` 文で明快に記述できます。

---

## Step 2: シークレット・環境変数と型定義（`cf workers types`）

### 2-1. `cf workers types` の仕組み
- **旧 `wrangler types`**: `.dev.vars` などのファイルを読み込んで `worker-configuration.d.ts`（`interface Env`）を生成していました。
- **新 `cf workers types`**: `cloudflare.config.ts` の設定内容から型（`InferEnv`）を逆算し、`.cloudflare/types/index.d.ts` に生成します。

そのため、Worker 内で利用するシークレット環境変数を TypeScript で型付けするには、`cloudflare.config.ts` の `env` に `bindings.secret()` として定義します。

```typescript
import { bindings, defineConfig } from "cf/config";

export default defineConfig({
  worker: {
    name: "my-app",
    compatibilityDate: "2026-09-04",
    compatibilityFlags: ["nodejs_compat"],
    entrypoint: "./workers/app.ts",
    placement: { mode: "smart" },
    observability: { enabled: true },
    env: {
      // Hyperdrive
      database: bindings.hyperdrive({
        id: "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        dev: {
          connectionString: "postgresql://postgres:password@localhost:5432/postgres",
        },
      }),
      // 静的アセット
      ASSETS: bindings.assets(),

      // シークレット環境変数
      DATABASE_URL: bindings.secret(),
      SECRET_KEY: bindings.secret(),
      GOOGLE_PROJECT_ID: bindings.secret(),
    },
  },
});
```

この状態で型生成コマンドを実行します。

```bash
pnpm exec cf workers types
# => .cloudflare/types/index.d.ts が生成される
```

### 2-2. ⚠️【重要】`bindings.secret()` はデプロイ時必須バリデーションがかかる

`cloudflare.config.ts` に `bindings.secret()` を記載した変数は、デプロイ時に **Cloudflare 側で「必須シークレット（Required secrets）」としてバリデーション** されます。

もし本番環境に登録されていないキーや、ローカルテスト用のみで本番には存在しないキー（例: `ENV=local` など）をうっかり `bindings.secret()` に含めてしまうと、デプロイ時に以下のエラーで停止します：

```text
┌ Error
│ The following required secrets have not been set: ENV
│ Use `wrangler secret put <NAME>` to set secrets before deploying,
│ or supply them when deploying with `cf deploy --secrets-file <path-to-file>`.
└
```

**本番環境で実際に必要となるシークレットのみを `bindings.secret()` に定義する** よう注意してください。

### 2-3. `tsconfig` の更新と旧ファイルの削除

型定義の出力先が変更されたため、TypeScript の設定を更新します。

```json
// tsconfig.json（または tsconfig.worker.json 等）
{
  "include": [
    "app/**/*",
    "workers/**/*",
    ".cloudflare/types/**/*" // worker-configuration.d.ts から変更
  ]
}
```

更新後、不要になった `worker-configuration.d.ts` は削除します。

```bash
git rm worker-configuration.d.ts
```

---

## Step 3: Vite / React Router との連携設定（`vite.config.ts`）

フルスタックフレームワーク（React Router / TanStack Start など）と組み合わせる場合、`vite.config.ts` で 2 つの重要な調整が必要です。

### 3-1. `experimental: { newConfig: true }` の有効化（404 解決）

`wrangler.jsonc` を削除して開発サーバーを起動すると、Vite の静的ファイルサーバーだけが動き、肝心の Worker が読み込まれず `http://localhost:3000/` が 404 になる事象が発生します。

**原因:**
`@cloudflare/vite-plugin` はデフォルトでは `wrangler.json` / `wrangler.jsonc` を探索します。`cloudflare.config.ts` を読み込ませるには、プラグインのオプションで **`experimental: { newConfig: true }`** を指定する必要があります。

```typescript
// vite.config.ts
import { cloudflare } from "@cloudflare/vite-plugin";

export default defineConfig({
  plugins: [
    cloudflare({
      experimental: {
        newConfig: true, // これが必要！
      },
      viteEnvironment: { name: "ssr" },
    }),
    // ...
  ],
});
```

これを指定することで、`wrangler.jsonc` が存在しなくても直接 `cloudflare.config.ts` が読み込まれ、ローカル開発環境（`dev`）で Worker や `.dev.vars` が正しくマウントされます。

### 3-2. BOS 出力とクライアントマニフェストの同期（ENOENT 解決）

`cf deploy`（または `--dry-run`）を実行すると、CLI は `CLOUDFLARE_VITE_FORCE_BUILD_OUTPUT=true` という環境変数を付与してビルドを実行します。

このとき、`@cloudflare/vite-plugin` は Cloudflare の新しい仕様である **Build Output Specification (BOS)** に従い、クライアントの出力先（`outDir`）を強制的に `.cloudflare/output/v0/workers/default/assets` に変更します。

しかし、React Router などの SSR ビルド処理は、クライアントマニフェストの出力先として `build/client/.vite/manifest.json` を探索するため、ファイル不在エラー（`ENOENT`）が発生します。

**解決策:**
クライアントビルドが完了したタイミングで、生成されたアセットディレクトリを React Router が参照する `build/client` へコピーする同期プラグインを `vite.config.ts` に追加します。

```typescript
import fs from "node:fs";
import path from "node:path";
import { cloudflare } from "@cloudflare/vite-plugin";
import { reactRouter } from "@react-router/dev/vite";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [
    cloudflare({
      experimental: { newConfig: true },
      viteEnvironment: { name: "ssr" },
    }),
    // React Router と Cloudflare BOS の出力先差異を吸収する同期プラグイン
    {
      name: "sync-client-manifest-for-react-router",
      writeBundle() {
        if (this.environment?.name === "client") {
          const src = path.resolve(".cloudflare/output/v0/workers/default/assets");
          const dest = path.resolve("build/client");
          if (fs.existsSync(src)) {
            fs.cpSync(src, dest, { recursive: true });
          }
        }
      },
    },
    tailwindcss(),
    reactRouter(),
  ],
});
```

このプラグインにより、Cloudflare の Build Output Specification とフレームワークのビルド要件が両立し、エラーなくビルド＆デプロイが完了します。

---

## Step 4: `package.json` のスクリプト更新

CLI が `wrangler` から `cf` に移行したことで、コマンド体系も整理されます。

### 4-1. コマンド対比表（`wrangler` vs `cf`）

| 用途 | 旧コマンド (`wrangler`) | 新コマンド (`cf`) | 備考 |
| :--- | :--- | :--- | :--- |
| **開発 (ローカル)** | `wrangler dev` | `cf dev` | 事前ビルド不要。Vite 開発サーバーに委譲 |
| **型生成** | `wrangler types` | `cf workers types` | `cloudflare.config.ts` から型を逆算 |
| **本番デプロイ** | `wrangler deploy` | `cf deploy` | 自動でビルドが実行される |
| **ドライラン** | `wrangler deploy --dry-run` | `cf deploy --dry-run` | バインディング検証・BOS アセット検証 |
| **シークレット一括反映** | `wrangler secret bulk .env.production` | `cf deploy --secrets-file .env.production` | デプロイ時にシークレットを注入 |
| **ログ監視** | `wrangler tail` | （`wrangler tail` を維持） | ※ 現時点の `cf` には対話型 tail コマンドが未実装 |

### 4-2. `package.json` の変更例

```json
{
  "scripts": {
    "dev": "npm-run-all -p dev:*",
    "dev:react-router": "react-router dev --port 3000",
    "start": "cf dev",
    "typecheck": "tsc --noEmit --pretty",
    "typegen": "cf workers types",
    "build": "react-router build",
    "deploy": "cf deploy",
    "dry-run": "cf deploy --dry-run",
    "deploy-secret": "cf deploy --secrets-file .env.production",
    "log": "wrangler tail my-app"
  }
}
```

> **Q. `cf dev` で起動する場合、事前ビルドは必要？**  
> **A. 不要です。**  
> 以前の `wrangler dev` ではビルド済み成果物（`build/server/index.js`）を参照するケースが一般的でしたが、`cf dev` はプロジェクトの Vite / React Router 開発サーバーを自動検知して直接委譲します。ソースコードをオンザフライで読み込み、HMR（ホットリロード）が有効な状態で高速に起動します。

---

## Step 5: 実務・本番運用で直面する 3 つの落とし穴

フルスタックアプリやモノレポ（複数 Worker やキュー処理 Worker が同居する構成）を実際に運用・移行する中で判明した実践的な落とし穴です。

### 落とし穴①: Vite を使わない純粋な Worker での Windows 特有エラー（`spawn EFTYPE`）

Vite を組み込んだ Web アプリ（`@cloudflare/vite-plugin` 導入済み）では `cf deploy` が正常に動きますが、**キューの処理やバッチ処理を行う Vite を使わないシンプルな Worker**（例: `entrypoint: "src/index.ts"` のみ）を Windows 環境で `cf deploy` しようとすると、以下のエラーが発生します：

```text
├  Build
|  Delegating to Wrangler

┌ Error
│ spawn EFTYPE
└
```

#### 原因の解析
`cf` CLI（`1.0.0-beta.2`）は、プロジェクト内に `@cloudflare/vite-plugin` が見つからない場合、フォールバックとして Wrangler に処理を委譲（`Delegating to Wrangler`）します。
その際、`cf` 内部（`spawn-*.mjs`）で以下のように直接 `.js` ファイルを指定して子プロセスを起動しようとします：

```javascript
// cf CLI 内部の簡易コード
spawn("node_modules/wrangler/bin/cf-wrangler.js", ["deploy", ...], { ... });
```

Linux や macOS ではシバン（`#!/usr/bin/env node`）が解釈されるため動きますが、**Windows カーネルは `.js` ファイルを実行可能バイナリ（PE 形式）として直接 spawn できない**ため、OS から `EFTYPE`（実行不能フォーマット）エラーが返されます。

#### 対処法
- **Vite なしの軽量 Worker**: 現時点のベータ版では、Windows ローカルからのデプロイや起動には `wrangler deploy` / `wrangler dev` をそのまま維持するのが最も堅牢です（Linux 上の CI / CD コンテナでは問題なく動きます）。
- あるいは、その Worker にも Vite / `@cloudflare/vite-plugin` を導入してバンドルさせる構成にします。

---

### 落とし穴②: `cf deploy` では `--var` オプションが使えない

従来の `wrangler deploy` では、特定のデプロイ時のみ環境変数を上書きするために `--var KEY:VALUE` オプションが使えました：

```bash
# wrangler では動いていたコマンド例
wrangler deploy --secrets-file secrets.json --var FEATURE_FLAG:true
```

しかし、現行の `cf deploy`（`1.0.0-beta.2`）のヘルプを確認すると、**`--var` フラグは提供されていません**。

```text
Options:
  --prebuilt            Deploy existing Build Output Specification files without building
  --secrets-file        Path to a file containing secrets to upload with the version (JSON or .env format)
  --dry-run             Build a project and run checks without actually uploading the Worker
  --worker              Name of the Worker in the Build Output to use
```

#### 対処法
動的に注入したい非シークレット変数がある場合：
1. `--secrets-file` の JSON または `.env` ファイルにその変数も含めて渡す（`--secrets-file` は加算継承されるため、ファイル内に書いた変数が注入されます）。
2. または `cloudflare.config.ts` 側で `process.env.FEATURE_FLAG` を参照し、実行時環境変数を読み取って `bindings.text()` に渡すように記述します。

---

### 落とし穴③: `wrangler.jsonc` を安易に削除してはならないケース

個人ブログなどの単一プロジェクトであれば `wrangler.jsonc` を削除して移行完了で問題ありませんが、CI / CD やテストが整備された本番プロジェクトでは、**安易に `wrangler.jsonc` を消すとパイプラインが壊れる**場合があります。

特に以下の依存がないか事前にチェックしてください：
1. **GitHub Actions（CI パイプライン）**:
   - `ci.yml` 内で `test -f apps/app/wrangler.jsonc` や `grep -q '"previews"' wrangler.jsonc` のようなバリデーションが存在しないか。
   - `package.json` 内の `"deploy:preview": "wrangler preview"` のコマンド名を CI が検証していないか。
2. **E2E テスト（Playwright 等）**:
   - ローカルでの E2E 実行時に `wrangler dev -c wrangler.e2e.jsonc` のように専用設定ファイルを参照していないか。
3. **リポジトリ内の preflight 検証スクリプト**:
   - Rate Limit や Queue の設定値を `wrangler.jsonc` からパースして整合性検証を行うカスタムスクリプトが存在しないか。

これらが存在する場合、**`cloudflare.config.ts` と `wrangler.jsonc` を安全に並行維持**し、CI やテストのスクリプト側を `cloudflare.config.ts` 対応に改修するまでは無理に `wrangler.jsonc` を削除しない運用をおすすめします。

---

## Step 6: 最終チェックリスト

移行作業が完了したら、以下のチェックリストで全体の整合性を確認します。

- [ ] **型チェック**: `tsc --noEmit` でリポジトリ全体に型エラーが出ないこと
- [ ] **型定義生成**: `cf workers types` で `.cloudflare/types/index.d.ts` が正常に出力されること
- [ ] **ローカル起動**: `pnpm run dev` または `cf dev` で 404 にならず、ページが正常に表示されること
- [ ] **デプロイドライラン**: `cf deploy --dry-run` でビルドが成功し、全バインディングと静的アセット（BOS）が正しく認識されること
- [ ] **CI / E2E テスト**: GitHub Actions やローカル E2E が設定ファイル変更後も green を維持していること
- [ ] **本番デプロイ**: `cf deploy` で本番環境へ正常にデプロイされること

---

## まとめ

Cloudflare の新 CLI `cf` と `cloudflare.config.ts` は、TypeScript の型チェックや IDE・AI エージェントとの親和性が非常に高く、今後の Cloudflare 開発のスタンダードになっていく強力なツールです。

一方で、現行バージョン（`1.0.0-beta`）では以下の点に注意が必要です：
- **React Router / Vite 連携**: `experimental.newConfig: true` の指定や BOS 出力ディレクトリの同期が必要。
- **シークレット**: `bindings.secret()` はデプロイ時必須バリデーションがかかる。
- **純粋な Worker**: Windows 環境で Wrangler への委譲時に `spawn EFTYPE` が発生するケースがある。
- **CLI フラグ**: `--var` オプションが廃止されているため `--secrets-file` や TypeScript 側の `process.env` で吸収する。
- **CI / E2E**: 既存のチェックスクリプトとの兼ね合いで `wrangler.jsonc` の共存が必要な場合がある。

これらの実践的なポイントをあらかじめ把握しておくことで、本番アプリケーションでもトラブルなくスムーズに `cf` への移行を実現できます。ぜひお試しください！
