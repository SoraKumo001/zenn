---
title: "FirebaseStorage(CloudStorage)をEdgeRuntimeで操作する"
emoji: "🚻"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [nodejs, typescript, firebase, storage]
published: true
---

# FirebaseStorage を操作する方法

一般的な方法として、FirebaseStorage を操作する方法は以下のようになります。

- OAuth を使う場合  
  @firebase/storage パッケージを使う
- PrivateKey を使う場合  
  firebase-admin パッケージを使う

今回やりたいのは PrivateKey を使って、追加で認証を挟まずアクセス可能にする方法です。さらに Next.js の EdgeRuntime 対応です。普通は firebase-admin を使うことになるのですが、このライブラリは Node.js のフル機能を要求するため、EdgeRuntime には対応していません。

要件を満たすものを探したのですがなかなか見つけられず、そうなると自分で作った方が早いという結論に至りました。

- npm でパッケージ化したもの

https://www.npmjs.com/package/firebase-storage

# RestAPI による FirebaseStorage の操作

仕様は以下のところで公開されています。
https://cloud.google.com/storage/docs/json_api/v1

ということで早速作っていきましょう。

# 認証

FirebaseStorage を RestAPI で操作しようとする時、初っ端にそびえる最大の関門です。ドキュメントを見ても、まともに説明されていません。

必要なのは PrivateKey と ClientEmail から JWT でキーを作成することです。ここで問題になるのは crypto のパッケージは EdgeRuntime では動かないということです。JWT の操作は crypto を使っていないものを選ぶ必要があります。そのため、Edge に対応している`jose`を使います。

認証用 Token を使った最小サンプルは以下のようになります。

```ts
import { SignJWT, importPKCS8 } from "jose";

export const createToken = ({
  clientEmail,
  privateKey,
}: {
  clientEmail: string;
  privateKey: string;
}) =>
  importPKCS8(privateKey, "RS256").then((key) =>
    new SignJWT({
      iss: clientEmail,
      sub: clientEmail,
      scope: "https://www.googleapis.com/auth/cloud-platform",
      iat: Math.floor(Date.now() / 1000) - 30,
      exp: Math.floor(Date.now() / 1000) + 3600,
    })
      .setProtectedHeader({ alg: "RS256", typ: "JWT" })
      .sign(key)
  );
```

# RestAPI の呼び出し

残りは普通に RestAPI で操作するだけなので、まとめて紹介します。

```ts
export interface StorageObject {
  kind: string;
  id: string;
  selfLink: string;
  mediaLink: string;
  name: string;
  bucket: string;
  generation: string;
  metageneration: string;
  contentType: string;
  storageClass: string;
  size: string;
  md5Hash: string;
  cacheControl: string;
  crc32c: string;
  etag: string;
  timeCreated: string;
  updated: string;
  timeStorageClassUpdated: string;
}

export const info = ({
  token,
  bucket,
  name,
}: {
  token: string;
  bucket: string;
  name: string;
}): Promise<StorageObject> => {
  const url = `https://storage.googleapis.com/storage/v1/b/${bucket}/o/${name}`;
  return fetch(url, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${token}`,
    },
  }).then((res) => {
    if (res.status !== 200) throw new Error(res.statusText);
    return res.json();
  });
};

export const download = ({
  token,
  bucket,
  name,
}: {
  token: string;
  bucket: string;
  name: string;
}) => {
  const url = `https://storage.googleapis.com/storage/v1/b/${bucket}/o/${name}?alt=media&no=${Date.now()}`;
  return fetch(url, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${token}`,
    },
  }).then((res) => {
    if (res.status !== 200) throw new Error(res.statusText);
    return res.arrayBuffer();
  });
};

export const upload = ({
  token,
  bucket,
  name,
  file,
  published,
  metadata,
}: {
  token: string;
  bucket: string;
  name: string;
  file: Blob;
  published?: boolean;
  metadata?: { [key: string]: unknown };
}) => {
  const id = encodeURI(name);

  const url = `https://storage.googleapis.com/upload/storage/v1/b/${bucket}/o?name=${id}&uploadType=multipart${
    published ? "&predefinedAcl=publicRead" : ""
  }`;
  const body = new FormData();
  body.append(
    "",
    new Blob([JSON.stringify({ metadata })], { type: "application/json" })
  );
  body.append("", file);
  return fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: body,
  }).then((res) => {
    if (res.status !== 200) throw new Error(res.statusText);
    return res.json();
  });
};

export const del = ({
  token,
  bucket,
  name,
}: {
  token: string;
  bucket: string;
  name: string;
}) => {
  const url = `https://storage.googleapis.com/storage/v1/b/${bucket}/o/${name}`;
  return fetch(url, {
    method: "DELETE",
    headers: {
      Authorization: `Bearer ${token}`,
    },
  }).then((res) => {
    if (res.status !== 204) throw new Error(res.statusText);
    return true;
  });
};

export const list = ({
  token,
  bucket,
}: {
  token: string;
  bucket: string;
}): Promise<StorageObject[]> => {
  const url = `https://storage.googleapis.com/storage/v1/b/${bucket}/o`;
  return fetch(url, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })
    .then((res) => {
      if (res.status !== 200) throw new Error(res.statusText);
      return res.json();
    })
    .then((res) => res.items);
};
```

ちなみにオブジェクトのデータを取得する時、StorageObject のような構造になっているのですが、注意点として全て文字列型だということです。

https://cloud.google.com/storage/docs/json_api/v1/objects

上記ドキュメントには文字列以外の型が書いてありますが嘘です。全部文字列です。必要なら自分で型を変換してください。

その他の点として、upload 時に metadata を同時指定するのであれば multipart でデータを送る必要があります。データを FormData にセットするだけなので、やり方さえ知っていれば簡単です。

# まとめ

コード的には大した量にならず、簡単な内容で処理を書くことが出来ます。ただ、ドキュメントから具体的な使い方を理解するまでがそれなりに面倒です。
