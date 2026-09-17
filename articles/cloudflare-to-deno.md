---
title: "最強の Cloudflare Workers の欠点、メモリ128MBを Deno Deploy で回避する"
emoji: "📘"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: [cloudflare, workers, deno, denodeploy, wasm]
published: true
---

# Cloudflare Workersのメモリ制約

Cloudflare Workersは高速なエッジ実行環境ですが、メモリ容量に厳しい制約があります。有料プラン（Workers Paid）であっても、メモリ上限は基本的に128MBです。

さらに、Cloudflare Workersは同一インスタンス（Isolate）内で複数のリクエストが並行処理され、メモリ空間が共有されます。そのため、高解像度画像の変換やアニメーション画像の処理など、メモリを消費する処理を行うと上限に達しやすく、安定した実行が困難です。

# Deno Deployの特徴と課題

Deno Deployは無料プランでも1インスタンスあたり768MBのメモリが利用できます。また無料プランのCPU上限もCloudflareWorkersのような、リクエストにつき10msのような単位ではなく、月あたりの合計稼働時間になるので、重い処理も安心です。

- Deno Deploy Builds Reference

https://docs.deno.com/deploy/reference/builds/

768MBのメモリがあれば、画像変換ライブラリやWebAssemblyを用いた処理、アニメーション画像の展開なども余裕を持って実行できます。

一方で、Deno Deployの実行リージョンは北米や欧州に限られており、日本リージョンが用意されていません。日本国内から直接アクセスするとネットワーク遅延が大きくなる点が課題です。

# CloudflareでDeno Deployをキャッシュする構成

重い処理を行うDeno Deployをオリジンとし、前段にCloudflareを配置してレスポンスをキャッシュすることで、双方の欠点を補えます。

1. クライアントからCloudflareへアクセス
2. Cloudflareにキャッシュが存在すれば即座に返却（国内エッジから高速配信）
3. キャッシュがない場合のみDeno Deployへリクエストを転送
4. Deno Deploy（768MBメモリ）で画像処理を実行
5. Cloudflareが処理結果をエッジにキャッシュし、クライアントへ返却

初回アクセス時のみDeno Deployのリージョンによる遅延が発生しますが、2回目以降は世界各地のCloudflareエッジからキャッシュが返されるため、リージョンの遅延問題は解消されます。

```
[Client]
   │
   ▼
[Cloudflare CDN] ──(キャッシュあり)──> 高速レスポンス
   │ (キャッシュなし)
   ▼
[Deno Deploy (768MB RAM)] ──> 画像最適化・重い処理
```

# CloudflareのDNSプロキシ機能

CloudflareのDNSプロキシは、DNS登録したドメインへの全通信をCloudflareのグローバルネットワーク経由にするリバースプロキシ機能です。

通常、DNSはオリジンサーバーのアドレスをそのままクライアントに返します。これに対し、プロキシを有効にするとCloudflareのエッジIPアドレスが返されるようになります。これにより、クライアントとDeno Deployの間に世界各地のCloudflareエッジサーバーが自動的に介在します。

主なメリットは以下の通りです。

- CDNキャッシュの自動適用: レスポンスヘッダーやルールに従い、エッジでコンテンツをキャッシュして最寄りのPOPから高速配信
- Workersのコード不要: プログラムの記述やメンテナンスを行わずに、DNS設定の切り替えのみでCDNを利用可能
- オリジンの保護: オリジンのURLやIPを隠蔽し、DDoS攻撃の遮断やSSL/TLS証明書の自動管理をエッジ側で実施

海外リージョンに置かれたDeno Deployの前にCloudflareのDNSプロキシを挟むことで、コードを書くことなく日本国内からの高速配信環境を構築できます。

# 画像最適化リポジトリ

Deno Deploy上で指定した画像を最適化するリポジトリを公開しています。アニメーションGIFやWebP、AVIF、JPEG XL（JXL）など、メモリ消費の大きいフォーマットの変換にも対応しています。中で使っているライブラリはHTMLの画像変換も可能ですが、ここでは紹介しません。

https://github.com/SoraKumo001/deno-image-convert

リポジトリを指定してデプロイすればそのまま使えます。

## DNS（Cloudflareプロキシ）によるキャッシュ設定

CloudflareのDNSプロキシを利用してキャッシュを構築する手順です。


### 1. Deno Deployにカスタムドメインを追加

Deno Deployのダッシュボード（Settings -> Domains）で、使用したいドメイン（例: image.example.com）を登録します。

### 2. Cloudflare DNSでCNAMEレコードを登録

CloudflareのDNS設定画面でCNAMEレコードを追加し、プロキシステータスを有効にします。

| タイプ | 名前 | ターゲット | プロキシステータス |
| --- | --- | --- | --- |
| CNAME | image | <your-app>.deno.dev | プロキシ済み（Proxied） |

プロキシステータスを有効にすることで、アクセスがCloudflareのグローバルCDNを経由するようになります。

### 3. キャッシュの制御

Cloudflareエッジでキャッシュを保持させるには、以下のいずれかの方法を用います。

- レスポンスヘッダーによる制御
Deno DeployのHTTPレスポンスにCache-Controlを含めます。

```http
Cache-Control: public, max-age=31536000, s-maxage=31536000
```

- Cache Rulesによる制御
Cloudflareダッシュボードの「Caching」→「Cache Rules」でルールを作成し、該当ホスト名に対するEdge TTLを設定します。これにより、オリジンの実装を変更することなくエッジにキャッシュさせることができます。

# まとめ

Cloudflare Workersのメモリ128MB制限により困難だった画像変換や重い処理も、768MBのメモリが使えるDeno Deployに逃がし、CloudflareのDNSプロキシでキャッシュすることで解決できます。Workersのコードを書くことなく、エッジの高速配信と十分なメモリリソースを両立できる構成です。
