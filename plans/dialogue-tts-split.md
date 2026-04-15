# 対話モード長文TTS分割

## ステータス: 未着手

## 概要

`_play_dialogues` で長い対話テキストを1回のTTS呼び出しで生成しているため、Gemini TTSの出力上限により末尾の音声が切り詰められる問題を修正する。

## 背景

- English 1-1 セクション2で442文字の対話テキストを1回のTTSに投げた結果、"Her office is" で音声が途切れた（末尾の約10%が無音）
- `_play_single_speaker` は `split_sentences()` で文単位に分割してから各文ごとにTTSを呼ぶため問題なし
- `_play_dialogues` は分割せず全文を1回のTTSに渡している

## 方針

`_play_dialogues` でも長文の対話テキストを `split_sentences()` で分割し、パートごとにTTS生成・再生する。短文（分割不要）はそのまま1回で処理。

## 実装ステップ

### Step 1: `_play_dialogues` の再生ループ内で分割

**ファイル**: `src/lesson_runner.py`

現在:
```python
content = dlg.get("content", "")
tts_text = dlg.get("tts_text", content)
# → 1回のTTS生成 + 1回のspeak
```

変更後:
```python
content = dlg.get("content", "")
tts_text = dlg.get("tts_text", content)
content_parts = SpeechPipeline.split_sentences(content)
tts_parts = SpeechPipeline.split_sentences(tts_text)
# → パートごとにTTS生成 + speak
```

### Step 2: TTS事前生成のキャッシュキー対応

現在のキャッシュは `dlg[index]` 単位。分割後は `dlg[index]_part[j]` のようにパート番号を含める必要がある。

### Step 3: 字幕表示の調整

分割されたパートごとに字幕が表示されるため、各パートの字幕は自然に短くなり、チャンク分割も不要になるケースが増える。

## 変更ファイル

| ファイル | 変更内容 |
|---------|---------|
| `src/lesson_runner.py` | `_play_dialogues` 内で `split_sentences()` による分割、キャッシュキー拡張 |

## リスク

- **キャッシュ互換性**: キャッシュキー変更により既存キャッシュが使えなくなる（再生成が必要）
- **対話テンポ**: パートごとにspeakするため、パート間に微小な間が入る可能性あり
- **split_sentencesの精度**: 英語テキスト（`.!?` ではなく `。！？` で分割）の場合に分割されない可能性がある → 必要なら英語句読点対応を追加
