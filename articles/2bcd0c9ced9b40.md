---
title: "Next.jsでFirebase経由でGoogle認証を利用する"
emoji: "🍣"
type: "tech"
topics: ["nextjs","typescript","firebase","javascript"]
published: true
---

# Firebaseを使えるようにするまで

## Firebaseでプロジェクトを作成

[Firebase](https://console.firebase.google.com/)を利用すると、無料で以下のサービスに対応した認証を行えます。
自力で一つ一つ対応するより遙かに簡単です。

![](/images/539d7f6e7f3c63/01.png)

上記の一覧はFirebaseにプロジェクトを作成し、Authenticationを選ぶと表示されます。

## Google認証の有効化

Firebaseの中でも最も認証が簡単に実装できるのが、Googleアカウントの認証です。
先ほどのメニューからGoogleを選んで有効にするを押すだけで、ほぼ設定が完了します。

![](/images/539d7f6e7f3c63/02.png)

## アプリケーションの登録

歯車ボタンからプロジェクトを設定を選びます

![](/images/539d7f6e7f3c63/03.png)

`</>`のアイコンを選びアプリケーション名を設定してWebアプリケーションを作成します

![](/images/539d7f6e7f3c63/04.png)

以下のようにAPIキーが発行されます。このキーは公開前提の内容なので流出しても問題ありません。

![](/images/539d7f6e7f3c63/05.png)

アプリケーション作成時に`firebaseConfig`の部分が必要になります。
この情報はプロジェクトを設定からいつでも確認出来ます。

# Next.jsの設定

## モジュールのインストール

firebaseのドキュメントには@系は単独で使うべきものではないと書いてあるので、気になる場合は20MBオーバーのfirebase本体を追加してください

```bash
yarn add @firebase/app @firebase/auth next react react-dom 
yarn add -D @types/react @types/react
```

## サンプルソース

![](/images/539d7f6e7f3c63/06.png)

```tsx
import { useCallback, useEffect, useState } from 'react';
import { initializeApp } from '@firebase/app';
import {
  getAuth,
  GoogleAuthProvider,
  signInWithPopup,
  UserCredential,
  signInWithCredential,
  signOut,
  Auth,
} from '@firebase/auth';

//https://console.firebase.google.com/
// プロジェクトを追加
// Authetication -> Sign-in method -> Googleを有効にする
// プロジェクトの概要 -> アプリの追加 -> ウェブ -> アプリの作成
// firebaseConfig の内容を持ってくる

const firebaseConfig = {
  apiKey: '',
  authDomain: '',
  databaseURL: '',
  projectId: '',
  storageBucket: '',
  messagingSenderId: '',
  appId: '',
};

const useAuth = (auth: Auth) => {
  const [state, setState] = useState<'idel' | 'progress' | 'logined' | 'logouted' | 'error'>(
    'idel'
  );
  const [error, setError] = useState<unknown>('');
  const [credential, setCredential] = useState<UserCredential>();
  const dispatch = useCallback(
    (action: { type: 'login'; payload?: { token: string } } | { type: 'logout' }) => {
      setError('');
      switch (action.type) {
        case 'login':
          setState('progress');
          const token = action.payload?.token;
          if (token) {
            signInWithCredential(auth, GoogleAuthProvider.credential(token))
              .then((result) => {
                setCredential(result);
                setState('logined');
              })
              .catch((e) => {
                setError(e);
                setState('error');
              });
          } else {
            signInWithPopup(auth, provider)
              .then((result) => {
                setCredential(result);
                setState('logined');
              })
              .catch((e) => {
                setError(e);
                setState('error');
              });
          }
          break;
        case 'logout':
          setState('progress');
          signOut(auth)
            .then(() => {
              setCredential(undefined);
              setState('logouted');
            })
            .catch((e) => {
              setError(e);
              setState('error');
            });
          break;
      }
    },
    [auth]
  );
  return { state, error, credential, dispatch };
};

const auth = getAuth(initializeApp(firebaseConfig));
const provider = new GoogleAuthProvider();

const Page = () => {
  const { state, dispatch, credential, error } = useAuth(auth);
  useEffect(() => {
    const token = sessionStorage.getItem('token');
    if (token) {
      dispatch({ type: 'login', payload: { token } });
    }
  }, [dispatch]);
  useEffect(() => {
    if (credential) {
      const token = GoogleAuthProvider.credentialFromResult(credential)?.idToken;
      token && sessionStorage.setItem('token', token);
    } else {
      sessionStorage.removeItem('token');
    }
  }, [credential]);
  const handleLogin = () => dispatch({ type: 'login' });
  const handleLogout = () => dispatch({ type: 'logout' });
  return (
    <div>
      <button onClick={handleLogin}>ログイン</button>
      <button onClick={handleLogout}>ログアウト</button>
      <div>User: {credential?.user.displayName}</div>
      <div>State: {state}</div>
      <div>Error: {String(error)}</div>
    </div>
  );
};

export default Page;
```

useAuthで認証管理しています。
dispatchで命令を与えて、取得した状態を表示しています。
最終的に必要なネイティブのtokenは`GoogleAuthProvider.credentialFromResult`でとることが出来ます。

サンプル用にtokenの管理はsessionStorageで行うようにして、ブラウザをリロードすると保持したtokenを使って再認証するようにしています。
ちなみに発行したtokenは`signOut`を使っても、無効にはなりません。
ただ忘れ去るのみです。

ここで受け取ったtokenをバックエンド側に送って`signInWithCredential`で検証するような仕組みを作ると、バックエンド側はメールアドレスだけ持っておく形で認証処理が完成します。

# まとめ

Firebaseを使うと認証処理が簡単になるので、自前で認証機能を作成するよりも工数が削減できておすすめです。
