---
title: "Reactのコンポーネントの階層構造をreduceで作る"
emoji: "💬"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [react, typescript]
published: true
---

# JSX 中で map はよく使われるのに、reduce は見かけない

React で JSX を作る際、配列に対して map でコンポーネントを配置する記述は当たり前のように見かけますが、reduce の例が見当たらないので作ってみました。

map がコンポーネントを平置きしていくのに対し、reduce を使うと階層構造を作ることが出来ます。ちなみに reduceRight を使っているのは、配列の評価順を後方から行うためです。

```tsx
import { ReactNode } from "react";

type Props = { value: string; children?: ReactNode };

const Test = ({ value, children }: Props) => (
  <>
    <div>{value}</div>
    <div style={{ margin: "16px" }}>{children}</div>
    <div>{value}</div>
  </>
);

const Page = () => {
  const values = ["ああああ", "いいいい", "うううう", "ええええ", "おおおお"];
  return (
    <>
      <div>[mapで並べる]</div>
      <div>
        {values.map((value) => (
          <Test key={value} value={value} />
        ))}
      </div>
      <hr />
      <div>[reduceで並べる]</div>
      <div>
        {values.reduceRight(
          (children, value) => (
            <Test value={value}>{children}</Test>
          ),
          <></>
        )}
      </div>
    </>
  );
};

export default Page;
```

![](/images/react-reduce/2023-10-02-08-51-06.png)

ということで、簡単に階層構造ができました。

# まとめ

技は盗むより、編み出したほうが早いです。
