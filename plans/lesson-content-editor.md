# プラン: 授業コンテンツ画面で会話文章・画面テキストを編集保存

ステータス: 未着手

## 背景

管理画面の授業コンテンツ画面（`static/js/admin/teacher.js`）では、セクション単位の `content` / `tts_text` / `display_text` / `question` / `answer` / `wait_seconds` / `display_properties` は既に編集可能（`sectionField` → `PUT /api/lessons/{lesson_id}/sections/{section_id}`、`scripts/routes/teacher.py:1007`）。

> 補足: `wait_seconds` は API/DB 層では編集可能だが、授業再生時の「間」は CLAUDE.md「授業再生の『間』」節のとおり `scenes.json` の `lesson_timings` から取得される。DB の `wait_seconds` は実再生では読み捨てになっている点に注意（dialogue 編集機能とは無関係）。

しかし **対話モード（`dialogues` がある授業）の各発話は読み取り専用**で表示されているだけで、誤字・読み間違い・違和感のある言い回しを直す手段が無い。

- 該当UI: `static/js/admin/teacher.js:818-879`（dialogue を `<div>` で並べているだけで input なし）
- 該当API: `scripts/routes/teacher.py` の `SectionUpdate` (`scripts/routes/teacher.py:169-177`) に `dialogues` フィールドが無い
- データモデル: `lesson_sections.dialogues` は JSON 文字列。v4 形式は `{dialogues: [...], original_dialogues, review, review_generation, review_overall_feedback}`、v1〜v3 は `[...]` の素配列（`teacher.js:712-722` の互換ロジック参照）
- DB層: `src/db/lessons.py:136-148` の `update_lesson_section()` の `allowed` ホワイトリストには既に `dialogues` / `dialogue_directions` が含まれているため、**DB層の変更は不要**（Pydantic `SectionUpdate` の field 追加だけで通る）

このため、いまは「ちょっと言い回しを直したい」程度の修正でもセクション全体を再生成するしかない。

## 方針

dialogue 単位の inline 編集UI と保存APIを足す。セクション単位の既存編集フローを踏襲し、保存時は該当 dialogue の TTS キャッシュ（`section_XX_dlg_YY.wav`）だけを無効化して再生成を促す。

スコープを 2 段階に分ける:

- **Step 1（必須）**: 既存 dialogue の **テキスト編集**（`content` / `tts_text` / `emotion`）。speaker は変更不可（TTSキャラ・声が紐づくため）。並び替え・追加・削除は対象外
- **Step 2（任意）**: dialogue の **追加・削除・並び替え**。需要が出たら別プランに切り出す

---

## Step 1: dialogue テキスト編集（必須）

### UI 変更（`static/js/admin/teacher.js`）

- 対話一覧（`teacher.js:818-879`）の各 dialogue ブロックを `<details>` で折り畳み、開いた中に編集 textarea を配置
  - `content`（表示テキスト）: textarea
  - `tts_text`（TTS用テキスト・空ならcontentと同じ扱い）: textarea
  - `emotion`: select。**選択肢ソースは speaker (teacher/student) ごとに対応するキャラの `character.emotions` から引く**（emotions はキャラ別仕様。`docs/speech-generation-flow.md:86` 参照）。`get_lesson_characters(lesson_id)` で既に取れているのでクライアント側でマッピングする。未知タグは BlendShape 適用時に `neutral` フォールバックされるため、雑にやるなら自由入力 textarea でも実害は小さい（emotion は TTS 音声に影響しない、表情BlendShape のみ）。実装難度を見て判断
- 折り畳みの summary 行は今と同じサマリ（speaker / emotion / 音声プレイヤー / TTS未生成バッジ）。デフォルト閉じ
- 編集後の保存は `onchange` で逐次 PUT（既存の `updateSectionField` と同じノリ。dialogue index も含めて送る）
- 保存中は対象行だけ視覚フィードバック（既存の `showToast` を流用）
- **試聴ボタンの状態同期**: 保存成功後、対象 dialogue の TTS バッジを「TTS未生成」（赤）に戻す。すでに再生中だったら停止
- 監督レビュー結果（`review` / `original_dialogues` / `review_overall_feedback`）と `dialogue_directions` の表示は現状維持（手動編集後にこの表示が残っても**矛盾扱いにしない**＝あくまで「直近の自動生成時のメタ」と割り切る）

### API（`scripts/routes/teacher.py`）

既存の `PUT /api/lessons/{lesson_id}/sections/{section_id}` を拡張する案と、専用エンドポイントを切る案。**既存PUT拡張**を採用する（理由: dialogue 単位の独立リソース化はオーバースペック / dialogues 配列の整合性は section の他フィールドと一緒に管理した方が単純）。

- `SectionUpdate` に以下を追加:
  ```python
  dialogues: list[dict] | dict | None = None  # v1〜v3=list, v4=dict({dialogues, review, ...})
  ```
- 受け取った `dialogues` を JSON 文字列にシリアライズして DB に保存（DB層の `update_lesson_section` は既に `dialogues` を受け付ける）
- **TTS キャッシュ無効化**:
  - 旧 dialogues と新 dialogues を比較し、`content` / `tts_text` が変わった index だけ `section_XX_dlg_YY.wav` を削除（emotion 変更は TTS 音声に影響しないので削除不要）
  - 既存の `clear_tts_cache` は section 全体削除なので、dialogue 単位の `clear_dialogue_tts_cache(lesson_id, order_index, dlg_index, lang, generator, version_number)` を `src/lesson_runner.py` に追加
  - 比較ロジックは `_normalize_dialogues_v4(raw)` ヘルパで v1〜v4 を統一して扱う
- `is_manually_edited` フラグは Step 1 では入れない（立てても表示する UI がないと意味が無いため）。需要が出たら Step 2 で UI バッジとセットで追加する

### 変更ファイル一覧（Step 1）

| ファイル | 変更内容 |
|---------|---------|
| `scripts/routes/teacher.py` | `SectionUpdate.dialogues` 追加・PUTで dialogues シリアライズ・差分検出して dialogue 単位 TTS キャッシュ削除 |
| `src/lesson_runner.py` | `clear_dialogue_tts_cache(...)` 追加（既存 `_dlg_cache_path` を再利用） |
| `static/js/admin/teacher.js` | dialogue 行に `<details>` + textarea/select、`updateDialogueField(lessonId, sectionId, dlgIndex, field, value)` 追加、保存後に該当行のTTSバッジ更新 |
| `tests/test_api_teacher.py` | dialogues 編集の API テスト（v3 array / v4 dict 両方、TTS キャッシュ削除確認） |

> DB層 (`src/db/lessons.py`) は既に `dialogues` カラムへの更新を受け付けるため変更不要。

### 動作確認チェック

- [ ] 対話モードの授業（例: lesson_id 100）で各発話の content を直して保存できる
- [ ] 保存後、該当 dialogue の `section_00_dlg_00.wav` が消えている
- [ ] 他 dialogue の wav は残っている
- [ ] TTS事前生成を再実行すると差分のみが再生成される
- [ ] v4 形式（`{dialogues, review, ...}`）でも保存後に `review` / `original_dialogues` が壊れない
- [ ] 配信して読み上げが直った内容で再生される

---

## Step 2: dialogue の追加・削除・並び替え（任意・別フェーズ）

需要が出てから着手する。やる場合の論点:

- 追加時の `speaker` 選択肢（teacher / student のどちらか）
- 並び替え時の TTS キャッシュ整合（index がズレるので全削除が安全）
- 監督レビュー (`review.revised_directions`) の index 参照とのズレ
- UI: ドラッグ&ドロップは複雑なので、まずは「↑↓ボタン」で十分

---

## リスクと注意点

- **監督レビュー結果との整合性**: `review.revised_directions` は dialogue index を持っているので、手動編集後に **「監督指示と本文がズレている」状態** が生まれ得る。Step 1 では UI に注意書きだけ出して、整合性チェックはしない（自動再生成時に上書きされるのが前提）
- **言語タグ漏れ**: 手動編集で `<en>...</en>` などの言語タグを削除/追加した場合、TTS の挙動が変わる（`docs/speech-generation-flow.md` 参照）。textarea の placeholder で注意喚起
- **保存先の version_number**: 現状の section 編集 PUT は version を意識していない（DB のレコード ID 直指定）。dialogue 編集も同じく ID 直指定で OK。version 切り替え後の編集は「現在表示中バージョンの dialogue を直す」挙動になる
- **同時編集**: 単一ユーザー前提なので楽観的更新でよい。競合検出は不要

---

## 関連ドキュメント

- `docs/speech-generation-flow.md` — TTS フロー、言語タグ、emotion の扱い
- `prompts/lesson_generate.md` — 授業生成プロンプト（`wait_seconds` を出さない理由など）
- `plans/lesson-content-improvement.md` — 別物（生成プロンプトの品質改善プラン、UI 編集とは無関係）
