# 掛け合いTTSの並列事前生成

## ステータス: 完了（2026-04-18）

実装完了。`src/comment_reader.py` (`speak_event` / `respond_webui` / `_respond`+`_segment_queue`) と `src/claude_watcher.py` (`_play_conversation`) で全エントリのTTSを並列起動→順次再生する方式に変更。`generate_tts` はキャンセル時にテンポラリをクリーンアップして再送出。割り込み・stop時は未完了タスクを `cancel()` する。

## 背景

キャラ2名の掛け合い（2〜4エントリ）を再生すると、エントリ間に数秒の「間」が発生する。原因は各エントリのTTS生成が直列で行われているため:

```
LLM生成 → [TTS生成1 → 再生1] → [TTS生成2 → 再生2] → [TTS生成3 → 再生3]
                                 ^^^^^^^^^^       ^^^^^^^^^^
                                 ここで数秒待ち   ここでも数秒待ち
```

Gemini 2.5 Flash TTSは1回あたり0.5〜1.5秒かかる。3エントリ掛け合いなら合計1〜4秒の余計な間。

一方、会話全体はLLMの1回呼び出しで既に全部揃っているので、再生前に全エントリのTTSを並列で先に生成しておけば、エントリ間の間を `asyncio.sleep(0.3)` の固定値まで詰められる。

```
LLM生成 → TTS生成1・2・3を並列起動 → [再生1] → [再生2] → [再生3]
          ^^^^^^^^^^^^^^^^^^^^^^
          生成1が終わる頃には2・3もほぼ完成
```

## 対象フロー

掛け合い（複数エントリを順次再生）しているコードパス:

| ファイル | 関数 | 用途 |
|---|---|---|
| `src/comment_reader.py` | `speak_event()` (multi=True) | Claude Code Hook・Git commit・作業開始 |
| `src/comment_reader.py` | `_respond()` (マルチキャラ) | Twitchチャット応答 |
| `src/comment_reader.py` | `respond_webui()` (マルチキャラ) | WebUIチャット応答 |
| `src/claude_watcher.py` | `_play_conversation()` | Claude Code実況 |

全4箇所で同じ「responses配列を順次speak」パターンを使っており、全てが改善対象。

## 設計方針

### 採用案: 並列事前生成 + 順次再生

```python
# 1. 全エントリのTTS WAVを並列生成開始
tasks = [
    asyncio.create_task(self._speech.generate_tts(
        entry["speech"],
        voice=cfg.get("tts_voice"),
        style=cfg.get("tts_style"),
        tts_text=entry.get("tts_text"),
    ))
    for entry, cfg in zip(responses, resolved_cfgs)
]

# 2. 先頭から順にawait→再生（後続タスクはバックグラウンドで生成継続）
for i, (entry, cfg, task) in enumerate(zip(responses, resolved_cfgs, tasks)):
    wav_path = await task  # 既に生成済みなら即返る
    if i > 0:
        await asyncio.sleep(0.3)  # キャラ間の間は固定0.3秒のみ
    await self._speech.speak(
        entry["speech"], wav_path=wav_path, ...
    )
```

- `speak()` は `wav_path` 引数を既にサポート（`src/speech_pipeline.py:104-125`）。指定時はTTS生成をスキップして再生のみ行う
- `generate_tts()` は失敗時 `None` を返す。`speak(wav_path=None)` は通常生成パスにフォールバックするので、並列タスクがこけても従来動作に戻る
- 並列生成中に `speak_lock` の順番待ちが発生することはない（`generate_tts` はロック取得しない）

### 代替案（不採用）

- **A. `asyncio.as_completed` で到着順再生**: 掛け合いは話者の順序が意味を持つので不可
- **B. ストリーミングTTS**: Gemini TTS APIはストリーミング対応していない
- **C. 1回のLLM呼び出しで全部入り音声を合成**: 話者ごとに声が違うので不可

## 実装ステップ

### Step 1: 共通ヘルパ関数を `src/speech_pipeline.py` に追加

4箇所で同じロジックを繰り返すのは避けたい。`SpeechPipeline` に薄いヘルパを追加:

```python
async def pregenerate_many(self, items: list[dict]) -> list[Path | None]:
    """複数エントリのTTSを並列で事前生成する。

    Args:
        items: [{"text": str, "voice": str | None, "style": str | None, "tts_text": str | None}, ...]

    Returns:
        list[Path | None]: 各エントリの生成WAVパス（失敗時None、入力と同じ長さ・順序）
    """
    tasks = [
        asyncio.create_task(self.generate_tts(
            it["text"], voice=it.get("voice"), style=it.get("style"), tts_text=it.get("tts_text"),
        ))
        for it in items
    ]
    return await asyncio.gather(*tasks, return_exceptions=False)
```

- `generate_tts` は既に失敗時Noneを返すので例外は出ない想定
- ヘルパはただの `gather` なので、呼び出し側で「1個目を先にawait→再生 / 残りはバックグラウンドで生成継続」としたい場合は `asyncio.create_task` 配列を直接使う（Step 2の各呼び出し元ではこちらを使う）

### Step 2: `speak_event()` (multi=True) を並列生成に変更

**ファイル**: `src/comment_reader.py` `speak_event()` のマルチキャラ分岐（行 505-536）

変更前（概略）:
```python
for i, entry in enumerate(responses):
    cfg = ...
    # speak() 内でTTS生成 → 再生
    await self._speech.speak(entry["speech"], voice=..., style=..., ...)
```

変更後:
```python
# 1. エントリ毎の設定を事前解決
resolved = []
for i, entry in enumerate(responses):
    cfg = self._characters.get(entry["speaker"], self._characters["teacher"])
    entry_voice = voice if i == 0 and voice else cfg.get("tts_voice")
    entry_style = style if i == 0 and style else cfg.get("tts_style")
    resolved.append({"entry": entry, "cfg": cfg, "voice": entry_voice, "style": entry_style})

# 2. 全エントリのTTSを並列起動
tts_tasks = [
    asyncio.create_task(self._speech.generate_tts(
        r["entry"]["speech"],
        voice=r["voice"], style=r["style"],
        tts_text=r["entry"].get("tts_text"),
    ))
    for r in resolved
]

# 3. 先頭から順にawait→再生
for i, (r, task) in enumerate(zip(resolved, tts_tasks)):
    entry, cfg = r["entry"], r["cfg"]
    wav = await task  # 並列生成中。先頭は~1秒待ち、後続はほぼ即返る
    if i > 0:
        await asyncio.sleep(0.3)
    self._speech.apply_emotion(entry["emotion"], avatar_id=entry["speaker"], character_config=cfg)
    await self._speech.speak(
        entry["speech"], wav_path=wav, voice=r["voice"], style=r["style"],
        avatar_id=entry["speaker"], subtitle={...},
        chat_result=entry if i == 0 else None,
        tts_text=entry.get("tts_text"),
        post_to_chat=self._post_to_chat if i == 0 else None,
    )
    self._speech.apply_emotion("neutral", avatar_id=entry["speaker"], character_config=cfg)
    await self._speech.notify_overlay_end()
    await self._save_avatar_comment(...)
```

注意点:
- `wav is None`（生成失敗）の場合は `speak(wav_path=None)` で従来動作（内部でリトライ）に自然フォールバックする
- 例外発生時に他のタスクがリークしないよう、`try: ...` で外側を囲み、`finally` で未await のタスクを `cancel()` する

### Step 3: `_respond()` のマルチキャラ経路に適用

**ファイル**: `src/comment_reader.py` `_respond()` 行 248-295

現状は:
1. `responses[0]` (1エントリ目) を即再生
2. `responses[1:]` は `_segment_queue` に積んで `_speak_segment` で逐次再生

`_segment_queue` を使う理由は「コメント到着で残り再生をキャンセル」するため（行122-124）。この動作は維持したい。

**設計**:
- `_respond` 内で全エントリのTTSを並列生成タスクとして起動
- 1エントリ目: TTS完了を待って即再生（従来通り）
- 2エントリ目以降: タスクを `_segment_queue` のセグメント辞書に `tts_task` キーとして格納
- `_speak_segment` で `tts_task` があればawait してそのwavを使う

セグメント辞書に追加するキー:
```python
{
    ...既存キー...,
    "tts_task": asyncio.Task,  # 並列生成中のTTSタスク（None許容）
}
```

`_speak_segment` の変更:
```python
async def _speak_segment(self, seg):
    wav_path = None
    task = seg.get("tts_task")
    if task is not None:
        try:
            wav_path = await task
        except Exception:
            wav_path = None
    # ... speak(wav_path=wav_path, ...)
```

コメント割り込みで `_segment_queue.clear()` する際、積まれていたタスクは実行中のまま残る。解消策:
```python
if self._segment_queue:
    for seg in self._segment_queue:
        t = seg.get("tts_task")
        if t and not t.done():
            t.cancel()
    self._segment_queue.clear()
```

### Step 4: `respond_webui()` のマルチキャラ経路に適用

**ファイル**: `src/comment_reader.py` `respond_webui()` 行 179-211

こちらは `_segment_queue` を使わず直接順次再生しているので、Step 2 と同じパターン（全エントリ並列起動 → 順次await→再生）をそのまま適用する。

### Step 5: `claude_watcher._play_conversation()` に適用

**ファイル**: `src/claude_watcher.py` `_play_conversation()` 行 373-434

ClaudeWatcher は「コメント割り込みで残り発話をスキップ」する（行 387-392）。並列生成済みの後続タスクがある場合、スキップ時にキャンセルする:

```python
tts_tasks = [asyncio.create_task(self._speech.generate_tts(...)) for dlg in dialogues]
try:
    for i, (dlg, task) in enumerate(zip(dialogues, tts_tasks)):
        if self._comment_reader and self._comment_reader.queue_size > 0:
            # 割り込み: 残りタスクをキャンセル
            for t in tts_tasks[i:]:
                if not t.done():
                    t.cancel()
            break
        wav = await task
        ...speak(wav_path=wav, ...)
finally:
    # 例外時も未完了タスクをキャンセル
    for t in tts_tasks:
        if not t.done():
            t.cancel()
```

### Step 6: テスト

**ファイル**: `tests/test_comment_reader.py`（新規 or 既存）、`tests/test_claude_watcher.py`

追加するテスト:
- `speak_event` のマルチキャラ経路で `generate_tts` が各エントリ分呼ばれ、かつ並列（ほぼ同時）に開始されることを確認
  - モックTTSにsleep入れて「1エントリ目awaitし始める前に全タスクが起動済み」を検証
- `speak` に `wav_path` が渡されることを検証（モックSpeechPipelineのspy）
- 生成失敗時 `wav_path=None` で `speak` が呼ばれ、従来のフォールバック経路を通ることを確認
- 割り込み時に未完了タスクが `cancel()` されることを確認（`_play_conversation`）

既存の `test_claude_watcher.py` は再生順序を検証しているはずなので、並列化後も順序は保たれていることを再確認。

### Step 7: ドキュメント更新

- `docs/speech-generation-flow.md` — 複数エントリの並列事前生成について追記（「テキスト生成 → 並列TTS → 順次再生」の図を追加）
- `MEMORY.md` / `.claude/projects/.../memory/tts-audio.md` — 並列生成パターンを記録

## 期待効果

| 条件 | 現状の合計「間」 | 変更後 |
|---|---|---|
| 2エントリ | TTS 0.5〜1.5秒 × 1回分の遅延 | 0.3秒（固定pause） |
| 3エントリ | TTS 0.5〜1.5秒 × 2回分 = 最大3秒 | 0.6秒 |
| 4エントリ | TTS 0.5〜1.5秒 × 3回分 = 最大4.5秒 | 0.9秒 |

体感上、「1人目が話し終わったらすぐ2人目が相槌」といった自然なテンポになる。

## リスク・注意点

1. **TTS並列リクエストのレート制限**: Gemini 2.5 Flash TTSのRPM制限に引っかかる可能性
   - 対策: 最大4エントリまでなので同時4リクエストが上限。公称60RPMに十分収まる
   - 万一レート制限が出たら `asyncio.Semaphore(2)` 等で絞る追加ステップを検討

2. **タスクリーク**: 例外や割り込みで未完了タスクが残ると、バックグラウンドで生成完了後にwavファイルが温存され温存されたままになる
   - 対策: 各呼び出し元で `try/finally` または割り込みパスで `task.cancel()` を徹底。`generate_tts` は `CancelledError` を受けたらテンポラリファイルをクリーンアップ済み（`src/speech_pipeline.py:98-102` の except 経路）

3. **メモリ使用量**: 最大4エントリ分のWAV（各~100KB〜1MB）を同時保持する。現状は1個ずつ。実害なし

4. **`_segment_queue` のタスク**: ユーザーが配信中に長時間コメントを投げないケースで、セグメントキュー内のタスクが数秒〜10秒程度保持される。問題なし（TTSは即生成完了する）

5. **generate_tts 内の一時ディレクトリ**: `tempfile.mkdtemp()` で作られたディレクトリは `speak()` が削除する。並列生成しても個別のテンポラリなので衝突なし

## ファイル変更一覧

| ファイル | 変更内容 |
|---|---|
| `src/comment_reader.py` | `speak_event()` / `_respond()` / `respond_webui()` を並列生成に変更。`_speak_segment` が `tts_task` をawait。`_segment_queue.clear()` 時にタスクをキャンセル |
| `src/claude_watcher.py` | `_play_conversation()` を並列生成に変更。割り込み時にタスクキャンセル |
| `src/speech_pipeline.py` | （任意）`pregenerate_many()` ヘルパ追加。各呼び出し元で `asyncio.create_task` を直接使う方針なら不要 |
| `tests/test_comment_reader.py` | 並列生成・フォールバック・キャンセルのテスト追加 |
| `tests/test_claude_watcher.py` | 並列生成・割り込み時キャンセルのテスト追加 |
| `docs/speech-generation-flow.md` | 並列事前生成フローを記載 |

## 完了条件

- 掛け合い（2〜4エントリ）の再生でエントリ間の「間」が体感で0.3秒程度になる
- TTS生成失敗時も従来通りの再生ができる（フォールバック動作）
- コメント割り込み時に未完了TTSタスクがリークしない
- `python3 -m pytest tests/ -q` が全通過
- サーバー起動確認（`curl /api/status`）OK
