# 授業パネルサイズのセクション別制御プラン

## ステータス: 完了

## 背景

授業コンテンツの `display_text` パネルは現在グローバル設定（全セクション共通）でサイズが固定されている。セクションによってコンテンツ量が大きく異なる（短い導入 vs 長いコード例）ため、パネルが大きすぎたり小さすぎたりする問題がある。

**ユーザーからのフィードバック**: lesson #175 セクション0に「教材コンテンツの表示パネルの高さが高すぎる」と評価。この種のフィードバックをAIが改善時に反映できるようにしたい。

## 方針

- セクションごとに `display_properties` (JSON) を持たせ、パネルサイズ等を制御可能にする
- AIが授業生成・改善時にセクションの内容量に応じて適切なサイズを指定する
- グローバル設定をベースに、セクション別プロパティで一時的にオーバーライドする設計
- 手動編集も可能だが、主な想定はAIによる自動指定

## 制御対象プロパティ

| プロパティ | 単位 | 説明 | 例 |
|-----------|------|------|-----|
| `maxHeight` | % | パネル最大高さ | 30, 50, 70 |
| `width` | % | パネル幅 | 40, 55, 70 |
| `fontSize` | vw | フォントサイズ | 1.0, 1.4, 1.8 |

最小限のプロパティから始め、必要に応じて追加する。

## 実装ステップ

### Step 1: DBスキーマ — `display_properties` カラム追加

**ファイル**: `src/db/core.py`, `src/db/lessons.py`

1. `lesson_sections` テーブルに `display_properties TEXT NOT NULL DEFAULT '{}'` を追加
2. `add_lesson_section()` に `display_properties=""` 引数を追加
3. `update_lesson_section()` で `display_properties` の更新に対応

**マイグレーション**: `_ensure_column()` パターンで安全に追加（既存DB互換）

### Step 2: API対応 — セクションCRUD・インポート

**ファイル**: `scripts/routes/teacher.py`

1. `SectionUpdate` モデルに `display_properties: dict | None = None` 追加
2. `PUT /api/lessons/{id}/sections/{sid}` でJSONシリアライズして保存
3. `POST /api/lessons/{id}/import-sections` で `display_properties` を受け付ける
4. `POST /api/lessons/{id}/improve` の改善結果から `display_properties` をコピー
5. セクション取得APIのレスポンスに `display_properties` を含める（既にSELECT *なので自動）

### Step 3: 授業再生 — WebSocketイベント拡張

**ファイル**: `src/lesson_runner.py`

1. `_play_section()` で `display_properties` を読み取り
2. `_show_lesson_text(text, display_properties)` に引数追加
3. WebSocketイベントに `display_properties` を含める:
   ```json
   {"type": "lesson_text_show", "text": "...", "display_properties": {"maxHeight": 40, "fontSize": 1.2}}
   ```
4. `_hide_lesson_text()` はそのまま（フロント側でリセット）

### Step 4: フロントエンド — セクション別スタイル適用

**ファイル**: `static/js/broadcast/panels.js`, `static/js/broadcast/websocket.js`

1. `websocket.js`: `lesson_text_show` イベントから `display_properties` を取り出して `showLessonText()` に渡す
2. `panels.js`: `showLessonText(text, displayProperties)` を拡張
   - `displayProperties` のプロパティを一時適用
   - 適用前にグローバル設定値を保存しておく
3. `hideLessonText()`: パネル非表示時にグローバル設定にリセット

```javascript
// panels.js イメージ
function showLessonText(text, displayProperties = {}) {
  const panel = document.getElementById('lesson-text-panel');
  const content = document.getElementById('lesson-text-content');
  if (!panel || !content) return;

  // セクション別オーバーライド適用
  if (displayProperties.maxHeight != null) panel.style.maxHeight = displayProperties.maxHeight + '%';
  if (displayProperties.width != null) panel.style.width = displayProperties.width + '%';
  if (displayProperties.fontSize != null) content.style.fontSize = displayProperties.fontSize + 'vw';

  content.textContent = stripLangTags(text);
  panel.style.display = 'block';
  // ... 既存のfade-in処理
}

function hideLessonText() {
  // ... 既存処理 + グローバル設定にリセット
  resetLessonTextToGlobalSettings();
}
```

### Step 5: AI生成プロンプト — display_properties の生成指示

**ファイル**: `prompts/lesson_generate.md`, `prompts/lesson_improve.md`

1. セクションの出力フォーマットに `display_properties` フィールドを追加
2. コンテンツ量に応じたサイズ指定のガイドライン:
   - 短いテキスト（1-2行）→ `maxHeight: 20-30`
   - 中程度（3-5行）→ `maxHeight: 40-50`
   - 長いテキスト/コード → `maxHeight: 60-70`
3. `lesson_improve.md`: 注釈コメントにパネルサイズへの言及がある場合の対応指示

### Step 6: 管理画面UI — プロパティ表示・編集

**ファイル**: `static/js/admin/teacher.js`

1. セクション詳細にパネルサイズ設定の表示を追加（折りたたみ）
2. `maxHeight`, `width`, `fontSize` のスライダーまたは数値入力
3. プレビュー機能は不要（配信画面で確認）

## テスト

- `tests/test_db.py`: `display_properties` の保存・取得テスト
- `tests/test_api_teacher.py`: セクション更新・インポート時の `display_properties` テスト
- `tests/test_lesson_runner.py`: WebSocketイベントに `display_properties` が含まれるテスト

## リスク

- **AI出力の安定性**: AIが不適切な値（負数、極端な値）を指定する可能性 → バリデーション/クランプ処理を入れる
- **グローバル設定との競合**: セクション別設定とグローバル設定のリセットが正しく動くか → `hideLessonText()` でのリセットを確実に

## 実装順序

Step 1 → 2 → 3 → 4 は順番に依存。Step 5（プロンプト）と Step 6（管理画面UI）は Step 4 完了後に並行可能。
