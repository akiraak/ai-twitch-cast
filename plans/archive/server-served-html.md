# broadcast.html / control-panel.html をサーバから受け取るメリットとデメリットの検討

## ステータス: 検討中

## 背景

現在、C#ネイティブアプリ（`win-native-app/`）は2つのWebView2を使用している。

| ファイル | 現在の配信元 | 場所 |
|---------|------------|------|
| **broadcast.html** | Python FastAPIサーバー | `static/broadcast.html` → `/broadcast?token=...` |
| **control-panel.html** | C#アプリ内蔵HTTPサーバー | `win-native-app/WinNativeApp/control-panel.html` → `localhost:9090/panel` |

つまり、**broadcast.htmlは既にサーバから受け取っている**が、**control-panel.htmlはC#アプリにバンドルされている**。

この検討は主に「control-panel.htmlもサーバ側に移すべきか」と「現状のbroadcast.htmlのサーバ配信を維持すべきか」の2点に焦点を当てる。

## 現行アーキテクチャ

```
Python Web Server (port 8080)
  ├─ /broadcast?token=XXX → broadcast.html を返す
  ├─ /ws/broadcast        → WebSocket（overlay/TTS/BGM制御）
  ├─ /static/*            → CSS/JS/画像等
  └─ /resources/*         → VRM/BGM等リソース

C# Native App (port 9090)
  ├─ /panel               → control-panel.html を返す（ローカルファイル読み込み）
  ├─ /api/capture/*       → キャプチャ制御API
  ├─ /api/stream/*        → 配信制御API
  └─ /ws/control          → WebSocket（パネル↔C#間通信）

WebView2 #1: http://localhost:8080/broadcast?token=XXX  (1280x720)
WebView2 #2: http://localhost:9090/panel                (400x720)
```

## 検討パターン

### パターンA: 現状維持（broadcast=サーバ、control-panel=ローカル）

現在の構成をそのまま維持する。

### パターンB: 両方サーバから配信

control-panel.htmlもPython FastAPIサーバーから配信する。

### パターンC: 両方ローカル（C#アプリにバンドル）

broadcast.htmlもC#アプリにバンドルし、ローカルから読み込む。

---

## パターンA: 現状維持

### メリット
- **変更不要** — 動いているものを壊すリスクがゼロ
- **broadcast.htmlのホットリロード** — サーバ側でファイルを更新すればC#アプリ再ビルド不要で反映可能
- **control-panel.htmlの独立性** — C#アプリのIPC（`postMessage`）と密結合しており、ローカル配信が自然

### デメリット
- **二重のHTTPサーバー** — Python（8080）とC#（9090）の両方が必要
- **HTMLファイルの管理場所が分散** — `static/` と `win-native-app/WinNativeApp/` の2箇所

---

## パターンB: 両方サーバから配信

control-panel.htmlをPythonサーバーに移動し、`/control-panel` 等のルートで配信する。

### メリット

1. **HTMLの一元管理**
   - 全HTMLファイルが `static/` に集約される
   - 変更・デプロイがサーバ側の操作だけで完結

2. **C#アプリ再ビルド不要のUI更新**
   - control-panel.htmlのUI改修時もC#アプリを再ビルド・再配布する必要がない
   - WSL2上でファイルを編集 → ブラウザリロードで即反映

3. **開発体験の向上**
   - ブラウザで直接 `http://localhost:8080/control-panel` を開いてデバッグできる
   - C#アプリを起動しなくてもUI開発が可能（一部機能はモック必要）

4. **サーバ側の状態・APIに直接アクセス**
   - control-panelからPythonサーバーのAPIを直接呼べる（現在はC#経由でプロキシ）
   - 例: 音量設定のDB保存、キャラクター設定変更など

5. **C#アプリの軽量化**
   - C#アプリからHTTPサーバーの `/panel` 配信機能を削除可能
   - C#アプリの責務がキャプチャ・配信パイプラインに集中する

### デメリット

1. **サーバ依存の強化**
   - Pythonサーバーが落ちると配信画面だけでなくコントロールパネルも使えなくなる
   - 現状: サーバダウン時もC#のパネルは生きているので配信停止等の操作は可能

2. **IPC通信の複雑化**
   - control-panel.htmlはC#の `window.chrome.webview.postMessage()` を使ってC#アプリと通信している
   - サーバ配信にすると、control-panel → Python WebSocket → C# API という間接経路になる
   - または、control-panelは引き続きC#の9090ポートにも接続する必要がある（二重接続）

3. **ネットワーク遅延の増加**
   - ローカルファイル読み込み（数ms）→ HTTP経由（10-50ms）
   - パネル操作のレスポンスに若干の影響（体感は微小）

4. **セキュリティ考慮**
   - control-panelに配信制御（開始/停止）機能がある
   - トークン認証やアクセス制限の追加が必要

5. **C#アプリとの結合度は下がらない**
   - control-panelはC#アプリのキャプチャ・配信機能と密結合
   - HTMLの配信元をサーバに移しても、C#アプリのAPIを呼ぶ必要は変わらない

---

## パターンC: 両方ローカル（C#バンドル）

broadcast.htmlもC#アプリにバンドルし、ローカルファイルとして読み込む。

### メリット

1. **サーバ非依存で画面表示**
   - Pythonサーバーが起動していなくても配信画面が表示される
   - サーバ障害時も最低限の画面は維持（データは空だが表示は可能）

2. **起動順序の自由度**
   - C#アプリを先に起動してもbroadcast.htmlが表示される
   - 現状: サーバが先に起動していないとbroadcast.htmlのロードに失敗する

3. **ネットワーク不要**
   - HTML読み込み自体はネットワークを経由しない

### デメリット

1. **broadcast.htmlの更新にC#アプリ再ビルドが必要**
   - **これが最大の問題** — broadcast.htmlは頻繁に更新される（レイアウト調整、オーバーレイ変更等）
   - WSL2で編集 → Windows側でビルド → 再起動、という手順が毎回必要

2. **リソースパスの問題**
   - broadcast.htmlは `/static/` や `/resources/` のアセットを参照している
   - ローカルファイルの場合、これらのパスの解決方法を変更する必要がある
   - VRMモデル、BGM、画像などの大量リソースをC#アプリにバンドルするのは非現実的

3. **WebSocket接続先の指定**
   - broadcast.htmlは起動時にサーバの `/ws/broadcast` に接続する
   - ローカルファイルだと接続先URLの指定方法が変わる（クエリパラメータ等で渡す必要あり）

4. **二重管理の発生**
   - `static/broadcast.html`（サーバ用）と `win-native-app/` のコピーが二重管理になる
   - または `static/` を廃止してC#アプリ側に統一するが、Web UIからの配信画面プレビューが不可能になる

---

## 総合評価

| 観点 | A: 現状維持 | B: 両方サーバ | C: 両方ローカル |
|------|:---------:|:----------:|:------------:|
| 変更コスト | ◎ なし | ○ 中程度 | △ 大きい |
| UI更新の容易さ | ○ | ◎ | △ |
| サーバ障害耐性 | ○ | △ | ◎ |
| 開発体験 | ○ | ◎ | △ |
| アーキテクチャの整合性 | △ 分散 | ◎ 統一 | ○ 統一 |
| IPC複雑度 | ○ | △ 複雑化 | ○ |
| C#アプリの軽量化 | △ | ○ | △ |

## 推奨

**短期的にはパターンA（現状維持）を推奨。**

理由:
- 現状の構成で問題なく動作している
- control-panel.htmlはC#アプリの `postMessage` IPCと密結合しており、サーバ側に移すメリットよりもIPC通信の複雑化デメリットが大きい
- broadcast.htmlは既にサーバ配信されており、頻繁なUI更新に対応できている

**中長期的にはパターンBへの段階的移行を検討。**

条件:
- control-panelの機能がC#固有のIPC（postMessage）から独立できる場合
  - 例: C#のキャプチャ・配信制御APIがHTTP REST APIとして十分に整備される
  - 例: control-panelがPython WebSocket経由でC# APIをプロキシする形に変更
- C#アプリの責務を「キャプチャ + FFmpegパイプライン + API」に限定し、UIロジックをサーバ側に寄せる方針が固まった場合

**パターンCは非推奨。**
- broadcast.htmlの更新頻度が高く、毎回C#アプリを再ビルドする運用コストが大きすぎる
- リソース参照の問題解決が複雑
