---
title: "React 用 Markdown エディタと unified の Plugin 作成"
emoji: "👻"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [react, markdown, unified, typescript, nextjs]
published: true
---

# React での Markdown エディタの実装

テキストエディット部分には Monaco エディタ、Markdown パーサには unified を使用します。その際に必要になる Plugin の作り方も合わせて紹介します。

※ 今回の記事で使用しているソースコード

- Next.js 板  
  https://github.com/SoraKumo001/next-unified
- React Router 板
  https://github.com/SoraKumo001/react-router-markdown

![](/images/markdown-react/capture.webp)

# unified を扱う上で知っておいたほうが良いこと

## unified に関して

- 特定の文書フォーマットを抽象構文木（AST）で扱うためのライブラリ
- プラグインによって拡張していく
- 単体では動作しない

## Markdown 変換 AST の流れ

| フェーズ    | 処理内容                     | プラグイン    | ベースライブラリ         |
| ----------- | ---------------------------- | ------------- | ------------------------ |
| Parser      | Markdown を AST に変換       | remark-parse  | mdast                    |
| Transformer | HTML の構造に近い AST に変換 | remark-rehype | hast                     |
| Compiler    | ReactComponent に変換        | rehype-react  | hast-util-to-jsx-runtime |

mdast と hast に関してはプラグインが呼び出すため、直接使用することはありませんが、プラグインを作成するときに TypeScript の型情報が必要になるため、`@types/mdast`や`@types/hast`が必要になります。

# unified を使う最低限の記述

最低限の実装は以下のようになります。`rehype-react`は`react/jsx-runtime`のインスタンスを必要とするので注意してください。

```ts
import prod from "react/jsx-runtime";
import rehypeReact from "rehype-react";
import remarkParse from "remark-parse";
import remarkRehype from "remark-rehype";
import { unified } from "unified";

export const markdownConverter = unified()
  // MDAST(マークダウンASTに変換)
  .use(remarkParse)
  // HAST(HTML用のASTに変換)
  .use(remarkRehype)
  // Reactコンポーネントに変換
  .use(rehypeReact, {
    ...prod,
  })
  .processSync("markdown");
```

## 記事の有効性判別

駄目なパターンは旧バージョンの書き方なので、検索などで引っ掛けてしまった場合はスルーしてください

- 有効なパターン

```ts
import { unified } from "unified";
```

- 駄目なパターン

```ts
import unified from "unified";
```

# unified をカスタマイズして使う

## 基本部分

適宜プラグインを追加して動作をカスタマイズします。ここで注意点があります

- remark 系:`remark-parse`が変換した mdast の AST を扱う
- rehype 系:`remark-rehype`が変換した hast の AST を扱う

プラグインで AST を扱う時、最初は汎用的な文章フォーマット用の AST だったのが、途中で HTML に近い AST に変換されます。そのため、プラグインを組み込み順序に注意が必要になります。

追加で`compilerResultTree`というプラグインを入れています。変換最終段階で`rehype-react`が React ノードを出力するのですが、この部分を細工して MastRoot の情報も出力させています。これによってヘッダ項目の一覧を取り出し様な、柔軟なデータ利用が可能になります。

```tsx
import rehypeRaw from "rehype-raw";
import rehypeReact from "rehype-react";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";
import remarkParse from "remark-parse";
import remarkRehype from "remark-rehype";
import { unified, type Processor } from "unified";
import { compilerResultTree } from "./plugins/compilerResultTree";
import { rehypeAddLineNumber } from "./plugins/rehypeAddLineNumber";
import { rehypeAddTargetBlank } from "./plugins/rehypeAddTargetBlank";
import { rehypeReactOptions } from "./plugins/rehypeReactOptions";
import { remarkCode } from "./plugins/remarkCode";
import { remarkDepth } from "./plugins/remarkDepth";
import { remarkEmptyParagraphs } from "./plugins/remarkEmptyParagraphs";
import { remarkHeadingId } from "./plugins/remarkHeadingId";
import type { Root } from "mdast";
import type { ReactNode } from "react";

export const markdownCompiler: Processor<
  undefined,
  undefined,
  undefined,
  undefined,
  [ReactNode, Root]
> = unified()
  // MDAST(マークダウンASTに変換)
  .use(remarkParse)
  // 表やテキスト中のリンクなど変換を追加
  .use(remarkGfm)
  // 段落内の改行を有効に
  .use(remarkBreaks)
  // 空行を復元
  .use(remarkEmptyParagraphs)
  // ヘッダにIDとリンクを付ける
  .use(remarkHeadingId)
  // コードブロックに追加情報を加える
  .use(remarkCode)
  // ノードに対してヘッダーに対応するインデント用の深度情報を与える
  .use(remarkDepth)
  // HAST(HTML用のASTに変換)
  .use(remarkRehype, {
    allowDangerousHtml: true,
  })
  // ノードに対して行番号情報を付与
  .use(rehypeAddLineNumber)
  // 埋め込みHTMLを有効にする
  .use(rehypeRaw)
  // aタグにtarget="_blank"を設定
  .use(rehypeAddTargetBlank)
  // Reactコンポーネントに変換
  .use(rehypeReact, rehypeReactOptions)
  // 出力情報を[Reactコンポーネント,MdastTree]の形式に変換
  .use(compilerResultTree);
```

## プラグインの作り方

remark 系と rehype 系で、操作する AST の構造が異なります。また、付加する情報の規則も違うので注意が必要です。

### 空行を復元

Markdown の標準仕様では空行が連続で続いた場合は除去されます。これを復元するプラグインです。ノードが存在しないポジションを計算して、改行を挿入しています。

```ts
import type { Root as MdastRoot, RootContent } from "mdast";
import type { Plugin } from "unified";

/**
 *  空白行をbreakに変換する
 */
export const remarkEmptyParagraphs: Plugin = () => {
  return (tree: MdastRoot) => {
    const lastLine = (tree.position?.end.line ?? 0) + 1;
    tree.children = tree.children.flatMap((node, index) => {
      const start = tree.children[index + 1]?.position?.start.line ?? lastLine;
      const end = node.position?.end.line;
      if (typeof start === "undefined" || typeof end === "undefined")
        return [node];
      const length = start - end - 1;
      if (length > 0) {
        return [
          node,
          ...Array(length)
            .fill(null)
            .map<RootContent>((_, index) => ({
              type: "paragraph",
              position: {
                start: {
                  offset: end + index + 1,
                  line: (node.position?.end?.line ?? 0) + index + 1,
                  column: 1,
                },
                end: {
                  offset: end + index + 1,
                  line: (node.position?.end?.line ?? 0) + index + 1,
                  column: 1,
                },
              },
              children: [{ type: "break" }],
            })),
        ];
      }
      return [node];
    });
  };
};
```

### ヘッダに ID とリンクを付ける

ヘッダにテキスト情報を ID として埋め込みます。これによって、ページ内の特定の見出しにリンクが可能になります。

```ts
import { visit } from "unist-util-visit";
import type { Node, Root } from "mdast";
import type { Plugin } from "unified";

/**
 *  子ノードから文字列を抽出
 */
const getNodeText = (node: Node | Root) => {
  const values: string[] =
    "children" in node
      ? node.children.map((v) =>
          "value" in v && typeof v.value === "string"
            ? v.value
            : getNodeText(v) || ""
        )
      : [];
  return values.join("");
};

/**
 *  Header内の文字列をIDとして埋め込み、リンクを作成
 */
export const remarkHeadingId: Plugin = () => {
  return (tree: Root) => {
    visit(tree, "heading", (node) => {
      const id = getNodeText(node);
      node.data = { hProperties: { id } };
      node.children = [
        ...node.children,
        {
          type: "link",
          children: [{ type: "text", value: "🔗" }],
          url: `#${id}`,
          data: { hProperties: { className: "inner-link" } },
        },
      ];
    });
  };
};
```

### コードブロックに追加情報を加える

code と inlineCode を`remark-rehype`以降で識別可能なようにデータを追加します。

```ts
import { visit } from "unist-util-visit";
import type { Node, Root } from "mdast";
import type { Plugin } from "unified";

/**
 *  子ノードから文字列を抽出
 */
const getNodeText = (node: Node | Root) => {
  const values: string[] =
    "children" in node
      ? node.children.map((v) =>
          "value" in v && typeof v.value === "string"
            ? v.value
            : getNodeText(v) || ""
        )
      : [];
  return values.join("");
};

/**
 *  codeに言語情報、inlineCodeにインラインフラグを追加
 */
export const remarkCode: Plugin = () => {
  return (tree: Root) => {
    visit(tree, "code", (node) => {
      node.data = { ...node.data, hProperties: { "data-language": node.lang } };
    });
    visit(tree, "inlineCode", (node) => {
      node.data = { ...node.data, hProperties: { "data-inline-code": "true" } };
    });
  };
};
```

### ノードに対してヘッダーに対応するインデント用の深度情報を与える

`<h1>`～`<h6>`の後続のエレメントに対して、ヘッダのレベル情報を付加しています。この情報によって、ヘッダに対応したインデントを CSS で記述することが可能になります。

```ts
import type { Root } from "mdast";
import type { Plugin } from "unified";

export const remarkDepth: Plugin = () => {
  return (tree: Root) => {
    tree.children.reduce((depth, node) => {
      if (node.type === "heading") {
        const index = node.depth;
        if (index) {
          return Number(index);
        }
      }
      node.data = {
        ...node.data,
        hProperties: {
          ...node.data?.hProperties,
          "data-depth": depth,
        },
      };
      return depth;
    }, 0);
  };
};
```

### ノードに対して行番号情報を付与

ポジションを持つノードに対して、行番号の情報を与えます。

```tsx
import { visit } from "unist-util-visit";
import type { Root } from "hast";
import type { Plugin } from "unified";
import type { VFile } from "vfile";

/**
 *  各ノードに行番号とカーソル位置の情報を埋め込む
 */
export const rehypeAddLineNumber: Plugin = () => {
  return (tree: Root) => {
    visit(
      tree,
      "element",
      (node) => {
        const start = node.position?.start?.line;
        const end = node.position?.end?.line;
        if (node.tagName === "code") {
        }
        if (start && end && !node.properties["data-inline-code"]) {
          node.properties = {
            ...node.properties,
            ["data-line"]: start,
          };
        }
      },
      true
    );
  };
};
```

### `<a>`に`target="_blank"`を設定

`<a>`に`_blank`の追加プロパティを与えています。ページ内リンクの場合は何もしません。

```ts
import { visit } from "unist-util-visit";
import type { Root } from "hast";
import type { Plugin } from "unified";

export const rehypeAddTargetBlank: Plugin = () => {
  return (tree: Root) => {
    visit(tree, "element", (node) => {
      if (
        node.tagName === "a" &&
        typeof node.properties?.href === "string" &&
        node.properties.href[0] !== "#"
      ) {
        node.properties.target = "_blank";
        node.properties.rel = "noopener noreferrer";
      }
    });
  };
};
```

### コードにハイライトを加える

こちらはプラグインではなく`rehype-react`に加えるオプションです。与えられたコードがハイライトされるようにします。また、変換したノードをキャッシュして、極力処理を省いています。

```tsx
import { Highlight, themes } from "prism-react-renderer";
import { useMemo, type ComponentProps } from "react";
import prod from "react/jsx-runtime";
import type { Options as RehypeReactOptions } from "rehype-react";
import { classNames } from "~/libs/classNames";

const Code = ({
  ref,
  children,
  ...props
}: ComponentProps<"code"> & {
  "data-language": string;
  "data-line": number;
  "data-inline-code": boolean;
}) => {
  const dataLine = Number(props["data-line"] ?? 0);
  const dataLanguage = props["data-language"];
  const dataInlineCode = props["data-inline-code"];
  const component = useMemo(() => {
    if (dataInlineCode) {
      return <code data-inline-code>{children}</code>;
    }
    return (
      <Highlight
        theme={themes.shadesOfPurple}
        code={String(children)}
        language={dataLanguage ?? "txt"}
      >
        {({ style, tokens, getLineProps, getTokenProps }) => {
          const numberWidth = Math.floor(Math.log10(tokens.length)) + 1;
          return (
            <div
              style={style}
              className="overflow-x-auto rounded py-1 font-mono"
            >
              {tokens.slice(0, -1).map((line, i) => (
                <div
                  key={i}
                  {...getLineProps({ line })}
                  data-line={dataLine + i + 1}
                >
                  <span
                    className={`sticky left-0 z-10 inline-block bg-blue-900 px-2 text-gray-300 select-none`}
                  >
                    <span
                      className="inline-block text-right"
                      style={{ width: `${numberWidth}ex` }}
                    >
                      {i + 1}
                    </span>
                  </span>
                  <span>
                    {line.map((token, key) => (
                      <span
                        key={key}
                        {...getTokenProps({ token })}
                        className={classNames(
                          getTokenProps({ token }).className
                        )}
                      />
                    ))}
                  </span>
                </div>
              ))}
            </div>
          );
        }}
      </Highlight>
    );
  }, [dataInlineCode, children, dataLanguage, dataLine]);
  return component;
};
export const rehypeReactOptions: RehypeReactOptions = {
  ...prod,
  components: { code: Code },
};
```

### 出力結果に追加情報を与える

`processSync`などでの最終的な出力結果をコンポーネントのみから、mdast のツリー情報も一緒に返すようにカスタマイズします。これにより、ツリー情報を利用した特殊な表示などに対応可能になります。

```ts
import type { Root } from "mdast";
import type { Processor } from "unified";

export function compilerResultTree(this: Processor<Root, Root, Root, Root>) {
  const originalCompiler = this.compiler;
  const originalParse = this.parse;
  let mdastTree: Root | undefined;
  this.parse = function (...args) {
    const tree = originalParse.apply(this, args) as Root;
    mdastTree = tree;
    return tree;
  };
  this.compiler = (...props) => {
    return [originalCompiler?.apply(this, props), mdastTree];
  };
}
```

### スタイル設定

Markdown 表示用のスタイルを一括設定します

```css
@reference "tailwindcss";
.markdown {
  @apply px-2;
  h1,
  h2,
  h3,
  h4,
  h5,
  h6 {
    @apply font-bold border-b-1 mb-2;
  }
  [data-depth="2"] {
    @apply ml-4;
  }
  [data-depth="3"] {
    @apply ml-8;
  }
  [data-depth="4"] {
    @apply ml-4;
  }
  [data-depth="5"] {
    @apply ml-8;
  }
  [data-depth="6"] {
    @apply ml-8;
  }
  h1 {
    @apply text-4xl;
  }
  h2 {
    @apply text-3xl ml-4;
  }
  h3 {
    @apply text-2xl ml-8;
  }
  h4 {
    @apply text-xl ml-12;
  }
  h5 {
    @apply text-lg ml-16;
  }
  h6 {
    @apply text-base ml-20;
  }
  p {
    @apply leading-relaxed p-0.5;
  }
  h1,
  h2,
  h3,
  h4,
  h5,
  h6,
  p,
  li,
  tr,
  :global(.token-line) {
    @apply relative;
  }
  em {
    @apply italic;
  }
  b {
    @apply font-bold;
  }
  strong {
    @apply font-bold;
  }
  [data-inline-code] {
    @apply inline-block bg-black/5 px-1 rounded;
  }
  a {
    @apply underline text-blue-700;
  }
  :global(.inner-link) {
    @apply no-underline text-base;
  }
  table {
    @apply rounded border;
  }
  td,
  th {
    @apply px-2;
  }
  th {
    @apply border-b;
  }
  td {
    @apply border border-black/20;
  }
  li {
    @apply ml-[1em] list-disc py-0.5;
  }
  img,
  canvas {
    margin: 0 auto;
    max-width: 80%;
    height: auto;
  }
  [data-line] {
    @apply relative;
  }
  [data-line]::after {
    @apply absolute -inset-0.5 w-full rounded pointer-events-none z-10 bg-blue-300/10 invisible border-b-blue-300 border-b-2 border-dotted;
    content: "";
  }
}
```

# テキストエディタとの連携

## Monaco エディタの使用

テキストエディタには扱いが簡単な Monaco エディタを使用します

```tsx
import { Editor as MonacoEditor, type OnMount } from "@monaco-editor/react";
import styled from "./MarkdownEditor.module.css";
import type { FC } from "react";
import { classNames } from "~/libs/classNames";

export const MarkdownEditor: FC<{
  onCurrentLine: (
    line: number,
    top: number,
    linePos: number,
    source: string
  ) => void;
  onUpdate: (value: string) => void;
  value: string;
  refEditor: React.RefObject<Parameters<OnMount>[0] | null>;
  className?: string;
}> = ({ onCurrentLine, onUpdate, value, refEditor, className }) => {
  const handleEditorDidMount: OnMount = (editor) => {
    refEditor.current = editor;
    editor.onDidChangeCursorPosition((event) => {
      const currentLine = event.position.lineNumber;
      const top = editor.getScrollTop();
      const linePos = editor.getTopForLineNumber(currentLine);
      onCurrentLine(currentLine, top, linePos, event.source);
    });
  };
  return (
    <MonacoEditor
      className={classNames(styled["markdown-editor"], className)}
      onMount={handleEditorDidMount}
      language="markdown"
      defaultValue={value}
      onChange={(e) => onUpdate(e ?? "")}
      options={{
        renderControlCharacters: true,
        renderWhitespace: "boundary",
        automaticLayout: true,
        scrollBeyondLastLine: false,
        wordWrap: "on",
        wrappingStrategy: "advanced",
        minimap: { enabled: false },
        dragAndDrop: true,
        dropIntoEditor: { enabled: true },
        contextmenu: false,
        occurrencesHighlight: "off",
        renderLineHighlight: "none",
        quickSuggestions: false,
        wordBasedSuggestions: "off",
        language: "markdown",
        selectOnLineNumbers: true,
      }}
    />
  );
};
```

## Markdown 表示部分

テキストエディタと連携してマークダウン表示をさせます。

```tsx
import { useMemo } from "react";
import { markdownCompiler } from "../markdownCompiler";

export const useMarkdown = ({ markdown }: { markdown?: string }) => {
  return useMemo(() => {
    return markdownCompiler.processSync({
      value: markdown,
    }).result;
  }, [markdown]);
};
```

マウスクリックに対応して対象ノードの強調表示し、エディタにイベントを送ります。

```tsx
import styled from "./MarkdownContent.module.css";
import { MarkdownHeaders } from "./MarkdownHeaders";
import type { FC } from "react";
import { classNames } from "~/libs/classNames";
import { useMarkdown } from "~/libs/MarkdownConverter";

export const MarkdownContext: FC<{
  className?: string;
  markdown?: string;
  line?: number;
  onClick?: (line: number, offset: number) => void;
}> = ({ className, markdown, line, onClick }) => {
  const [node, tree] = useMarkdown({ markdown });

  return (
    <div
      className={classNames(className, styled["markdown"])}
      onClick={(e) => {
        const framePos = e.currentTarget.getBoundingClientRect();
        let node = e.target as HTMLElement | null;
        while (node && !node.dataset.line) {
          node = node.parentElement;
        }
        if (node) {
          const p = node.getBoundingClientRect();
          onClick?.(Number(node.dataset.line), p.top - framePos.top);
        }
      }}
    >
      <style>{`[data-line="${line}"]:not(:has([data-line="${line}"]))::after {
          visibility: visible;
    }`}</style>
      {node}
      <MarkdownHeaders tree={tree} />
    </div>
  );
};
```

ヘッダ情報を収集して、一覧表示を行います

```tsx
import { useMemo, type FC } from "react";
import { visit } from "unist-util-visit";
import type { Root } from "mdast";

export const MarkdownHeaders: FC<{ tree: Root }> = ({ tree }) => {
  const headers = useMemo(() => {
    const titles: { id: number; text?: string; depth: number }[] = [];
    const property = { count: 0 };
    visit(tree, "heading", (node) => {
      titles.push({
        id: property.count,
        text: node.data?.hProperties?.id as string | undefined,
        depth: node.depth,
      });
    });
    return titles;
  }, [tree]);
  return (
    headers.length > 0 && (
      <ul className="sticky bottom-0 left-full z-10 h-60 w-80 overflow-y-auto rounded bg-white/90 p-2 text-sm">
        {headers.map(({ id, text, depth }) => (
          <li key={id} style={{ marginLeft: `${depth * 16}px` }}>
            <a href={`#${text}`}>{text}</a>
          </li>
        ))}
      </ul>
    )
  );
};
```

テキストエディタとマークダウン表示を連携させるときは、文字列の更新に`useTransition`を使います。文書量が多い状態で連続で文字を入力したときに、ある程度負荷が回避できます。

```tsx
import { useRef, useState, useTransition } from "react";
import type { OnMount } from "@monaco-editor/react";
import { MarkdownContext } from "~/components/MarkdownContent";
import { MarkdownEditor } from "~/components/MarkdownEditor";

const initText = "";

const Page = () => {
  const [content, setContent] = useState(initText);
  const refEditor = useRef<Parameters<OnMount>[0]>(null);
  const [currentLine, setCurrentLine] = useState(1);
  const refMarkdown = useRef<HTMLDivElement>(null);
  const [, startTransition] = useTransition();
  return (
    <div className="flex h-screen gap-2 divide-x divide-blue-100 overflow-hidden p-2">
      <div className="flex-1 overflow-hidden rounded border border-gray-200">
        <MarkdownEditor
          refEditor={refEditor}
          value={content}
          onUpdate={(value) => startTransition(() => setContent(value))}
          onCurrentLine={(line, top, linePos, source) => {
            startTransition(() => {
              setCurrentLine(line);
              const node = refMarkdown.current;
              if (node && source !== "api") {
                const nodes = node.querySelectorAll<HTMLElement>("[data-line]");
                const target = Array.from(nodes).find((node) => {
                  const nodeLine = node.dataset.line?.match(/(\d+)/)?.[1];
                  if (!line) return false;
                  return line === Number(nodeLine);
                });
                if (target) {
                  const { top: targetTop } = target.getBoundingClientRect();
                  const { top: nodeTop } = node.getBoundingClientRect();
                  node.scrollTop =
                    targetTop - nodeTop + node.scrollTop - (linePos - top);
                }
              }
            });
          }}
        />
      </div>
      <div
        ref={refMarkdown}
        className="flex-1 overflow-auto rounded border-2 border-gray-200"
      >
        <MarkdownContext
          markdown={content}
          line={currentLine}
          onClick={(line, offset) => {
            const editor = refEditor.current;
            const node = refMarkdown.current;
            if (editor && node) {
              const linePos = editor.getTopForLineNumber(line);
              editor.setScrollTop(linePos - offset + node.scrollTop);
              editor.setPosition({ lineNumber: line, column: 1 });
            }
          }}
        />
      </div>
    </div>
  );
};

export default Page;
```

# まとめ

`unified`で Markdown 用のプラグインを作る時に気になるのは、定義されている型情報が色々なパッケージに分散している上、定義そのものがかなり中途半端だという部分です。どこから何を持ってくるのかを理解するまでがそれなりに面倒です。
