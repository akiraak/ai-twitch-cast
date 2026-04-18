# Claude Code 実況のセリフ間ギャップを詰める（バッファ縮小 + speak_batch 化）

## ステータス: 完了（ステップ1 + ステップ2 実装済み）

## 要旨

Claude Code 実況でセリフ間に最大4秒前後のギャップが残る問題の本命原因は、当初想定していた NAudio の再生バッファではなく、**`comment_reader.speak_event` マルチキャラパスが旧 `speak()` をループで呼んでおり `_wait_tts_complete` のポーリング（per-entry で数秒）を挟んでいること**だった（2026-04-18 の server.log 実測で判明）。

本プランは以下の2ステップ構成に更新する:

1. **ステップ1 — NAudio バッファ縮小（完了）**: 単発再生の開始/終端レイテンシを 〜400ms 短縮
2. **ステップ2 — `speak_event` マルチを `speak_batch` に移行（本命・未着手）**: per-entry の `_wait_tts_complete` 消滅でギャップを 500ms 以下に

## 背景（2026-04-18 実測）

- 実装済みのチェーン再生（`plans/claude-narration-chain-playback.md`）は **`claude_watcher._play_conversation` 側だけ** に適用されていた
- Hook 経由の `/api/avatar/speak` → `reader.speak_event` はマルチキャラでも旧 `_speech.speak()` をループで呼ぶ実装が残っていた（`src/comment_reader.py:600-635`）
- 旧 `speak()` は `_wait_tts_complete`（`src/speech_pipeline.py:246-265`）で C# 側 `IsTtsActive` をポーリングし、duration × 0.5 秒を上限に追加待機する。これが **2〜6秒の余剰** を生む

### server.log 実測（2026-04-18）

```
13:14:36  [tts] C#音声投入完了: 363ms       ← entry#0 送信
          ... entry#0 再生中 ...
13:14:48  [tts] TTS完了待ち: 4.0秒追加       ← _wait_tts_complete の余剰
13:14:48  [tts] C#音声投入完了: 191ms       ← entry#1 送信
13:14:54  [tts] TTS完了待ち: 2.0秒追加
13:14:55  [tts] C#音声投入完了: 180ms       ← entry#2 送信
13:15:11  [tts] TTS完了待ち: 5.4秒追加
13:15:12  [tts] C#音声投入完了: 206ms       ← entry#3 送信
13:15:19  [tts] TTS完了待ち: 2.2秒追加
```

---

## ステップ1（完了）: NAudio バッファ縮小

### 変更

`win-native-app/WinNativeApp/MainForm.cs:1475` の `PlayTtsLocally` 内 `WaveOutEvent` に `DesiredLatency=100, NumberOfBuffers=3` を明示指定。既定（300ms × 3 = 900msバッファ）→ 100ms × 3 = 300msバッファ。

### 効果の評価

- 単発再生の開始・終端で合算 〜400ms 短縮（計測待ち）
- しかし本問題の主因（数秒の `_wait_tts_complete` 余剰）には効かないため、体感改善は限定的
- ただし **ステップ2 実装後** は NAudio バッファが最後に残るギャップ源になるため、ここでの短縮は効いてくる

### 検証待ち項目

- 5 分以上の連続実況で音切れ・プツッとしたノイズが出ないか（Windows 側で要実配信確認）
- 問題なければ `NumberOfBuffers=2` への更なる縮小（ステップ1-b）を検討

---

## ステップ2（完了）: `speak_event` マルチを `speak_batch` に移行

### 方針

`src/comment_reader.py:573-635` のマルチキャラパスを、`src/claude_watcher.py:373-495` の `_play_conversation` と同じ構造に書き換える:

- TTS 並列生成 → 全 WAV 完了待ち → `entries` 組み立て → `self._speech.speak_batch(entries)` 一括送信
- エントリごとの字幕・口パク・感情は C# からの `tts_entry_started` Push に乗せて発火（`speak_batch` 内部で既に実装済み）
- DB 保存（`_save_avatar_comment`）は `speak_batch` 呼び出し前にまとめて行う（`_play_conversation` の前例に合わせる）
- コメント割り込み監視（`_watch_interrupt` → `cancel_tts_batch`）も合わせて移植

### 影響範囲

`speak_event` マルチ経路は以下のイベントで使われている:

| 入り口 | 経路 |
|---|---|
| Claude Code Hook（`/api/avatar/speak`） | `avatar.py:30` → `speak_event` |
| Git コミット報告 | `comment_reader` のコミット監視 → `speak_event` |
| Twitch 配信開始通知など | 同上 |
| TTS テスト multi（`/api/tts/test-multi`） | segment_queue 経由（別系統、本プラン対象外） |

### 実装ステップ

1. `speak_event` マルチ分岐（line 574-635）を `speak_batch` ベースに書き換え
   - `_play_conversation` を参考に構造を合わせる
   - `chat_result` / `post_to_chat` / `first entry translation` の扱いは既存挙動を保つ
2. `post_to_chat`（最初のエントリのみ）の発火タイミングを `speak_batch` 前または前後で適切に挟む
3. 旧 `_wait_tts_complete` 呼び出しは `speak_batch` 経由では通らないため除去される（`speak()` 側は他経路で残る）
4. テスト追加: `tests/test_comment_reader.py`（無ければ新設）で `speak_event` multi が `speak_batch` を1回呼び、per-entry の `speak` は呼ばれないことを確認
5. 既存テスト `tests/test_speech_pipeline.py::TestSpeakBatch` と `tests/test_claude_watcher.py` が通ることを確認

### 対象ファイル

| ファイル | 想定変更 |
|---|---|
| `src/comment_reader.py` | `speak_event` マルチ分岐を `speak_batch` ベースに書き換え |
| `tests/test_comment_reader.py` | （必要なら新設）マルチパスが `speak_batch` を呼ぶ回帰テスト |
| `docs/speech-generation-flow.md` | マルチキャラ経路のフロー図を更新 |
| `.claude/projects/.../memory/tts-audio.md` | チェーン再生の適用範囲を更新 |

## リスク

1. **字幕・口パク・感情の同期タイミングが微妙に変わる**
   - 旧: Python 側が順番に `speak()` → 内部で `notify_overlay` / `apply_emotion` を発火
   - 新: `speak_batch` が C# の `tts_entry_started` Push を受けて発火
   - `_play_conversation` で既に動いている経路なので挙動は検証済み
2. **`chat_result` / `post_to_chat` の発火タイミング**
   - 旧: 最初のエントリの `speak()` 内で 2 秒遅延後に投稿
   - 新: `speak_batch` には `chat_result` を渡すインターフェースがないため、`speak_batch` 呼び出しの直前または開始Push受信後に別途発火する必要がある
3. **コメント割り込み時の中断**
   - 旧: per-entry の `speak()` ループなので、次エントリの前にコメントキューを見ればよい
   - 新: `speak_batch` 中は C# キューに全 WAV が積まれているため、`cancel_tts_batch` で中断する必要あり（`_play_conversation` の `_watch_interrupt` を移植）

## 検証

- `stream.sh` で配信アプリ起動 → `curl -X POST http://localhost:$WEB_PORT/api/avatar/speak ...` で multi 発話を連続でトリガー
- `server.log` で `TTS完了待ち` が出なくなったこと、`[batch] 素材準備完了` + `[batch] C#へバッチ送信完了` + `tts_entry_started` のタイムスタンプ間隔が `duration + 0.5秒` 以内に収まることを確認
- `jslog.txt` で `tts_entry_started` / `tts_batch_complete` Push が正常発火していることを確認
- 5 分以上の連続実況で音切れ・字幕のずれ・感情切替の飛びが起きないこと
- `python3 -m pytest tests/ -q` でリグレッションチェック

## 完了条件

- Claude Code 実況の `C#音声投入完了` 間隔（entry#n → entry#n+1）が **`duration + 500ms 以下`** に収まる
- `server.log` から `TTS完了待ち: N.N秒追加` が消える（または ステップ1-b 以降の小さな値に収まる）
- 字幕・口パク・感情切替のズレが体感で目立たない
- `python3 -m pytest tests/ -q` オールグリーン
