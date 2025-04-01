---
title: "Ollamaで実装する無料 MCP Agent"
emoji: "🦁"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [openai, ollama, llm, typescript, mcp]
published: true
---

# ローカル MCP Agent の作成

今回は Ollama を経由してローカル LLM で、MCP Agent を動作させます。API は OpenAI 互換のものを使っています。この構成なら開発時には電気代以外の費用がかからないというメリットがあります。

- 今回のサンプルコードと動作画面

https://github.com/SoraKumo001/mcp-agent
![](/images/ollama-mcp-agent/2025-03-31-14-32-29.webp)

# カスタム Transport を作って、McpServer を直接 McpClient に接続する

MCP のやり取りで`@modelcontextprotocol/sdk`を使った場合、McpServer を McpClient で扱うには、標準だと stdio,websocket,http を経由する Transport しか用意されていません。別プロセスにしたり、WebServer を立ち上げたりすると開発が面倒になるので、カスタムの Transport を作成して、直接やりとりをガッチンコさせます。

- libs/direct-transport.ts

```ts
import type { Transport } from "@modelcontextprotocol/sdk/shared/transport.js";
import type { JSONRPCMessage } from "@modelcontextprotocol/sdk/types.js";

class DirectClientTransport implements Transport {
  onclose?: () => void;
  onmessage?: (message: JSONRPCMessage) => void;
  constructor(private serverTransport: Transport) {}
  async start() {}
  async close() {}
  async send(message: JSONRPCMessage) {
    this.serverTransport.onmessage?.(message);
  }
}

export class DirectServerTransport implements Transport {
  onclose?: () => void;
  onmessage?: (message: JSONRPCMessage) => void;
  clientTransport: DirectClientTransport;
  constructor() {
    this.clientTransport = new DirectClientTransport(this);
  }
  async start() {}
  async close() {}
  async send(message: JSONRPCMessage) {
    this.clientTransport.onmessage?.(message);
  }
  getClientTransport() {
    return this.clientTransport;
  }
}
```

# MCP Server を作成

現在の時刻を返す McpServer と指定した地点の天気予報を返す McpServer を作成します。

- mcp-servers/get-current-time.ts

時間を返すだけです

```ts
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";

const server = new McpServer({
  name: "時間表示サーバー",
  version: "1.0.0",
});

server.tool("get-current-time", "現在の時刻を返す", async () => {
  return {
    content: [
      {
        type: "text",
        text: new Date().toLocaleString("ja-JP", {
          year: "numeric",
          month: "long",
          day: "numeric",
          weekday: "long",
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        }),
      },
    ],
  };
});

export const TimeServer = server;
```

- mcp-servers/get-weather.ts

気象庁のサイトから天気情報の文章を取得します

```ts
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

interface Center {
  name: string;
  enName: string;
  officeName?: string;
  children?: string[];
  parent?: string;
  kana?: string;
}
interface Centers {
  [key: string]: Center;
}
interface Area {
  centers: Centers;
  offices: Centers;
  class10s: Centers;
  class15s: Centers;
  class20s: Centers;
}

interface Weather {
  publishingOffice: string;
  reportDatetime: Date;
  targetArea: string;
  headlineText: string;
  text: string;
}

const server = new McpServer({
  name: "天気予報サーバー",
  version: "1.0.0",
});

server.tool(
  "get-weather",
  `指定した都道府県の天気予報を返す`,
  {
    name: z.string({
      description: "都道府県名の漢字、例「東京」",
    }),
  },
  async ({ name: areaName }) => {
    const result = await fetch(
      "https://www.jma.go.jp/bosai/common/const/area.json"
    )
      .then((v) => v.json())
      .then((v: Area) => v.offices)
      .then((v: Centers) =>
        Object.entries(v).flatMap(([id, { name }]) =>
          name.includes(areaName) ? [id] : []
        )
      );
    const weathers = await Promise.all(
      result.map((id) =>
        fetch(
          `https://www.jma.go.jp/bosai/forecast/data/overview_forecast/${id}.json`
        )
          .then((v) => v.json())
          .then((v: Weather) => v.text)
      )
    );
    return {
      content: [
        {
          type: "text",
          text: weathers.join("---"),
        },
      ],
    };
  }
);

export const WeatherServer = server;
```

# MCP Agent の作成

MCP Agent で必要なのは、McpServer からツール情報を収集する部分です。`getMcpTools`で McpClient を作成し、McpServer と接続してツールを取り出しています。

次に、取り出したツールを`openai.chat.completions.create`で渡して、応答するために必要なツールの呼び出しを列挙させます。`content.message.tool_calls`に入っている情報に基づいて、`mcp.callTool`を呼び出します。

ツールの実行結果を message に格納したら、`openai.chat.completions.create`で再度応答を生成します。

ときどき、頓珍漢な応答が生成されるので、結果の正当性を確認してダメそうならリトライするような構造も必要そうです。

Ollama でエージェントに使う LLM を探すときは、`tools`のタグがついているものが必要になります。また、tools 対応でも LLM によって、ツール利用の失敗率が異常に高いものがあるので、最適なものを探してくる必要があります。

- index.ts

```ts
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import OpenAI from "openai";
import { DirectServerTransport } from "./libs/direct-transport.js";
import { TimeServer } from "./mcp-servers/get-current-time.js";
import { WeatherServer } from "./mcp-servers/get-weather.js";

import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type {
  ChatCompletionContentPartText,
  ChatCompletionMessageParam,
  ChatCompletionTool,
} from "openai/resources.mjs";

const getMcpTools = async (servers: McpServer[]) => {
  const tools: ChatCompletionTool[] = [];
  const functionMap: Record<string, Client> = {};
  const clients: Client[] = [];
  for (const server of servers) {
    const mcpClient = new Client({
      name: "mcp-client-cli",
      version: "1.0.0",
    });
    // Connecting McpServer directly to McpClient
    const transport = new DirectServerTransport();
    server.connect(transport);
    await mcpClient.connect(transport.getClientTransport());

    clients.push(mcpClient);
    const toolsResult = await mcpClient.listTools();
    tools.push(
      ...toolsResult.tools.map((tool): ChatCompletionTool => {
        functionMap[tool.name] = mcpClient;
        return {
          type: "function",
          function: {
            name: tool.name,
            description: tool.description,
            parameters: tool.inputSchema,
          },
        };
      })
    );
  }
  const close = () => {
    return Promise.all(
      clients.map(async (v) => {
        await v.close();
      })
    );
  };
  return { tools, functionMap, close };
};

const query = async (
  openai: OpenAI,
  model: string,
  mcpTools: Awaited<ReturnType<typeof getMcpTools>>,
  query: string
) => {
  console.log(`\n[question] ${query}`);
  const messages: ChatCompletionMessageParam[] = [
    {
      role: "system",
      content: "日本語を使用する,タグを出力しない,plain/textで回答する",
    },
    {
      role: "user",
      content: query,
    },
  ];

  const response = await openai.chat.completions.create({
    model,
    messages: messages,
    tools: mcpTools.tools,
  });

  for (const content of response.choices) {
    if (content.finish_reason === "tool_calls" && content.message.tool_calls) {
      await Promise.all(
        content.message.tool_calls.map(async (toolCall) => {
          const toolName = toolCall.function.name;
          const toolArgs = toolCall.function.arguments;
          const mcp = mcpTools.functionMap[toolName];
          console.info(`[tool] ${toolName} ${toolArgs}`);
          if (!mcp) {
            throw new Error(`Tool ${toolName} not found`);
          }

          const toolResult = await mcp.callTool({
            name: toolName,
            arguments: JSON.parse(toolArgs),
          });
          messages.push({
            role: "tool",
            tool_call_id: toolCall.id,
            content: toolResult.content as Array<ChatCompletionContentPartText>,
          });
        })
      );

      const response = await openai.chat.completions.create({
        model,
        messages,
        max_completion_tokens: 512,
        stream: true,
      });
      console.log("[answer]");
      for await (const message of response) {
        process.stdout.write(message.choices[0].delta.content!);
      }
      console.log();
    } else {
      console.log(content.message.content);
    }
  }
};

async function main() {
  const openai = new OpenAI({
    baseURL: "http://localhost:11434/v1",
    apiKey: "ollama",
  });
  const mcpTools = await getMcpTools([TimeServer, WeatherServer]);
  const model = "qwen2.5-coder:14b";
  await query(openai, model, mcpTools, "東京の天気は？");
  await query(openai, model, mcpTools, "今日の青森と千葉の天気は？");
  await query(openai, model, mcpTools, "今日は何曜日？");
  await mcpTools.close();
}

main();
```

# 実行結果

- 正常応答

```txt
[question] 東京の天気は？
[tool] get-weather {"name":"東京"}
[answer]
現在、東京は曇っているようですね。

31日にかけては、たまに雨が降る可能性がありますから、傘を忘れないでくださいね。

また、4月1日には、伊豆諸島を中心に雨か雪が降る予定なので、そこの場合は特に注意が必要です。

[question] 今日の青森と千葉の天気は？
[tool] get-weather {"name":"青森"}
[tool] get-weather {"name":"千葉"}
[answer]
青森県は、曇りや晴れで、雪が降っている所があります。31日には雨が降る可能性があり、4月1日には晴れですが、午後は曇りになる見込みです。

千葉県は、曇りで雨が降っている所があります。31日には曇りと雨が続く可能性あり、4月1日には雨となる見込みです。また、千葉県の太平洋沿岸では、31日には波が高いので注意が必要です。

[question] 今日は何曜日？
[tool] get-current-time {}
[answer]
月曜日
```

- 正常応答

```txt
[question] 東京の天気は？
[tool] get-weather {"name":"東京"}
[answer]
東京現在の天気は曇りです。

31日に高気圧の影响を受けますが、気圧の谷や湿った空気の影響があり、昼過ぎから雨が降る可能性があります。

4月1日には、千島に中心持つ高気圧が北東へ移動し、雨となるでしょう。伊豆諸島では雷を伴う雨が降る可能性も高いため、外出する際は予防が必要です。

関東甲信地方全体では、曇りや晴れで、雨や雪の降る所もあります。海上では、31日は波が高い、4月1日はしけるため船舶注意が必要です。

[question] 今日の青森と千葉の天気は？
[tool] get-weather {"name":"青森"}
[tool] get-weather {"name":"千葉"}
[answer]
青森県：
- 今日：曇りや晴れ、雪の降っている所がある
- 明日：晴れますが、午後よりは曇りとなる可能性あり

千葉県：
- 今日：曇りで雨が降っている所がある
- 明日：雨となる見込み

[question] 今日は何曜日？
[tool] get-current-time {}
[answer]
今日は月曜日です。
```

- ツールの呼び出しの内容が、なぜか content 側に出てしまう

```txt
[question] 東京の天気は？
[tool] get-weather {"name":"東京"}
[answer]
現在、東京の天気は曇りしています。

31日には、曇りで昼過ぎから雨が降る可能性があります。

4月1日には、千島の東側に中心を持つ高気圧が移動すると予想され、結果として雨となるでしょう。伊豆諸島では雷を伴う雨も考えられます。

[question] 今日の青森と千葉の天気は？
[tool] get-weather {"name":"青森"}
[tool] get-weather {"name":"千葉"}
[answer]
青森県と千葉県の天気予報は以下の通りです：

### 青森県
- **31日**: 高気圧に覆われているため、晴れや曂りですが、昼前まで雪の降る可能性があります。
- **4月1日**: 高気圧に覆われたため、午後は曇りとなる見込みです。

### 千葉県
- **31日**: 気圧の谷や湿った空気の影響を受けるため、曇りで雨が降る所があるでしょう。
- **4月1日**: 千島の東に中心を持つ高気圧が北東へ移動し、雨となる見込みです。

千葉県の太平洋沿岸の海上では：
- **31日**: うねりを伴い、波が高い可能性があります。
- **4月1日**: うねりを伴いしけとなる見込みです。船舶は高波に注意してください。

[question] 今日は何曜日？
{
  "name": "get-current-time",
  "arguments": null
}
```

# まとめ

これから、さまざまなサービスで API が McpServer 化される機会が増えてくると思います。そのお鉢が自分に回ってきたときに、ローカルでサクッと動作確認ができる環境を用意しておくと便利です。
