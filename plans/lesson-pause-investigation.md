---
ステータス: 進行中（Step 1, 2, 3 完了 / Step 4 以降）
作成日: 2026-05-06
更新日: 2026-05-06（Step 3 完了: C# 側 LessonTimings 受信・ハードコード値を _timings 参照に置換）
関連TODO: 「クイズの解答前に長い間がある。この原因の調査。また同様に会話やセクションの間になりそうなところがないか調査」
---

# 授業再生 — 「間」の時間を単一 config ファイルに集約する

## 1. 目的

ユーザー報告: **クイズ（question セクション）の解答前に長い間がある**。同様に dialogue 間 / セクション間にも違和感の出やすい箇所がある。

これを次の 2 ステップで解消する:

1. **棚卸し**: 再生フローで発生する「間」の発生源をすべて特定する（§2）
2. **集約**: 全ての「間」を **1 つの config ファイル** に集約し、そこを編集すれば全授業に即反映されるようにする（§3〜§4）

**ユーザー方針**: 「全部 config 固定」— 授業ごとの `wait_seconds` 上書きは廃止する。授業 JSON / DB から `wait_seconds` を削除し、再生時はすべて config 値を参照する。

## 2. 既存の「間」発生源の棚卸し

すべてのコード位置は `win-native-app/WinNativeApp/Streaming/LessonPlayer.cs` を指す（明示外を除く）。

### 2.1 セクション再生の構造（再掲）

```
[各セクション]
  showText()                                      ← InjectJs
  PlayDialoguesAsync(main_dialogues)
    [各 dialogue]
      startDialogue() / PlayAudio() / endDialogue()
      ─ dialogue 間: PauseAwareDelayAsync(300)   ← (※A) 固定 300ms
  ※ section_type == "question" のとき:
      PauseAwareDelayAsync(question.wait_seconds * 1000)   ← (※B) 解答前の間（DB値）
      PlayDialoguesAsync(answer_dialogues)
  hideText()
  PauseAwareDelayAsync(section.wait_seconds * 1000)        ← (※C) セクション間（DB値）
```

### 2.2 設定で動かせる「間」（集約対象）

| ID | 名称 | 現在の置き場所 | 単位 | 既定 |
|----|------|-----------------|------|------|
| **A** | dialogue 間ギャップ | `LessonPlayer.cs:631-635` ハードコード | ms | 300 |
| **B** | question 解答前の間 | DB `sections.question.wait_seconds`（LLM 生成） | sec | 8（推奨 8-15） |
| **C** | セクション間の間 | DB `sections.wait_seconds`（LLM 生成） | sec | 2（推奨 2-3） |
| **D** | PlaybackStopped fallback 余裕 | `MainForm.cs:2075` ハードコード | sec | 1.5 |

### 2.3 設定では動かせない「間」（参考・スコープ外）

| ID | 名称 | 出所 | 備考 |
|----|------|-----|------|
| E | WAV 末尾無音 | TTS 生成（Gemini）／`src/tts.py` | 個別 wav に依存。config 化は別タスク（必要なら TTS 後処理で trim） |
| F | InjectJs / WebView2 のレイテンシ | C# → JS の同期コスト | OS / ハード依存。本タスクでは扱わない |

これら（特に E）は §6 の調査結果次第で別 TODO として切り出す。

## 3. config ファイル設計

### 3.1 配置先

**結論: `scenes.json` に `lesson_timings` キーを追加する**（既存の `audio_volumes` と同じ既存パターン）。

理由:
- 専用ファイル新設だと読み込み経路を増やすだけで利点が薄い
- `scenes.json` は既に Python（`scene_config.py`）から読み込まれており、配信プロセス内で一元管理されている
- 既存パターンに合わせれば、ホットリロード（再起動なしの反映）も既存の挙動と揃う

### 3.2 スキーマ

```json
{
  "audio_volumes": { ... },
  "lesson_timings": {
    "inter_dialogue_gap_ms": 300,
    "playback_stopped_fallback_extra_sec": 1.5,
    "section_wait_sec": {
      "introduction": 2,
      "explanation": 2,
      "example": 2,
      "question": 3,
      "summary": 3,
      "default": 2
    },
    "question_answer_wait_sec": 8
  }
}
```

- **`inter_dialogue_gap_ms`** … (※A) dialogue 間ギャップ
- **`playback_stopped_fallback_extra_sec`** … (※D) PlayLessonAudioAsync の fallback 余裕
- **`section_wait_sec`** … (※C) セクション間の間。`section_type` 別に指定可能、不在なら `default`
- **`question_answer_wait_sec`** … (※B) question セクションの解答前の間（単一値）

`section_type` 別マップにする理由: 推奨表（`prompts/lesson_generate.md:168`）が type 別に違うため。ただしすべて `default` に統一する選択も可能（後述 §7.1 で議論）。

### 3.3 受け渡し経路

`LessonPlayer` は C# 側に常駐するため、Python 側の config を C# に渡す必要がある。

**結論: `lesson_load` イベントの payload に `timings` オブジェクトを含めて C# に渡す**。

- `scripts/routes/teacher.py` で授業ロード時に `scene_config.get_lesson_timings()` を呼び、payload に同梱
- C# `LessonPlayer.LoadLesson(JsonElement json)` でパース、`_timings` フィールドに保持
- 以後の再生で `_timings.InterDialogueGapMs` / `_timings.QuestionAnswerWaitSec` 等を参照

利点:
- 授業をロードした時点の値が固定される（再生中に config が変わっても暴れない）
- 次の lesson_load で新しい値が反映される（実質ホットリロード）
- C# 側に独立した設定ファイル読み込みロジックを増やさない

### 3.4 デフォルト値とフォールバック

- C# 側は `_timings == null` の場合に **コード内既定値**（A=300, B=8, C=2, D=1.5）にフォールバック
- Python 側で `scenes.json` に `lesson_timings` が無ければ §3.2 の既定で初期化（書き戻しはしない）
- 不正値（負数、NaN、文字列など）は既定値にクランプし `Log.Warning` を出す

## 4. 実装方針

### 4.1 Python 側

#### 4.1.1 `src/scene_config.py`
- `get_lesson_timings() -> dict` を追加
- `scenes.json` の `lesson_timings` キーを読み、欠損時は §3.2 の既定値を返す
- `set_lesson_timings(value)` も用意（管理画面 API から書き換え用、必要に応じて）

#### 4.1.2 `scripts/routes/teacher.py`
- `POST /api/lessons/{id}/start`（と `/load`）で lesson payload を作るときに `timings = scene_config.get_lesson_timings()` を呼んで同梱
- 既存の section データから `wait_seconds` を **送信しない**（C# 側でも参照しないので削除）

#### 4.1.3 `src/db/lessons.py` / 授業 JSON 周り
- DB スキーマの `wait_seconds`（sections / question）は **既存データ保持のため残す**（マイグレーションせず）
- ただし read 経路では参照しない・write 経路は何も書かない（NULL 許容）
- 将来削除する場合は別タスク

#### 4.1.4 `prompts/lesson_generate.md`
- セクションスキーマから `wait_seconds` フィールドを削除
- `section_type` 別の推奨表（`168行目`）も削除（config に移ったため）
- LLM が誤って生成しても無視される旨を明記

#### 4.1.5 `src/lesson_generator/extractor.py` / `improver.py`
- セクション生成ロジックで `wait_seconds` を組み立てている箇所があれば削除

### 4.2 C# 側

#### 4.2.1 `LessonPlayer.cs`
- `class LessonTimings { ... }` を追加（4 フィールド）
- `LoadLesson` で `timings` JSON をパースして `_timings` に保持
- `PlayDialoguesAsync` の `PauseAwareDelayAsync(300, ct)` を `_timings.InterDialogueGapMs` に置換
- `PlaySectionInternalAsync` の `section.WaitSeconds * 1000` を `_timings.SectionWaitSec(section.SectionType) * 1000` に置換
- `PlaySectionInternalAsync` の `section.Question.WaitSeconds * 1000` を `_timings.QuestionAnswerWaitSec * 1000` に置換
- `SectionData.WaitSeconds` / `QuestionData.WaitSeconds` フィールドは削除（または `[Obsolete]`）

#### 4.2.2 `MainForm.cs`
- `PlayLessonAudioAsync` の `Task.Delay(TimeSpan.FromSeconds(duration + 1.5), ct)` を `_timings.PlaybackStoppedFallbackExtraSec` に置換
- `LessonPlayer` から `_timings` を取得するアクセサを追加（または `MainForm` も `LessonPlayer.Timings` プロパティ経由）

#### 4.2.3 `CalcRemainingDuration`
- `LessonPlayer.cs:434-460` で `sec.Question.WaitSeconds` / `sec.WaitSeconds` を見ているので config 値に置換

### 4.3 管理画面（任意・第2フェーズ）

`scenes.json` を直接編集する運用で十分だが、将来的に管理画面から `lesson_timings` を編集できる UI を用意するなら別タスクとして起票。

## 5. 実装ステップ

### Step 1: config スキーマと Python 側の読み出し
1. `scenes.json` に `lesson_timings` の既定値を追加
2. `src/scene_config.py` に `get_lesson_timings()` を実装
3. `tests/test_scene_config.py` に既定値・欠損時フォールバック・不正値クランプのテストを追加

### Step 2: lesson_load payload に timings 同梱（完了 / 2026-05-06）
1. `src/lesson_runner.py` の `_send_all_and_play` で `ws_request("lesson_load", ...)` に `timings=get_lesson_timings()` を同梱（teacher.py ではなく実際のペイロード組立箇所はここ）
2. `_build_section_bundle` から `wait_seconds` を削除、`_build_question_data` から `wait_seconds` を削除
3. `_calc_section_duration` を `timings` 引数ベースに変更（section_type 別 section_wait_sec / question_answer_wait_sec を参照）
4. `tests/test_lesson_runner.py` を更新: TestQuestionData / TestBuildSectionBundle / test_calc_section_duration を新フォーマットに合わせ、`test_sends_lesson_load_with_all_sections` に `timings` 同梱と section から `wait_seconds` が消えていることの検証を追加

**注意**: Step 4 で `prompts/lesson_generate.md` から `wait_seconds` を削除した後も、過去 LLM 出力に残った `wait_seconds` は `import-sections` で DB に書き戻る可能性がある。Python は読まない / C# は受信しないので実害なし（プラン §8.1 の通り）。

### Step 3: C# 側で timings を受信して使用（完了 / 2026-05-06）
1. `LessonPlayer.cs` に `LessonTimings` クラス追加（4 設定値 + `GetSectionWaitSec()` + `FromJson()`）+ `LoadLesson` で `json.timings` をパースして `_timings` に保持。`Timings` プロパティで MainForm から参照可能。`timings` キー不在時はコード内既定値（A=300, B=8, C=type別 default=2, D=1.5）にフォールバック + `Log.Warning`
2. `PlayDialoguesAsync`: `PauseAwareDelayAsync(300, ct)` → `PauseAwareDelayAsync(_timings.InterDialogueGapMs, ct)`
3. `PlaySectionInternalAsync`: question wait → `_timings.QuestionAnswerWaitSec * 1000`、セクション間 → `_timings.GetSectionWaitSec(section.SectionType) * 1000`
4. `CalcRemainingDuration`: `sec.Question.WaitSeconds` / `sec.WaitSeconds` を `_timings` 参照に置換
5. `MainForm.PlayLessonAudioAsync`: `duration + 1.5` → `duration + _lessonPlayer.Timings.PlaybackStoppedFallbackExtraSec`
6. `SectionData.WaitSeconds` / `QuestionData.WaitSeconds` を削除、`ParseSectionData` から `wait_seconds` パースも削除
7. `tests/test_native_app_patterns.py` にガード追加（5 ケース、全 32 テスト green）

**注意**: `PlayTtsLocally` の `duration + 1.5` は授業ではなく単発 TTS チェーン再生用なので対象外（plans/tts-batch-playback-hang-fix.md Fix B）。

### Step 4: LLM プロンプト・既存データの整理
1. `prompts/lesson_generate.md` から `wait_seconds` 関連の記述を削除
2. `src/lesson_generator/*.py` で `wait_seconds` 生成箇所を削除
3. DB 内の既存値は保持（マイグレーションなし、参照経路を切るだけ）

### Step 5: 動作確認
1. `pytest tests/ -q -m "not slow"` 全 green
2. Windows 実機で授業再生 → クイズ前の間 / dialogue 間 / セクション間 が config 通りであることを実測
3. `scenes.json` の `lesson_timings.question_answer_wait_sec` を 8 → 5 に変更 → サーバー再起動なしでも次回 lesson_load から反映されること

### Step 6: ドキュメント更新
1. `DONE.md` に変更内容を追記
2. `TODO.md` から該当行を削除
3. このプランの `ステータス: 完了` に変更
4. `CLAUDE.md` または `docs/` に「授業の間は scenes.json で調整」を1行記載

## 6. 既存の不可視レイテンシの確認（参考調査）

config 化と並行して、§2.3 の参考レイテンシが体感に効いていないか軽く確認する。**実装には含めない**（このタスクでは config 化が主目的）。

### 6.1 計測ログ追加（暫定）
- `Log.Information("[Lesson] Audio gap: dialogue={I} expected={Exp:F2}s actual={Act:F2}s", ...)` のような行を `PlayDialoguesAsync` に暫定追加
- 1 授業（lesson_id 100 推奨）を流して `tail jslog.txt` または C# ログを確認
- 計測終わったらログは戻す

### 6.2 期待値
- `inter_dialogue_gap_ms` を 300 → 0 にしても体感的にギャップが残るなら、WAV 末尾無音（E）が支配的
- `question_answer_wait_sec` を 8 → 4 にしても「長い」と感じるなら、視覚演出側（hideText 後の暗転、表情切替の遅延）が効いている可能性

### 6.3 別タスク化候補
- TTS WAV の末尾無音 trim（`src/tts.py`）
- question wait 中のカウントダウン UI / 効果音（演出で間を埋める）
- アバター切替時のフェード短縮

## 7. 設計上の論点

### 7.1 `section_wait_sec` を section_type 別マップにすべきか
**案 A（提案中）**: `{introduction: 2, ..., question: 3, default: 2}` 形式
**案 B**: 単一値 `section_wait_sec: 2`

- A の利点: 推奨表（プロンプト）と整合、`question` だけ余韻を長く取る等の柔軟性
- B の利点: シンプル。管理画面で1スライダにできる
- ユーザーが「シンプルに1値で」を選ぶなら B に切り替え可能（実装コストはほぼ同じ）

### 7.2 `inter_dialogue_gap_ms` の将来拡張
- 現状: 全 dialogue 間で固定
- 将来案: 同一 speaker 連投時は短く、speaker 切替時は長く（例 200ms / 400ms）
- 今回はスコープ外。スキーマを `inter_dialogue_gap_ms`（数値1個）にしておけば後から `{same_speaker: 200, switch: 400}` に拡張しても下位互換は取れる

### 7.3 ホットリロードの粒度
- 現方針: lesson_load 単位で固定（再生中の変更は無視）
- これでユーザー要件「config 変更で反映される」は満たす（次の授業ロードから即時反映）
- もし「再生中の section.WaitSeconds を即時変更したい」なら別実装になるが、今回は不要

## 8. リスク・注意点

### 8.1 既存授業データの整合
- DB / 授業 JSON に残っている `wait_seconds` は無視される
- ユーザーが手動で授業 JSON をエクスポートして再インポートしたとき、古い `wait_seconds` がそのまま DB に書き戻る → C# は無視するので実害なし。ただし**「DB の値が読まれていない」ことに気付きにくい**ので、`docs/` または `prompts/lesson_generate.md` に明記する

### 8.2 C# 側の `_timings == null` フォールバック
- 古い Python サーバーが `timings` を送らない場合、C# は既定値で動作 → サーバー / ネイティブアプリのバージョン不一致でも壊れない
- ログに `Log.Warning("[Lesson] timings missing in lesson_load, using defaults")` を出す

### 8.3 単体テスト
- C# 側は `tests/test_native_app_patterns.py` にハードコード除去ガード（`PauseAwareDelayAsync\(300\b` が残っていない等）を追加
- Python 側は `tests/test_scene_config.py` で既定値とフォールバックを検証

### 8.4 リグレッション防止
- 既存の `wait_seconds` を持つ授業を再生 → 体感的に同じ秒数（config 既定値）で再生されること
- 既存テスト `tests/test_api_teacher.py` の payload 検証が `wait_seconds` を期待していたら更新

## 9. 受け入れ基準

- [ ] `scenes.json` に `lesson_timings` セクションがあり、§3.2 のスキーマで読み書きできる
- [ ] `LessonPlayer` のハードコード値（A=300, D=1.5）と DB 由来値（B, C）がすべて `_timings` 参照に置換されている
- [ ] `prompts/lesson_generate.md` から `wait_seconds` の記述が削除されている
- [ ] `scenes.json` の値を変更すると、次の lesson_load から即時反映される（再起動不要）
- [ ] `tests/test_scene_config.py` / `tests/test_api_teacher.py` / `tests/test_native_app_patterns.py` が green
- [ ] Windows 実機で再生してクイズ解答前の間 / dialogue 間 / セクション間が config の値と一致すること
- [ ] `DONE.md` 更新・`TODO.md` 該当行削除・このプランの `ステータス: 完了` 化
