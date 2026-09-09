---
title: "GitHub Packages (npm) の認証にPATを使わず GitHub CLI を活用する"
emoji: "📦"
type: "tech"
topics: ["github", "npm", "security", "githubactions", "gh"]
published: true
---

GitHub Packages（`npm.pkg.github.com`）でホストされているプライベートな npm パッケージをローカル環境で利用する際、[公式ドキュメント](https://docs.github.com/ja/packages/working-with-a-github-packages-registry/working-with-the-npm-registry#personal-access-token-%E3%81%A7%E8%AA%8D%E8%A8%BC%E3%81%99%E3%82%8B)や多くの解説記事では、Personal Access Token（PAT）を発行して `.npmrc` に記載する手順が紹介されています。

しかし、ローカルマシン上に PAT を平文で保存したり、長期間有効なトークンを個別に管理したりすることには、いくつかのセキュリティ上の懸念があります。

この記事では、PAT を個別に発行・保存する運用をやめ、GitHub CLI（`gh`）の OAuth 認証と一時トークンを活用して、安全かつ手軽に npm の認証を行う方法をまとめます。

## PAT を直接管理することの課題

従来の運用では、GitHub の管理画面で Classic PAT または Fine-grained PAT を発行し、環境変数や `~/.npmrc` に保存することが一般的でした。この方法には次のような課題があります。

- 長期有効トークンの放置
  - 期限切れによる作業中断を避けるために有効期限を「無期限」に設定したり、長期間更新されずに放置されたりしがちです。
- スコープと影響範囲の管理
  - Classic PAT の場合、`read:packages` スコープであっても、アカウント全体のパッケージに対する読み取り権限が付与されます。
- 平文保存と漏洩リスク
  - プロジェクト内の `.npmrc` やホームディレクトリの `~/.npmrc` にトークンを平文で保存すると、誤ってリポジトリへコミットしてしまったり、ローカルマシンの別プロセスやスクリプトから意図せず参照されたりする危険性があります。

## GitHub CLI による一時トークンの活用

GitHub CLI（`gh`）がインストールされている環境であれば、`gh auth login` を通じてブラウザ経由の OAuth 認証（2要素認証やパスキー含む）が行われており、認証情報は OS のセキュアなストレージに保管されています。

この認証セッションを利用して、次のコマンドで一時的なアクセストークンを標準出力として取り出すことができます。

```bash
gh auth token
```

このトークンは現在のログインセッションに紐づくため、Web 画面から手作業で PAT を発行・更新・削除する必要がありません。

### 必要なスコープの付与

GitHub Packages からパッケージをインストールするには、`read:packages` スコープが必要です。まだ付与されていない場合は、次のコマンドでスコープを追加します。

```bash
# 既存の認証にスコープを追加する場合
gh auth refresh -s read:packages

# 新規にログインする場合
gh auth login -s read:packages
```

SAML SSO が有効な Organization のリソースにアクセスする場合は、画面の指示に従ってブラウザ上で Organization への認可（Authorize）を行ってください。

## `.npmrc` の設定

プロジェクトのリポジトリ内、またはホームディレクトリに `.npmrc` を配置します。トークンそのものは直書きせず、環境変数展開の記法を用います。

```ini
@my-org:registry=https://npm.pkg.github.com
//npm.pkg.github.com/:_authToken=${NODE_AUTH_TOKEN}
```

`@my-org` には対象の GitHub Organization 名またはユーザー名を指定します。

このように記述しておくことで、`.npmrc` に秘密情報が含まれなくなるため、安全に Git リポジトリへコミットできます。また、GitHub Actions などの CI 環境でも同じ `.npmrc` をそのまま利用できます。

```yaml
# CI (GitHub Actions) での記述例
- name: Install dependencies
  run: npm ci
  env:
    NODE_AUTH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

## ローカル環境でのトークン設定の自動化

`.npmrc` に `${NODE_AUTH_TOKEN}` と記述した場合、コマンド実行時に環境変数 `NODE_AUTH_TOKEN` が設定されている必要があります。開発者が毎回トークンを意識せずに済むよう、いくつかの自動化アプローチがあります。

### 1. コマンド実行時に渡す

最もシンプルな方法は、パッケージのインストール時に一時トークンを環境変数として渡す方法です。

macOS や Linux、WSL（Bash / Zsh）の場合：

```bash
NODE_AUTH_TOKEN=$(gh auth token) npm install
```

Windows（PowerShell）の場合：

```powershell
$env:NODE_AUTH_TOKEN = (gh auth token); npm install
```

一時的に環境変数を渡すだけなので、環境変数や設定ファイルに永続化されるリスクを低減できます。

### 2. direnv を利用する（macOS / Linux / WSL）

プロジェクトごとにディレクトリ単位で環境変数を自動設定できる `direnv` を導入している場合、プロジェクトルートの `.envrc` に以下を記述します。

```bash
export NODE_AUTH_TOKEN=$(gh auth token)
```

設定後、`direnv allow` を実行すれば、そのディレクトリに移動した時点で自動的に最新のトークンが環境変数に展開されます。

### 3. シェルのプロファイルにラッパー関数を定義する

日常的にプライベートパッケージを含むリポジトリで作業する場合は、シェルの設定ファイルにラッパーを定義しておく方法もあります。

#### Bash / Zsh（`~/.bashrc` または `~/.zshrc`）

```bash
npm() {
  if [ -z "$NODE_AUTH_TOKEN" ] && command -v gh >/dev/null 2>&1; then
    NODE_AUTH_TOKEN="$(gh auth token 2>/dev/null)" command npm "$@"
  else
    command npm "$@"
  fi
}
```

#### PowerShell（`$PROFILE`）

```powershell
function npm {
    if (-not $env:NODE_AUTH_TOKEN -and (Get-Command gh -ErrorAction SilentlyContinue)) {
        try {
            $env:NODE_AUTH_TOKEN = (gh auth token 2>$null)
            & (Get-Command -CommandType Application npm) @args
        } finally {
            Remove-Item env:NODE_AUTH_TOKEN -ErrorAction SilentlyContinue
        }
    } else {
        & (Get-Command -CommandType Application npm) @args
    }
}
```

この設定をしておくと、通常の `npm install` や `npm update` を実行した際、自動的に `gh auth token` から取得した値がそのプロセス実行中のみ適用されます。

## 注意点

- GitHub CLI の認証状態
  - `gh auth status` でログイン状態が切れている場合は、再度 `gh auth login` を行う必要があります。
- パッケージマネージャーごとの仕様
  - pnpm を使用している場合も同様に `.npmrc` の `${NODE_AUTH_TOKEN}` が解釈されます。
  - Yarn（Berry / v2以降）を使用している場合は、`.yarnrc.yml` 内で `npmAuthToken: "${NODE_AUTH_TOKEN}"` のように設定します。

## まとめ

GitHub Packages の利用において PAT の手動発行や平文保存を避け、GitHub CLI を認証の基盤とすることで、次のようなメリットが得られます。

- トークン漏洩や誤コミットのリスクを排除できる
- トークンの期限切れや更新作業による開発の滞りを防げる
- CI（GitHub Actions）とローカルで `.npmrc` の設定を共通化できる

すでに業務や個人開発で GitHub CLI を利用している場合は、最小限の設定変更で導入できるため、認証管理の見直しとして有効です。
