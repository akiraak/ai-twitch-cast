# speech-generation-flow.md 現状整合性調査プラン

## ステータス: 完了

## 背景

`docs/speech-generation-flow.md` はキャラクター発話生成フローの全体像を定義するドキュメント。
CLAUDE.mdで「コードを変更する前に必ず参照すること」と指定されており、正確性が重要。
複数の機能追加（メインコンテンツ種別、監督レビュー、v3/v4対応等）を経て、ドキュメントが現状コードと乖離している。

## 調査結果: 乖離箇所一覧（全20箇所）

---

### 重大（フロー・構造が変わっている）— 7件

#### 1. LLMモデル名が古い
- **ドキュメント**: Phase Aの3エキスパートすべて `gemini-2.5-flash`
- **現状コード**:
  - 知識エキスパート: `gemini-3-flash-preview`（`_get_knowledge_model()`）
  - エンタメエキスパート: `gemini-3-flash-preview`（`_get_entertainment_model()`）
  - 監督: `gemini-3.1-pro-preview`（`_get_director_model()`）※最高推論モデル
  - セリフ生成: `gemini-3-flash-preview`（`_get_dialogue_model()`）
- **影響**: Phase A詳細の表が不正確。モデルは環境変数で切替可能な点も未記載

#### 2. Phase Aの監督出力が大幅に拡張されている
- **ドキュメント**: `[{section_type, title, summary, emotion, has_question, wait_seconds}]`
- **現状コード**: 監督の出力スキーマ:
  ```json
  {
    "section_type": "introduction|explanation|example|question|summary",
    "title": "10文字以内",
    "display_text": "視聴者が見る実際の内容",
    "emotion": "...",
    "wait_seconds": number,
    "question": "",
    "answer": "",
    "dialogue_directions": [
      {"speaker": "teacher|student", "direction": "演出指示", "key_content": "必ず言及すべき内容"}
    ]
  }
  ```
- **影響**: `summary`→`display_text`に変更、`has_question`→`question`+`answer`に分離、`dialogue_directions`（`key_content`含む）が新規追加。Phase B-1への入力が根本的に変わっている
- **wait_secondsガイドライン**: 一部更新（驚き4-5秒、まとめ2-3秒が追加）

#### 3. Phase B-3（監督レビュー）とPhase B-4（再生成）が未記載
- **ドキュメント**: Phase B-2の後はPhase Cへ直行
- **現状コード**: `generate_lesson_script_v2()` に以下が追加:
  - **Phase B-3**: `_director_review()` — 5つのレビュー観点:
    1. display_text読み上げ網羅性（例文・会話・キーフレーズが実際に話されているか）
    2. キャラクター一貫性（先生/生徒が役割に合った発話をしているか）
    3. セクション間の流れ（文脈連続性、情報フロー）
    4. 正確性・網羅性（教材の要点カバー、事実誤認なし）
    5. コンテンツ種別準拠（main_contentのcontent_typeに応じた読み方）
  - **Phase B-4**: レビュー不合格セクションのみ `revised_directions` で再生成（1回限り）
- **影響**: 授業モードフローの重要な品質保証ステップが完全に欠落

#### 4. メインコンテンツ種別（content_type）が未記載
- **ドキュメント**: content_typeの概念なし
- **現状コード**:
  - `extract_main_content()` で教材のcontent_typeを識別（conversation/passage/word_list/table）
  - `_build_structure_prompt()` にcontent_type別の読み上げルール:
    - `conversation`: 先生/生徒で役割分担して読む
    - `passage`: 先生が読み+解説、生徒がリアクション
    - `word_list`: 先生が読み+解説、生徒が繰り返し/質問
    - `table`: 先生が行/列を説明、生徒がコメント
  - `_director_review()` でcontent_type準拠チェック
- **影響**: 構造生成〜レビューに影響する主要機能が欠落

#### 5. 感情BlendShapeの適用タイミングが不正確
- **ドキュメント**: 共通再生パイプライン `_speak_impl()` 内の1ステップとして記載
- **現状コード**: `apply_emotion()` は `_speak_impl()` の中で**呼ばれていない**
  - comment_reader.py: speak()の**前後**で呼出（前=感情適用、後=neutral復帰）
  - lesson_runner.py: 同様にspeak()の**前後**で呼出
  - 呼出箇所: comment_reader.py 約8箇所、lesson_runner.py 約4箇所
- **影響**: パイプラインの図が実装と異なる。感情はパイプライン外で制御される

#### 6. コメント応答フローの関数名・パラメータが不正確
- **ドキュメント**: `generate_ai_response()` + `build_system_prompt(char.system_prompt, char.rules, char.emotions, char.self_note, char.persona, 会話履歴, 配信コンテキスト, ユーザーメモ)` の8パラメータ
- **現状コード**:
  - 関数名: `generate_response()`（`generate_ai_response`ではない）
  - `build_system_prompt(char, stream_context=None, self_note=None, persona=None)` の4パラメータ
  - `char` はキャラ設定dict全体を渡す（rules/emotions等はchar内に含まれる）
  - 会話履歴・ユーザーメモは `generate_response()` 内で別途処理（build_system_promptには渡さない）
- **影響**: コメント応答フロー図の疑似コードが不正確

#### 7. コメント応答・イベント応答の戻り値が不完全
- **ドキュメント**:
  - シングル: `{speech, emotion, translation}`
  - マルチ: `[{speaker, speech, emotion}, ...]`
- **現状コード**:
  - シングル: `{speech, emotion, translation, tts_text, se}`
  - マルチ: `[{speaker, speech, emotion, translation, tts_text, se}, ...]`
- **影響**: `tts_text`（言語タグ付きTTS用テキスト）と`se`（SE選択）が欠落

---

### 中程度（パラメータ・API仕様のズレ）— 6件

#### 8. 全行番号が古い（コード大幅リファクタリング済み）
- **ドキュメント** → **現状**:
  - 知識エキスパート: 315-359 → 450-517
  - エンタメエキスパート: 381-467 → 520-637
  - 監督: 492-600 → 644-900+
  - `_build_structure_prompt`: 1196-1337 → 1488-1705+
  - LLM呼び出し（構造）: 1562-1600 → 2194-2203
  - teacher.py 生成方式選択: 521-563 → 590-615

#### 9. 直接発話（API）のフロー・パラメータが不正確
- **ドキュメント**: `{text: "こんにちは", character: "teacher"}` → `speak_event() → speech_pipeline.speak()`、キャラ個性★★☆☆☆
- **現状コード**:
  - パラメータ: `SpeakRequest(event_type="手動", detail=str, voice=str|None)`
  - 呼出: `state.reader.speak_event(body.event_type, body.detail, voice=body.voice)`
  - speak_event()はAIでテキスト生成（キャラのsystem_prompt使用）→ 実質イベント応答と同フロー
  - キャラ個性: ★★★★☆が妥当（テキストもAI生成されるため）

#### 10. speak_event()のvoice/styleパラメータが未記載
- **ドキュメント**: `speak_event(event_type, detail)` の2パラメータ
- **現状コード**: `speak_event(event_type, detail, voice=None, style=None, avatar_id="teacher")`
  - マルチキャラ時: 最初のエントリのみパラメータのvoice/styleを使用、2番目以降はキャラconfigから取得

#### 11. speech_pipeline.speak()の呼出パラメータが不完全
- **ドキュメント**: `speak(text, voice, style, avatar_id)` の4パラメータ
- **現状コード**: `speak(text, voice, style, subtitle, chat_result, tts_text, post_to_chat, se, wav_path, avatar_id)` の10パラメータ
  - `subtitle={author, trigger_text, result}` — 字幕表示用データ
  - `chat_result` — Twitchチャット投稿用データ
  - `tts_text` — 言語タグ付きTTS用テキスト（textとは別）
  - `post_to_chat` — チャット投稿コールバック
  - `se` — SE情報dict
  - `wav_path` — 事前生成済みWAVパス

#### 12. Phase C TTS事前生成のtts_style取得方法が不正確
- **ドキュメント**: `get_localized_field(config, "tts_style")` で言語モード対応
- **現状コード**: teacher.pyでは `teacher_cfg.get("tts_style")` / `student_cfg.get("tts_style")` で直接取得
  - `get_localized_field()` は使われていない → 英語モードでも日本語のtts_styleが使われる
  - ※ai_responder.py（コメント応答）では `get_localized_field()` を使っている

#### 13. dialogue_plan vs dialogue_directions の二重形式が未記載
- **ドキュメント**: `dialogue_plan: [{speaker, direction}]` のみ
- **現状コード**: 2つの形式が並存:
  - v2（レガシー）: `dialogue_plan: [{speaker, direction}]` — key_contentなし
  - v3（現行）: `dialogue_directions: [{speaker, direction, key_content}]` — key_content付き
  - `generate_lesson_script_v2()` は `director_sections` が渡された場合B-1をスキップし、v3形式を直接使用

---

### 軽微（補足・表記レベル）— 7件

#### 14. v3/v4フォーマットの互換性への言及なし
- lesson_runner.pyがv4形式（`{dialogues: [...], review: {...}}`）をパースしている
- generate_lesson_script_v2()がdirector_sectionsを受け取るとB-1スキップ（v3パス）

#### 15. 言語別プラン保存（lesson_plansテーブル）が未記載
- teacher.pyがlesson_plansテーブルから言語別プランを取得（lessonsテーブルにフォールバック）

#### 16. ペース制御（pace_scale）が未記載
- lesson_runner.pyのPhase Dにペーススケール機能（DB設定、デフォルト1.0）

#### 17. TTS/SE音量計算が未記載
- TTS音量: `min(1.0, tts² × master²)`
- SE音量: `min(1.0, se² × master² × track_volume)`
- WebSocket送信時に `volume` パラメータとして渡される

#### 18. チャット投稿の遅延が未記載
- speech_pipeline.pyでチャット投稿が音声再生開始2秒後に実行される

#### 19. WAVファイルクリーンアップが未記載
- 事前キャッシュ（`resources/audio/` 配下）: 保持
- テンプファイル: 再生完了後に削除

#### 20. パイプラインのspeaking_endイベントが未記載
- リップシンク停止後に `speaking_end` イベントが送信される

---

## 追加発見: バグ

### clear_tts_cache()が_dlg_ファイルを削除しない
- **場所**: `src/lesson_runner.py` `clear_tts_cache()` 内
- `order_index` 指定時に `section_XX_part_*.wav` のみ削除、`section_XX_dlg_*.wav` は**削除されない**
- **影響**: セクション編集後に古いTTSキャッシュが残り、古い音声が再生される可能性

---

## 修正方針

### 方針A: 全面改訂（推奨）
全セクションを現状コードに合わせて書き直す。行番号の参照は**全削除**し、関数名のみで参照する（行番号は頻繁にズレるため）。

### 方針B: 差分パッチ
乖離箇所のみ修正。既存構造は維持。

**推奨: 方針A** — 乖離が20箇所と多岐にわたり、パッチでは見落としのリスクが高い。

## 修正ステップ（方針A）

### Step 1: 全体像セクション更新
- LLMモデル名を汎用的な記載に（環境変数で切替可能と注記）
- 入力ソースに変更がないか確認

### Step 2: キャラクター設定セクション更新
- DB構造の注記: config JSONカラム + character_memoryテーブル
- フィールド一覧に変更がないか確認

### Step 3: コメント応答フロー更新
- 関数名: `generate_ai_response()` → `generate_response()`
- `build_system_prompt()` のパラメータを4つに修正
- 戻り値に `tts_text`, `se` を追加
- マルチキャラ戻り値に `tts_text`, `translation`, `se` を追加
- `speak()` 呼出のパラメータを10個に拡充（subtitle, chat_result, tts_text等）

### Step 4: 授業モードフロー全面改訂
- Phase A: 監督の出力スキーマ全面更新（display_text, dialogue_directions, key_content）
- Phase A: モデル名更新（gemini-3系 + 監督はgemini-3.1-pro）
- Phase B-1: dialogue_plan vs dialogue_directions の二重形式、content_type対応を追加
- Phase B-2: key_content パラメータを追加
- **Phase B-3: 監督レビュー（新規追加）** — 5つのレビュー観点を記載
- **Phase B-4: 再生成（新規追加）** — revised_directionsによる1回限りリトライ
- Phase C: tts_style取得方法の修正（get_localized_field未使用）
- Phase D: ペース制御、v4形式対応、パイプライン先読みを追加

### Step 5: イベント応答フロー更新
- speak_event()のvoice/style/avatar_idパラメータ追加
- 戻り値にtts_textを追加

### Step 6: 直接発話フロー更新
- SpeakRequestの正しいパラメータ: `{event_type, detail, voice}`
- speak_event()経由のAI生成フローであることを明記
- 個性反映度: ★★☆☆☆ → ★★★★☆ に修正

### Step 7: 共通再生パイプライン更新
- 感情BlendShapeをパイプライン外（呼出元で制御）に移動
- SE/TTS音量計算を記載
- チャット投稿2秒遅延を記載
- speaking_endイベントを追加
- WAVクリーンアップ（キャッシュ保持/テンプ削除）を記載

### Step 8: 個性反映度まとめ表更新
- 直接発話の★を修正
- 各モードの変更を反映

### Step 9: 行番号参照の全削除
- 関数名のみで参照するスタイルに統一
- `ファイル: src/xxx.py（関数名）` 形式に変更

### Step 10: 実装履歴セクション更新
- v3/v4への言及追加
- 監督レビュー・再生成機能追加の履歴
- content_type機能追加の履歴

## リスク

- ドキュメント改訂中にコードが変更される可能性 → 改訂は1セッションで完了させる
- 行番号削除でナビゲーションが不便になる → 関数名をコード内検索しやすい形で記載

## 見積もり

全10ステップ、ドキュメント1ファイル（520行→推定650行程度）の改訂作業。
