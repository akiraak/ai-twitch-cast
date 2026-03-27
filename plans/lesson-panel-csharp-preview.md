# C#プレビューから授業パネルデザインを操作可能にする

## 背景

授業パネル（タイトル・テキスト・進捗）のデザイン変更は現在Webブラウザの管理画面（index.html）からのみ可能。C#ネイティブアプリのコントロールパネル（control-panel.html）からも操作できるようにする。

### 現状のアーキテクチャ

```
[index.html 管理画面]  → POST /api/overlay/settings → DB保存
                         → broadcast_overlay(settings_update)
                         → [broadcast.html] applySettings()
```

- C#アプリの**control-panel.html**は400×720pxの右サイドパネル
- 既存タブ: Stream / Sound / Chat
- 既にPython API直接呼び出しの実績あり（Twitch API、Chat API）
- `serverUrl` 変数でAPIエンドポイントにアクセス可能

### 設計の選択肢

| 方式 | 長所 | 短所 |
|------|------|------|
| **A: Designタブ追加（スキーマ駆動）** | 既存UIパターンに統一、オフライン動作 | control-panel.htmlに新規コード追加 |
| B: iframe埋め込み | コード重複なし | 400pxでindex.htmlの横幅が足りない、スタイル不統一 |
| C: ブラウザで開くボタン | 最小実装 | C#プレビュー内での操作にならない |

→ **方式A**を採用。スキーマAPIで動的にコントロール生成し、コード量を最小化。

## 方針

1. control-panel.htmlに「Design」タブを追加
2. `/api/items/schema?item_id=xxx` からフィールド定義を取得し、動的にUI生成
3. `/api/overlay/settings` から現在値を取得してUIに反映
4. 変更時はデバウンスして `POST /api/overlay/settings` で保存（既存フロー経由でbroadcast.htmlに自動反映）
5. テスト表示/非表示ボタンも追加

## 実装ステップ

### Step 1: Designタブの枠組み（control-panel.html）

タブバーに「Design」タブを追加し、タブコンテンツ領域を作成。

```html
<button class="tab" data-tab="design">Design</button>

<div class="tab-content" id="tab-design">
  <div class="section" style="overflow-y:auto; flex:1;">
    <div class="section-title">授業パネル</div>
    <div id="designPanels"></div>
  </div>
</div>
```

### Step 2: スキーマ駆動のUI生成

起動時に以下を実行:
1. `GET /api/items/schema?item_id=lesson_title` でスキーマ取得
2. `GET /api/items/schema?item_id=lesson_text` でスキーマ取得
3. `GET /api/items/schema?item_id=lesson_progress` でスキーマ取得
4. `GET /api/overlay/settings` で現在値を取得
5. スキーマのgroupsからUI要素を動的生成（表示・配置グループはスキップ）

各フィールドタイプに対応するレンダラー:
- `slider` → `<input type="range">` + 値表示
- `color` → `<input type="color">`
- `toggle` → チェックボックス（既存volume-rowパターン流用）
- `select` → `<select>`

### Step 3: 設定の保存・反映

- スライダー/カラーピッカーの `oninput` で値をバッファ
- 200msデバウンスで `POST /api/overlay/settings` に送信
- 既存のWebSocketフローでbroadcast.htmlに自動反映（追加実装不要）

### Step 4: テスト表示ボタン

各パネルにテスト表示/非表示ボタンを配置:
- タイトル+進捗: `POST /api/debug/lesson-title` / `POST /api/debug/lesson-title/hide`
- テキスト: `POST /api/debug/lesson-text` / `POST /api/debug/lesson-text/hide`

### Step 5: CSS

control-panel.htmlの既存スタイルに合わせたDesignタブ用CSS:
- `.design-group`: グループヘッダー（背景/文字等）
- `.design-row`: 各コントロール行（volume-rowパターン踏襲）
- `.design-panel`: パネル折りたたみ（details/summary）

## 変更ファイル

| ファイル | 変更内容 |
|---------|----------|
| `win-native-app/WinNativeApp/control-panel.html` | Designタブ追加（HTML/CSS/JS） |

**1ファイルのみ**。バックエンドは既存API（スキーマ・設定・デバッグ）をそのまま利用。

## UI構成イメージ（400px幅）

```
[Stream] [Sound] [Chat] [Design]
─────────────────────────────────
LESSON PANELS

▸ タイトル（画面上部）
  [テスト表示] [非表示]

▸ テキスト（画面中央）
  [テスト表示] [非表示]

▸ 進捗（画面左）
  [テスト表示] [非表示]

────────── 背景 ──────────
  色       [■]
  透明度   ──●───── 0.70
  ぼかし   ────●─── 10
  角丸     ──●───── 8
  枠色     [■]
  枠透明度 ─●────── 0.40

────────── 文字 ──────────
  サイズ   ───●──── 1.6
  色       [■]
  フォント [▼ デフォルト]
  ...
```

※ パネルを選択すると、そのパネルの設定グループが展開される

## 追加実装: broadcast.htmlでのドラッグ/右クリック編集対応

初回プランではcontrol-panel.htmlにDesignタブを追加。
追加要件として、broadcast.htmlプレビュー上でも授業パネルをマウスで直接操作可能にした。

### 追加変更
- `data-fixed-layout` → `data-editable` + `data-managed-visibility`（位置はドラッグ可能、表示/非表示は授業モード制御）
- CSS: `transform`（中央寄せ用）と `pointer-events: none` を除去
- ITEM_REGISTRY に3パネルを追加（`skipVisible: true`）
- `applyCommonStyle` に `data-managed-visibility` チェック追加
- デフォルト位置を `_OVERLAY_DEFAULTS` に設定

## ステータス: 完了
