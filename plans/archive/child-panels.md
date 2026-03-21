# 子パネル（入れ子パネル）実装プラン

## ステータス: 完了

## 背景

現在のbroadcast_itemsはフラットな構造で、各パネルは独立して配置される。これを入れ子構造に拡張し、任意のパネルにテキストパネルを子として追加できるようにする。

### ユースケース
- アバターパネルにバージョンテキストを子パネルとして配置（名前、ステータス等）
- テキストパネルにさらに子テキストパネルを配置（複合レイアウト）
- どのパネルにも子パネルを追加可能（将来的にテキスト以外の子パネルも対応可能）

## 方針

### データモデル
- `broadcast_items`テーブルに`parent_id`カラムを追加（NULLならルートパネル）
- 子パネルの`x`, `y`は**親パネルからの相対座標（%）**
- 子パネルのIDは`child:{親ID}:{連番}`の形式
- 子パネルの`type`は`child_text`（まずはテキストのみ）

### レンダリング
- 親パネルのHTML要素内に子パネルのDOM要素を追加
- 子パネルは`position: absolute`で親パネル基準の相対配置
- 親パネルは`position: relative`（既存パネルは`position: absolute`なので、子パネル用に`overflow: visible`が必要かどうか検討）

### 編集
- 子パネルも`data-editable`属性を持ち、ドラッグ＆リサイズ可能
- 子パネルのドラッグは親パネル基準の相対座標で保存
- 右クリックメニューに「子パネルを追加」メニュー項目を追加
- 子パネルの右クリックメニューには「子パネルを削除」を追加

## 実装ステップ

### Step 1: DBスキーマ拡張
**ファイル:** `src/db.py`

1. `broadcast_items`テーブルに`parent_id`カラムを追加（マイグレーション）
   ```sql
   ALTER TABLE broadcast_items ADD COLUMN parent_id TEXT REFERENCES broadcast_items(id)
   ```
2. `_item_row_to_dict()`で`parent_id`フィールドを出力に含める
3. `get_broadcast_items()`に子アイテム取得のサポートを追加
   - `get_child_items(parent_id)` — 指定親の子アイテム一覧
4. `upsert_broadcast_item()`で`parent_id`を扱えるようにする
5. 子アイテム削除関数: `delete_child_item(item_id)`
6. 親パネル削除時に子パネルも連鎖削除（CASCADE的な処理）

### Step 2: API拡張
**ファイル:** `scripts/routes/overlay.py`（または`scripts/routes/items.py`）

1. `GET /api/items` — 子アイテムを`children`配列としてネストして返す
   ```json
   {
     "id": "avatar",
     "type": "avatar",
     "children": [
       {
         "id": "child:avatar:1",
         "type": "child_text",
         "parentId": "avatar",
         "positionX": 10,
         "positionY": 80,
         "content": "v1.0",
         ...
       }
     ]
   }
   ```
2. `POST /api/items/{parent_id}/children` — 子パネル追加
   - リクエスト: `{ "type": "child_text", "label": "...", "content": "..." }`
   - 連番IDを自動生成
   - レスポンス: 作成された子パネル情報
3. `PUT /api/items/{item_id}` — 子パネル更新（既存APIで対応可能）
4. `DELETE /api/items/{item_id}` — 子パネル削除
5. `POST /api/items/{item_id}/layout` — 子パネルレイアウト更新（既存APIで対応可能）

### Step 3: WebSocket通知
**ファイル:** `scripts/routes/overlay.py`

1. 子パネル追加時に`child_panel_add`イベントをブロードキャスト
2. 子パネル更新時に`child_panel_update`イベントをブロードキャスト
3. 子パネル削除時に`child_panel_remove`イベントをブロードキャスト
4. `settings_update`で子パネル情報も含める

### Step 4: broadcast.html — レンダリング
**ファイル:** `static/js/broadcast-main.js`

1. `addChildPanel(parentEl, childData)` 関数を追加
   - 親要素内に`div.child-panel`を作成
   - `data-editable="child:{parentId}:{id}"`属性を付与
   - `position: absolute`で親基準の相対配置
   - テキストコンテンツを表示
2. `removeChildPanel(childId)` 関数を追加
3. `applySettings()`で子パネルも適用
4. 初期化時（`init()`）にAPIから子パネル情報を取得してレンダリング
5. WebSocketイベントハンドラで`child_panel_add/update/remove`に対応

### Step 5: broadcast.html — 編集機能
**ファイル:** `static/js/broadcast-main.js`

1. 子パネルにも`setupEditable()`を適用（ドラッグ＆リサイズ可能）
2. 子パネルのドラッグ時の座標計算:
   - 親パネルの位置・サイズを基準に相対%を計算
   - `parentEl.getBoundingClientRect()`を使って変換
3. `editSave()`で子パネルのレイアウトも保存
   - 子パネルは`POST /api/items/{childId}/layout`で個別保存
4. 右クリックメニューの拡張:
   - 通常パネル右クリック → 「テキスト子パネルを追加」メニュー項目を追加
   - 子パネル右クリック → 「この子パネルを削除」メニュー項目を追加
5. 子パネルのスナップは親パネル内でのスナップ（親の端・中央に吸着）

### Step 6: broadcast.html — CSS
**ファイル:** `static/css/broadcast.css`

1. `.child-panel` スタイル定義
   - `position: absolute` （親パネル基準）
   - 共通スタイルプロパティ（背景・枠・テキスト色等）のCSS変数対応
   - 編集時のハイライト表示
2. 親パネル側の調整
   - 子パネルを含む親パネルは `position: relative`（既に`position: absolute`なので問題なし）
   - `overflow: visible` にするか `hidden` にするか → とりあえず `visible`（子パネルが親からはみ出してもOK）

### Step 7: 管理UI（index.html）
**ファイル:** `static/js/index-app.js`

1. パネル設定UIに子パネル一覧を表示
2. 子パネルの追加ボタン
3. 子パネルのラベル・コンテンツ編集
4. 子パネルの削除ボタン

### Step 8: テスト
**ファイル:** `tests/`

1. `test_db.py` — 子パネルのCRUDテスト
   - 子パネル作成・取得・更新・削除
   - 親パネル削除時の連鎖削除
   - `parent_id`のバリデーション
2. `test_api_items.py`（新規or既存拡張）— 子パネルAPIテスト
   - POST /api/items/{parent_id}/children
   - GET /api/items の children ネスト確認
   - DELETE /api/items/{child_id}

## 設計上の判断ポイント

### 子パネルの座標系
- **相対座標（%）**: 親パネルの左上を(0,0)、右下を(100,100)として%指定
- 親パネルがリサイズされても子パネルの相対位置が維持される
- DBの`x`, `y`カラムをそのまま使用（親ありなら相対、親なしなら絶対）

### 子パネルのサイズ
- 子パネルの`width`, `height`も親パネル基準の%指定
- デフォルト: `width: 50%, height: 20%`

### 入れ子の深さ
- Phase 1では**1階層のみ**（子パネルにさらに子は追加不可）
- 右クリックメニューの「子パネルを追加」は`parent_id`がNULLのパネルでのみ表示
- 将来的に再帰対応する場合はDB構造はそのまま使える

### 子パネルのスタイル継承
- 子パネルは独自のスタイルプロパティを持つ（親から継承しない）
- デフォルト値は小さめの設定（半透明背景、小さいフォント等）

### 子パネルのデフォルト値
```json
{
  "type": "child_text",
  "label": "テキスト",
  "content": "",
  "positionX": 5,
  "positionY": 75,
  "width": 90,
  "height": 20,
  "zIndex": 10,
  "visible": true,
  "bgColor": "rgba(0,0,0,0.5)",
  "bgOpacity": 0.5,
  "borderRadius": 4,
  "borderSize": 0,
  "fontSize": 0.8,
  "textColor": "#ffffff",
  "padding": 4
}
```

## リスク

1. **ドラッグ座標変換**: 親パネル基準の相対座標への変換が正確でないと位置ずれが起きる
   - 対策: `parentEl.getBoundingClientRect()`で正確に計算
2. **イベントバブリング**: 子パネルのクリック/ドラッグが親に伝播して意図しない動作
   - 対策: 子パネルのイベントで`e.stopPropagation()`
3. **保存順序**: 親と子の保存タイミングがずれると不整合
   - 対策: editSave()で親→子の順で保存
4. **パフォーマンス**: 大量の子パネルがある場合のレンダリング負荷
   - Phase 1では実用上問題なし（数個程度の想定）

## 実装順序の推奨

1. **Step 1 (DB)** → **Step 2 (API)** → **Step 8 (テスト)** でバックエンドを固める
2. **Step 6 (CSS)** → **Step 4 (レンダリング)** → **Step 3 (WebSocket)** でフロントを実装
3. **Step 5 (編集)** で編集機能を追加
4. **Step 7 (管理UI)** は最後に対応

全体で8ステップ、バックエンド3ステップ + フロントエンド4ステップ + テスト1ステップ。
