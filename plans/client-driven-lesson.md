# クライアント主導型授業再生システム

## ステータス: 設計中

## 背景と動機

### 現状の問題

現在の授業再生はPython（LessonRunner）が全てをインメモリで制御する:

```
Python: TTS生成 → C#に音声送信 → sleep(duration) → ポーリング → 次のdialogue
```

この設計には**2つの根本的な問題**がある:

1. **タイミングの乖離**: Pythonが推定時間で待つため、C#側の実再生と最大10秒ズレる
2. **サーバーが単一障害点**: LessonRunnerの状態が全てインメモリ。サーバー再起動で授業が即死する

#### (1) はPush通知で改善可能（tts-wait-excess-delay.md）。(2) はアーキテクチャを変えない限り解決できない。

### 開発中の実害

- `server.sh` はコミットごとにサーバーをkill→再起動する（post-commit hook）
- Claude Codeが開発中にコミットすると、**配信中の授業が途切れる**
- LessonRunnerの `_task: asyncio.Task` はサーバープロセスと運命共同体
- `.server_state` による自動復旧は授業再生に対応していない

### 現状のフロー

```
Python (LessonRunner)              C# (NAudio/FFmpeg)           broadcast.html
  for each section:
    for each dialogue:
      TTS生成（キャッシュ対応）
      リップシンク解析
      WAV base64 → ws_request ────→ PlayTtsLocally + FFmpeg
      subtitle/lipsync ──────────────────────────────────→ 表示
      asyncio.sleep(duration)
      _wait_tts_complete(polling) ←→ tts_status
      lipsync_stop ──────────────────────────────────────→ 停止
      speaking_end ──────────────────────────────────────→ フェード
```

**問題**: Pythonが死ぬと全フローが止まる。C#とbroadcast.htmlはデータを持っていないので続行不能。

## 設計方針

| 役割 | 担当 | 原則 |
|------|------|------|
| 何を再生するか（コンテンツ生成） | Python | TTS生成・リップシンク解析・データパッケージング |
| どう再生するか（タイミング制御） | C# | 音声再生の主体として自然。PlaybackStopped で正確な完了検知 |
| どう表示するか（字幕・アバター） | broadcast.html | C#からWebView2 JS interopで指示を受ける |
| 進捗管理 | Python + DB永続化 | サーバー再起動後に復旧可能 |

## アーキテクチャ概要

```
Python (WSL2)                       C# (Windows)                  broadcast.html (WebView2)
                                                                  
[コンテンツ生成]                    [LessonPlayer 再生エンジン]    [表示エンジン]
                                                                  
  全dialogue TTS事前生成                                          
  リップシンク解析                                                
  セクションデータ送信                                            
                                                                  
  ── lesson_section_load ──→       データ保持                     
  ── lesson_section_play ──→       dialogue[0] 音声再生           
                                    ── ExecuteScriptAsync ────→   字幕+口パク+感情
                                   PlaybackStopped               
                                    ── ExecuteScriptAsync ────→   フェード+口パク停止
                                   0.3秒待ち                     
                                   dialogue[1] 音声再生           
                                    ── ExecuteScriptAsync ────→   字幕+口パク+感情
                                   ...                           
  ←─ lesson_section_complete ──    全dialogue完了                 
  進捗DB記録                                                      
  次セクション生成→送信                                           
```

**サーバー再起動時**: C#が再生中のセクションを最後まで再生→完了通知→Python復帰後に次セクション送信。

## データフォーマット

### セクションバンドル（Python → C#）

```jsonc
// ws_request("lesson_section_load", ...)
{
  "lesson_id": 123,
  "section_index": 2,
  "total_sections": 8,
  "section_type": "dialogue",
  // 教材表示
  "display_text": "Today's Topic: Greetings",
  "display_properties": { "type": "image", "url": "/resources/images/..." },
  // 対話データ（音声・表示・リップシンク全部入り）
  "dialogues": [
    {
      "index": 0,
      "speaker": "teacher",
      "avatar_id": "teacher",
      "content": "こんにちは！今日は挨拶を学びましょう。",
      "emotion": "joy",
      "gesture": "nod",
      "lipsync_frames": [0.1, 0.5, 0.8, 0.3, ...],
      "duration": 4.2,
      "wav_b64": "UklGR..."
    },
    {
      "index": 1,
      "speaker": "student",
      "avatar_id": "student",
      "content": "はい、お願いします！",
      "emotion": "excited",
      "gesture": null,
      "lipsync_frames": [0.2, 0.6, ...],
      "duration": 2.1,
      "wav_b64": "UklGR..."
    }
  ],
  // questionセクション用（通常はnull）
  "question": {
    "wait_seconds": 8,
    "answer_dialogues": [
      { "index": 0, "speaker": "teacher", "content": "答えは…", ... }
    ]
  },
  // セクション間の間（C#が待つ）
  "wait_seconds": 2,
  "pace_scale": 1.0
}
```

### 単話者モードの統一

現在の `_play_single_speaker` は `split_sentences()` で文分割して再生する。新方式では分割結果を `dialogues` 配列に統一:

```python
# Python側で統一フォーマットに変換
# 従来: content="長い文章。次の文。最後。" → split → 3回 speak()
# 新方式: dialogues配列として送信
dialogues = [
    {"index": 0, "speaker": "teacher", "content": "長い文章。", "wav_b64": "...", ...},
    {"index": 1, "speaker": "teacher", "content": "次の文。", "wav_b64": "...", ...},
    {"index": 2, "speaker": "teacher", "content": "最後。", "wav_b64": "...", ...},
]
```

C#側は単話者/対話を区別せず、同じ再生ロジックで処理できる。

## 詳細フロー

### Phase 1: セクションデータ生成・配信（Python）

```python
# lesson_runner.py（概念）
async def _prepare_and_send_section(self, section):
    dialogues = self._parse_dialogues(section)  # 対話 or 文分割
    bundle = []
    
    for i, dlg in enumerate(dialogues):
        # TTS生成（キャッシュ対応 — 既存ロジック流用）
        wav_path = await self._generate_dlg_tts(dlg, i, order_index)
        if not wav_path or not wav_path.exists():
            continue
        
        # リップシンク解析
        lipsync_frames = await asyncio.to_thread(analyze_amplitude, wav_path)
        
        # WAV読み込み
        with wave.open(str(wav_path), "rb") as wf:
            duration = wf.getnframes() / wf.getframerate()
        wav_b64 = base64.b64encode(wav_path.read_bytes()).decode()
        
        bundle.append({
            "index": i,
            "speaker": dlg.get("speaker", "teacher"),
            "avatar_id": dlg.get("speaker", "teacher"),
            "content": dlg.get("content", ""),
            "emotion": dlg.get("emotion", "neutral"),
            "gesture": EMOTION_GESTURES.get(dlg.get("emotion", "neutral")),
            "lipsync_frames": lipsync_frames,
            "duration": duration,
            "wav_b64": wav_b64,
        })
    
    # C#に送信
    await ws_request("lesson_section_load", section_data={
        "lesson_id": self._lesson_id,
        "section_index": self._current_index,
        "total_sections": len(self._sections),
        "display_text": section.get("display_text", ""),
        "display_properties": section.get("display_properties", {}),
        "dialogues": bundle,
        "wait_seconds": section.get("wait_seconds", 2),
        "pace_scale": self._get_pace_scale(),
    })
    
    # 再生開始指示
    await ws_request("lesson_section_play")
    
    # 進捗をDBに永続化
    db.set_setting("lesson.playback", json.dumps({
        "lesson_id": self._lesson_id,
        "section_index": self._current_index,
        "state": "playing",
        "lang": self._lang,
        "generator": self._generator,
        "version_number": self._version_number,
    }))
    
    # C#からのセクション完了通知を待つ
    evt = get_lesson_section_complete_event()
    evt.clear()
    try:
        timeout = sum(d["duration"] for d in bundle) + 30  # 余裕を持つ
        await asyncio.wait_for(evt.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning("[lesson] セクション完了タイムアウト")
```

### Phase 2: 再生（C#、Pythonなしで動作）

```csharp
// LessonPlayer.cs（概念）
class LessonPlayer
{
    private List<DialogueData> _dialogues;
    private int _currentIndex;
    private bool _playing;
    private bool _paused;
    
    public async Task PlaySection()
    {
        _playing = true;
        
        // 教材テキスト表示
        if (!string.IsNullOrEmpty(_sectionData.DisplayText))
            InjectJs($"window.lesson.showText({JsonSerialize(...)})");
        
        // dialogue順次再生
        for (_currentIndex = 0; _currentIndex < _dialogues.Count; _currentIndex++)
        {
            if (!_playing) break;
            while (_paused) await Task.Delay(100);  // pause対応
            
            var dlg = _dialogues[_currentIndex];
            
            // 音声再生（既存 PlayTtsLocally + FFmpeg WriteTtsData を流用）
            var volume = CalcTtsVolume();
            PlayTtsLocally(dlg.WavData, volume);
            if (_ffmpeg is { IsRunning: true })
                _ffmpeg.WriteTtsData(TtsDecoder.DecodeWav(dlg.WavData, 1.0f));
            
            // broadcast.htmlに表示指示（WebView2 JS interop）
            InjectJs($"window.lesson.startDialogue({JsonSerialize(new {
                content = dlg.Content,
                speaker = dlg.Speaker,
                avatarId = dlg.AvatarId,
                emotion = dlg.Emotion,
                gesture = dlg.Gesture,
                lipsyncFrames = dlg.LipsyncFrames,
                duration = dlg.Duration,
            })})");
            
            // PlaybackStopped を待つ（実際の再生完了）
            await WaitForPlaybackComplete();
            
            // 表示終了
            InjectJs("window.lesson.endDialogue()");
            
            // 発話間の間
            if (_currentIndex < _dialogues.Count - 1)
                await Task.Delay(300);
        }
        
        // 教材テキスト非表示
        InjectJs("window.lesson.hideText()");
        
        // wait_seconds（セクション間の間）
        await Task.Delay((int)(_waitSeconds * _paceScale * 1000));
        
        // Python に完了通知（Push）
        await _httpServer.BroadcastWsEvent(new { type = "lesson_section_complete" });
        
        _playing = false;
    }
}
```

### Phase 3: broadcast.html 表示ハンドラ

```javascript
// static/js/broadcast/lesson.js（概念）
window.lesson = {
    showText(text, displayProperties) {
        // 既存の lesson_text_show ロジックを流用
    },
    
    hideText() {
        // 既存の lesson_text_hide ロジックを流用
    },
    
    startDialogue(data) {
        // 1. 感情 BlendShape 適用
        if (data.emotion && window.avatarManager) {
            window.avatarManager.applyEmotion(data.avatarId, data.emotion, data.gesture);
        }
        
        // 2. 字幕表示（既存 showSubtitle 流用）
        showSubtitle({
            author: data.speaker === 'teacher' ? teacherName : studentName,
            speech: data.content,
            emotion: data.emotion,
            duration: data.duration,
        });
        
        // 3. リップシンク開始
        if (data.lipsyncFrames && window.avatarManager) {
            window.avatarManager.startLipsync(data.avatarId, data.lipsyncFrames);
        }
    },
    
    endDialogue() {
        fadeSubtitle();
        if (window.avatarManager) {
            window.avatarManager.stopLipsync();
            window.avatarManager.resetEmotion();
        }
    },
};
```

## サーバー再起動時の復旧

```
1. Python再起動
2. DBから lesson.playback を読み取り
   → { lesson_id: 123, section_index: 2, state: "playing", ... }
3. C#に lesson_status を問い合わせ（ws_request）
   → 応答パターン:

   A) C#: "idle"（セクション再生完了、次を待っている）
      → section_index + 1 から再開。次セクション生成→送信

   B) C#: "playing section 2, dialogue 5/8"（再生中）
      → lesson_section_complete イベント受信を待つ
      → 完了後に次セクション生成→送信

   C) C#: "no lesson"（C#も再起動した場合）
      → DBの section_index から授業を再開
      → 全セクション再ロード → 該当セクションから再生

   D) C#未接続
      → 接続確立を待ち、接続後にCのフローへ
```

### 永続化するデータ（DB `settings` テーブル）

```json
// key: "lesson.playback"
{
  "lesson_id": 123,
  "section_index": 2,
  "state": "playing",
  "lang": "ja",
  "generator": "gemini",
  "version_number": 1,
  "episode_id": 456
}
```

セクション完了時に `section_index` をインクリメント。授業完了時にキーを削除。

## 一時停止・再開

```
ユーザー操作（管理画面）
  → Python API: POST /api/teacher/lessons/{id}/pause
  → Python → C#: ws_request("lesson_pause")
  → C#: 音声一時停止 + broadcast.html通知
    → InjectJs("window.lesson.pause()")

再開:
  → Python → C#: ws_request("lesson_resume")
  → C#: 音声再開 + InjectJs("window.lesson.resume()")

停止:
  → Python → C#: ws_request("lesson_stop")
  → C#: 再生中断 + クリーンアップ
  → DB lesson.playback 削除
```

一時停止中にサーバーが再起動しても、C#がpause状態を保持。Python復帰後に `lesson_status` で状態同期。

## questionセクションの扱い

questionセクションは以下のデータ構造で送信:

```json
{
  "section_type": "question",
  "dialogues": [
    { "content": "What is 'hello' in Japanese?", "speaker": "teacher", ... }
  ],
  "question": {
    "wait_seconds": 8,
    "answer_dialogues": [
      { "content": "答えは「こんにちは」です！", "speaker": "teacher", ... }
    ]
  }
}
```

C#側の再生フロー:
1. `dialogues`（質問部分）を再生
2. `question.wait_seconds × pace_scale` 秒待つ
3. `question.answer_dialogues`（回答部分）を再生
4. `lesson_section_complete` 送信

## 実装フェーズ

各フェーズは独立してマージ・動作確認可能。前フェーズが完了するまで次に進まない。

### Phase 1: C# 再生エンジン + WebSocket API

**ゴール**: C#にLessonPlayerを作り、WebSocket経由でセクションデータを受信→dialogue順次再生できる状態にする。

**変更ファイル**:
| ファイル | 変更 |
|---------|------|
| `Streaming/LessonPlayer.cs` (新規) | dialogue順次再生、PlaybackStopped完了検知、pause/resume/stop、完了Push通知 |
| `Server/HttpServer.cs` | `lesson_section_load` / `lesson_section_play` / `lesson_pause` / `lesson_resume` / `lesson_stop` / `lesson_status` アクション追加 |
| `MainForm.cs` | LessonPlayer初期化、コールバック設定（PlayTtsLocally・FFmpeg・WebView2参照） |

**確認方法**: WebSocketクライアントから手動でセクションデータを送信し、C#が音声を順次再生することを確認。

### Phase 2: broadcast.html 授業表示ハンドラ

**ゴール**: C#からWebView2 JS interop経由で字幕・リップシンク・感情を表示できるようにする。

**変更ファイル**:
| ファイル | 変更 |
|---------|------|
| `static/js/broadcast/lesson.js` (新規) | `window.lesson.startDialogue()` / `endDialogue()` / `showText()` / `hideText()` / `pause()` / `resume()` |
| `static/broadcast.html` | lesson.js のscript読み込み追加 |

**確認方法**: Phase 1と合わせて、C#がdialogue再生時にbroadcast.htmlに字幕・口パク・感情が表示されることを確認。

### Phase 3: Python LessonRunner 書き換え

**ゴール**: Pythonからセクションデータを送信し、C#が再生→完了通知で次セクションに進む方式に切り替える。旧フロー（speak+sleep+polling）を置換。

**変更ファイル**:
| ファイル | 変更 |
|---------|------|
| `src/lesson_runner.py` | `_play_section`→`_prepare_and_send_section`（バンドル生成・送信・完了イベント待ち）、単話者/対話モード統一、旧speak()呼び出し削除 |
| `scripts/services/capture_client.py` | `lesson_section_complete` Push通知受信・イベント発火 |
| `tests/test_lesson_runner.py` | バンドル組み立て、完了イベント待ち・タイムアウト、単話者/対話統一のテスト |

**確認方法**: 管理画面から授業を開始し、セクションが正常に順次再生されることを確認。

### Phase 4: DB永続化・サーバー再起動復旧

**ゴール**: サーバーが再起動しても授業が途切れない。本プランの核心的価値。

**変更ファイル**:
| ファイル | 変更 |
|---------|------|
| `src/lesson_runner.py` | 進捗のDB永続化（`lesson.playback` settingsキー）、起動時復旧ロジック（`lesson_status`問い合わせ→続行） |
| `scripts/web.py` (startup) | 授業復旧をstartup自動復旧フローに統合 |
| `tests/test_lesson_runner.py` | DB永続化・復旧ロジックのテスト |

**確認方法**: 授業再生中にサーバーを再起動し、再起動後に続きのセクションから授業が再開されることを確認。

### Phase 5: 旧コード整理

**ゴール**: 不要になった旧フローのコードを削除。

- LessonRunnerから `_play_single_speaker` / `_play_dialogues` / 旧 `_play_section` を削除
- `speech_pipeline.py` の `speak()` はコメント応答用にそのまま残す
- `tts_status` アクション削除を検討（コメント応答が使わなくなった場合）
- ドキュメント更新（`docs/speech-generation-flow.md` 等）

## 変更ファイル一覧

| 領域 | ファイル | 変更 |
|------|---------|------|
| C# 新規 | `Streaming/LessonPlayer.cs` | 再生エンジン |
| C# | `Server/HttpServer.cs` | lesson_* アクション追加 |
| C# | `MainForm.cs` | LessonPlayer初期化・コールバック |
| JS 新規 | `static/js/broadcast/lesson.js` | 授業表示ハンドラ |
| JS | `static/broadcast.html` | lesson.js の読み込み追加 |
| Python | `src/lesson_runner.py` | セクション生成・送信・イベント待ち・DB永続化・復旧 |
| Python | `scripts/services/capture_client.py` | `lesson_section_complete` Push通知受信 |
| Python | `tests/test_lesson_runner.py` | 新フローのテスト |

## tts-wait-excess-delay.md との関係

| プラン | 対象 | 関係 |
|--------|------|------|
| tts-wait-excess-delay.md | `speak()` のPush通知改善 | **コメント応答に引き続き有効** |
| 本プラン | 授業再生のクライアント主導化 | **授業再生では `speak()` を使わなくなる** |

両プランは独立して実装可能。授業再生では本プランが `speak()` のタイミング問題を根本的に解消するため、授業に限れば tts-wait-excess-delay は不要。

## データ転送サイズの見積もり

| 項目 | サイズ |
|------|--------|
| 1 dialogue WAV（10秒, 24kHz 16bit mono） | ~480 KB |
| base64エンコード後 | ~640 KB |
| lipsync_frames（10秒, 30fps） | ~1.2 KB |
| メタデータ（字幕・感情等） | ~0.5 KB |
| **1 dialogue 合計** | **~642 KB** |
| **10 dialogue セクション** | **~6.4 MB** |

現在も1 dialogueずつWebSocket送信しているため、まとめて送っても問題ない。大きなセクションでは dialogue を順次送信することも可能（`lesson_section_load` を複数回 + `lesson_section_ready` で開始）。

## リスク

| リスク | 影響 | 対策 |
|--------|------|------|
| C# LessonPlayer 新設の工数 | 中 | 既存の PlayTtsLocally + ExecuteScriptAsync パターンを流用 |
| WebSocket メッセージサイズ | 低 | 10 dialogue ~6.4MB。現状と同等。必要なら分割送信 |
| C# 未接続時 | 低 | 従来通りC#なしでは授業再生不可（変わらない） |
| WebView2 JS interop レイテンシ | 低 | 既存の音量制御・キャプチャで実績あり（< 5ms） |
| pause 中のサーバー再起動 | 低 | C# が pause 状態保持。Python 復帰後に状態同期 |
| TTS事前生成の待ち時間 | 中 | 現在もセクション単位で事前生成済み。変化なし |
