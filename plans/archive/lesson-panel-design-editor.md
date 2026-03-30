# 授業パネルデザイン編集機能

## 背景

管理画面の「授業パネル」セクションで、授業タイトルパネルと授業の流れ（進捗）パネルのデザイン（背景色・透明度・フォント・枠線など）を変更できるようにする。

### 現状

| パネル | 管理画面コントロール | settings.js対応 | `_OVERLAY_DEFAULTS` | `fixed_items` | テスト表示ボタン |
|--------|---------------------|-----------------|---------------------|---------------|-----------------|
| 授業テキスト | maxHeight, lineHeight + 共通(背景/文字) | ✅ | ✅ | ✅ | ✅ |
| 授業進捗 | titleFontSize, itemFontSize + 共通(背景/文字) | ✅ | ✅ | ✅ | ❌ |
| **授業タイトル** | **なし** | **❌** | **❌** | **❌** | **❌** |

- 授業テキストパネルは既に完成（共通プロパティ + 固有設定 + テスト表示）
- 授業進捗パネルは共通プロパティ（背景/文字）は動的注入されるが、テスト表示ボタンがない
- **授業タイトルパネルは設定システムに未登録で、デザイン変更が一切できない**

### 共通プロパティの仕組み

管理画面では `_injectCommonProps()` が `.panel-item[data-section]` に以下のグループを自動注入する：
- **表示**: visible トグル
- **配置**: X/Y位置, 幅/高さ, Z順序
- **背景**: 色, 透明度, ぼかし, 角丸, 枠
- **文字**: フォント, サイズ, 色, 揃え, 縁取り, 内余白

授業パネルは `data-skip-groups="表示,配置"` で表示/配置をスキップし、背景と文字グループのみ表示する（CSSで位置固定のため）。

broadcast.html側では `applyCommonStyle()` が `data-fixed-layout` 属性を見て位置プロパティをスキップする。

## 方針

既存パターン（授業テキストパネル）に完全に倣い、最小限の変更で実装する。

## 実装ステップ

### Step 1: 授業タイトルパネルをバックエンドに登録

**`scripts/routes/overlay.py`**
- `_OVERLAY_DEFAULTS` に `lesson_title` を追加：
  ```python
  "lesson_title": _make_item_defaults({
      "bgOpacity": 0.7, "backdropBlur": 10,
      "fontSize": 1.6,
      "bgColor": "#0a0a1e", "borderColor": "#7c4dff", "borderOpacity": 0.4,
      "textColor": "#ffffff",
  }),
  ```
- `fixed_items` セットに `"lesson_title"` を追加

**`scripts/routes/items.py`**
- `_ITEM_SPECIFIC_SCHEMA` に `lesson_title` を追加（固有設定なし、共通プロパティで十分）：
  ```python
  "lesson_title": [],
  ```
- `_SCHEMA_ITEM_LABELS` に追加：`"lesson_title": "授業タイトル"`

### Step 2: 管理画面にUIを追加

**`static/index.html`** — 「授業パネル」カード内に授業タイトルセクションを追加：
```html
<div class="lesson-subgroup panel-item" data-section="lesson_title" data-skip-groups="表示,配置">
  <div class="lesson-subgroup-title">タイトルパネル（画面上部）</div>
  <div class="panel-body">
    <!-- 共通プロパティ（背景/文字）は _injectCommonProps() で自動注入 -->
    <div class="layout-row" style="margin-top:6px;">
      <button onclick="fetch('/api/debug/lesson-title',{method:'POST'})" ...>テスト表示</button>
      <button onclick="fetch('/api/debug/lesson-title/hide',{method:'POST'})" ...>非表示</button>
    </div>
  </div>
</div>
```

授業進捗セクションにもテスト表示ボタンを追加。

### Step 3: デバッグAPIエンドポイントを追加

**`scripts/routes/overlay.py`**
- `POST /api/debug/lesson-title` — タイトルパネルのテスト表示（`lesson_status` イベント送信）
- `POST /api/debug/lesson-title/hide` — タイトルパネルの非表示
- `POST /api/debug/lesson-progress` — 進捗パネルのテスト表示（サンプルセクション付き）
- `POST /api/debug/lesson-progress/hide` — 進捗パネルの非表示

### Step 4: broadcast.html側で設定を適用

**`static/js/broadcast/settings.js`**
- `lesson_title` セクションの処理を追加（`applyCommonStyle` + 固有プロパティ）：
  ```javascript
  if (s.lesson_title) {
    const ltp = document.getElementById('lesson-title-panel');
    if (ltp) {
      applyCommonStyle(ltp, s.lesson_title);
      const ltx = document.getElementById('lesson-title-text');
      if (ltx && s.lesson_title.fontSize != null) {
        ltx.style.fontSize = s.lesson_title.fontSize + 'vw';
      }
    }
  }
  ```

### Step 5: 授業進捗パネルにmaxHeight設定を管理画面に追加

**`static/index.html`** — 進捗パネルの固有設定にmaxHeight行を追加（スキーマには既に定義済み）。

**`static/js/broadcast/settings.js`** — lesson_progress の maxHeight 適用を追加（未対応なら）。

## 変更ファイル一覧

| ファイル | 変更内容 |
|---------|----------|
| `scripts/routes/overlay.py` | `_OVERLAY_DEFAULTS` + `fixed_items` + デバッグAPI 4つ |
| `scripts/routes/items.py` | `_ITEM_SPECIFIC_SCHEMA` + `_SCHEMA_ITEM_LABELS` |
| `static/index.html` | タイトルパネルUI + 進捗テスト表示ボタン + maxHeight行 |
| `static/js/broadcast/settings.js` | `lesson_title` スタイル適用 |

## リスク

- **低リスク**: 既存パターンの踏襲で、新規概念なし
- broadcast.htmlの既存CSS定義と settings.js の動的スタイルが競合しないよう、`applyCommonStyle` が `data-fixed-layout` を見て位置をスキップする仕組みがそのまま使える

## ステータス: 完了
