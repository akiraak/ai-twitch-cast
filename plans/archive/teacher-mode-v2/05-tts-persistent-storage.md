# TTS音声ファイルの永続保存

## ステータス: 完了

## 背景

現在TTS音声は `/tmp/tmpXXXXXX/speech.wav` に一時生成され、再生後すぐ削除される。
セクションを再生するたびにGemini TTS APIを呼び出すため:
- 毎回数秒のTTS生成待ちが発生する（事前一括生成で再生間は短縮済みだが、生成自体の待ちは残る）
- 同じセクションを何度再生しても毎回API呼び出し → コスト・時間の無駄
- 生成結果の確認・デバッグが困難（再生後にファイルが消える）

## 現状のコード

### TTS生成（`src/speech_pipeline.py:82-98`）
```python
async def generate_tts(self, text, voice=None, tts_text=None):
    wav_path = Path(tempfile.mkdtemp()) / "speech.wav"
    await asyncio.to_thread(synthesize, tts_text or text, str(wav_path), voice=voice)
    return wav_path
```

### 再生後削除（`src/speech_pipeline.py:207-210`）
```python
self._current_audio = None
wav_path.unlink(missing_ok=True)
wav_path.parent.rmdir()
```

### 授業再生時の事前生成（`src/lesson_runner.py:203-212`）
```python
wav_paths = []
for i, part in enumerate(content_parts):
    wav = await self._speech.generate_tts(part, tts_text=part_tts)
    wav_paths.append(wav)
```

## 改善内容

### 保存先

```
resources/audio/lessons/{lesson_id}/section_{order_index}_part_{part_index}.wav
```

例:
```
resources/audio/lessons/1/
├── section_00_part_00.wav    # セクション1の1文目
├── section_00_part_01.wav    # セクション1の2文目
├── section_01_part_00.wav    # セクション2の1文目
├── section_01_part_01.wav
├── section_01_part_02.wav
└── ...
```

### 生成タイミング

スクリプト生成直後ではなく、**授業再生時の事前生成のタイミング**でキャッシュする。

1. `_play_section` でTTS事前生成時、まずキャッシュファイルの存在を確認
2. あればそれを使う（TTS API呼び出しスキップ）
3. なければ生成してキャッシュに保存

### キャッシュ無効化

以下のタイミングでキャッシュを削除する:
- セクションの `tts_text` が編集された時（`updateSectionField` API）
- スクリプト再生成時（`generate-script` API、`delete_lesson_sections` で既存セクション削除時）
- レッスン削除時（既存の `_clear_lesson_data` にディレクトリ削除を追加）

### 変更対象

- `src/lesson_runner.py` — `_play_section` のTTS事前生成ループでキャッシュ確認・保存
- `src/speech_pipeline.py` — `generate_tts()` にキャッシュパス指定オプション追加（または lesson_runner 側で制御）
- `scripts/routes/teacher.py` — セクション編集・スクリプト再生成・レッスン削除時にキャッシュ削除
- `src/db.py` または定数定義 — `LESSON_AUDIO_DIR` パス定義

### WebUI表示

管理画面のスクリプト生成セクション（Step 2b）で、各セクションにTTSキャッシュの状態を表示:
- キャッシュあり: ファイルパスとサイズを表示
- キャッシュなし: 「未生成（初回再生時に生成）」表示
- API: `GET /api/lessons/{lesson_id}/tts-cache` でキャッシュ状況を返す

## 想定API

```
GET /api/lessons/{lesson_id}/tts-cache
→ { ok: true, sections: [
     { order_index: 0, parts: [
         { part_index: 0, path: "resources/audio/lessons/1/section_00_part_00.wav", size: 48000 },
         { part_index: 1, path: "resources/audio/lessons/1/section_00_part_01.wav", size: 52000 },
       ]},
     { order_index: 1, parts: [] },  // 未生成
   ]}

DELETE /api/lessons/{lesson_id}/tts-cache
→ 全キャッシュ削除

DELETE /api/lessons/{lesson_id}/tts-cache/{order_index}
→ 特定セクションのキャッシュ削除
```

## リスク

- ディスク使用量の増加 → WAVは16bit mono 24kHz なので1秒≒48KB、10セクション×3パート×5秒=約7MB/レッスン。許容範囲
- キャッシュ不整合（tts_textを編集したのにキャッシュが残る）→ 編集APIでキャッシュ削除を確実に行う
- `.gitignore` に `resources/audio/` を追加する必要あり
