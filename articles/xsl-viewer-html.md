---
title: "電子公文書(XML+XSL)をChromeで表示する"
emoji: "📚"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [javascript, html, xsl, xml, zip]
published: true
---

# 電子公文書とは

電子公文書とは、電子的な形式で作成、保存、管理される公文書のことを指します。これには、政府機関や企業が発行する公式な文書が含まれます。電子公文書は、紙の文書と同様に法的効力を持つ場合があり、デジタル署名や暗号化技術を用いることで、その信頼性や安全性が確保されます。

この電子公文書の中には、XML+XSL 形式で作成されたものがあります。XML は、データを構造化して記述するためのマークアップ言語であり、XSL は、XML 文書を別の形式に変換するためのスタイルシート言語です。XML+XSL 形式の電子公文書は、Web ブラウザで表示することができますが、その表示方法にはいくつかの制約があります。

# 電子公文書の表示方法

電子公文書を Web ブラウザで表示するためには、XML+XSL 形式のファイルを HTML 形式に変換する必要があります。この変換は、XSLT（XSL Transformations）という技術を用いて行われます。XSLT は、XML 文書を別の形式に変換するためのスタイルシート言語であり、XSL ファイルを使って XML 文書を HTML 形式に変換することができます。

電子公文書を Web ブラウザで表示する方法として以下の内容が案内されています。

- Q.XML ファイル形式の公文書ファイルを開く方法を教えてください。  
  https://shinsei.e-gov.go.jp/contents/help/faq/document.html

Microsoft Edge の IE11 互換モードや Safari のローカルファイルの制限を無効にする方法が案内されています。

ぶっちゃけ酷いとしか言いようがありません。真っ当に表示する方法が無いのです。本来であれば、もっと汎用的なフォーマットで配布するべきです。

# Chrome で表示する方法

Chrome では XML+XSL のファイルをドラッグドロップしても表示されません。しかし、XSL 自体は Web 標準で対応しているため、XSLTProcessor を使って HTML に変換することができます。ただ、API の呼び出しが必要なため、変換のためのスクリプトを組む必要があります。

ということで変換スクリプトを作りました。電子公文書は ZIP 形式で配布されているため、そのまま ZIP 形式でドラッグドロップ出来るようにしています。ブラウザは ZIP で使われている圧縮アルゴリズムの deflate には対応しているのですが、ZIP ファイルには対応していません。そのため、ZIP ファイルから圧縮データを取り出す処理は自分で書く必要があります。そして電子公文書で使われている ZIP 形式が曲者で、レガシーなシーケンシャル形式になっています。これがどういうことかというと、圧縮されたデータサイズを含んだヘッダが、データ本体よりも後にあるという、非常に扱いにくい形式です。データサイズが不明なため、後続のヘッダを先に探さないとデータが読めないのです。今、こんな形式の ZIP ファイルを作るシステムはそうそうお目にかかれません。

ZIP ファイルの展開から XML+XSL を HTML に変換するコードはこちらです。

https://github.com/SoraKumo001/xsl-viewer-html

```html
<!DOCTYPE html>
<html>
  <head>
    <title>XSL Viewer</title>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
      html,
      body {
        min-height: 100%;
        min-width: 100%;
        margin: 0;
        padding: 0;
      }
    </style>
    <script>
      /**
       * @param {arrayBuffer} ArrayBuffer
       * @returns {Promise<File[]>}
       */
      const decompressZip = async (arrayBuffer) => {
        async function decompressData(compressedData) {
          const reader = new Blob([compressedData])
            .stream()
            .pipeThrough(new DecompressionStream("deflate-raw"))
            .getReader();
          const chunks = [];
          let result = await reader.read();
          while (!result.done) {
            chunks.push(result.value);
            result = await reader.read();
          }
          return new Blob(chunks);
        }

        const dataView = new DataView(arrayBuffer);
        let offset = 0;
        const files = [];

        while (offset < dataView.byteLength) {
          const signature = dataView.getUint32(offset, true);
          if (signature !== 0x04034b50) break;
          const generalPurposeFlag = dataView.getUint16(offset + 6, true);
          const fileNameLength = dataView.getUint16(offset + 26, true);
          const extraFieldLength = dataView.getUint16(offset + 28, true);
          let compressedSize = dataView.getUint32(offset + 18, true);
          const pathName = new TextDecoder().decode(
            arrayBuffer.slice(offset + 30, offset + 30 + fileNameLength)
          );
          offset += fileNameLength + extraFieldLength + 30;
          const dataOffset = offset;
          const isDataDescriptor = (generalPurposeFlag & 0x0008) !== 0;

          if (isDataDescriptor) {
            while (offset < dataView.byteLength) {
              const potentialSignature = dataView.getUint32(offset, true);
              if (potentialSignature === 0x08074b50) {
                compressedSize = dataView.getUint32(offset + 8, true);
                offset += 16;
                break;
              }
              offset++;
            }
          } else {
            offset += compressedSize;
          }

          if (pathName[pathName.length - 1] !== "/") {
            const decompressedData = await decompressData(
              arrayBuffer.slice(dataOffset, dataOffset + compressedSize)
            );
            const fileName = pathName.replace(/.*\//, "");
            files.push(new File([decompressedData], fileName));
          }
        }
        return files;
      };
      /**
       * @param {File[]} sourceFiles
       * @returns {Promise<[string, string][]>}
       * */
      const convertXsl = async (sourceFiles) => {
        const unCompressPromises = sourceFiles.map(async (file) => {
          if (file.type === "application/x-zip-compressed") {
            return file.arrayBuffer().then(decompressZip);
          }
          return file;
        });
        const unCompressFiles = Promise.all(unCompressPromises).then(
          (files) => {
            return files.flat();
          }
        );
        const documentFiles = unCompressFiles.then(async (files) => {
          return Promise.all(
            files
              .filter((file) => file.name.match(/\.xml$|\.xsl$/))
              .map(async (file) => {
                const parser = new DOMParser();
                const xml = parser.parseFromString(
                  await file.text(),
                  "application/xml"
                );
                return [file.name, xml];
              })
          );
        });
        return documentFiles.then((files) => {
          const fileMap = Object.fromEntries(files);
          const xmlDocs = files.filter(([name]) => name.endsWith(".xml"));
          const documents = xmlDocs.map(([name, xmlDoc]) => {
            const xsltProcessor = new XSLTProcessor();
            const styleNodes = Array.from(xmlDoc.childNodes).filter(
              (node) =>
                node.nodeType === Node.PROCESSING_INSTRUCTION_NODE &&
                node.target === "xml-stylesheet"
            );
            styleNodes.forEach((styleNode) => {
              const href = styleNode.data.match(/href="([^"]+)"/)[1];
              const xslDoc = fileMap[href];
              if (xslDoc) xsltProcessor.importStylesheet(xslDoc);
            });
            const resultDoc = xsltProcessor.transformToDocument(xmlDoc);
            const serializer = new XMLSerializer();
            const resultString = serializer.serializeToString(resultDoc);
            return [name, resultString];
          });
          return documents;
        });
      };
      const handleDrop = (e) => {
        e.preventDefault();
        convertXsl(Array.from(e.dataTransfer.files)).then((docs) => {
          const body = document.body;
          body.innerHTML = "";
          const nodes = docs.map(([name, doc]) => {
            const contents = document.createElement("div");
            contents.innerHTML = doc;
            const div = document.createElement("div");
            div.style.padding = "16px";
            const header = document.createElement("h1");
            header.innerText = name;
            const hr = document.createElement("hr");
            div.append(header, contents, hr);
            return div;
          });
          body.append(...nodes);
        });
      };
    </script>
  </head>
  <body ondragover="event.preventDefault()" ondrop="handleDrop(event)">
    <div
      style="
        height: 100vh;
        display: flex;
        justify-content: center;
        align-items: center;
      "
    >
      <span
        style="
          padding: 16px;
          font-size: 2em;
          border: 2px dashed black;
          border-radius: 16px;
        "
      >
        Drop files or zip-file here
      </span>
    </div>
  </body>
</html>
```

以下のアドレスで試すことが出来ます。

https://sorakumo001.github.io/xsl-viewer-html/

社会保険料の通知を表示してみました。

![screenshot](https://raw.githubusercontent.com/SoraKumo001/xsl-viewer-html/refs/heads/master/document/image.png)

# まとめ

Chrome で XML+XSL 形式の電子公文書を表示する方法を紹介しました。今回は外部ライブラリを使わず、標準の API だけで実装しています。やっている事自体はそれほど複雑ではないので、HTML ファイル一つで簡単に収まるレベルで済みました。
