---
title: "Cloudflare の CLI を wrangler から cf に移行する"
emoji: "🦔"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: ["cloudflare", "cloudflareworkers", "reactrouter", "vite", "typescript"]
published: true
---

# はじめに

Cloudflare から次世代の統合 CLI ツール **`cf`**（現在 v1.0.0-beta）が登場しました。
従来の `wrangler`（`wrangler.json` / `wrangler.jsonc` / `wrangler.toml`）から、TypeScript ベースの型安全な設定ファイル **`cloudflare.config.ts`** への移行が推奨されています。

公式には `cf migrate` という移行コマンドが用意されていますが、実行するだけでそのまま本番稼働できるわけではなく、いくつかの設定調整やハマりどころが存在します。

この記事では、**React Router（v8 / Vite）+ Cloudflare Workers** のフルスタック構成を例に、`cf migrate` 実行からデプロイ成功までに必要だった全ステップと、実際に直面したエラーとその対処法をまとめました。

---

# なぜ今 `cf` に移行するのか？移行のメリット

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

# 1. `cf migrate` の実行と `cloudflare.config.ts` の修正

まずはプロジェクトルートで移行コマンドを実行します。

```bash
pnpm dlx cf migrate
```

これにより以下が行われます：
- `package.json` の `devDependencies` に `"cf": "1.0.0-beta.x"` が追加
- `cloudflare.config.ts` が自動生成
- `.gitignore` に `.cloudflare` ディレクトリが追加

### `cloudflare.config.ts` の `throw new Error` を解消する

生成された `cloudflare.config.ts` を開くと、以下のような TODO や例外スローが含まれている場合があります。

```typescript
// 移行直後のコード例
export default defineConfig({
  worker: {
    name: "my-app",
    compatibilityDate: "2025-12-13",
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

---

# 2. シークレット・環境変数の設定と型定義（`cf workers types`）

### `cf workers types` の仕組み
- **旧 `wrangler types`**: `.dev.vars` などのファイルを読み込んで `worker-configuration.d.ts`（`interface Env`）を生成していました。
- **新 `cf workers types`**: `cloudflare.config.ts` の設定内容から型（`InferEnv`）を逆算し、`.cloudflare/types/index.d.ts` に生成します。

そのため、Worker 内で利用するシークレット環境変数を TypeScript で型付けするには、`cloudflare.config.ts` の `env` に `bindings.secret()` として定義します。

```typescript
import { bindings, defineConfig } from "cf/config";

export default defineConfig({
  worker: {
    name: "my-app",
    compatibilityDate: "2025-12-13",
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
      NEXT_PUBLIC_API_KEY: bindings.secret(),
    },
  },
});
```

この状態で型生成コマンドを実行します。

```bash
pnpm exec cf workers types
# => .cloudflare/types/index.d.ts が生成される
```

### ⚠️【注意】`bindings.secret()` はデプロイ時の必須シークレットになる
ここが 1 つ目の重要なポイントです。

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

---

# 3. `tsconfig` の更新と旧ファイルの整理

型定義の出力先が変更されたため、TypeScript の設定を更新します。

### `tsconfig.json`（または `tsconfig.cloudflare.json`）
`worker-configuration.d.ts` への参照を `.cloudflare/types/**/*` に変更します。

```json
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

# 4. `vite.config.ts` の調整（2 つの落とし穴と解決法）

ここが移行において最もハマりやすい部分です。

### 落とし穴①: `wrangler.jsonc` を消すと `dev` が 404 になる
`wrangler.jsonc` を削除して `react-router dev` を起動すると、Vite の静的ファイルサーバーだけが動き、肝心の Worker が読み込まれず `http://localhost:3000/` が 404 になる事象が発生します。

**原因:**
`@cloudflare/vite-plugin` はデフォルトでは `wrangler.json` / `wrangler.jsonc` を探索します。`cloudflare.config.ts` を読み込ませるには、プラグインのオプションで **`experimental: { newConfig: true }`** を指定する必要があります。

```typescript
// vite.config.ts
import { cloudflare } from "@cloudflare/vite-plugin";

export default defineConfig({
  plugins: [
    cloudflare({
      viteEnvironment: { name: "ssr" },
      experimental: { newConfig: true }, // これが必要！
    }),
    // ...
  ],
});
```

これを指定することで、`wrangler.jsonc` が存在しなくても直接 `cloudflare.config.ts` が読み込まれ、ローカル開発環境（`dev`）で Worker や `.dev.vars` が正しくマウントされるようになります。

---

### 落とし穴②: `cf deploy` で React Router のマニフェストが見つからずエラーになる
`cf deploy`（または `--dry-run`）を実行すると、CLI は `CLOUDFLARE_VITE_FORCE_BUILD_OUTPUT=true` という環境変数を付与してビルドを実行します。

このとき、`@cloudflare/vite-plugin` は Cloudflare の新しい仕様である **Build Output Specification (BOS)** に従い、クライアントの出力先（`outDir`）を強制的に `.cloudflare/output/v0/workers/default/assets` に変更します。

しかし、React Router（v8 / Remix 系統）の SSR ビルド処理は、クライアントマニフェストの出力先として `build/client/.vite/manifest.json` をハードコードで探索するため、以下のファイル不在エラーが発生します：

```text
[plugin react-router:virtual-modules]
Error: ENOENT: no such file or directory, open '.../build/client/.vite/manifest.json'
```

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
      viteEnvironment: { name: "ssr" },
      experimental: { newConfig: true },
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

このプラグインにより、Cloudflare の Build Output Specification と React Router のビルド要件が両立し、エラーなくビルド＆デプロイが完了します。

---

# 5. `package.json` のスクリプト更新

CLI が `wrangler` から `cf` に移行したことで、コマンドの書き方も変わります。

| 用途 | 旧コマンド (`wrangler`) | 新コマンド (`cf`) | 備考 |
| :--- | :--- | :--- | :--- |
| **開発 (ローカル)** | `wrangler dev` | `cf dev` | 事前ビルド不要。Vite 開発サーバーに委譲 |
| **型生成** | `wrangler types` | `cf workers types` | `cloudflare.config.ts` から生成 |
| **本番デプロイ** | `wrangler deploy` | `cf deploy` | 自動でビルドが実行される |
| **ドライラン** | `wrangler deploy --dry-run` | `cf deploy --dry-run` | バインディング検証・事前チェック |
| **シークレット一括反映** | `wrangler secret bulk .env.production` | `cf deploy --secrets-file .env.production` | デプロイ時にシークレットを注入 |
| **ログ監視** | `wrangler tail` | （`wrangler tail` を維持） | ※ 現時点の `cf` には対話型 tail コマンドが未実装 |

### `package.json` の変更例

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
    "log": "wrangler tail dr-blog"
  }
}
```

> **Q. `cf dev` で起動する場合、事前ビルドは必要？**
> **A. 不要です。**
> 以前の `wrangler dev` ではビルド済み成果物（`build/server/index.js`）を参照するケースが一般的でしたが、`cf dev` はプロジェクトの Vite / React Router 開発サーバーを自動検知して直接委譲します。ソースコードをオンザフライで読み込み、HMR（ホットリロード）が有効な状態で起動します。

---

# 6. 旧設定ファイル（`wrangler.jsonc`）の削除

すべての動作確認（型チェック、ローカル起動、ドライラン）が完了したら、設定の二重管理を防ぐために旧設定ファイルを削除します。

```bash
git rm wrangler.jsonc
```

### 最終チェックリスト
- [ ] `pnpm run typecheck` (`tsc --noEmit`): 型エラーが出ないこと
- [ ] `pnpm run typegen` (`cf workers types`): `.cloudflare/types/index.d.ts` が正常に出力されること
- [ ] `pnpm run dev` または `cf dev`: ローカルで 404 にならず正常にページが表示されること
- [ ] `pnpm run dry-run` (`cf deploy --dry-run`): ビルドおよびバインディング検証が通過すること
- [ ] `pnpm run deploy` (`cf deploy`): 本番環境へ正常にデプロイされること

---

# まとめ

Cloudflare の新 CLI `cf` と `cloudflare.config.ts` は、TypeScript の型チェックや IDE・AI エージェントとの親和性が非常に高く、今後の Cloudflare 開発のスタンダードになっていくツールです。

現時点のベータ版では、フレームワークとの組み合わせにおいて出力ディレクトリの差異やオプション指定（`experimental.newConfig`）などの注意点がありますが、本記事の手順を踏むことでスムーズに移行することができます。移行を検討されている方の参考になれば幸いです。
