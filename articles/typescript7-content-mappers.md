---
title: "Next.js で TypeScript7.1 の Content Mappers を使い、*.graphql ファイルを直接使用する"
emoji: "⚡"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: ["typescript", "graphql", "nextjs", "urql", "react"]
published: true
---

# はじめに

TypeScript 7.1 では、新機能として Content Mappers（コンテンツマッパー）が導入されました。

これまで TypeScript で GraphQL を扱う場合、以下のようなアプローチが一般的でした。

1. `*.d.ts` のアンビエント宣言: `declare module "*.graphql"` と記述して型を大まかに定義する
2. コードジェネレーターの事前実行: `graphql-codegen` を watch モードで動かし、物理的な TypeScript ファイル（`src/generated/graphql.ts` など）をディスクに出力してインポートする

しかし後者の方法では、「codegen の watch プロセスを常駐させる必要がある」「巨大な生成ファイルで Git 差分が肥大化する」「ファイルの生成が完了するまでエディタに型エラーが出る」といった煩わしさがありました。

TypeScript 7.1 の Content Mappers を使用すると、コンパイラが外部プロセスと連携してメモリ上でリアルタイムに TypeScript コードへ変換してくれるため、物理的な生成ファイルを作らずに `.graphql` ファイルを直接インポートして完全な型安全性を得ることができます。

本記事では、Next.js + Urql プロジェクトにおいて Content Mappers を TypeScript で自作し、`graphql-codegen` の静的ファイル出力なしで `.graphql` を直接インポートして実行する仕組みの全容を解説します。

---

# 完成した使い心地

https://github.com/SoraKumo001/next-graphql

まずは完成後のコードをご覧ください。

以下のように、`query.graphql` から直接クエリドキュメント（`TypedDocumentNode`）や Enum 定義を名前付きインポートして、Urql の `useQuery` や `useMutation` に渡すことができます。

```tsx:src/app/Home.tsx
"use client";

import { useMutation, useQuery } from "urql";
// 直接読める
import {
  BooksDocument,
  CategoriesDocument,
  CreateBookDocument,
  DeleteBookDocument,
  OrderBy,
  UpdateBookDocument,
} from "../../graphql/query.graphql";

export default function Home() {
  // BooksDocument は型付けされた TypedDocumentNode
  // data や variables の型が自動推論・検証される
  const [{ data, fetching }] = useQuery({
    query: BooksDocument,
    variables: {
      order: OrderBy.Asc,
    },
  });

  const [, createBook] = useMutation(CreateBookDocument);

  if (fetching) return <div>Loading...</div>;

  return (
    <div>
      {data?.books.map((book) => (
        <div key={book.id}>
          <span>{book.title}</span>
          <span>{book.category.name}</span>
        </div>
      ))}
    </div>
  );
}
```

`tsc --runExternalCode --noEmit` を実行するだけで、中間生成ファイルなしに `.graphql` のクエリと引数の型が厳密に検証されます。

VS Code 上でも以下のように型解決や補完が機能します。

![](/images/typescript7-content-mappers/2026-10-22-20-37-08.png)

---

# Content Mappers の仕組み

Content Mappers は、TypeScript コンパイラが未知の拡張子（`.graphql`, `.sql` など）に遭遇した際、指定された外部プロセスを JSON-RPC（stdio 経由）で起動し、仮想の TypeScript コードを受け取る仕組みです。

```
[tsc / Language Server]
        │
        │ JSON-RPC 2.0 (stdio)
        ▼
[graphql-content-mapper (外部プロセス)]
        │
        ├─ 1. initialize
        ├─ 2. openProject (プロジェクト設定の読込)
        ├─ 3. transform (query.graphql の内容を解析し、TypeScript コードを返却)
        └─ 4. closeProject
```

コンパイラはメモリ上で受け取った仮想の TypeScript コードをもとに型解決を行うため、ディスク上に `.ts` ファイルが書き出されることはありません。

:::message alert
外部プロセスが任意のコードを実行できるため、安全機能としてコンパイル時には `--runExternalCode` フラグの指定が必須となっています。
:::

---

# Content Mapper の実装

マッパー本体を TypeScript で実装します。構成は以下の通りです。

```
packages/graphql-content-mapper/
├── package.json
├── tsconfig.json
└── src/
    ├── index.ts    # JSON-RPC サーバー (TypeScript コンパイラ用)
    └── loader.ts   # Next.js 実行時用の Webpack/Turbopack ローダー
```

### 1. JSON-RPC ハンドラーの実装 (`src/index.ts`)

TypeScript コンパイラとは、Language Server Protocol と同様の `Content-Length: ...\r\n\r\n` 形式で JSON-RPC 2.0 のメッセージを送受信します。

```typescript:packages/graphql-content-mapper/src/index.ts
import * as fs from "node:fs";
import * as path from "node:path";
import process from "node:process";
import { Buffer } from "node:buffer";
import { parse, type DocumentNode, type OperationDefinitionNode } from "graphql";
import { executeCodegen } from "@graphql-codegen/cli";

interface JsonRpcRequest {
  jsonrpc?: string;
  id?: number | string;
  method: string;
  params?: any;
}

interface JsonRpcResponse {
  jsonrpc: "2.0";
  id: number | string;
  result?: any;
  error?: any;
}

interface TransformResult {
  text: string;
  extension: string;
  mappings: unknown[];
}

const originalStdoutWrite = process.stdout.write.bind(process.stdout);

// 内部ライブラリが stdout にログを出して JSON-RPC フレームが壊れるのを防止
process.stdout.write = ((chunk: any, encoding?: any, callback?: any): boolean => {
  if (typeof encoding === "function") encoding();
  else if (typeof callback === "function") callback();
  return true;
}) as any;

function send(response: JsonRpcResponse): void {
  const json = JSON.stringify(response);
  const len = Buffer.byteLength(json, "utf-8");
  const header = `Content-Length: ${len}\r\n\r\n`;
  originalStdoutWrite(header + json);
}

// stdio バッファから JSON-RPC メッセージを抽出
let buffer = Buffer.alloc(0);
process.stdin.on("data", (chunk: Buffer) => {
  buffer = Buffer.concat([buffer, chunk]);
  while (true) {
    const headerEnd = buffer.indexOf("\r\n\r\n");
    if (headerEnd === -1) break;

    const header = buffer.subarray(0, headerEnd).toString("utf-8");
    const match = header.match(/Content-Length:\s*(\d+)/i);
    if (!match) break;

    const contentLength = parseInt(match[1], 10);
    const bodyStart = headerEnd + 4;
    if (buffer.length < bodyStart + contentLength) break;

    const body = buffer.subarray(bodyStart, bodyStart + contentLength).toString("utf-8");
    buffer = buffer.subarray(bodyStart + contentLength);

    try {
      const msg: JsonRpcRequest = JSON.parse(body);
      handleMessage(msg);
    } catch {}
  }
});

// 重複する型宣言の除去
function deduplicateDeclarations(content: string): string {
  const lines = content.split("\n");
  const seen = new Set<string>();
  const cleaned: string[] = [];
  let skipping = false;
  let braceCount = 0;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (!skipping) {
      const match = line.match(/^export (?:type|enum)\s+(\w+)/);
      if (match) {
        const name = match[1];
        if (seen.has(name)) {
          skipping = true;
          braceCount = (line.match(/{/g) || []).length - (line.match(/}/g) || []).length;
          if (braceCount === 0 && line.trim().endsWith(";")) skipping = false;
          continue;
        } else {
          seen.add(name);
        }
      }
      cleaned.push(line);
    } else {
      braceCount += (line.match(/{/g) || []).length - (line.match(/}/g) || []).length;
      if (braceCount === 0 && line.trim().endsWith(";")) skipping = false;
    }
  }
  return cleaned.join("\n");
}

// GraphQL の変換処理
async function transformGraphQL(
  fileName: string,
  content: string,
  projectDir: string
): Promise<TransformResult> {
  if (fileName.endsWith("schema.graphql")) {
    return { text: "export {};", extension: ".ts", mappings: [] };
  }

  const schemaPath = path.join(projectDir, "graphql", "schema.graphql");
  if (!fs.existsSync(schemaPath)) {
    return { text: "export {};", extension: ".ts", mappings: [] };
  }

  try {
    const doc: DocumentNode = parse(content);

    // メモリ上で codegen コアを実行（物理ファイル出力なし）
    const codegenResult = await executeCodegen({
      schema: schemaPath,
      documents: fileName,
      generates: {
        "virtual.ts": {
          plugins: ["typescript", "typescript-operations"],
          config: {
            scalars: { DateTime: "string" },
            skipTypename: false,
          },
        },
      },
    });

    const rawGenerated = codegenResult?.result?.[0]?.content || "";
    const cleanGenerated = deduplicateDeclarations(rawGenerated);

    // OperationDefinition から TypedDocumentNode の export 定義を生成
    const operations = doc.definitions
      .filter((d): d is OperationDefinitionNode => d.kind === "OperationDefinition" && !!d.name)
      .map((d) => ({
        name: d.name!.value,
        op: d.operation.charAt(0).toUpperCase() + d.operation.slice(1),
      }));

    const docTypeDefinitions = `
import type { DocumentNode } from "graphql";

export interface TypedDocumentNode<
  Result = { [key: string]: any },
  Variables = { [key: string]: any },
> extends DocumentNode {
  __apiType?: (variables: Variables) => Result;
}
`;

    const docExports = operations
      .map((o) => {
        const varType = o.name + o.op + "Variables";
        const resType = o.name + o.op;
        return `export declare const ${o.name}: TypedDocumentNode<${resType}, ${varType}>;`;
      })
      .join("\n");

    const fullText = [docTypeDefinitions, cleanGenerated, docExports].join("\n\n");

    return {
      text: fullText,
      extension: ".ts",
      mappings: [],
    };
  } catch {
    return { text: "export {};", extension: ".ts", mappings: [] };
  }
}

const projectDirMap = new Map<unknown, string>();

async function handleMessage(msg: JsonRpcRequest): Promise<void> {
  if (msg.id === undefined) return;

  let result: any = null;
  switch (msg.method) {
    case "initialize":
      result = {
        positionEncoding: "utf-16",
        diagnosticSource: "graphql-content-mapper",
      };
      break;
    case "openProject":
      {
        const configPath: string | undefined = msg.params?.configFileName;
        const projectDir = configPath ? path.dirname(configPath) : process.cwd();
        projectDirMap.set(msg.params?.projectHandle, projectDir);
        result = {};
      }
      break;
    case "transform":
      {
        const projectDir = projectDirMap.get(msg.params?.projectHandle) || process.cwd();
        result = await transformGraphQL(msg.params?.fileName, msg.params?.content, projectDir);
      }
      break;
    case "closeProject":
      projectDirMap.delete(msg.params?.projectHandle);
      result = null;
      break;
    default:
      result = {};
  }

  send({ jsonrpc: "2.0", id: msg.id, result });
}
```

### 2. パッケージマニフェスト (`package.json`)

TypeScript にこのパッケージが Content Mapper であることを伝えるため、`package.json` に `"typescript.contentMapper"` フィールドを記述します。

```json:packages/graphql-content-mapper/package.json
{
  "name": "graphql-content-mapper",
  "version": "1.0.0",
  "main": "dist/index.js",
  "types": "dist/index.d.ts",
  "scripts": {
    "build": "tsc -p tsconfig.json"
  },
  "typescript": {
    "contentMapper": {
      "exec": [
        "node",
        "dist/index.js"
      ],
      "outputExtensions": {
        ".graphql": ".js"
      }
    }
  }
}
```

---

# Next.js 実行時のローダー設定

TypeScript 側は Content Mapper で型解決できますが、ブラウザ実行時（Next.js の Webpack / Turbopack）には `.graphql` ファイルを JavaScript としてバンドルできるようにする必要があります。

`graphql-tag/loader` をラップし、TypeScript 側で生成した Enum オブジェクトもランタイムにエクスポートするローダーを用意します。

```typescript:packages/graphql-content-mapper/src/loader.ts
import * as fs from "node:fs";
import * as path from "node:path";
import process from "node:process";
// @ts-expect-error graphql-tag/loader has no official types
import loader from "graphql-tag/loader";

export interface LoaderContext {
  cacheable?: () => void;
  [key: string]: any;
}

export default function graphqlContentMapperLoader(this: LoaderContext, source: string): string {
  if (this.cacheable) this.cacheable();
  const rawJs: string = loader.call(this, source);

  // schema.graphql から Enum を読み取ってランタイムの module.exports に付与
  try {
    const schemaPath = path.resolve(process.cwd(), "graphql/schema.graphql");
    if (fs.existsSync(schemaPath)) {
      const schemaText = fs.readFileSync(schemaPath, "utf-8");
      const enumMatches = [...schemaText.matchAll(/enum\s+(\w+)\s*\{([^}]+)\}/g)];
      let enumCode = "";
      for (const match of enumMatches) {
        const enumName = match[1];
        const values = match[2]
          .split("\n")
          .map((v: string) => v.trim())
          .filter((v: string) => v && !v.startsWith("#"));
        const objEntries = values.map((v: string) => `"${v}": "${v}"`).join(", ");
        enumCode += `\nmodule.exports["${enumName}"] = { ${objEntries} };\n`;
      }
      return rawJs + enumCode;
    }
  } catch {}

  return rawJs;
}

module.exports = graphqlContentMapperLoader;
```

`next.config.js` で Webpack と Turbopack の両方にこのローダーを登録します。

```javascript:next.config.js
const path = require("path");

const graphqlLoader = path.resolve(__dirname, "packages/graphql-content-mapper/dist/loader.js");

/** @type {import('next').NextConfig} */
const config = {
  serverExternalPackages: ["@whatwg-node"],
  typescript: {
    // Next.js 内蔵の型チェックは --runExternalCode なしで動作するためスキップし、
    // ビルドスクリプト側で npm run typecheck を実行する
    ignoreBuildErrors: true,
  },
  webpack: (config) => {
    config.module.rules.push({
      test: /\.(graphql|gql)$/,
      exclude: /node_modules/,
      loader: graphqlLoader,
    });
    return config;
  },
  turbopack: {
    rules: {
      "*.graphql": {
        loaders: [graphqlLoader],
        as: "*.js",
      },
    },
  },
};

module.exports = config;
```

---

# プロジェクト本体の設定

プロジェクトの `tsconfig.json` に `contentMappers` を追加し、`.graphql` ファイルを `include` に含めます。

```json:tsconfig.json
{
  "compilerOptions": {
    "module": "ESNext",
    "moduleResolution": "bundler",
    "rewriteRelativeImportExtensions": true,
    "strict": true
    // ... その他の設定
  },
  "contentMappers": [
    {
      "package": "graphql-content-mapper",
      "extensions": [".graphql"]
    }
  ],
  "include": [
    "next-env.d.ts",
    "**/*.ts",
    "**/*.tsx",
    "graphql/query.graphql"
  ]
}
```

ルートの `package.json` にスクリプトを定義します。

```json:package.json
{
  "scripts": {
    "build:mapper": "tsc -p packages/graphql-content-mapper/tsconfig.json",
    "typecheck": "npm run build:mapper && tsc --runExternalCode --noEmit",
    "build": "npm run build:mapper && prisma generate && npm run typecheck && next build"
  }
}
```

`npm run typecheck` を実行すると、コード生成コマンドを別途叩くことなく、`.graphql` ファイルの内容に合わせた完全な型チェックが行われます。

---

# VS Code エディタでの動作と設定

### TypeScript 7 系とネイティブ刷新の背景

TypeScript 7.1 は内部アーキテクチャが Go/C++ ネイティブ（`tsc.exe`）および LSP（Language Server Protocol）に刷新されています。

そのため、従来の VS Code 組み込み TypeScript（TS 5.x〜6.x 系）が探す `node_modules/typescript/lib/tsserver.js` が存在せず、そのままでは VS Code 上で「ワークスペースのバージョンを読み込めません」というエラーになります。

### VS Code で Content Mappers を動かす設定

Microsoft 公式が提供しているネイティブ対応の拡張機能 `TypeScript 7`（`TypeScriptTeam.native-preview`）をインストールします。

プロジェクトの `.vscode/settings.json` に以下を設定します。

```json:.vscode/settings.json
{
  "js/ts.tsdk.path": "node_modules/typescript",
  "js/ts.tsdk.additionalLocations": [
    "node_modules/typescript"
  ],
  "js/ts.contentMappers.enabled": true
}
```

設定後、以下の手順でワークスペースの TypeScript を切り替えます。

1. ステータスバーの `TypeScript Language Server` をクリック（またはコマンドパレットから `TypeScript: Select Version...` を実行）
2. `Use Custom Version`（`7.1.0-beta` - `node_modules/typescript`）を選択

これでエディタ上でも Content Mapper がリアルタイムに動作し、`.graphql` ファイルからインポートした変数やドキュメントに補完・型ホバーが表示されるようになります。

---

# まとめ

TypeScript 7.1 の Content Mappers により、以下のようなメリットが得られます。

- ファイルレスな型安全性: `graphql-codegen` による物理ファイルの出力が不要になり、Git 差分やリポジトリをクリーンに保てる
- 自動同期: `.graphql` ファイルを編集して保存した瞬間、再ビルドや watch コマンドの待機なしに最新の型が即座に反映される
- 既存エコシステムとの統合: `TypedDocumentNode` を動的エクスポートすることで、Urql や Apollo Client などの GraphQL クライアントでそのまま型推論が効く

GraphQL と TypeScript の開発体験を大きく向上させる機能です。ぜひ試してみてください。
