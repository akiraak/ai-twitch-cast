# TTS生成に使用されたテキストの表示（管理画面 / C#サイドバー）

## ステータス
完了（2026-04-17）

## 背景

授業モードの各ダイアログは、画面表示用テキスト（`content`）とTTS読み上げ用テキスト（`tts_text`）を別々に持つ。`tts_text` はDB上に保存されており、管理画面の**セクション編集フォーム**や**注釈ビュー**では確認できるが、以下の場所では表示されていない。

1. **管理画面のダイアログ一覧**（`static/js/admin/teacher.js` 内の `_dlgs` レンダリング: line 887–898）
   - 現状は `dlg.content` のみ表示。`dlg.tts_text` が画面側テキストと異なる場合も見分けが付かない。
2. **C#コントロールパネルのサイドバーLessonタイムライン**（`control-panel.html` の `_renderDialogueGroup`: line 863–897）
   - `dlg.content` のみ表示。`tts_text` はそもそもWebSocket outlineに含まれていない。

TTSに実際に渡ったテキストが画面上で確認できないと、音声と画面表示のズレ・誤読・タグ処理の問題を追跡できない。

## 目的

各ダイアログに対して「TTS生成に使用されたテキスト（= `tts_text`、`content` と異なる場合のみ）」を以下2箇所に表示する:

- 管理画面の授業ダイアログ一覧（セクション内のdialogue行）
- C#アプリ コントロールパネル サイドバーのLessonタイムライン

## 対象外（今回はやらない）

- 言語タグ変換後の「Geminiに実際に渡ったプロンプト」の表示（`src/tts.py:116` の `_convert_lang_tags` 処理後のテキスト）
  - これはログにしか残っていない。必要になれば別プランで対応。
- 単話者モードでセクション → 文単位に split された内訳の表示

## 実装ステップ

### 1. サーバ → C# のバンドルに `tts_text` を含める

- `src/lesson_runner.py:904` `_wav_to_bundle_entry()` の戻り辞書に `"tts_text": dlg.get("tts_text", "")` を追加。
  - `content` と同じ場合も空文字ではなく同一値を入れて OK（消費側で差分判定する）。
- これにより `lesson_load` で C# に渡るバンドルに TTS テキストが含まれる。

### 2. C# 側のデータ構造と outline 送信

- `win-native-app/WinNativeApp/Streaming/LessonPlayer.cs`
  - `DialogueData`（line 10–21）に `public string TtsText { get; set; } = "";` を追加。
  - `ParseDialogue()`（line 578）で `tts_text` を読み取り `TtsText` にセット。
  - `SendOutlineToPanel()`（line 137）の dialogue projection（main/answer 両方）に `tts_text = d.TtsText` を追加。

### 3. C# コントロールパネル UI

- `win-native-app/WinNativeApp/control-panel.html`
  - `_renderDialogueGroup()`（line 863–897）で、`dlg.tts_text` が存在しかつ `dlg.content` と異なる場合、`.ld-content` の下に小さめのセカンダリ行として追加表示する。
  - 差分がない場合は何も出さない（UIノイズ防止）。
  - スタイルは既存の `.ld-row` に合わせ、`color` を薄くし、アイコン（例: `\u{1F3A4}`）で区別。

### 4. 管理画面 UI

- `static/js/admin/teacher.js`
  - `_dlgs` レンダリングブロック（line 842–900）の `<div style="margin-top:2px; color:#2a1f40;">${esc(dlg.content || '')}</div>`（line 896）の直後に、
    `dlg.tts_text && dlg.tts_text !== dlg.content` の場合のみ「TTS: 〜」の行を追加。
  - スタイルは既存の監督指示ブロック（line 892–895）に準じ、薄色背景＋左ボーダーで視覚的に区別。

### 5. テスト

- `tests/test_lesson_runner.py`: `_wav_to_bundle_entry`（または代替のパブリックI/F）が返す辞書に `tts_text` が含まれることを確認。
- `tests/test_native_app_patterns.py`: C# ソース上で `LessonPlayer.cs` の `DialogueData` に `TtsText` が存在することをパターンマッチで確認（他パターンと同様のスタイル）。
- 既存テストがregressしないことを `python3 -m pytest tests/ -q` で確認。

### 6. 動作確認

- 授業を一本ロードし、`content ≠ tts_text` のダイアログが含まれるものを選んで:
  - 管理画面のダイアログ一覧にTTSテキストが併記されること
  - C# 起動後、コントロールパネルのLessonタイムラインにTTSテキストが併記されること
- `content == tts_text` のダイアログで余分な行が出ないことを確認。

### 7. ドキュメント / メモリ更新

- `DONE.md` に 1 行追記。
- `TODO.md` から該当行を削除。
- `.claude/projects/-home-ubuntu-ai-twitch-cast/memory/` の授業関連メモリ（`lesson`関連のファイル）に、`lesson_outline` に `tts_text` が含まれるようになった旨を追記。

## リスク / 注意

- **送信データ量の増加**: outline に tts_text が増えるが、1ダイアログあたり数十〜数百文字のオーダーで影響は小さい。
- **差分判定**: JS/C# 両側で「`content` と同じなら表示しない」ロジックが必要。片側だけだと二重表示になる。
- **キャッシュされた既存WAVには影響しない**: 表示のみの変更で、TTS再生処理や生成ロジックは変えない。
- **後方互換**: 旧バンドルに `tts_text` が欠けていても、C# 側は `""`、JS側は `undefined` で無視されるよう実装する（`TryGetProperty` パターンを踏襲）。

## 関連ファイル

- `src/lesson_runner.py:904` (_wav_to_bundle_entry)
- `src/tts.py:116` (_convert_lang_tags — 参考、今回は触らない)
- `src/db/core.py:284` (lesson_sections スキーマ — 既に tts_text 存在)
- `win-native-app/WinNativeApp/Streaming/LessonPlayer.cs:10,137,578`
- `win-native-app/WinNativeApp/control-panel.html:863`
- `static/js/admin/teacher.js:887`
