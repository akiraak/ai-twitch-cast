# プラン: speech-generation-flow.md とコード実装の同期

ステータス: 進行中

## 背景

`docs/speech-generation-flow.md` は発話生成フロー全体の仕様書だが、Phase 1（メインコンテンツ読み上げ）・Phase 2（導入の自然化）や各種機能追加の実装後、ドキュメントが更新されておらず、実装との乖離が発生している。

## 差分一覧

### A. 実装にあるがドキュメントに記載なし

| # | 対象 | 内容 |
|---|------|------|
| A1 | `clean_extracted_text()` | テキスト抽出後のクリーニング処理（HTMLエンティティ・装飾記号除去・空行圧縮）。Phase B-1の前に実行される |
| A2 | `_normalize_roles()` | `role`（main/sub）と `read_aloud` フィールドの正規化。mainが必ず1つ、read_aloudの自動判定 |
| A3 | `_format_main_content_for_prompt()` の上限値 | `read_aloud=true && role=main` → 2000文字、その他 → 200文字。🔊マーカー付与 |
| A4 | `apply_emotion()` の gesture 対応 | `EMOTION_GESTURES` マッピングによるジェスチャー連動 |
| A5 | `respond_webui()` | WebUI経由の発話機能（マルチキャラ・シングルキャラ両対応） |
| A6 | `build_language_rules()` / `build_tts_style()` | prompt_builder.py の補助関数 |
| A7 | `GEMINI_DIALOGUE_MODEL` 環境変数 | セリフ個別生成用モデル（Phase B-2）。フォールバック: GEMINI_CHAT_MODEL → gemini-3-flash-preview |
| A8 | Phase B-3 レビュー観点の拡張 | 6→8観点に増加（🔊読み上げ網羅性チェック + 🔊導入チェック を追加） |
| A9 | `tts_test()` / `tts_test_emotion()` / `tts_voice_sample()` | avatar.py のテスト系エンドポイント |

### B. ドキュメントと実装が不一致

| # | 対象 | ドキュメント記載 | 実装 |
|---|------|-----------------|------|
| B1 | `generate_multi_event_response()` 戻り値 | `se` フィールドあり | `se` フィールドなし |
| B2 | なるこの `tts_voice` | Aoede | Kore |

### C. ドキュメントの説明不足

| # | 対象 | 内容 |
|---|------|------|
| C1 | モデル環境変数のフォールバック | 実装は多段階（専用env → GEMINI_CHAT_MODEL → ハードコード値）だがドキュメントは「既定」のみ |
| C2 | Phase B-4 の並列制御 | `ThreadPoolExecutor(max_workers=3)` の記載なし |

## 更新方針

speech-generation-flow.md に対して以下を反映する:

### 1. 授業モードの全体フローに追加 ✅
- Phase A の前に「テキスト抽出 → クリーニング → メインコンテンツ識別」のステップを追記
- `clean_extracted_text()` と `extract_main_content()` → `_normalize_roles()` のフローを図示

### 2. Phase B-1 セクションに追記 ✅
- `_format_main_content_for_prompt()` の上限ルール（2000文字/200文字）
- 🔊マーカーの意味と条件

### 3. Phase B-2 セクションに追記 ✅
- `GEMINI_DIALOGUE_MODEL` 環境変数の説明

### 4. Phase B-3 セクションを更新 ✅
- レビュー観点を6→8に更新
- 🔊読み上げ網羅性チェック（観点7）と導入チェック（観点8）を追加

### 5. イベント応答セクションを修正 ✅
- `generate_multi_event_response()` の戻り値から `se` を削除（B1）

### 6. キャラクター設定テーブルを修正 ✅
- なるこの `tts_voice` を Kore に修正（B2）

### 7. apply_emotion セクションに追記
- gesture パラメータと EMOTION_GESTURES マッピングの説明（A4）

### 8. 環境変数一覧を追加（オプション）
- 全モデル環境変数のフォールバックチェーン

### 追記しないもの（低優先・別ドキュメント向き）
- `respond_webui()`（A5）: API一覧ドキュメント向き
- `build_language_rules()` / `build_tts_style()`（A6）: 内部補助関数
- テスト系エンドポイント（A9）: API一覧ドキュメント向き

## 変更ファイル

| ファイル | 変更内容 |
|---------|---------|
| `docs/speech-generation-flow.md` | 上記の差分反映 |

## リスク

- なし（ドキュメント更新のみ）
