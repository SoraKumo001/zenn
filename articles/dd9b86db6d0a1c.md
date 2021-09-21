---
title: "ZennのGitHubリポジトリ連携でキャプチャ画像のコピペを簡単にする"
emoji: "🦔"
type: "tech"
topics: ["zenn","github","vscode"]
published: true
---

# 画像の貼り付けが面倒くさい

Zennの記事をローカルで編集してGitHubリポジトリ連携を行う場合、面倒なのがスクリーンショットをとった後の画像の貼り付けです。
Web編集なら簡単にコピペ出来ますが、ローカル編集だとファイルを適切な位置に保存し、そのリンクを書かねばなりません。

今回はこの作業を消し飛ばしたいと思います。

# VSCodeにプラグインをインストールと設定

## インストール

https://marketplace.visualstudio.com/items?itemName=mushan.vscode-paste-image

## プラグインの設定

Zenn専用なので、ワークスペース設定での利用をお勧めします

- .vscode/settings.json

```json
{
    "pasteImage.insertPattern": "${imageSyntaxPrefix}/images/${currentFileNameWithoutExt}/${imageFileName}${imageSyntaxSuffix}",
    "pasteImage.path": "${projectRoot}/images/${currentFileNameWithoutExt}"
}
```

# 貼り付け

画像をコピーしたらCTRL(cmd)+ALT+Cを押します
すると画像ファイルが作成され、以下のような画像リンクが作成されます

```md
![](/images/dd9b86db6d0a1c/2021-09-21-14-43-04.png)
```

# まとめ

この記事をアップする前に同じようなことをしている人がいないか確認したら、既にいらっしゃいました

https://zenn.dev/waddy/articles/image-paste-zenn-upload
