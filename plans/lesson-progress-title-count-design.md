# 授業の流れパネル — タイトル文字・進捗カウント文字のデザイン調整

## 背景

授業の流れパネル（`#lesson-progress-panel`）のヘッダー部分には2つのサブ要素がある:

```
┌──────────────────────────┐
│ 授業の流れ          1/10 │  ← #lesson-progress-title
│ ─────────────────────── │     .lp-title-text + .lp-title-count
│ 🎬 はじめに              │
│ 📖 本題       ← current  │
│ 🏁 まとめ                │
└──────────────────────────┘
```

1. **タイトル文字** (`.lp-title-text`): 「授業の流れ」テキスト
2. **進捗カウント** (`.lp-title-count`): 「1/10」テキスト

これらの文字デザインを、既存の「文字」グループと同等のプロパティセット（サイズ・色・縁取り）で調整できるようにする。

### 現状

| プロパティ | タイトル文字 | カウント文字 |
|-----------|-------------|-------------|
| サイズ | `titleFontSize` ✅（1.1vw） | CSS固定 0.85vw ❌ |
| 色 | CSS固定 `rgba(124,77,255,0.8)` ❌ | CSS固定 `rgba(200,180,255,0.7)` ❌ |
| 縁取りサイズ | なし ❌ | なし ❌ |
| 縁取り色 | なし ❌ | なし ❌ |
| 縁取り透明度 | なし ❌ | なし ❌ |

## 方針

既存の「文字」グループのプロパティセット（サイズ・色・縁取り3種）に合わせ、タイトル・カウントそれぞれに同等のプロパティを追加する。

### 新規プロパティ一覧（10個）

**タイトル文字（5個、うち1個は既存）:**
| key | label | type | default |
|-----|-------|------|---------|
| `titleFontSize` | タイトル文字 (vw) | slider | 1.1 **既存** |
| `titleColor` | タイトル色 | color | `#7c4dff` |
| `titleStrokeSize` | タイトル縁取りサイズ | slider 0-10 | 0 |
| `titleStrokeColor` | タイトル縁取り色 | color | `#000000` |
| `titleStrokeOpacity` | タイトル縁取り透明度 | slider 0-1 | 0.8 |

**カウント文字（5個）:**
| key | label | type | default |
|-----|-------|------|---------|
| `countFontSize` | カウント文字 (vw) | slider 0.5-2 | 0.85 |
| `countColor` | カウント色 | color | `#c8b4ff` |
| `countStrokeSize` | カウント縁取りサイズ | slider 0-10 | 0 |
| `countStrokeColor` | カウント縁取り色 | color | `#000000` |
| `countStrokeOpacity` | カウント縁取り透明度 | slider 0-1 | 0.8 |

## 実装ステップ

### Step 1: スキーマに新フィールド追加

**`scripts/routes/items.py`** — `_ITEM_SPECIFIC_SCHEMA["lesson_progress"]` を2グループに分割:

```python
"lesson_progress": [
    {"title": "固有設定", "fields": [
        {"key": "maxHeight", ...},   # 既存
        {"key": "itemFontSize", ...}, # 既存
    ]},
    {"title": "タイトル文字", "fields": [
        {"key": "titleFontSize", ...},    # 既存（移動）
        {"key": "titleColor", ...},
        {"key": "titleStrokeSize", ...},
        {"key": "titleStrokeColor", ...},
        {"key": "titleStrokeOpacity", ...},
    ]},
    {"title": "カウント文字", "fields": [
        {"key": "countFontSize", ...},
        {"key": "countColor", ...},
        {"key": "countStrokeSize", ...},
        {"key": "countStrokeColor", ...},
        {"key": "countStrokeOpacity", ...},
    ]},
],
```

### Step 2: デフォルト値を追加

**`scripts/routes/overlay.py`** — `_OVERLAY_DEFAULTS["lesson_progress"]` に追加:
```python
"titleColor": "#7c4dff",
"titleStrokeSize": 0, "titleStrokeColor": "#000000", "titleStrokeOpacity": 0.8,
"countFontSize": 0.85, "countColor": "#c8b4ff",
"countStrokeSize": 0, "countStrokeColor": "#000000", "countStrokeOpacity": 0.8,
```

### Step 3: broadcast.html側で設定を適用

**`static/js/broadcast/settings.js`** — lesson_progressセクションを拡張:
- タイトル要素（`.lp-title-text`）に色・縁取りを適用
- カウント要素（`.lp-title-count`）にサイズ・色・縁取りを適用

**`static/js/broadcast/settings-panel.js`** — `_scheduleSpSave` の lesson_progress 即時反映に新プロパティを追加。

### Step 4: 管理画面に固有設定UI追加

**`static/index.html`** — 進捗パネルの `.panel-body` に新しい行を追加。
ただし、スキーマのグループ分け（タイトル文字/カウント文字）で自動注入されるため、
`_injectCommonProps` が処理する。HTMLには固有設定の行のみ必要。

## 変更ファイル

| ファイル | 変更内容 |
|---------|----------|
| `scripts/routes/items.py` | スキーマ10フィールド追加（2グループ） |
| `scripts/routes/overlay.py` | デフォルト値追加 |
| `static/js/broadcast/settings.js` | 新プロパティの適用 |
| `static/js/broadcast/settings-panel.js` | 右クリック即時反映 |
| `static/index.html` | 管理画面の固有設定行を整理 |

C#コントロールパネル（control-panel.html）はスキーマ駆動なので変更不要。

## ステータス: 完了
