# 授業モード: TTS事前生成が対話モード(dlg)にならないバグの修正

## ステータス: 完了

## 背景

授業モードのTTS事前生成・再生で、dialoguesにテキストがあるにもかかわらず単話者モード（part）にフォールバックする。
結果、`section.content`（短い要約）だけが読み上げられ、dialoguesで設計されたdisplay_textの全文読み上げが行われない。

## 原因

**2箇所で `student_cfg` が `None` のときにdialogue全体をスキップしている。**

### 1. TTS事前生成 — `src/tts_pregenerate.py:48`

```python
def _parse_dialogues(section: dict, student_cfg: dict | None) -> list[dict] | None:
    dialogues_raw = section.get("dialogues", "")
    if not dialogues_raw or not student_cfg:  # ← ここ
        return None
```

`student_cfg` が `None`（DBに生徒キャラ未登録）だと、dialogues_rawに有効なJSONがあっても即座に `None` を返す。

### 2. 授業再生 — `src/lesson_runner.py:474`

```python
if dialogues_raw and self._student_cfg:  # ← ここ
    try:
        parsed = ...
```

同じく `self._student_cfg` が `None` だとdialogueパースを完全にスキップし、`_play_single_speaker()` にフォールバック。

### なぜ単話者モードだと問題なのか

`_play_single_speaker()` は `section["content"]`（短い要約テキスト）を読み上げる。
`display_text`（配信画面に表示する全文教材）は画面に表示されるが、音声としては読まれない。
dialogues にはdisplay_textを先生が紹介・読み上げるセリフが含まれているため、dialogueモードでないと教材の全文読み上げが実現できない。

### 下流コードは既に student_cfg=None に対応済み

- `_generate_dlg_tts()` L571: `cfg = (self._teacher_cfg or {}) if speaker == "teacher" else (self._student_cfg or {})`
- `_play_dialogues()` L600: `student_cfg = self._student_cfg or {}`
- `pregenerate_section_tts()` L97: `cfg = cfg or {}`

→ student_cfgがNoneでも`{}`にフォールバックし、voice/styleはNone（TTS側のデフォルト）になるだけで動作する。

## 修正方針

**`student_cfg` ガードを削除し、dialoguesがあれば常に対話モードで処理する。**

生徒キャラが未設定の場合、studentスピーカーの発話はTTSデフォルト音声で再生されるが、これは許容範囲。
（実運用では生徒キャラは通常設定済みだが、設定漏れでdialogue全体が無視されるのは重大なバグ。）

## 実装ステップ

### Step 1: `src/tts_pregenerate.py` の修正

`_parse_dialogues()` から `student_cfg` の条件を削除する。

```python
# Before
def _parse_dialogues(section: dict, student_cfg: dict | None) -> list[dict] | None:
    dialogues_raw = section.get("dialogues", "")
    if not dialogues_raw or not student_cfg:
        return None

# After
def _parse_dialogues(section: dict) -> list[dict] | None:
    dialogues_raw = section.get("dialogues", "")
    if not dialogues_raw:
        return None
```

`_parse_dialogues` の呼び出し元 (`pregenerate_section_tts` L80) も引数を修正。

### Step 2: `src/lesson_runner.py` の修正

`_play_section()` のdialogue判定から `self._student_cfg` を削除する。

```python
# Before (L474)
if dialogues_raw and self._student_cfg:

# After
if dialogues_raw:
```

### Step 3: ログメッセージの修正

`lesson_runner.py` L349 の起動ログを修正（dialogue有無の判定を student_cfg ではなく実際のdialogues有無にする）。

### Step 4: テスト

- 既存テスト `tests/test_lesson_runner.py` が通ることを確認
- student_cfg=None の状態でdialoguesが正しくパースされることを確認

## リスク

- **低リスク**: 下流コードは既にNullセーフ。student_cfgがNoneのときstudentスピーカーのvoice/styleがNone→TTSデフォルトになるだけ
- **キャッシュ互換性**: 既に part ファイルで生成済みのレッスンは、修正後に dlg ファイルで再生成が必要。管理画面のTTS再生成ボタンで対応可能
