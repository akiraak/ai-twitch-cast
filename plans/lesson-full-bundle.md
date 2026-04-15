# 授業データ一括送信方式

## ステータス: プラン作成済み

## 背景

### 現状の問題

現在の授業再生は**セクション単位の往復通信**で動作する:

```
セクションごとに:
  Python → C#: lesson_section_load（1セクション分のデータ）
  Python → C#: lesson_section_play
  Python:      lesson_section_complete 待ち…（最大71秒）
  C# → Python: lesson_section_complete
```

この方式では:
- **毎セクション往復通信が発生** — セクション数 × 3回のWebSocketメッセージ
- **完了イベントロスト** — `lesson_section_complete` が届かないと71秒タイムアウトまでフリーズ
- **サーバー依存** — Python が次セクションを送らないとC#は先に進めない
- **実際のバグ** — English 1-1 v7 で最初のセリフしか読まれず先に進まない

### ユーザーの想定

> 一番最初に授業データをすべてクライアントに渡し、サーバはその後は一切関与しない

## 設計方針

```
Python → C#: lesson_load（全セクション一括送信）
Python → C#: lesson_play
C#:          全セクションを自律的に順次再生
C# → Python: lesson_complete（授業全体の完了通知）
```

**原則: C#は授業データを受け取ったら、Pythonなしで最後まで再生できる**

## データサイズの見積もり

English 1-1 v7（7セクション、36 dialogues）の場合:

| 項目 | サイズ |
|------|--------|
| WAV合計（24kHz 16bit mono, 平均7秒/dialogue） | ~11.5 MB |
| base64エンコード後 | ~15.4 MB |
| lipsyncフレーム + メタデータ | ~2 MB |
| **JSON全体** | **~17 MB** |

### 送信方式の検討

17MBのWebSocketメッセージは大きいが、現在もセクション単位で2-3MBを送信しており、技術的には可能。ただし以下の選択肢がある:

**A) 一括送信** — 1回の `lesson_load` で全データを送信
- メリット: シンプル、通信1回
- リスク: 大きなJSON解析の負荷、メモリ使用量

**B) セクション分割ストリーミング** — セクションごとに `lesson_section_add` を送信し、全セクション送信後に `lesson_play`
- メリット: メッセージサイズが小さい、メモリ効率的
- リスク: 送信中にエラーが起きた場合の対処

**推奨: B) セクション分割ストリーミング**

```
Python → C#: lesson_start（メタデータ: lesson_id, total_sections, pace_scale）
Python → C#: lesson_section_add（セクション0のデータ）
Python → C#: lesson_section_add（セクション1のデータ）
...
Python → C#: lesson_section_add（セクション6のデータ）
Python → C#: lesson_play
C#:          全セクションを順次自律再生
C# → Python: lesson_complete（全セクション再生完了）
```

Pythonは `lesson_play` 送信後、`lesson_complete` を待つだけ。セクション間通信は不要。

## データフォーマット

### lesson_start

```json
{
  "action": "lesson_start",
  "lesson_id": 1,
  "total_sections": 7,
  "pace_scale": 1.0
}
```

### lesson_section_add

```json
{
  "action": "lesson_section_add",
  "section_index": 0,
  "section_type": "introduction",
  "display_text": "英語で自己紹介",
  "display_properties": {},
  "dialogues": [
    {
      "index": 0,
      "speaker": "teacher",
      "avatar_id": "teacher",
      "content": "みなさんこんにちは！...",
      "emotion": "excited",
      "gesture": "nod",
      "lipsync_frames": [0.1, 0.5, ...],
      "duration": 18.4,
      "wav_b64": "UklGR..."
    }
  ],
  "question": null,
  "wait_seconds": 2
}
```

### lesson_play

```json
{
  "action": "lesson_play"
}
```

### lesson_complete（C# → Python Push通知）

```json
{
  "type": "lesson_complete",
  "lesson_id": 1,
  "sections_played": 7
}
```

## C# LessonPlayer 変更

### 現在

- `LoadSection(json)` — 1セクション分のデータをロード
- `PlayAsync()` — ロードされた1セクションを再生→完了通知

### 変更後

- `StartLesson(json)` — メタデータをセット、セクションリストを初期化
- `AddSection(json)` — セクションを追加（再生前にすべて追加される）
- `PlayAsync()` — 全セクションを順次再生→**授業全体の**完了通知
- 内部で `PlaySectionAsync` を for ループで呼ぶ（既存ロジック流用）

```csharp
public async Task PlayAsync()
{
    _playing = true;
    _state = "playing";
    _cts = new CancellationTokenSource();

    try
    {
        for (int i = 0; i < _sections.Count; i++)
        {
            _cts.Token.ThrowIfCancellationRequested();
            await WaitIfPausedAsync(_cts.Token);
            _currentSectionIndex = i;
            await PlaySectionAsync(_sections[i], _cts.Token);
        }
    }
    catch (OperationCanceledException) { }
    catch (Exception ex) { Log.Error(ex, "[Lesson] Playback error"); }
    finally
    {
        _playing = false;
        _state = "idle";
        // 授業全体の完了通知
        await BroadcastEvent(new { type = "lesson_complete", lesson_id = _lessonId });
    }
}
```

## Python LessonRunner 変更

### _prepare_and_send_section → _send_all_and_play

```python
async def _run_loop(self):
    try:
        await self._send_all_and_play()
        # 全セクション完了
        ...
    except ...

async def _send_all_and_play(self):
    from scripts.services.capture_client import get_lesson_complete_event, ws_request

    # 1. 授業開始通知
    await ws_request("lesson_start", lesson_id=self._lesson_id,
                     total_sections=len(self._sections),
                     pace_scale=self._get_pace_scale())

    # 2. 全セクションのバンドルを生成して送信
    for i, section in enumerate(self._sections):
        if self._state == LessonState.IDLE:
            break
        await self._pause_event.wait()

        bundle = await self._build_section_bundle(section, i)
        await ws_request("lesson_section_add", timeout=30.0, **bundle)
        logger.info("[lesson] セクション %d/%d 送信完了", i + 1, len(self._sections))

    # 3. 再生開始
    await ws_request("lesson_play")
    self._save_playback_state()

    # 4. 授業全体の完了を待つ（サーバーは関与しない）
    total_duration = ...  # 全セクションの合計時間
    evt = get_lesson_complete_event()
    evt.clear()
    await self._wait_lesson_complete(evt, total_duration)
```

## C# HttpServer アクション変更

| 現在 | 変更後 | 説明 |
|------|--------|------|
| `lesson_section_load` | `lesson_start` | メタデータのみ |
| — | `lesson_section_add` | セクション追加（複数回） |
| `lesson_section_play` | `lesson_play` | 全セクション再生開始 |
| `lesson_pause` | `lesson_pause` | 変更なし |
| `lesson_resume` | `lesson_resume` | 変更なし |
| `lesson_stop` | `lesson_stop` | 変更なし |
| `lesson_status` | `lesson_status` | 進捗情報を拡張（セクション+dialogue） |
| — | — | `lesson_section_complete` **廃止** |
| — | — | `lesson_complete` 新設（Push通知） |

## 進捗通知（オプション）

C#が再生中に進捗をPush通知することで、管理画面で状況を表示可能:

```json
{
  "type": "lesson_progress",
  "section_index": 2,
  "dialogue_index": 3,
  "total_sections": 7
}
```

これはオプション。最低限 `lesson_complete` だけあれば動作する。

## pause / resume / stop

現行と同様にPythonからC#に転送。C#が内部で一時停止/再開/停止する。

stop の場合、C#は再生を中断し `lesson_complete` を送信（`sections_played` で途中停止を示す）。

## サーバー再起動時の復旧

1. DBに `lesson.playback` として授業IDとセクション数を保存（現行と同じ）
2. サーバー再起動後、C#に `lesson_status` を問い合わせ
3. C#がまだ再生中なら `lesson_complete` を待つだけ（データはC#が持っている）
4. C#も再起動していたら、全セクションを再生成→再送信

## コントロールパネル授業進捗表示

C#アプリ右側のコントロールパネル（control-panel.html）に「Lesson」タブを追加し、授業データと再生進捗をリアルタイム表示する。

### 表示内容

- **状態バッジ**: idle / loaded / playing / paused をカラーバッジで表示
- **セクション進捗バー**: 全セクションの完了/現在/未再生を横バーで可視化
- **教材テキスト**: 現在のセクションの `display_text` を表示
- **現在の発話**: 再生中のダイアログの speaker + content をハイライト表示
- **ダイアログ一覧**: セクション内の全ダイアログをリスト表示（再生済み=薄く、現在=ハイライト、未再生=通常）

### 実装方針

#### LessonPlayer.cs

- `NotifyPanel` コールバック（`Action<object>?`）を追加
- `SendPanelUpdate()` ヘルパーメソッドで以下のタイミングに発火:
  - `LoadSection` 完了時
  - `PlayDialoguesAsync` 各ダイアログ開始時（speaker, content を含む）
  - `Pause` / `Resume` / `Stop` 時
  - `PlaySectionAsync` finally（セクション完了時）

パネルメッセージ形式:

```json
{
  "type": "lesson",
  "state": "playing",
  "lesson_id": 1,
  "section_index": 2,
  "total_sections": 7,
  "section_type": "dialogue",
  "display_text": "英語で自己紹介",
  "dialogue_index": 3,
  "total_dialogues": 5,
  "dialogues": [
    { "index": 0, "speaker": "teacher", "content": "みなさんこんにちは！…（80文字で切り詰め）" }
  ],
  "current_content": "再生中の発話全文",
  "current_speaker": "teacher"
}
```

#### MainForm.cs

- LessonPlayer 初期化時に `NotifyPanel` を `SendPanelMessage` に接続:
  ```csharp
  _lessonPlayer.NotifyPanel = (data) => BeginInvoke(() => SendPanelMessage(data));
  ```

#### control-panel.html

- タブバーに「Lesson」タブボタン追加（Chat と Design の間）
- `tab-lesson` コンテンツ: 状態バッジ、セクションバー、教材テキスト、発話表示、ダイアログ一覧
- `wv.addEventListener('message')` に `case 'lesson': updateLesson(m)` 追加
- `updateLesson(m)` 関数: バッジ更新、セクションバー描画、ダイアログ一覧のDOM生成+スクロール追従

### 注意点

- ダイアログ一覧には音声データ（`wav_b64`）を含めない（パネルに送るのはテキストのみ）
- ダイアログの `content` は80文字で切り詰め（一覧表示用）
- `current_content` は切り詰めず全文送信（現在の発話表示用）

## 実装フェーズ

### Phase A: C# LessonPlayer 全セクション対応

- `LessonPlayer` に `StartLesson` / `AddSection` / `PlayAsync`（全セクション版）を実装
- `HttpServer` に `lesson_start` / `lesson_section_add` / `lesson_play` アクションを追加
- `lesson_complete` Push通知を実装

### Phase B: Python LessonRunner 書き換え

- `_run_loop` を全セクション一括送信方式に変更
- `_prepare_and_send_section` → `_send_all_and_play` に置き換え
- `lesson_complete` イベント受信を `capture_client.py` に追加
- テスト更新

### Phase C: コントロールパネル授業進捗表示

- `LessonPlayer` に `NotifyPanel` コールバック + `SendPanelUpdate()` 追加
- `MainForm` で `NotifyPanel` → `SendPanelMessage` 接続
- `control-panel.html` に Lesson タブ追加（状態・セクション進捗・ダイアログ一覧）

### Phase D: 旧コード整理

- `lesson_section_load` / `lesson_section_play` / `lesson_section_complete` を廃止
- 旧テストの削除・更新

## リスク

| リスク | 影響 | 対策 |
|--------|------|------|
| TTS事前生成に時間がかかる | 中 | 送信開始前に全セクション生成。UIにプログレス表示 |
| セクション追加中の送信失敗 | 低 | lesson_start後にエラーならlesson_stopで片付け |
| 大量メモリ使用（C#側） | 低 | 現状もセクション毎のWAVデータを保持。36 dialogue × ~350KB = ~12MB |
| WebSocket切断 | 低→なし | データ送信完了後はWebSocket不要。C#は独立動作 |
