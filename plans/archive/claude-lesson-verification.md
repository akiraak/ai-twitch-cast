# Claude Code授業生成の動作確認

**ステータス: 完了**

## 概要

`prompts/lesson_generate.md` のワークフロー（画像読取り → スクリプト生成 → JSONインポート → 授業再生）が正常に動作するか検証した結果。

---

## 検証結果

### API・バックエンド

| ステップ | エンドポイント | 結果 | 備考 |
|---------|---------------|------|------|
| 授業情報取得 | `GET /api/lessons/{id}` | ✅ | extracted_text・sections_by_generator 正常 |
| キャラクター取得 | `GET /api/characters` | ✅ | teacher/student 設定取得可能 |
| 教材画像 | ファイルシステム | ✅ | `resources/images/lessons/164/` に2枚あり |
| JSONインポート | `POST /api/lessons/{id}/import-sections?generator=claude` | ✅ | セクション保存・dialogues JSON変換OK |
| 授業開始 | `POST /api/lessons/{id}/start?generator=claude` | ✅ | generatorパラメータ対応済み |
| TTSキャッシュ | `GET /api/lessons/{id}/tts-cache?generator=claude` | ✅ | generatorパラメータ対応済み |

### UI（管理画面）

| 機能 | 結果 | 備考 |
|------|------|------|
| ジェネレータ切替タブ | ✅ | Gemini/Claude Codeタブ、セクション数バッジ表示 |
| JSONインポートダイアログ | ✅ | フォーマット検証・確認ダイアログ付き |
| Step 2a/QA Geminiのみ表示 | ✅ | 未コミットだが正しい変更あり |
| インポート成功トースト | ❌ バグ | `res.imported` → `res.count` に修正が必要 |

---

## 発見されたバグ

### `res.imported` → `res.count` 不一致

- **ファイル**: `static/js/admin/teacher.js:1433`
- **現象**: インポート成功時のトーストに「インポート完了: undefinedセクション」と表示される
- **原因**: APIレスポンスは `{"ok": true, "sections": [...], "count": N}` だが、UIは `res.imported` を参照
- **修正**: `res.imported` → `res.count` に変更

---

## 未コミットの変更（teacher.js）

`git diff` で確認済みの変更内容:

1. Step 2a（プラン生成）を `generator === 'gemini'` 時のみ表示
2. QA（品質分析）を `generator === 'gemini'` 時のみ表示
3. Step 2bのラベル typo修正（「スクリプ生成」→「スクリプト生成」）

これらはClaude Codeタブで不要なUIを非表示にする正しい変更。

---

## 作業項目

- [x] `teacher.js:1433` の `res.imported` → `res.count` バグ修正
- [x] 未コミットのteacher.js変更 + バグ修正をまとめてコミット
- [x] TODOから本項目を削除、DONE.mdに記録
