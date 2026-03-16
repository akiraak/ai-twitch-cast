# コントロールパネル タブ化

## 背景
現在の `control-panel.html` は全セクション（配信制御・キャプチャ・音量・ログ）が縦に並んでいる。
画面が狭く、特にログエリアが圧迫される。タブ化して整理する。

## タブ構成

| タブ名 | 内容 |
|--------|------|
| **Stream** | 配信制御（Go Live / Stop）+ キャプチャ（ウィンドウ選択・開始・一覧）+ ログ |
| **Sound** | 音量スライダー（Master / Voice / BGM）+ 音量メーター |
| **Chat** | 将来のチャット機能用（現時点はプレースホルダー「Coming soon」） |

## 方針

- **HTML/CSS/JSのみの変更**（`control-panel.html` 1ファイルで完結）
- C#側（MainForm.cs）の変更は不要。WebView2メッセージの仕組みはそのまま
- タブ切替はCSS class toggle + JS。ページ遷移やiframeは使わない
- タブバーはページ上部に固定。各タブの中身は `.tab-content` divで切替
- 現在のセクション構造（`.section`）はタブ内でそのまま活用
- ログエリアはStreamタブの下部に配置（flex-growで残り領域を埋める）
- タブの選択状態はセッション中のみ保持（localStorage不要）

## 実装ステップ

### 1. タブバーHTML追加
```html
<div class="tab-bar">
  <button class="tab active" data-tab="stream">Stream</button>
  <button class="tab" data-tab="sound">Sound</button>
  <button class="tab" data-tab="chat">Chat</button>
</div>
```

### 2. 既存セクションをタブコンテンツでラップ
```html
<div class="tab-content active" id="tab-stream">
  <!-- 配信制御セクション -->
  <!-- キャプチャセクション -->
  <!-- ログセクション（flex） -->
</div>
<div class="tab-content" id="tab-sound">
  <!-- 音量セクション -->
</div>
<div class="tab-content" id="tab-chat">
  <!-- プレースホルダー -->
</div>
```

### 3. CSS追加
- `.tab-bar`: flexbox、上部固定、ボーダー下線
- `.tab`: VS Code風の控えめなタブスタイル
- `.tab.active`: アクセントカラーの下線 or 背景色変更
- `.tab-content`: 非表示デフォルト、`display: none`
- `.tab-content.active`: `display: flex; flex-direction: column; flex: 1`

### 4. JS追加
- タブクリック時に `active` classを切替
- 初期表示は Stream タブ

## C#側への影響
- なし。`postMessage` / `addEventListener` のインターフェースは変更しない
- `action` の種類も変わらない

## ステータス: 完了
