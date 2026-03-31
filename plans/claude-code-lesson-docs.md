# Claude Code授業生成手順のドキュメント化 + プロンプト管理UI

## ステータス: 未着手

## 背景

Gemini自動生成パイプラインは全て削除済み。現在は Claude Code で手動生成 → JSONインポートが唯一の授業生成方法。

課題:
1. **`docs/speech-generation-flow.md`** に削除済みの Gemini 自動生成パイプライン（約350行）が残存。CLAUDE.md で「必読」指定されているため古い情報は問題
2. **管理画面 Step 2** は「prompts/lesson_generate.md に従い生成」とだけ表示し、具体的な手順が見えない
3. **プロンプトファイルの閲覧・編集** が管理画面からできない。`prompts/lesson_generate.md` を変更するにはファイルを直接編集する必要がある

## 変更内容

### Step 1: プロンプト管理API（バックエンド）

#### 1-1: `scripts/routes/prompts.py`（新規）

`docs_viewer.py` をベースに、`prompts/` ディレクトリのファイル管理APIを追加:

| メソッド | エンドポイント | 説明 |
|---------|--------------|------|
| GET | `/api/prompts` | `prompts/` 内のmdファイル一覧 |
| GET | `/api/prompts/{name}` | ファイル内容を返す（PlainTextResponse） |
| PUT | `/api/prompts/{name}` | ファイル内容を上書き保存 |
| POST | `/api/prompts/ai-edit` | AI指示で編集（現在の内容 + 指示 → 修正内容 + diff） |

**AI編集API（`POST /api/prompts/ai-edit`）の仕様:**

```python
# リクエスト
{
  "name": "lesson_generate.md",
  "instruction": "dialoguesの生成ルールで、1セクションあたり6-10ターンに変更して"
}

# レスポンス
{
  "ok": true,
  "original": "（変更前の全文）",
  "modified": "（変更後の全文）",
  "diff_html": "（行単位のHTMLカラーdiff）"
}
```

- Gemini（GEMINI_CHAT_MODEL）で現在の内容 + 指示 → 修正版を生成
- Pythonの `difflib.unified_diff` で差分生成 → HTMLに変換（追加行=緑、削除行=赤）
- フロントで確認後、`PUT /api/prompts/{name}` で保存する2段階フロー

#### 1-2: `scripts/web.py` にルーター登録

`from scripts.routes import prompts` を追加、`app.include_router(prompts.router)`

### Step 2: 管理画面 プロンプト閲覧・編集UI（フロントエンド）

#### 2-1: teacher.js Step 2 にプロンプト管理セクション追加

現在の「使い方」セクション（L293-302）を以下に置換:

```
┌─ Step 2: スクリプト生成 ─────────────────────┐
│                                                │
│ [📋 JSONインポート]  [ステータス表示]            │
│                                                │
│ ▼ 📖 授業生成ガイド（折りたたみ）               │
│   1. 教材画像を読み取る                         │
│   2. キャラ情報確認                              │
│   3. 授業プラン設計                              │
│   4. JSON生成                                   │
│   5. インポート                                  │
│                                                │
│ ▼ 📝 生成プロンプト（折りたたみ）               │
│   [プロンプト内容（Markdown表示）]               │
│   ┌─ AI編集 ─────────────────────────┐          │
│   │ 指示: [________________] [実行]   │          │
│   │                                   │          │
│   │ 差分プレビュー:                    │          │
│   │  - 赤: 削除された行               │          │
│   │  + 緑: 追加された行               │          │
│   │                                   │          │
│   │ [適用] [やり直す] [キャンセル]     │          │
│   └───────────────────────────────────┘          │
└────────────────────────────────────────────────┘
```

**UI要素:**
1. **ガイド折りたたみ** — 手順の概要（details/summary）
2. **プロンプト表示折りたたみ** — `GET /api/prompts/lesson_generate.md` で取得、`simpleMarkdownToHtml()` でレンダリング
3. **AI編集エリア:**
   - テキスト入力（指示文）+ 実行ボタン
   - 実行 → スピナー表示 → diff結果表示
   - diff表示: 削除行（赤背景）、追加行（緑背景）、コンテキスト行（グレー）
   - 「適用」→ PUT API で保存 → プロンプト表示を更新
   - 「やり直す」→ 別の指示で再度AI編集
   - 「キャンセル」→ 差分を破棄

**既存パターンの再利用:**
- Markdown表示: `simpleMarkdownToHtml()`（`static/js/admin/markdown.js`）
- スピナー: `.lesson-spinner` パターン
- トースト: `showToast()` （成功/エラー通知）
- カラー: 既存パレット（紫系 `#7b1fa2` / `#f3e5f5`）

#### 2-2: diff表示用CSS

`static/css/index.css` に差分表示用スタイルを追加:

```css
.diff-line-add { background: #e8f5e9; color: #1b5e20; }     /* 追加: 緑 */
.diff-line-del { background: #ffebee; color: #b71c1c; }     /* 削除: 赤 */
.diff-line-ctx { background: #fafafa; color: #666; }         /* コンテキスト: グレー */
.diff-container { font-family: monospace; font-size: 0.75rem;
                  max-height: 400px; overflow-y: auto;
                  border: 1px solid #d0c0e8; border-radius: 4px; }
```

### Step 3: ドキュメント更新

#### 3-1: `docs/speech-generation-flow.md` の更新

**削除する部分（削除済みコードの記述）:**
- プラン生成の詳細（3人のエキスパート）— L287-346
- セクション構造生成〜再生成 — L347-501
- 生成フローの具体例（Lesson #20）— L520-561
- 生成方式の選択ロジック表 — L563-571
- 授業モードの実装履歴（v3/v4）— L702-725
- 環境変数一覧の削除済みモデル — L735-738

**書き換える部分:**
- 授業モードの全体フロー（L169-277）→ Claude Code手動生成 + JSONインポート + TTS事前生成 + 授業再生
- 環境変数一覧 → 残る2つ（CHAT_MODEL, TTS_MODEL）のみ

**維持する部分:**
- 授業の構造（L6-35）— セクション・display_text・dialoguesの説明
- TTS事前生成 / 授業再生
- コメント応答・イベント応答・直接発話のフロー

#### 3-2: `prompts/lesson_generate.md` の微修正

- Gemini版との共存記述（L456: "generatorが別なので共存する"）を削除
- 概要文の "Gemini APIによる自動生成とは独立した" → 削除

## 実装順序

1. **Step 1** — バックエンドAPI（prompts.py）
2. **Step 2** — フロントエンドUI（teacher.js + CSS）
3. **Step 3** — ドキュメント更新

## 変更ファイル一覧

| ファイル | 変更内容 |
|---------|---------|
| `scripts/routes/prompts.py` | **新規** プロンプトファイル管理API |
| `scripts/web.py` | ルーター登録追加 |
| `static/js/admin/teacher.js` | Step 2にガイド + プロンプト表示・AI編集UI |
| `static/css/index.css` | diff表示用スタイル |
| `docs/speech-generation-flow.md` | 削除済みGemini生成フロー除去 + Claude Codeフロー記述 |
| `prompts/lesson_generate.md` | Gemini共存記述の削除 |

## 検証

1. `python3 -m pytest tests/ -q` — テスト全通過
2. 管理画面 教師モード → Step 2:
   - 「授業生成ガイド」折りたたみが表示される
   - 「生成プロンプト」折りたたみでprompts/lesson_generate.mdの内容が表示される
   - AI編集: 指示入力 → 差分表示 → 適用でファイルが更新される
3. `docs/speech-generation-flow.md` に削除済み関数名の参照が無い
4. `curl /api/prompts/lesson_generate.md` でプロンプト内容が返る
