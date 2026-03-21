# WebUI描画のファイル構成の最適化の検証

## ステータス: 完了

## 背景

現在のWebUI静的ファイル構成は以下の通り:

```
static/
├── broadcast.html          (117行) - 配信合成ページ
├── index.html              (422行) - 管理UI
├── css/
│   ├── broadcast.css       (545行)
│   └── index.css           (300行)
├── js/
│   ├── avatar-renderer.js  (544行) - VRMアバター（ES Module）
│   ├── broadcast-main.js   (1625行) - broadcast.htmlのメインロジック
│   ├── index-app.js        (2098行) - index.htmlのメインロジック
│   ├── panel-ui.js         (43行)  - パネル描画共通関数
│   └── lib/
│       ├── api-client.js   (35行)  - fetch ラッパー
│       └── text-variables.js (39行) - テキスト変数展開
合計: 約5,770行（HTML+CSS+JS）
```

## 現状の問題点

### 1. broadcast-main.js が肥大化（1,625行）
1つのファイルに以下の全機能が混在:
- 音量管理・リップシンク同期
- 共通スタイル適用（applyCommonStyle: 175行）
- ライティング適用
- 設定適用（applySettings）
- 字幕表示・フェード
- トピックパネル
- TODO表示
- WebSocket接続・メッセージハンドラ（150行の巨大switch）
- アバターストリーム
- ウィンドウキャプチャ（スナップショットポーリング含む）
- カスタムテキスト
- 子パネル
- フローティング設定パネル（スキーマ取得・フィールドレンダリング・保存）
- 編集モード（ドラッグ・リサイズ・スナップガイド・キー操作）
- レイアウト保存（editSave）
- 初期化

### 2. index-app.js が肥大化（2,098行）
1つのファイルに以下の全機能が混在:
- タブ切替・ユーティリティ（showToast, showModal, escHtml等）
- 音量制御
- ステータス更新
- ウィンドウキャプチャ管理
- カスタムテキスト管理
- 子パネル管理
- キャラクター設定（ルール・感情・BlendShape編集）
- プロンプトレイヤー表示
- 視聴者メモ編集
- 配信言語設定
- サウンド（TTS・BGM・YouTube DL）
- トピック管理
- DB閲覧
- スクリーンショット
- ライティングプリセット
- TODO管理
- チャットログ
- Markdownレンダリング
- レイアウト設定UI
- 素材ファイル管理
- WebSocket接続

### 3. broadcast.htmlにインラインスクリプトが残っている
- console.logキャプチャ（32行）
- 背景画像ローダー（10行）

### 4. 共有ロジックの重複
- broadcast-main.jsとindex-app.jsの両方にキャプチャ・カスタムテキスト関連のコードがある（用途は異なるが概念は同じ）
- applyCommonStyle等の共通関数がbroadcast-main.jsに閉じている

## 最適化方針

### 方針A: 機能別にJSファイルを分割（推奨）

バンドラー（Vite等）は導入せず、`<script>`タグによる分割のみで対応する。理由:
- プロジェクトの規模的にバンドラーはオーバーキル
- CDN（Three.js）はimportmapで読み込み済みで変更不要
- サーバー再起動時に自動反映される現行運用と相性が良い

#### broadcast-main.js の分割案

| 分割先ファイル | 行数目安 | 内容 |
|---|---|---|
| `js/broadcast/style-utils.js` | ~200 | applyCommonStyle, setBgOpacity, _hexToRgba, _loadGoogleFont |
| `js/broadcast/settings.js` | ~100 | applySettings, _applyLighting |
| `js/broadcast/panels.js` | ~150 | 字幕(show/fade), トピック, TODO |
| `js/broadcast/websocket.js` | ~160 | connectWS, メッセージハンドラ |
| `js/broadcast/capture.js` | ~120 | キャプチャレイヤー, スナップショットポーリング |
| `js/broadcast/custom-text.js` | ~60 | カスタムテキストレイヤー |
| `js/broadcast/child-panel.js` | ~70 | 子パネル |
| `js/broadcast/settings-panel.js` | ~200 | フローティング設定パネル（スキーマ・レンダリング・保存） |
| `js/broadcast/edit-mode.js` | ~400 | ドラッグ・リサイズ・スナップ・editSave |
| `js/broadcast/init.js` | ~100 | init(), グローバル変数宣言 |

→ 合計10ファイル（1ファイル60〜400行、平均150行）

#### index-app.js の分割案

| 分割先ファイル | 行数目安 | 内容 |
|---|---|---|
| `js/admin/utils.js` | ~120 | switchTab, showToast, showModal, esc, escHtml, setStatus, apiラッパー |
| `js/admin/volume.js` | ~70 | onVolume, onSyncDelay, loadVolumes |
| `js/admin/status.js` | ~30 | refreshStatus |
| `js/admin/capture.js` | ~100 | キャプチャソース管理UI |
| `js/admin/custom-text.js` | ~60 | カスタムテキスト管理UI |
| `js/admin/child-panel.js` | ~60 | 子パネル管理UI |
| `js/admin/character.js` | ~250 | キャラクター設定（ルール・感情・BlendShape） |
| `js/admin/language.js` | ~80 | 配信言語設定 |
| `js/admin/layers.js` | ~160 | プロンプトレイヤー・視聴者メモ |
| `js/admin/sound.js` | ~120 | BGM・YouTube DL |
| `js/admin/topic.js` | ~130 | トピック管理 |
| `js/admin/db.js` | ~80 | DB閲覧 |
| `js/admin/todo.js` | ~160 | TODO管理 |
| `js/admin/chat.js` | ~80 | チャットログ |
| `js/admin/debug.js` | ~60 | スクリーンショット |
| `js/admin/lighting.js` | ~80 | ライティングプリセット |
| `js/admin/layout.js` | ~120 | レイアウト設定UI・共通プロパティ |
| `js/admin/files.js` | ~80 | 素材ファイル管理 |
| `js/admin/markdown.js` | ~80 | Markdownレンダリング |
| `js/admin/websocket.js` | ~40 | WebSocket接続 |
| `js/admin/init.js` | ~40 | 初期化 |

→ 合計21ファイル（1ファイル30〜250行、平均100行）

### 方針B: ES Modulesで分割

`type="module"` + `import/export` で分割する。メリット:
- 依存関係が明確（暗黙のグローバル変数に頼らない）
- 名前空間の衝突が起きない

デメリット:
- 現状のグローバル関数ベース（onclick="..."等）との互換性が崩れる
- index.htmlのonclick属性を全てaddEventListenerに書き換える必要がある（422行のHTMLに大量のonclick）
- avatar-renderer.js（既にES Module）以外は全て非モジュール → 移行コストが大きい

**結論: 方針Aが現実的。将来的にBに移行する余地は残す。**

### 方針C: バンドラー（Vite）導入

メリット:
- HMR（ホットリロード）で開発効率UP
- Tree shaking、minification
- TypeScript対応が容易

デメリット:
- ビルドステップが必要（現行はファイル直接配信）
- post-commit hookの再起動フローと相性が悪い
- Node.js依存が増える
- プロジェクトの規模（5,800行のJS）に対してオーバーキル

**結論: 現時点では不要。JSが1万行を超えたら再検討。**

## 実装ステップ（方針A採用時）

### Phase 1: broadcast-main.js の分割
1. `static/js/broadcast/` ディレクトリ作成
2. 共通ユーティリティ（style-utils.js）を切り出し
3. 機能単位で順次分割（panels → capture → custom-text → child-panel → settings-panel → edit-mode → websocket → settings → init）
4. broadcast.htmlの`<script>`タグを更新
5. broadcast.htmlのインラインスクリプトを外部ファイルに移動
6. 全機能テスト

### Phase 2: index-app.js の分割
1. `static/js/admin/` ディレクトリ作成
2. utils.js（共通ユーティリティ）を切り出し
3. タブ単位で順次分割
4. index.htmlの`<script>`タグを更新
5. 全機能テスト

### Phase 3: 共有コードの統合
1. lib/に共通関数を追加（必要に応じて）
2. 重複コードの共通化

## リスク

- **グローバル変数の依存関係**: 現状は全関数がグローバルスコープにあり、読み込み順序が重要。分割時に順序を間違えると動かなくなる
- **onclick属性との互換**: HTMLのonclick="funcName()"は関数がグローバルでないと動かない。方針Aなら問題なし
- **キャッシュ**: ブラウザキャッシュで古いファイルが使われる可能性 → ?v= パラメータで対応
- **テストの難しさ**: フロントエンドの自動テストがないため、手動テストが必要

## 判断基準

- 1ファイル300行以下を目安（大きな機能は400行まで許容）
- 各ファイルは1つの責務に集中
- ファイル名から内容が推測できること
- 既存のonclick属性はそのまま維持（HTMLの変更を最小限に）
