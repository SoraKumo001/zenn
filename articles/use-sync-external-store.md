---
title: "🚻 ReactのuseSyncExternalStoreで作るオレオレStateライブラリ"
emoji: "🚻"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [nextjs, typescript, react, javascript]
published: true
---

- サンプルコード
  - GitHub  
    https://github.com/SoraKumo001/next-syncexternalstore
  - Vercel  
    https://next-syncexternalstore.vercel.app/

# あまり話題にされない useSyncExternalStore

ReactHooks 解説系の記事で無かったことにされたり、一瞬だけ概要が紹介されるだけなことが多い useSyncExternalStore です。可哀想なので、オレオレ State ライブラリを作って使い方を紹介したいと思います。

ちなみに useSyncExternalStore を使うと、こちらの記事で使っているようなライブラリも簡単に作れます。

https://zenn.dev/sora_kumo/articles/app-dir-client-ssr

# オレオレ State ライブラリは一瞬で構築できる

```ts
import { useRef, useSyncExternalStore } from "react";

export type ContextType<T> = {
  state: T;
  storeChanges: Set<() => void>;
  dispatch: (callback: (state: T) => T) => void;
  subscribe: (onStoreChange: () => void) => () => void;
};

export const createStoreContext = <T>(initState: () => T) => {
  const context = useRef<ContextType<T>>({
    state: initState(),
    storeChanges: new Set(),
    dispatch: (callback) => {
      context.state = callback(context.state);
      context.storeChanges.forEach((storeChange) => storeChange());
    },
    subscribe: (onStoreChange) => {
      context.storeChanges.add(onStoreChange);
      return () => {
        context.storeChanges.delete(onStoreChange);
      };
    },
  }).current;
  return context;
};

export const useSelector = <T, R>(
  context: ContextType<T>,
  getSnapshot: (state: T) => R
) =>
  useSyncExternalStore(
    context.subscribe,
    () => getSnapshot(context.state),
    () => getSnapshot(context.state)
  );
```

はい、出来上がりです。これだけでコンポーネントの State の更新を自由自在に操れます。では、使い方を見てみましょう。

```tsx
type StateType = { a: number; b: number; c: number };

const A = ({ context }: { context: ContextType<StateType> }) => {
  const value = useSelector(context, (state) => state.a);
  return <div>A:{value}</div>;
};
const B = ({ context }: { context: ContextType<StateType> }) => {
  const value = useSelector(context, (state) => state.b);
  return <div>B:{value}</div>;
};
const C = ({ context }: { context: ContextType<StateType> }) => {
  const value = useSelector(context, (state) => state.c);
  return <div>C:{value}</div>;
};

const Buttons = ({ context }: { context: ContextType<StateType> }) => {
  return (
    <div>
      <button
        onClick={() =>
          context.dispatch((state) => ({ ...state, a: state.a + 1 }))
        }
      >
        A
      </button>
      <button
        onClick={() =>
          context.dispatch((state) => ({ ...state, b: state.b + 1 }))
        }
      >
        B
      </button>
      <button
        onClick={() =>
          context.dispatch((state) => ({ ...state, c: state.c + 1 }))
        }
      >
        C
      </button>
    </div>
  );
};

const Page = () => {
  const context = createStoreContext<StateType>(() => ({
    a: 0,
    b: 10,
    c: 100,
  }));
  return (
    <div>
      <A context={context} />
      <B context={context} />
      <C context={context} />
      <Buttons context={context} />
    </div>
  );
};
```

これで共有されている State の内、コンポーネントが必要とする部分が更新された場合のみ、最小限で再レンダリングされるようになります。

![](/images/fd99b000aa57f0/2023-04-18-17-20-04.gif)

# Context を配るのが面倒な場合

`createContext`を使って Provider を作り、配下に Context を配るようにします。

```tsx
import {
  useRef,
  useSyncExternalStore,
  createContext,
  ReactNode,
  useContext,
} from "react";

export type ContextType<T> = {
  state: T;
  storeChanges: Set<() => void>;
  dispatch: (callback: (state: T) => T) => void;
  subscribe: (onStoreChange: () => void) => () => void;
};

export const createStoreContext = <T,>(initState: () => T) => {
  const context = useRef<ContextType<T>>({
    state: initState(),
    storeChanges: new Set(),
    dispatch: (callback) => {
      context.state = callback(context.state);
      context.storeChanges.forEach((storeChange) => storeChange());
    },
    subscribe: (onStoreChange) => {
      context.storeChanges.add(onStoreChange);
      return () => {
        context.storeChanges.delete(onStoreChange);
      };
    },
  }).current;
  return context;
};

const StoreContext = createContext<ContextType<any>>(undefined as never);

export const StoreProvider = <T,>({
  children,
  initState,
}: {
  children: ReactNode;
  initState: () => T;
}) => {
  const context = createStoreContext(initState);
  return (
    <StoreContext.Provider value={context}>{children}</StoreContext.Provider>
  );
};

export const useSelector = <T, R>(getSnapshot: (state: T) => R) => {
  const context = useContext<ContextType<T>>(StoreContext);
  return useSyncExternalStore(
    context.subscribe,
    () => getSnapshot(context.state),
    () => getSnapshot(context.state)
  );
};

export const useDispatch = <T,>() => {
  const context = useContext<ContextType<T>>(StoreContext);
  return context.dispatch;
};
```

使い方はこんな形です。

```tsx
type StateType = { a: number; b: number; c: number };

const A = () => {
  const value = useSelector((state: StateType) => state.a);
  return <div>A:{value}</div>;
};
const B = () => {
  const value = useSelector((state: StateType) => state.b);
  return <div>B:{value}</div>;
};
const C = () => {
  const value = useSelector((state: StateType) => state.c);
  return <div>C:{value}</div>;
};

const Buttons = () => {
  const dispatch = useDispatch<StateType>();
  return (
    <div>
      <button
        onClick={() => dispatch((state) => ({ ...state, a: state.a + 1 }))}
      >
        A
      </button>
      <button
        onClick={() => dispatch((state) => ({ ...state, b: state.b + 1 }))}
      >
        B
      </button>
      <button
        onClick={() => dispatch((state) => ({ ...state, c: state.c + 1 }))}
      >
        C
      </button>
    </div>
  );
};

const Page = () => {
  return (
    <StoreProvider
      initState={() => ({
        a: 0,
        b: 10,
        c: 100,
      })}
    >
      <A />
      <B />
      <C />
      <Buttons />
    </StoreProvider>
  );
};
export default Page;
```

Context を配る必要が無くなり、コード量が少なくなりました。

# useSyncExternalStore を使わずに同じ事をしてみる

実は`useState`の dispatch を収集する構造を作るだけで、`useSyncExternalStore`と同じ事が可能です。コード量のほとんど同じです。

```tsx
import {
  useRef,
  createContext,
  ReactNode,
  useContext,
  useState,
  Dispatch,
  SetStateAction,
  useEffect,
} from "react";

type ContextType<T> = {
  state: T;
  storeChanges: Map<Dispatch<SetStateAction<any>>, (state: T) => unknown>;
  dispatch: (callback: (state: T) => T) => void;
};

const createStoreContext = <T,>(initState: () => T) => {
  const context = useRef<ContextType<T>>({
    state: initState(),
    storeChanges: new Map(),
    dispatch: (callback) => {
      context.state = callback(context.state);
      context.storeChanges.forEach((callback, storeChange) =>
        storeChange(callback(context.state))
      );
    },
  }).current;
  return context;
};

const StoreContext = createContext<ContextType<any>>(undefined as never);

const StoreProvider = <T,>({
  children,
  initState,
}: {
  children: ReactNode;
  initState: () => T;
}) => {
  const context = createStoreContext(initState);
  return (
    <StoreContext.Provider value={context}>{children}</StoreContext.Provider>
  );
};

const useSelector = <T, R>(getSnapshot: (state: T) => R) => {
  const context = useContext<ContextType<T>>(StoreContext);
  const [state, dispatch] = useState(() => getSnapshot(context.state));
  context.storeChanges.set(dispatch, getSnapshot);
  useEffect(() => {
    context.storeChanges.set(dispatch, getSnapshot);
    return () => {
      context.storeChanges.delete(dispatch);
    };
  }, [context, getSnapshot]);
  return state;
};

const useDispatch = <T,>() => {
  const context = useContext<ContextType<T>>(StoreContext);
  return context.dispatch;
};
```

使い方も前のサンプルと同じです。

# まとめ

State ライブラリを作るときは公式で`useSyncExternalStore`が推奨されているので必要とあらば使うようにしていますが、ぶっちゃけ無くても何にも困りません。

`useSyncExternalStore`の使い道としては外部ライブラリを入れるほどでも無いけれど、局地的に再レンダリングする場所を調整したい場合などに使うと良いかもしれません。
