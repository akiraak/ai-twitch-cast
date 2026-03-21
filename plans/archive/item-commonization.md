# プレビューアプリ アイテム共通化と機能追加プラン

## ステータス: 計画中

## 背景

broadcast.htmlには8種類のアイテムが存在するが、それぞれの実装がバラバラで以下の問題がある:

1. **DB保存パターンが不統一**: `overlay.*` settingsキー / `custom_texts`テーブル / `capture_windows`テーブル / インラインCSS（保存なし）
2. **保存漏れバグ**: subtitle（positionのみzIndex）、topic（maxWidth/titleFontSize欠落）、version（fontSize/stroke/format欠落）
3. **プロパティの格差**: 背景色・角丸・ふち枠・文字色・パディングなどが一部アイテムにしかない
4. **dev-activityが編集不可**: `data-editable`属性なし、DB保存なし
5. **JS `editSave()`がハードコード**: アイテムごとに個別の保存ロジック

## 現在のアイテム一覧

| アイテム | DB保存先 | data-editable | 表示ON/OFF | 背景設定 | 文字設定 |
|----------|----------|---------------|------------|----------|----------|
| avatar | `overlay.avatar.*` | ○ | × | × | × |
| subtitle | `overlay.subtitle.*` | ○（zIndexのみ保存） | × | bgOpacityのみ | fontSizeのみ |
| todo | `overlay.todo.*` | ○ | × | bgOpacityのみ | fontSize/titleFontSize |
| topic | `overlay.topic.*` | ○ | × | bgOpacityのみ | titleFontSize |
| version | `overlay.version.*` | ○ | visible | bgOpacityのみ | fontSize/stroke |
| dev-activity | なし（インラインCSS） | × | × | ハードコード | ハードコード |
| capture | `capture_windows`テーブル | ○ | visible | × | × |
| custom-text | `custom_texts`テーブル | ○ | visible | bgOpacityのみ | fontSize |

## ゴール

TODO.mdの要件:
- **表示**: ON/OFF
- **配置**: XY座標、WHサイズ、Z値
- **背景**: 色、透明度、角丸、ふち枠の有無と色とサイズと透明度
- **文字**: テキスト、色、サイズ、ふち枠の色とサイズと透明度、パディングサイズ

## 方針

### 段階的移行（既存機能を壊さない）

Phase 1-5で既存DB構造を維持しつつ共通プロパティ追加・JS/CSS統一を先行実施。
Phase 6-7で`broadcast_items`統合テーブルへ全アイテムを移行し、旧テーブル・旧APIを廃止する。

Phase 1-5を先にやる理由:
- 共通プロパティ追加やバグ修正はすぐにユーザー価値を届けられる
- DB統合は大規模変更で全レイヤーに影響するため、先にJS/CSSを統一しておくと移行がスムーズ
- Phase 2のITEM_REGISTRYパターンがPhase 6-7の統合APIと自然に接続する

### 共通プロパティモデル

全アイテムに以下の共通プロパティを追加:

```json
{
  "visible": true,
  "positionX": 0, "positionY": 0,
  "width": 100, "height": 100,
  "zIndex": 10,
  "bgColor": "rgba(20,20,35,1)",
  "bgOpacity": 0.85,
  "borderRadius": 8,
  "borderEnabled": false,
  "borderColor": "rgba(255,255,255,0.5)",
  "borderSize": 1,
  "borderOpacity": 1.0,
  "textColor": "#e0e0e0",
  "fontSize": 1.0,
  "textStrokeColor": "rgba(0,0,0,0.8)",
  "textStrokeSize": 0,
  "textStrokeOpacity": 0.8,
  "padding": 8
}
```

## 実装ステップ

### Phase 1: 共通プロパティのDB保存基盤

**目的**: 全アイテムの共通プロパティをDBに保存できるようにする

#### 1-1. overlay.py にデフォルト値辞書を統一

現在 `_OVERLAY_DEFAULTS` に各アイテムのデフォルトがバラバラに定義されている。これに共通プロパティを追加する。

```python
_COMMON_DEFAULTS = {
    "visible": 1,
    "positionX": 0, "positionY": 0,
    "width": 50, "height": 50,
    "zIndex": 10,
    "bgColor": "rgba(20,20,35,1)",
    "bgOpacity": 0.85,
    "borderRadius": 8,
    "borderEnabled": 0,
    "borderColor": "rgba(255,255,255,0.5)",
    "borderSize": 1,
    "borderOpacity": 1.0,
    "textColor": "#e0e0e0",
    "fontSize": 1.0,
    "textStrokeColor": "rgba(0,0,0,0.8)",
    "textStrokeSize": 0,
    "textStrokeOpacity": 0.8,
    "padding": 8,
}
```

各アイテムのデフォルトは `_COMMON_DEFAULTS` をベースにオーバーライド。

#### 1-2. GET /api/overlay/settings を拡張

全アイテムの共通プロパティを返すように拡張。既存のキーがDBにない場合はデフォルト値を返す（後方互換性維持）。

#### 1-3. POST /api/overlay/settings を拡張

新しい共通プロパティキーも受け付けて保存できるようにする。

#### 1-4. dev-activityをDB保存対応

`overlay.dev_activity.*` キーを新設。インラインCSSからDB値を参照するように変更。

**変更ファイル**: `scripts/routes/overlay.py`
**テスト**: `tests/test_overlay.py` に共通プロパティの保存・取得テスト追加

---

### Phase 2: broadcast.html JS共通化

**目的**: `applySettings()` と `editSave()` を統一的なループに変更

#### 2-1. 共通applyLayout関数

```javascript
function applyCommonStyle(el, settings, prefix) {
    // 配置
    if (settings[prefix + '.positionX'] !== undefined) el.style.left = settings[prefix + '.positionX'] + '%';
    if (settings[prefix + '.positionY'] !== undefined) el.style.top = settings[prefix + '.positionY'] + '%';
    if (settings[prefix + '.width'] !== undefined) el.style.width = settings[prefix + '.width'] + '%';
    if (settings[prefix + '.height'] !== undefined) el.style.height = settings[prefix + '.height'] + '%';
    if (settings[prefix + '.zIndex'] !== undefined) el.style.zIndex = settings[prefix + '.zIndex'];
    // 表示
    if (settings[prefix + '.visible'] !== undefined) {
        el.style.display = Number(settings[prefix + '.visible']) ? '' : 'none';
    }
    // 背景
    el.style.setProperty('--bg-color', settings[prefix + '.bgColor'] || 'rgba(20,20,35,1)');
    el.style.setProperty('--bg-opacity', settings[prefix + '.bgOpacity'] ?? 0.85);
    el.style.borderRadius = (settings[prefix + '.borderRadius'] ?? 8) + 'px';
    // ふち枠
    if (Number(settings[prefix + '.borderEnabled'])) {
        const bc = settings[prefix + '.borderColor'] || 'rgba(255,255,255,0.5)';
        const bs = settings[prefix + '.borderSize'] || 1;
        el.style.border = bs + 'px solid ' + bc;
    } else {
        el.style.border = 'none';
    }
    // 文字
    el.style.color = settings[prefix + '.textColor'] || '#e0e0e0';
    el.style.fontSize = (settings[prefix + '.fontSize'] || 1.0) + 'vw';
    // テキスト縁取り
    const strokeSize = settings[prefix + '.textStrokeSize'] || 0;
    if (strokeSize > 0) {
        const strokeColor = settings[prefix + '.textStrokeColor'] || 'rgba(0,0,0,0.8)';
        el.style.webkitTextStroke = strokeSize + 'px ' + strokeColor;
        el.style.paintOrder = 'stroke fill';
    } else {
        el.style.webkitTextStroke = '';
    }
    // パディング
    el.style.padding = (settings[prefix + '.padding'] ?? 8) + 'px';
}
```

#### 2-2. editSave() の統一

アイテム定義レジストリを作り、ループで全アイテムを保存:

```javascript
const ITEM_REGISTRY = [
    { id: 'avatar-area', prefix: 'avatar', hasSize: true },
    { id: 'subtitle', prefix: 'subtitle', hasSize: false, special: 'subtitle' },
    { id: 'todo-panel', prefix: 'todo', hasSize: true },
    { id: 'topic-panel', prefix: 'topic', hasSize: false },
    { id: 'version-panel', prefix: 'version', hasSize: false },
    { id: 'dev-activity-panel', prefix: 'dev_activity', hasSize: false },
];

function editSave() {
    const payload = {};
    for (const item of ITEM_REGISTRY) {
        const el = document.getElementById(item.id);
        if (!el) continue;
        const p = item.prefix;
        payload[p + '.positionX'] = parseFloat(el.style.left);
        payload[p + '.positionY'] = parseFloat(el.style.top);
        if (item.hasSize) {
            payload[p + '.width'] = parseFloat(el.style.width);
            payload[p + '.height'] = parseFloat(el.style.height);
        }
        payload[p + '.zIndex'] = parseInt(el.style.zIndex) || 0;
        payload[p + '.visible'] = el.style.display !== 'none' ? 1 : 0;
    }
    // capture/custom-text は個別APIに保存（既存ロジック維持）
    fetch('/api/overlay/settings', { method: 'POST', body: JSON.stringify(payload), ... });
}
```

#### 2-3. dev-activityをdata-editable対応

`#dev-activity-panel` に `data-editable="dev_activity"` を追加し、ドラッグ・リサイズ可能にする。

**変更ファイル**: `static/js/broadcast-main.js`, `static/broadcast.html`

---

### Phase 3: CSS統一

**目的**: インラインスタイルをCSS変数ベースに統一

#### 3-1. 共通CSS変数

```css
[data-editable] {
    position: absolute;
    /* 共通プロパティはCSS変数で制御 */
    background: var(--item-bg-color, rgba(20,20,35,1));
    opacity: 1; /* bgOpacityはbackgroundのalpha値で制御 */
    border-radius: var(--item-border-radius, 8px);
    color: var(--item-text-color, #e0e0e0);
    padding: var(--item-padding, 8px);
}
```

#### 3-2. version-panelのインラインスタイル除去

現在HTMLにインラインで書かれているスタイルをCSS変数ベースに移行。

#### 3-3. dev-activity-panelのインラインスタイル除去

同上。CSSクラスに移行。

**変更ファイル**: `static/css/broadcast.css`, `static/broadcast.html`

---

### Phase 4: Web UI設定パネル

**目的**: 各アイテムの共通プロパティをWeb UIから編集可能にする

#### 4-1. 配信画面タブにアイテム設定セクション

各アイテムの折りたたみカードに以下を追加:
- **表示ON/OFF**: トグルスイッチ
- **背景色**: カラーピッカー
- **背景透明度**: スライダー（0〜1）
- **角丸**: スライダー（0〜30px）
- **ふち枠**: ON/OFF + 色 + サイズ + 透明度
- **文字色**: カラーピッカー
- **文字サイズ**: スライダー（0.3〜5vw）
- **文字縁取り**: 色 + サイズ + 透明度
- **パディング**: スライダー（0〜30px）

#### 4-2. リアルタイムプレビュー

Web UIのスライダー変更 → `/api/overlay/preview` でbroadcast.htmlに即座反映（保存は「保存」ボタンで）。

#### 4-3. アイテム固有プロパティの維持

共通プロパティに加えて、各アイテム固有のプロパティ（subtitle.fadeDuration、version.format等）は個別セクションに残す。

**変更ファイル**: `static/index.html`, `static/js/index-app.js`

---

### Phase 5: 保存漏れバグ修正 + 全アイテムのvisible対応

**目的**: 既存の保存漏れを修正し、全アイテムにvisible切替を追加

#### 5-1. editSave() 保存漏れ修正

- subtitle: position（bottom）、fontSize、maxWidth、fadeDuration、bgOpacity を保存
- topic: maxWidth、titleFontSize を保存
- version: fontSize、strokeSize、strokeOpacity、format を保存

#### 5-2. 全アイテムにvisible対応

avatar、subtitle、todo、topicにもvisibleプロパティを追加。DB保存し、broadcast.htmlで display:none 切替。

#### 5-3. Web UIのプレビュー画面変更がリアルタイム反映されない問題

TODO.md「プレビューで位置をずらしたりZ値を変更してもWEbUIにリアルタイムで反映されない」の対応。
editSave()時にWebSocketでsettings_updateを送信し、Web UIのスライダー値を更新。

**変更ファイル**: `static/js/broadcast-main.js`, `scripts/routes/overlay.py`

---

### Phase 6: broadcast_items テーブル作成 + 固定アイテム移行

**目的**: 全アイテムの統合DBテーブルを作成し、固定アイテム（overlay.* settings）を移行する

#### 6-1. broadcast_items テーブル設計

```sql
CREATE TABLE IF NOT EXISTS broadcast_items (
    id TEXT PRIMARY KEY,           -- 'avatar', 'subtitle', 'todo', 'topic', 'version', 'dev_activity', 'customtext:{n}', 'capture:{n}'
    type TEXT NOT NULL,            -- 'avatar','subtitle','todo','topic','version','dev_activity','custom_text','capture'
    label TEXT NOT NULL DEFAULT '',
    -- 配置（共通）
    x REAL NOT NULL DEFAULT 0,
    y REAL NOT NULL DEFAULT 0,
    width REAL NOT NULL DEFAULT 50,
    height REAL NOT NULL DEFAULT 50,
    z_index INTEGER NOT NULL DEFAULT 10,
    visible INTEGER NOT NULL DEFAULT 1,
    -- 背景（共通）
    bg_color TEXT NOT NULL DEFAULT 'rgba(20,20,35,1)',
    bg_opacity REAL NOT NULL DEFAULT 0.85,
    border_radius REAL NOT NULL DEFAULT 8,
    border_enabled INTEGER NOT NULL DEFAULT 0,
    border_color TEXT NOT NULL DEFAULT 'rgba(255,255,255,0.5)',
    border_size REAL NOT NULL DEFAULT 1,
    border_opacity REAL NOT NULL DEFAULT 1.0,
    -- 文字（共通）
    text_color TEXT NOT NULL DEFAULT '#e0e0e0',
    font_size REAL NOT NULL DEFAULT 1.0,
    text_stroke_color TEXT NOT NULL DEFAULT 'rgba(0,0,0,0.8)',
    text_stroke_size REAL NOT NULL DEFAULT 0,
    text_stroke_opacity REAL NOT NULL DEFAULT 0.8,
    padding REAL NOT NULL DEFAULT 8,
    -- アイテム固有プロパティ（JSON）
    properties TEXT NOT NULL DEFAULT '{}',
    created_at TEXT,
    updated_at TEXT
);
```

`properties` JSONにアイテム固有データを格納:
- subtitle: `{"fadeDuration": 3, "maxWidth": 62, "bottom": 7.4}`
- version: `{"format": "Chobi v{version} ({date})", "strokeSize": 2, "strokeOpacity": 0.8}`
- todo: `{"titleFontSize": 1.5}`
- topic: `{"maxWidth": 31, "titleFontSize": 1.25}`
- custom-text: `{"content": "テキスト内容"}`
- capture: `{"window_name": "Terminal", "source_id": "cap_1"}`
- lighting: `{"brightness": 1.0, "contrast": 1.0, "temperature": 0.1, ...}` ※ lightingもアイテム化するか要検討

#### 6-2. マイグレーション関数

db.pyに `migrate_overlay_to_items()` を追加:

```python
def migrate_overlay_to_items(db):
    """overlay.* settings → broadcast_items に移行（初回起動時に自動実行）"""
    # 既に移行済みなら何もしない（broadcast_itemsにavatarが存在するか確認）
    existing = db.execute("SELECT id FROM broadcast_items WHERE id='avatar'").fetchone()
    if existing:
        return

    # overlay.* settings を読み込み
    for item_type in ['avatar', 'subtitle', 'todo', 'topic', 'version', 'dev_activity']:
        settings = _load_overlay_section(db, item_type)
        # 共通プロパティとproperties JSONに分離
        common, props = _split_common_and_specific(settings, item_type)
        db.execute("""
            INSERT INTO broadcast_items (id, type, label, x, y, width, height, z_index, visible,
                bg_color, bg_opacity, ..., properties, created_at, updated_at)
            VALUES (?, ?, ?, ..., ?, datetime('now'), datetime('now'))
        """, (item_type, item_type, ITEM_LABELS[item_type], ...))

    # 移行後、overlay.* settingsキーは残す（フォールバック用、Phase 7で削除）
```

起動時に `_ensure_tables()` 内で自動実行。

#### 6-3. 統合API追加（旧API互換維持）

新エンドポイント:

```
GET  /api/items                    → 全アイテム一覧
GET  /api/items/{id}               → アイテム取得
PUT  /api/items/{id}               → アイテム更新（共通プロパティ + properties）
POST /api/items/{id}/layout        → レイアウトのみ更新（broadcast.htmlドラッグ保存用）
POST /api/items/{id}/visibility    → 表示ON/OFF切替
```

旧API `/api/overlay/settings` は互換レイヤーとして維持:
- GET: broadcast_itemsテーブルから読み込み、従来のフラット形式に変換して返す
- POST: 受け取ったデータをbroadcast_itemsに書き込む

#### 6-4. broadcast-main.js を新APIに対応

Phase 2のITEM_REGISTRYのeditSave()を新API `/api/items/{id}/layout` に切替:

```javascript
async function editSave() {
    for (const item of ITEM_REGISTRY) {
        const el = document.getElementById(item.id);
        if (!el) continue;
        const layout = extractLayout(el, item);
        await apiClient.post(`/api/items/${item.prefix}/layout`, layout);
    }
    // capture/custom-text も同じAPIに統一
    for (const el of document.querySelectorAll('[data-editable^="capture:"]')) { ... }
    for (const el of document.querySelectorAll('[data-editable^="customtext:"]')) { ... }
}
```

**変更ファイル**: `src/db.py`, `scripts/routes/overlay.py`（新: `scripts/routes/items.py`）, `static/js/broadcast-main.js`
**テスト**: `tests/test_db.py` にマイグレーション・CRUDテスト、`tests/test_api_items.py` 新規

---

### Phase 7: 動的アイテム移行 + 旧構造廃止

**目的**: custom_texts・capture_windowsを統合テーブルに移行し、旧テーブル・旧APIを廃止する

#### 7-1. custom_texts → broadcast_items 移行

マイグレーション:
```python
def migrate_custom_texts_to_items(db):
    rows = db.execute("SELECT * FROM custom_texts").fetchall()
    for row in rows:
        item_id = f"customtext:{row['id']}"
        properties = json.dumps({"content": row["content"]})
        db.execute("""
            INSERT OR IGNORE INTO broadcast_items
            (id, type, label, x, y, width, height, z_index, visible,
             font_size, bg_opacity, properties, created_at, updated_at)
            VALUES (?, 'custom_text', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (item_id, row["label"], row["x"], row["y"], row["width"], row["height"],
              row["z_index"], row["visible"], row["font_size"], row["bg_opacity"],
              properties, row["created_at"]))
```

旧API互換:
- `/api/overlay/custom-texts` → broadcast_itemsから `type='custom_text'` をフィルタ
- `/api/overlay/custom-texts/{id}` → `/api/items/customtext:{id}` にリダイレクト

#### 7-2. capture_windows → broadcast_items 移行 + 二重管理解消

現在の問題:
- `capture_windows`テーブル: 永続的な保存済み設定
- `capture.sources` settingsキー: アクティブセッション状態
- 両方にレイアウトが書き込まれ、同期ロジックが複雑

解消方針:
- broadcast_itemsを唯一の真のソースにする
- アクティブ/非アクティブはメモリ管理（state.pyのactive_capturesディクショナリ）
- DB保存はbroadcast_itemsのみ

```python
def migrate_capture_windows_to_items(db):
    rows = db.execute("SELECT * FROM capture_windows").fetchall()
    for row in rows:
        item_id = f"capture:{row['id']}"
        properties = json.dumps({"window_name": row["window_name"]})
        db.execute("""
            INSERT OR IGNORE INTO broadcast_items
            (id, type, label, x, y, width, height, z_index, visible,
             properties, created_at, updated_at)
            VALUES (?, 'capture', ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (item_id, row["label"], row["x"], row["y"], row["width"], row["height"],
              row["z_index"], row["visible"], properties, row["created_at"]))
    # capture.sources settingsキーを削除
    db.execute("DELETE FROM settings WHERE key = 'capture.sources'")
```

capture.py の書き換え:
- `_load_capture_sources()` / `_save_capture_sources()` → broadcast_items CRUDに置換
- `upsert_capture_window()` / `update_capture_window_layout()` → `update_item()` に置換
- レイアウト変更時は broadcast_items のみ更新（二重書き込み廃止）

#### 7-3. 旧テーブル・旧API廃止

1. `overlay.*` settingsキーを削除（DBから `DELETE FROM settings WHERE key LIKE 'overlay.%'`）
2. `custom_texts` テーブルをDROP
3. `capture_windows` テーブルをDROP
4. `capture.sources` settingsキーを削除
5. 旧API `/api/overlay/custom-texts/*` を廃止（一定期間は互換レイヤー維持後に削除）
6. db.pyから旧CRUD関数を削除（`add_custom_text`, `upsert_capture_window` 等）

#### 7-4. Web UI・broadcast.html の最終調整

- 全APIコールを `/api/items/*` に統一
- custom-textの作成: `POST /api/items` with `type: 'custom_text'`
- captureの作成: キャプチャ開始時にbroadcast_itemsにも自動追加

**変更ファイル**: `src/db.py`, `scripts/routes/capture.py`, `scripts/routes/overlay.py`, `scripts/routes/items.py`, `static/js/broadcast-main.js`, `static/js/index-app.js`, `static/index.html`
**テスト**: `tests/test_db.py` マイグレーションテスト、`tests/test_api_items.py` 拡張、旧テスト更新

---

## Phase別の優先度と実装順

| Phase | 優先度 | 理由 |
|-------|--------|------|
| Phase 1 | 高 | DBの基盤がないと他が進まない |
| Phase 5 | 高 | 既存バグ修正を含む（Phase 1直後に実施） |
| Phase 2 | 高 | JS共通化が全体の品質に直結 |
| Phase 4 | 高 | ユーザーが実際に使う設定UI |
| Phase 3 | 中 | CSSは見た目に影響するが機能には影響しない |
| Phase 6 | 中 | DB統合の基盤（Phase 1-5の成果物を統合テーブルに移行） |
| Phase 7 | 中 | 旧構造廃止（Phase 6完了後に実施） |

**推奨実装順**: Phase 1 → 5 → 2 → 4 → 3 → 6 → 7

Phase 1-5は独立して価値を届けられる。Phase 6-7はアーキテクチャ改善であり、Phase 1-5完了後にまとめて実施するのが効率的。

## リスク

1. **後方互換性**: 既存のDB値（`overlay.*`キー）を壊さないよう、新プロパティはデフォルト値つきで追加
2. **パフォーマンス**: settingsキーの増加によるDB読み書きの増加 → バッチ保存で対応
3. **Phase 6マイグレーション**: overlay.* settingsからbroadcast_itemsへの移行は起動時に自動実行。失敗時はフォールバック（旧settingsを読む）で安全に
4. **Phase 7のcapture二重管理解消**: capture.pyの大幅書き換えが必要。アクティブキャプチャのメモリ管理をstate.pyに移す設計変更を伴う
5. **subtitleの特殊配置**: 固定bottom+translateX中央配置は統合テーブル移行後も`properties`JSONで対応可能

## テスト方針

- `tests/test_overlay.py`: 共通プロパティのCRUDテスト（Phase 1-5）
- `tests/test_api_overlay.py`: APIエンドポイントのテスト（Phase 1-5）
- `tests/test_api_items.py`: 統合APIのテスト（Phase 6-7、新規作成）
- `tests/test_db.py`: マイグレーションテスト（Phase 6-7）
- 手動確認: broadcast.htmlで全アイテムの表示・編集・保存が正常に動作すること
