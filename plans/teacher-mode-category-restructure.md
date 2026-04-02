# 教師モード：カテゴリUI構造の再設計

## ステータス: 進行中

## 背景

教師モードのUI構造に2つの問題がある：

1. **「学習」が教師モードと並列のサブタブ** — 学習ダッシュボードはカテゴリごとの分析・プロンプト改善を行う教師モードの運用ツールであり、独立した会話モードではない
2. **カテゴリ管理が折りたたみ `<details>` で埋もれている** — カテゴリは教師モードの根幹機能（全レッスンがカテゴリに属し、学習分析もカテゴリ単位）だが、コンテンツ一覧の中に副次的な機能として配置されている

### 付随バグ

- カテゴリ追加後に `loadLessons()` が全体を再レンダリングし、`<details>` が閉じた状態で再生成される → ユーザーには「何も反応しない」ように見える（API自体は正常動作）

## 現在の構造

```
会話モード [メインタブ]
├── 教師モード [サブタブ]
│   └── コンテンツ一覧 (div#lesson-list)
│       ├── 間のスケールスライダー
│       ├── カテゴリ管理 (collapsed <details>)  ← 問題②
│       └── 個別レッスン...
├── 学習 [サブタブ]                              ← 問題①
│   └── 学習ダッシュボード
└── 雑談モード [サブタブ]
    └── 準備中
```

## 新しい構造

```
会話モード [メインタブ]
├── 教師モード [サブタブ]
│   ├── カテゴリタブバー                          ← NEW
│   │   例: [全て] [プログラミング] [英語] ... [+ 新規] [⚙ 管理]
│   ├── 間のスケールスライダー
│   ├── フィルタされたコンテンツ一覧
│   └── 学習セクション（選択カテゴリ）              ← 旧「学習」タブの内容を統合
└── 雑談モード [サブタブ]
    └── 準備中
```

## 実装ステップ

### Step 1: カテゴリタブバーの新設 + カテゴリ管理モーダル化 ✅

**変更ファイル**: `static/js/admin/teacher.js`

- 状態変数 `_selectedCategory` を追加（`null` = 全て）
- `_renderCategoryTabs(container)` 関数を新設
  - 「全て」タブ + 各カテゴリ名タブ + 「+ 新規」ボタン + 「⚙ 管理」ボタン
  - 選択中のタブにactiveスタイル（pill style）
  - タブクリックで `_selectedCategory` を更新し `loadLessons()` を呼ぶ
- `selectCategory(slug)` — タブ切り替え関数
- `openCategoryManager()` — ⚙ボタンからモーダルでカテゴリ一覧表示・削除
- `deleteCategoryFromManager()` — モーダル内からの削除（モーダル閉じて再読み込み）
- `loadLessons()` を修正：`_renderCategoryManager()` → `_renderCategoryTabs()` に置換
- レッスン一覧を `_selectedCategory` でフィルタ表示
- 旧 `_renderCategoryManager()` を削除済み

### Step 2: 学習ダッシュボードの教師モード内統合 ✅

**変更ファイル**: `static/index.html`, `static/js/admin/teacher.js`

- HTML: サブタブから「学習」を削除、`div#conv-sub-learnings` を削除
- JS: `_renderLearningSection(container)` を新設 — `loadLessons()` 末尾でコンテンツ一覧の下に学習セクションを描画（`#learning-section` + `#learnings-dashboard`）
- JS: `loadLearningsDashboard()` を修正 — `_selectedCategory` でフィルタして選択カテゴリに連動
- JS: `switchConvSubtab()` から `learnings` 分岐を削除

### Step 3: CSSスタイリング（index.css）+ インラインスタイル→CSSクラス移行 ✅

**変更ファイル**: `static/css/index.css`, `static/js/admin/teacher.js`

- カテゴリタブバーのスタイル（`.cat-tabs`, `.cat-tab`, `.cat-tab.active`, `.cat-tab--action`, `.cat-tab--manage`）
  - 横スクロール対応（薄いスクロールバー）、hover/active状態、pill style
- 学習セクションのスタイル（`#learning-section`, `.learning-header`, `.learning-card`, `.learning-btn--*`, `.learning-detail`）
  - ダッシュボードカード、アクションボタン（hover付き）、学習結果折りたたみ
- JS側: `_renderCategoryTabs`, `_renderLearningSection`, `loadLearningsDashboard` のインラインスタイルをCSSクラス参照に置換

### Step 4: テスト・動作確認

- カテゴリの追加・削除が即座に反映されること
- カテゴリタブ切り替えでレッスン一覧がフィルタされること
- 学習ダッシュボードが選択カテゴリに連動すること
- 既存の教師モード機能（授業作成・再生・バージョニング等）に影響がないこと
- test_api_teacher.py が全パスすること

## 影響範囲

| ファイル | 変更内容 |
|---------|---------|
| `static/js/admin/teacher.js` | カテゴリタブバー新設、管理モーダル化、学習統合、フィルタ |
| `static/index.html` | サブタブ構造変更、学習ダッシュボードコンテナ移動 |
| `static/css/index.css` | カテゴリタブバーのスタイル追加 |
| `scripts/routes/teacher.py` | **変更不要**（APIはそのまま） |
| `tests/test_api_teacher.py` | **変更不要**（バックエンドテスト影響なし） |

## リスク

- 学習ダッシュボードの移動でレイアウトが崩れる可能性 → Step 4のCSS調整で対応
- カテゴリが多い場合にタブバーが溢れる → 横スクロール対応が必要
