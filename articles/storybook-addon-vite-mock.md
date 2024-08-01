---
title: "Storybook + Vite + React のインタラクションテストでモジュールモックする"
emoji: "📌"
type: "tech" # tech: 技術記事 / idea:  アイデア
topics: [vite, react, typescript, storybook, jest]
published: true
---

# `@storybook/nextjs`使用時のインタラクションテストとモジュールモック

Storybook でインタラクションテストを使用すると、コンポーネントの動作を GUI で確認しつつテストを書くことが出来ます。Jest や Vitest の CUI 上で表示確認無しでテストを書くのに比べると、圧倒的に楽にテストを書くことが可能です。ただし問題があって、Jest や Vitest から専用コマンドでテストを呼び出すときには、依存パッケージなどを関数単位で簡単にモック化できますが、Storybook のインタラクションテストではそうではありません。以下のようなファイル単位でのモックが必要となります。

https://storybook.js.org/blog/type-safe-module-mocking/

関数単位でのモック作成は、以前に`@storybook/nextjs`用に Webpack と Babel の挙動をカスタマイズして[storybook-addon-module-mock](https://www.npmjs.com/package/storybook-addon-module-mock)を作りました。これを使えば import した外部モジュール内の関数をモック化することが可能です。[公式ドキュメント](https://storybook.js.org/docs/get-started/nextjs#react-server-components-rsc)にも紹介されています。ただし、Webpack の使用が必須となるため、Vite を使用している場合は使用できません。

# `@storybook/react-vite`使用時のインタラクションテストとモジュールモック

`@storybook/react-vite`はその名の通り Vite を経由してモジュールバンドルが行われます。ということで今回、Vite 使用時にモジュールをモックするため以下のものを開発しました。

https://www.npmjs.com/package/storybook-addon-vite-mock

Vite の挙動をカスタマイズし、外部モジュールの関数をモック化することが可能となります。

# モジュールモックの原理

モジュールモックを作るためには export する直前の function に割り込んで、オリジナル関数とカスタム関数を切り替える必要があります。それを実現するため、Vite の Plugin を作成し、そこから`transform`を使ってコードを変換することが可能です。`transform`はモジュールの内容を変換するための関数で、`transform`関数内で JavaScript の AST を解析し、`export`する直前の関数を探し出し、切り替える機能を割り込ませます。原理は簡単なのですが、変換対象のコードは ESM や CJS、export の書き方など様々なパターンがあるため、実装は控えめに言って地獄でした。一応 Storybook から使用することを前提に作って入るのですが、Vite の Plugin として独立させても良いかもしれません。ただ、用途が思いつきません。

# Storybook の Addon としての実装

Vite 用 Plugin で割り込み処理を書いたら、次は Storybook の Addon 作成です。インタラクションテストから簡単に割り込めるように、モックの切り替え機能を実装します。このあたりの処理はかなりの部分を[storybook-addon-module-mock](https://www.npmjs.com/package/storybook-addon-module-mock)から持ってきたので、実装の手間をかなり省くことが出来ました。

# Addon の組み込み方

`@storybook/react-vite`を使用している場合、`storybook-addon-vite-mock`をインストールします。その後、`.storybook/main.js`に以下の設定を追加します。

- .storybook/main.ts の例

options は指定しなくても動作します。debugPath は指定すると、変換状態を確認するためのファイルが出力されます。

```js
/** @type { import('@storybook/react-vite').StorybookConfig } */
const config = {
  stories: [
    "../stories/**/*.mdx",
    "../stories/**/*.stories.@(js|jsx|mjs|ts|tsx)",
  ],
  addons: [
    "@storybook/addon-onboarding",
    "@storybook/addon-links",
    "@storybook/addon-essentials",
    "@chromatic-com/storybook",
    "@storybook/addon-interactions",
    "@storybook/addon-coverage",
    {
      name: "storybook-addon-vite-mock",
      options: {
        exclude: ({ id }) => id.includes(".stories."),
        // debugPath: "tmp",
      },
    },
  ],
  build: {
    test: {
      disabledAddons: [],
    },
  },
  framework: {
    name: "@storybook/react-vite",
  },
  docs: {
    autodocs: "tag",
  },
};
export default config;
```

# サンプルソース

https://github.com/SoraKumo001/storybook-addon-vite-mock-test

## 関数の呼び出しパラメータのフック

login 関数をモック化して、引数を確認するのに使用しています。

- login.ts

```ts
export default (_user: string, _name: string) => {
  //
};
```

- FormMock.tsx

```tsx
import React, { FC } from "react";
import login from "./login";

interface Props {}

/**
 * FormMock
 *
 * @param {Props} { }
 */
export const FormMock: FC<Props> = ({}) => {
  const handleSubmit: React.FormEventHandler<HTMLFormElement> = (e) => {
    e.preventDefault();
    login(e.currentTarget["user"].value, e.currentTarget["password"].value);
  };

  return (
    <div>
      <form onSubmit={handleSubmit}>
        <label>
          User:
          <input
            type="text"
            name="user"
            data-testid="testid"
            placeholder="User ID"
          />
        </label>
        <label>
          Password:
          <input
            type="password"
            name="password"
            aria-label="password"
            placeholder="Password"
          />
        </label>
        <button type="submit">Submit</button>
      </form>
    </div>
  );
};
```

- FormMock.stories.tsx

```tsx
import { Meta, StoryObj } from "@storybook/react";
import { expect, userEvent, within } from "@storybook/test";
import { createMock, getMock } from "storybook-addon-vite-mock";
import { FormMock } from "./FormMock";
import login from "./login";

const meta: Meta<typeof FormMock> = {
  tags: ["autodocs"],
  component: FormMock,
  parameters: {},
  args: {},
};
export default meta;

export const Primary: StoryObj<typeof FormMock> = {};

export const Submit: StoryObj<typeof FormMock> = {
  args: {},
  parameters: {
    moduleMock: {
      mock: () => {
        const mock = createMock(login);
        return mock;
      },
    },
  },
  play: async ({ canvasElement, parameters }) => {
    const mock = getMock(parameters, login);
    const canvas = within(canvasElement);
    const userInput = await canvas.findByLabelText("User:");
    const passwordInput = await canvas.findByLabelText("Password:");
    await userEvent.type(userInput, "User");
    await userEvent.type(passwordInput, "Password");
    await userEvent.click(await canvas.findByText("Submit"));
    expect(mock.mock.lastCall).toStrictEqual(["User", "Password"]);
  },
};
```

## 戻り値の変更

- message.ts

getMessage 関数をモック化して、戻り値を変更しています。

```ts
export const getMessage = () => {
  return "Before";
};
```

- LibHook.tsx

```tsx
import React, { FC, useState } from "react";
import { getMessage } from "./message";

interface Props {}

/**
 * LibHook
 *
 * @param {Props} { }
 */
export const LibHook: FC<Props> = ({}) => {
  const [, reload] = useState({});
  const value = getMessage();
  return (
    <div>
      <button onClick={() => reload({})}>{value}</button>
    </div>
  );
};
```

- LibHook.stories.tsx

```tsx
import { Meta, StoryObj } from "@storybook/react";
import { expect, userEvent, waitFor, within } from "@storybook/test";
import { createMock, getMock } from "storybook-addon-vite-mock";
import { LibHook } from "./LibHook";
import { getMessage } from "./message";

const meta: Meta<typeof LibHook> = {
  component: LibHook,
};
export default meta;

export const Primary: StoryObj<typeof LibHook> = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    expect(canvas.getByText("Before")).toBeInTheDocument();
  },
};

export const Mock: StoryObj<typeof LibHook> = {
  parameters: {
    moduleMock: {
      mock: () => {
        const mock = createMock(getMessage);
        mock.mockReturnValue("After");
        return [mock];
      },
    },
  },
  play: async ({ canvasElement, parameters }) => {
    const canvas = within(canvasElement);
    expect(canvas.getByText("After")).toBeInTheDocument();
    const mock = getMock(parameters, getMessage);
    expect(mock).toBeCalled();
  },
};

export const Action: StoryObj<typeof LibHook> = {
  parameters: {
    moduleMock: {
      mock: () => {
        const mock = createMock(getMessage);
        return [mock];
      },
    },
  },
  play: async ({ canvasElement, parameters }) => {
    const canvas = within(canvasElement);
    const mock = getMock(parameters, getMessage);
    mock.mockReturnValue("Action");
    userEvent.click(await canvas.findByRole("button"));
    await waitFor(() => {
      expect(canvas.getByText("Action")).toBeInTheDocument();
    });
  },
};
```

## モックのリセット

- action.ts

テストの途中でいったんモックのリセットを行っています。

```ts
export const action1 = () => {
  //
};
export const action2 = () => {
  //
};
```

- MockReset.tsx

```tsx
import React, { FC } from "react";
import { action1, action2 } from "./action";

interface Props {}

/**
 * MockReset
 *
 * @param {Props} { }
 */
export const MockReset: FC<Props> = ({}) => {
  return (
    <div>
      <button onClick={action1}>Button1</button>
      <button onClick={action2}>Button2</button>
    </div>
  );
};
```

- MockReset.stories.tsx

```tsx
import { Meta, StoryObj } from "@storybook/react";
import { expect, userEvent, waitFor, within } from "@storybook/test";
import { createMock, getMock, resetMock } from "storybook-addon-vite-mock";
import { action1, action2 } from "./action";
import { MockReset } from "./MockReset";

const meta: Meta<typeof MockReset> = {
  component: MockReset,
};
export default meta;

export const Primary: StoryObj<typeof MockReset> = {
  parameters: {
    moduleMock: {
      mock: () => {
        // The mock to be used is created here
        const mock1 = createMock(action1);
        const mock2 = createMock(action2);
        return [mock1, mock2];
      },
    },
  },
  play: async ({ canvasElement, parameters }) => {
    const mock1 = getMock(parameters, action1);
    const mock2 = getMock(parameters, action2);

    const canvas = within(canvasElement);
    await waitFor(() => {
      expect(mock1).not.toBeCalled();
      expect(mock2).not.toBeCalled();
    });
    userEvent.click(await canvas.findByText("Button1"));
    await waitFor(() => {
      expect(mock1).toBeCalled();
      expect(mock2).not.toBeCalled();
    });

    // Reset all mock
    resetMock(parameters);
    await waitFor(() => {
      expect(mock1).not.toBeCalled();
      expect(mock2).not.toBeCalled();
    });

    userEvent.click(await canvas.findByText("Button2"));
    await waitFor(() => {
      expect(mock1).not.toBeCalled();
      expect(mock2).toBeCalled();
    });
  },
};
```

## useMemo への割り込み

React の useMemo をモック化して、戻り値を変更しています。ただ、useMemo は他のコンポーネントにも影響するので、こういう使い方は注意が必要です。

- MockTest.tsx

```tsx
import React, { FC, useMemo, useState } from "react";
interface Props {}

/**
 * MockTest
 *
 * @param {Props} { }
 */
export const MockTest: FC<Props> = ({}) => {
  const [, reload] = useState({});
  const value = useMemo(() => {
    return "Before";
  }, []);
  return (
    <div>
      <button onClick={() => reload({})}>{value}</button>
    </div>
  );
};
```

- MockTest.stories.tsx

```tsx
import { Meta, StoryObj } from "@storybook/react";
import { expect, userEvent, waitFor, within } from "@storybook/test";
import { DependencyList, useMemo } from "react";
import { createMock, getMock, getOriginal } from "storybook-addon-vite-mock";
import { MockTest } from "./MockTest";

const meta: Meta<typeof MockTest> = {
  component: MockTest,
};
export default meta;

export const Primary: StoryObj<typeof MockTest> = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    expect(canvas.getByText("Before")).toBeInTheDocument();
  },
};

export const Mock: StoryObj<typeof MockTest> = {
  parameters: {
    moduleMock: {
      mock: () => {
        const mock = createMock(useMemo);
        mock.mockImplementation((fn: () => unknown, deps: DependencyList) => {
          const value = getOriginal(useMemo)(fn, deps);
          return value === "Before" ? "After" : value;
        });
        return [mock];
      },
    },
  },
  play: async ({ canvasElement, parameters }) => {
    const canvas = within(canvasElement);
    expect(canvas.getByText("After")).toBeInTheDocument();
    const mock = getMock(parameters, useMemo);
    expect(mock).toBeCalled();
  },
};

export const Action: StoryObj<typeof MockTest> = {
  parameters: {
    moduleMock: {
      mock: () => {
        const mock = createMock(useMemo);
        mock.mockImplementation(getOriginal(useMemo));
        return [mock];
      },
    },
  },
  play: async ({ canvasElement, parameters }) => {
    const canvas = within(canvasElement);
    const mock = getMock(parameters, useMemo);
    mock.mockImplementation((fn: () => unknown, deps: DependencyList) => {
      const value = getOriginal(useMemo)(fn, deps);
      return value === "Before" ? "Action" : value;
    });
    userEvent.click(await canvas.findByRole("button"));
    await waitFor(() => {
      expect(canvas.getByText("Action")).toBeInTheDocument();
    });
  },
};
```

## 強制再描画

インタラクションテスト中にコンポーネントを強制再描画します

- message.ts

```tsx
export const getMessage = () => {
  return "Before";
};
```

- ReRender.tsx

```tsx
import React, { FC } from "react";
import { getMessage } from "./message";

interface Props {}

/**
 * ReRender
 *
 * @param {Props} { }
 */
export const ReRender: FC<Props> = ({}) => {
  const value = getMessage();
  return <div>{value}</div>;
};
```

- ReRender.stories.tsx

```tsx
import { Meta, StoryObj } from "@storybook/react";
import { expect, waitFor, within } from "@storybook/test";
import { createMock, getMock, render } from "storybook-addon-vite-mock";
import { getMessage } from "./message";
import { ReRender } from "./ReRender";

const meta: Meta<typeof ReRender> = {
  component: ReRender,
};
export default meta;

export const Primary: StoryObj<typeof ReRender> = {};

export const ReRenderTest: StoryObj<typeof ReRender> = {
  parameters: {
    moduleMock: {
      mock: () => {
        const mock = createMock(getMessage);
        return [mock];
      },
    },
  },
  play: async ({ canvasElement, parameters }) => {
    const canvas = within(canvasElement);
    const mock = getMock(parameters, getMessage);
    mock.mockReturnValue("Test1");
    render(parameters);
    await waitFor(() => {
      expect(canvas.getByText("Test1")).toBeInTheDocument();
    });
    mock.mockReturnValue("Test2");
    render(parameters);
    await waitFor(() => {
      expect(canvas.getByText("Test2")).toBeInTheDocument();
    });
  },
};
```

## 引数を設定してコンポーネントを再描画

コンポーネントを再描画する際に引数を設定して再描画します。

- ReRenderArgs.tsx

```tsx
import React, { FC } from "react";
import styled from "./ReRenderArgs.module.scss";

interface Props {
  value: string;
}

/**
 * ReRenderArgs
 *
 * @param {Props} { value: string }
 */
export const ReRenderArgs: FC<Props> = ({ value }) => {
  return <div className={styled.root}>{value}</div>;
};
```

- ReRenderArgs.stories.tsx

```tsx
import { Meta, StoryObj } from "@storybook/react";
import { expect, waitFor, within } from "@storybook/test";
import { render } from "storybook-addon-vite-mock";
import { ReRenderArgs } from "./ReRenderArgs";

const meta: Meta<typeof ReRenderArgs> = {
  component: ReRenderArgs,
  args: { value: "Test" },
};
export default meta;

export const Primary: StoryObj<typeof ReRenderArgs> = {
  args: {},
  play: async ({ canvasElement, parameters, step }) => {
    const canvas = within(canvasElement);

    await step("first props", async () => {
      expect(canvas.getByText("Test")).toBeInTheDocument();
    });

    await step("Re-render with new props", async () => {
      // Re-render with new props
      render(parameters, { value: "Test2" });
      await waitFor(() => {
        expect(canvas.getByText("Test2")).toBeInTheDocument();
      });

      // Re-render with new props
      render(parameters, { value: "Test3" });
      await waitFor(() => {
        expect(canvas.getByText("Test3")).toBeInTheDocument();
      });

      // Re-render with new props
      render(parameters, { value: "Test4" });
      await waitFor(() => {
        expect(canvas.getByText("Test4")).toBeInTheDocument();
      });
    });
  },
};
```

# まとめ

Storybook + Vite のインタラクション環境下で import した関数のモックが可能になりました。これでテストを書くのが容易になります。
