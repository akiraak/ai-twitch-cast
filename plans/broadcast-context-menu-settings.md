# 右クリックメニューからの設定編集機能

## ステータス: Phase 1-2 完了

## 背景

現在、broadcast.htmlの右クリックメニューには以下の3項目しかない:
- Z順序を変更
- テキスト子パネルを追加
- 子パネルを削除

一方、Web UI（index.html）には`_commonPropsHTML()`による豊富な設定コントロール（表示/配置/背景/文字など）が存在する。
これらの設定をbroadcast.html上でも右クリックメニューから直接編集できるようにしたい。
さらに、C#ネイティブアプリ側のプレビューでも同じ設定項目を表示したい。

## 方針

**サーバ駆動スキーマAPI** + **フローティング設定パネル**を採用する。

- サーバが「この項目にはどんな設定項目があるか」をJSONスキーマとして返す
- クライアント（Web UI / broadcast.html / C#アプリ）はスキーマに従ってUIを動的生成
- 設定項目の追加・変更はサーバ側のみで完結し、全クライアントに自動反映

### サーバ駆動スキーマAPIを採用する理由

- **マルチクライアント対応**: Web UI（index.html）、broadcast.html、C#ネイティブアプリの3箇所が同一のスキーマを共有。サーバ側で設定項目を追加するだけで全クライアントに反映
- **単一の定義ソース**: フィールド定義（label, type, min/max/step, options）がサーバ側Python1箇所に集約。JS側やC#側にフィールド定義のハードコードが不要
- **`_commonPropsHTML()`の二重管理解消**: index.htmlのハードコードUIもスキーマAPIベースに置き換え可能

## 設計

### 1. サーバ側: 設定スキーマAPI

#### エンドポイント
```
GET /api/items/schema
GET /api/items/schema?item_id={item_id}
```

パラメータなしで全アイテムタイプの共通スキーマを返す。
`item_id`指定で、そのアイテムの固有プロパティも含めたスキーマを返す。

#### レスポンス例（`GET /api/items/schema?item_id=subtitle`）
```json
{
  "item_id": "subtitle",
  "item_type": "subtitle",
  "label": "字幕",
  "groups": [
    {
      "title": "固有設定",
      "fields": [
        { "key": "bottom", "label": "下からの距離 (%)", "type": "slider", "min": 0, "max": 30, "step": 0.1 },
        { "key": "maxWidth", "label": "最大幅 (%)", "type": "slider", "min": 20, "max": 90, "step": 1 },
        { "key": "fadeDuration", "label": "フェード (秒)", "type": "slider", "min": 1, "max": 10, "step": 0.5 }
      ]
    },
    {
      "title": "表示",
      "fields": [
        { "key": "visible", "label": "表示", "type": "toggle" }
      ]
    },
    {
      "title": "配置",
      "fields": [
        { "key": "positionX", "label": "X位置 (%)", "type": "slider", "min": 0, "max": 100, "step": 0.5 },
        { "key": "positionY", "label": "Y位置 (%)", "type": "slider", "min": 0, "max": 100, "step": 0.5 },
        { "key": "width", "label": "幅 (%)", "type": "slider", "min": 5, "max": 100, "step": 0.5 },
        { "key": "height", "label": "高さ (%)", "type": "slider", "min": 5, "max": 100, "step": 0.5 },
        { "key": "zIndex", "label": "Z順序", "type": "slider", "min": 0, "max": 100, "step": 1 }
      ]
    },
    {
      "title": "背景",
      "fields": [
        { "key": "bgColor", "label": "色", "type": "color" },
        { "key": "bgOpacity", "label": "透明度", "type": "slider", "min": 0, "max": 1, "step": 0.05 },
        { "key": "backdropBlur", "label": "ぼかし (px)", "type": "slider", "min": 0, "max": 30, "step": 1 },
        { "key": "borderRadius", "label": "角丸 (px)", "type": "slider", "min": 0, "max": 30, "step": 1 },
        { "key": "borderSize", "label": "枠サイズ", "type": "slider", "min": 0, "max": 10, "step": 0.5 },
        { "key": "borderColor", "label": "枠色", "type": "color" },
        { "key": "borderOpacity", "label": "枠透明度", "type": "slider", "min": 0, "max": 1, "step": 0.05 }
      ]
    },
    {
      "title": "文字",
      "fields": [
        { "key": "fontFamily", "label": "フォント", "type": "select", "options": [["", "デフォルト"], ["Noto Sans JP", "Noto Sans JP"], ["Yu Gothic UI", "Yu Gothic UI"], ["Meiryo", "メイリオ"], ["Yu Mincho", "游明朝"], ["BIZ UDPGothic", "BIZ UDPゴシック"], ["M PLUS Rounded 1c", "M PLUS Rounded 1c"], ["Kosugi Maru", "小杉丸ゴシック"], ["monospace", "等幅"]] },
        { "key": "fontSize", "label": "サイズ (vw)", "type": "slider", "min": 0.3, "max": 5, "step": 0.05 },
        { "key": "textColor", "label": "色", "type": "color" },
        { "key": "textAlign", "label": "水平揃え", "type": "select", "options": [["left", "左"], ["center", "中央"], ["right", "右"]] },
        { "key": "verticalAlign", "label": "垂直揃え", "type": "select", "options": [["top", "上"], ["center", "中央"], ["bottom", "下"]] },
        { "key": "textStrokeSize", "label": "縁取りサイズ", "type": "slider", "min": 0, "max": 10, "step": 0.5 },
        { "key": "textStrokeColor", "label": "縁取り色", "type": "color" },
        { "key": "textStrokeOpacity", "label": "縁取り透明度", "type": "slider", "min": 0, "max": 1, "step": 0.05 },
        { "key": "padding", "label": "内余白 (px)", "type": "slider", "min": 0, "max": 30, "step": 1 }
      ]
    }
  ]
}
```

#### サポートするフィールドtype
| type | 説明 | 追加パラメータ |
|------|------|----------------|
| `slider` | スライダー + 数値入力 | `min`, `max`, `step` |
| `color` | カラーピッカー | - |
| `toggle` | ON/OFFスイッチ | - |
| `select` | ドロップダウン | `options`: `[[value, label], ...]` |
| `text` | テキスト入力 | `maxlength`（任意） |

### 2. サーバ側: スキーマ定義の実装場所

`scripts/routes/items.py`にスキーマ定義を追加。
既存の`_OVERLAY_DEFAULTS`（overlay.py）と近い場所に置く。

```python
# scripts/routes/items.py に追加

# 共通プロパティスキーマ（全アイテム共通）
_COMMON_SCHEMA_GROUPS = [
    {
        "title": "表示",
        "fields": [
            {"key": "visible", "label": "表示", "type": "toggle"},
        ]
    },
    {
        "title": "配置",
        "fields": [
            {"key": "positionX", "label": "X位置 (%)", "type": "slider", "min": 0, "max": 100, "step": 0.5},
            {"key": "positionY", "label": "Y位置 (%)", "type": "slider", "min": 0, "max": 100, "step": 0.5},
            {"key": "width", "label": "幅 (%)", "type": "slider", "min": 5, "max": 100, "step": 0.5},
            {"key": "height", "label": "高さ (%)", "type": "slider", "min": 5, "max": 100, "step": 0.5},
            {"key": "zIndex", "label": "Z順序", "type": "slider", "min": 0, "max": 100, "step": 1},
        ]
    },
    # ... 背景・文字グループも同様
]

# アイテムタイプ別の固有スキーマ
_ITEM_SPECIFIC_SCHEMA = {
    "avatar": [
        {"title": "固有設定", "fields": [
            {"key": "scale", "label": "スケール", "type": "slider", "min": 0.1, "max": 3, "step": 0.05},
        ]}
    ],
    "subtitle": [
        {"title": "固有設定", "fields": [
            {"key": "bottom", "label": "下からの距離 (%)", "type": "slider", "min": 0, "max": 30, "step": 0.1},
            {"key": "maxWidth", "label": "最大幅 (%)", "type": "slider", "min": 20, "max": 90, "step": 1},
            {"key": "fadeDuration", "label": "フェード (秒)", "type": "slider", "min": 1, "max": 10, "step": 0.5},
        ]}
    ],
    "todo": [
        {"title": "固有設定", "fields": [
            {"key": "titleFontSize", "label": "タイトルサイズ (vw)", "type": "slider", "min": 0.5, "max": 3, "step": 0.05},
        ]}
    ],
    "topic": [
        {"title": "固有設定", "fields": [
            {"key": "maxWidth", "label": "最大幅 (%)", "type": "slider", "min": 10, "max": 60, "step": 1},
            {"key": "titleFontSize", "label": "タイトルサイズ (vw)", "type": "slider", "min": 0.5, "max": 3, "step": 0.05},
        ]}
    ],
    "custom_text": [
        {"title": "コンテンツ", "fields": [
            {"key": "label", "label": "ラベル", "type": "text"},
            {"key": "content", "label": "テキスト", "type": "text"},
        ]}
    ],
}

# アイテムラベル
_ITEM_LABELS = {
    "avatar": "アバター",
    "subtitle": "字幕",
    "todo": "TODO",
    "topic": "トピック",
    "custom_text": "カスタムテキスト",
    "capture": "キャプチャ",
    "child_text": "子テキスト",
}

def _get_item_type(item_id: str) -> str:
    if item_id.startswith("customtext:"): return "custom_text"
    if item_id.startswith("capture:"): return "capture"
    if item_id.startswith("child:"): return "child_text"
    return item_id

@router.get("/api/items/schema")
async def get_item_schema(item_id: str | None = None):
    if item_id:
        item_type = _get_item_type(item_id)
        specific = _ITEM_SPECIFIC_SCHEMA.get(item_type, [])
        item = db.get_broadcast_item(item_id)
        label = (item or {}).get("label", _ITEM_LABELS.get(item_type, item_id))
        return {
            "item_id": item_id,
            "item_type": item_type,
            "label": label,
            "groups": specific + _COMMON_SCHEMA_GROUPS,
        }
    # パラメータなし: 共通スキーマのみ
    return {"groups": _COMMON_SCHEMA_GROUPS}
```

### 3. broadcast.html: フローティング設定パネル

#### UIレイアウト

配信画面を遮らないフローティングパネル。ドラッグで移動可能。

```
┌─────────────────────────────────────────────────┐
│                                                 │
│           配信画面                               │
│                                                 │
│     ┌──── 設定: アバター ────[×]┐               │
│     │ ▼ 固有設定                │               │
│     │   スケール  ═══●═══ 1.0  │               │
│     │ ▼ 表示                    │               │
│     │   □ ON                    │               │
│     │ ▶ 配置                    │  ←折り畳み可  │
│     │ ▶ 背景                    │               │
│     │ ▶ 文字                    │               │
│     └───────────────────────────┘               │
│                                                 │
└─────────────────────────────────────────────────┘
```

**特徴:**
- **フローティング**: position: fixed、ドラッグでどこでも移動可能
- **コンパクト**: 幅280px程度。グループは折り畳み式（`<details>`）で必要な部分だけ開く
- **閉じる**: ×ボタン、Escキー、別パネル右クリック時に自動切替
- **非遮蔽**: 配信画面上に浮いているが、小さいので邪魔になりにくい
- **リアルタイム反映**: 値変更 → デバウンス200ms → API保存 → 即座に配信画面に反映
- **スキーマキャッシュ**: 初回取得したスキーマはメモリにキャッシュ。同じitem_typeなら再リクエスト不要

#### 動作フロー

1. ユーザーがパネルを右クリック
2. コンテキストメニューに「設定を編集...」項目を追加表示
3. クリックすると:
   - `GET /api/items/schema?item_id={id}`でスキーマを取得（キャッシュあればスキップ）
   - `GET /api/items/{item_id}`で現在値を取得
   - スキーマに基づいてフローティング設定パネルを動的生成して表示
4. 値変更 → デバウンス200ms → `PUT /api/items/{item_id}` → WebSocket `settings_update`
5. 別のパネルを右クリック → 設定パネルの中身を切り替え

#### UI生成関数（broadcast-main.js）

スキーマのフィールドtypeに応じてHTMLを生成:

```javascript
// スキーマキャッシュ（item_type → schema）
const _schemaCache = {};

async function openSettingsPanel(itemId) {
  // スキーマ取得（キャッシュ優先）
  const itemType = itemId.startsWith('customtext:') ? 'custom_text'
                 : itemId.startsWith('capture:') ? 'capture'
                 : itemId.startsWith('child:') ? 'child_text'
                 : itemId;
  let schema = _schemaCache[itemType];
  if (!schema) {
    schema = await (await fetch(`/api/items/schema?item_id=${encodeURIComponent(itemId)}`)).json();
    _schemaCache[itemType] = schema;
  }
  // 現在値取得
  const values = await (await fetch(`/api/items/${encodeURIComponent(itemId)}`)).json();
  // パネル生成
  renderFloatingPanel(schema, values, itemId);
}

function renderFieldHTML(field, value) {
  switch (field.type) {
    case 'slider':
      const v = value ?? field.min;
      return `<div class="sp-row">
        <label>${field.label}</label>
        <input type="range" min="${field.min}" max="${field.max}" step="${field.step}"
               value="${v}" data-key="${field.key}">
        <input type="number" min="${field.min}" max="${field.max}" step="${field.step}"
               value="${v}" data-key="${field.key}">
      </div>`;
    case 'color':
      return `<div class="sp-row">
        <label>${field.label}</label>
        <input type="color" value="${value ?? '#000000'}" data-key="${field.key}">
      </div>`;
    case 'toggle':
      return `<div class="sp-row">
        <label>${field.label}</label>
        <input type="checkbox" ${value ? 'checked' : ''} data-key="${field.key}">
      </div>`;
    case 'select':
      const opts = field.options.map(([v, l]) =>
        `<option value="${v}" ${value === v ? 'selected' : ''}>${l}</option>`
      ).join('');
      return `<div class="sp-row">
        <label>${field.label}</label>
        <select data-key="${field.key}">${opts}</select>
      </div>`;
    case 'text':
      return `<div class="sp-row">
        <label>${field.label}</label>
        <input type="text" value="${value ?? ''}" data-key="${field.key}">
      </div>`;
  }
}
```

### 4. C#アプリ側の対応

C#ネイティブアプリ（`win-native-app/`）でも同じスキーマAPIを利用して設定UIを生成。

#### 方式
- WebView2内のbroadcast.htmlが設定パネルを表示する場合 → JS側の実装がそのまま使える
- C#ネイティブUIで設定パネルを表示する場合 → `GET /api/items/schema?item_id={id}`を呼び、WinFormsまたはWPFコントロールを動的生成

#### C#側の実装イメージ
```csharp
// スキーマからWinFormsコントロールを動的生成
var schema = await httpClient.GetFromJsonAsync<ItemSchema>($"/api/items/schema?item_id={itemId}");
foreach (var group in schema.Groups) {
    var groupBox = new GroupBox { Text = group.Title };
    foreach (var field in group.Fields) {
        switch (field.Type) {
            case "slider":
                var trackBar = new TrackBar { Minimum = field.Min, Maximum = field.Max };
                groupBox.Controls.Add(trackBar);
                break;
            case "color":
                // ColorDialogボタン
                break;
            // ...
        }
    }
    settingsPanel.Controls.Add(groupBox);
}
```

**注意**: C#側の具体的な実装は本プランのスコープ外。スキーマAPIさえ完成すればC#側は独立して実装可能。

### 5. editSave()との競合防止

broadcast.htmlにはドラッグ終了時にDOM状態からAPI保存する`editSave()`が存在する。
設定パネルからの変更と競合しないよう対策が必要。

**問題シナリオ:**
1. 設定パネルでpositionXを50%に変更 → API送信中
2. 直後にドラッグ終了 → `editSave()`がDOMから古い位置を読み取って上書き

**対策:**
- 設定パネルからの変更時に`_saving`フラグを立てる（既存の仕組みを再利用）
- `_saving`中はWebSocket `settings_update`のDOM適用をスキップ（既存動作）
- 設定パネルで値を変更したら、対応するDOM要素のスタイルも即座に更新する（APIレスポンスを待たない）
- `editSave()`実行時、設定パネルが開いている場合は設定パネルの値を優先

### 6. index.html側の統一

`_commonPropsHTML()`をスキーマAPIベースに置き換え。

```javascript
// index-app.js（変更後）
let _cachedCommonSchema = null;

async function loadSchema() {
  if (!_cachedCommonSchema) {
    _cachedCommonSchema = await (await fetch('/api/items/schema')).json();
  }
  return _cachedCommonSchema;
}

function _commonPropsHTML(section) {
  // スキーマからHTML生成（既存のrow/slider/color/toggle/select関数を再利用）
  if (!_cachedCommonSchema) return ''; // 初回ロード前は空
  return _cachedCommonSchema.groups.map(group => {
    const header = groupHeader(group.title);
    const rows = group.fields.map(f => renderFieldRow(section, f)).join('');
    return header + rows;
  }).join('');
}
```

既存の`row()`, `slider()`, `color()`, `toggle()`, `select()`ヘルパー関数はそのまま活用し、
フィールド定義だけをスキーマAPIから読む形にすることで変更量を最小化する。

## 実装ステップ

### Phase 1: サーバ側スキーマAPI
1. `scripts/routes/items.py`にスキーマ定義（共通 + タイプ別）を追加
2. `GET /api/items/schema`エンドポイントを実装
3. テスト追加（`tests/test_api_items.py`）

### Phase 2: broadcast.html フローティング設定パネル
1. 右クリックメニューに「設定を編集...」項目を追加
2. フローティング設定パネルのHTML/CSS追加
   - ドラッグ移動、グループ折り畳み（`<details>`）、スクロール
   - 幅280px、position: fixed、z-index: 10002
3. スキーマAPIからUI動的生成（`renderFieldHTML()`）
4. 現在値の取得（`GET /api/items/{item_id}`）と反映
5. 値変更→デバウンス200ms→`PUT /api/items/{item_id}`→WebSocket反映
6. `editSave()`との競合防止（`_saving`フラグ拡張）
7. スキーマキャッシュ（同一item_typeは再取得しない）
8. 既存のZ順序ダイアログは残す（クイック操作として有用）

### Phase 3: index.html側のスキーマAPI統一
1. `_commonPropsHTML()`をスキーマAPIベースに書き換え
2. 起動時に`GET /api/items/schema`でスキーマ取得→キャッシュ
3. 動作確認（index.htmlの設定UIが従来通り機能すること）

### Phase 4（任意）: C#アプリ側の設定パネル
- C#ネイティブアプリからスキーマAPIを呼び出して設定UIを動的生成
- または、WebView2内のbroadcast.htmlの設定パネルをそのまま利用

### Phase 5（任意）: 右クリックメニューのクイック設定
- よく使う設定（表示ON/OFF、背景透明度）を右クリックメニューに直接配置
- 設定パネルを開かずに1クリックで変更可能にする

## 影響範囲

### 変更するファイル
| ファイル | 変更内容 |
|---------|----------|
| `scripts/routes/items.py` | スキーマ定義 + `GET /api/items/schema`エンドポイント追加 |
| `tests/test_api_items.py` | スキーマAPIのテスト追加 |
| `static/js/broadcast-main.js` | フローティング設定パネルの生成・操作ロジック追加 |
| `static/css/broadcast.css` | フローティングパネルのスタイル追加 |
| `static/broadcast.html` | フローティングパネルのコンテナ要素追加 |
| `static/js/index-app.js` | `_commonPropsHTML()`をスキーマAPIベースに書き換え（Phase 3） |

### 変更しないもの
- DB構造
- 既存のWebSocketイベント形式
- 既存のItems CRUD API（`GET/PUT/POST/DELETE /api/items/*`）
- 既存の右クリックメニュー項目（Z順序、子パネル追加/削除）

## リスク・注意点

- **スキーマキャッシュ戦略**: クライアント側でitem_typeごとにキャッシュする。スキーマはサーバ再起動時しか変わらないため、ページロード時に1回取得すれば十分。必要ならキャッシュTTLを設定
- **editSave()競合**: 設定パネルの値変更がDOM適用される前にeditSave()が走ると古い値で上書きされる。`_saving`フラグで防止するが、タイミングによっては1フレーム遅れる可能性がある
- **配信中の操作**: 設定パネル操作でWebSocket `settings_update`が頻繁に発火すると配信画面がちらつく可能性。デバウンスで緩和するが、カラーピッカーのドラッグ操作などは注意
- **Z順序ダイアログ**: 設定パネルにもzIndexスライダーがあるが、既存のクイック操作（±ボタン）も残す。ユーザーは状況に応じて使い分ける
- **index.html統一のタイミング**: Phase 3でindex.htmlをスキーマベースに書き換える際、スキーマAPI取得が非同期になるため、ページ初期化順序に注意が必要（スキーマ取得完了後にUI生成）
