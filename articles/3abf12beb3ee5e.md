---
title: "[React] 最短で\nを<br>に変換する方法"
emoji: "📌"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [react]
published: true
---

# 最短で`\n`を`<br>`に変換する方法

テキストを分離して奇数個目を`<br>`、偶数個目を普通に出力します
splitで分離するとき正規表現で`()`を使い`\n`自体を抽出することで、確実に位置を特定できます

@[codesandbox](https://codesandbox.io/embed/react-convert-return-8821o?autoresize=1&fontsize=14&theme=dark)


# 最短で`URL`を`<a>`に変換する方法

ついでにURLをリンクに変換する例も置いていきます

@[codesandbox](https://codesandbox.io/embed/react-convert-link-e718n?autoresize=1&fontsize=14&theme=dark)
