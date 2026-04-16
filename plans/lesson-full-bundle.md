# 授業データ一括送信方式

## ステータス: Phase A・B・C 完了 / Phase D 未着手

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
- メリット: シンプル、通信1回、アトミック（全データが届くか届かないか）、部分的な不整合状態が存在しない
- リスク: 大きなJSON解析の負荷（ただしC#の`System.Text.Json`は高速で17MB程度は問題にならない）

**B) セクション分割ストリーミング** — セクションごとに `lesson_section_add` を送信し、全セクション送信後に `lesson_play`
- メリット: メッセージサイズが小さい、送信進捗を表示しやすい
- リスク: `lesson_start`→N回の`lesson_section_add`→`lesson_play`が暗黙のトランザクションになる。途中で失敗した場合のロールバック（`lesson_stop`で片付け）が必要。通信回数がN+2回に増加
- 注意: C#は`lesson_play`前に全セクションをメモリに保持するため、メモリ効率はAと同等

**推奨: A) 一括送信**

Bのメッセージサイズ削減メリットは、現状2-3MB/セクションで問題がない以上小さい。一方Aはプロトコルがシンプルで、部分送信失敗時の不整合状態が存在しないという大きな利点がある。将来データサイズが問題になった場合にBへ移行可能。

```
Python → C#: lesson_load（全セクションデータ一括送信）
Python → C#: lesson_play
C#:          全セクションを順次自律再生
C# → Python: lesson_complete（授業全体の完了通知）
```

Pythonは `lesson_play` 送信後、`lesson_complete` を待つだけ。セクション間通信は不要。

## データフォーマット

### lesson_load

全セクションのデータを一括送信する。

```json
{
  "action": "lesson_load",
  "lesson_id": 1,
  "total_sections": 7,
  "pace_scale": 1.0,
  "sections": [
    {
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
  ]
}
```

C#は`lesson_load`で受け取った`pace_scale`を全セクションの`wait_seconds`に適用する。

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
  "sections_played": 7,
  "reason": "completed"
}
```

`reason` フィールド:
- `"completed"` — 全セクション再生完了
- `"stopped"` — ユーザーによるstop
- `"error"` — 再生エラーによる中断

## C# LessonPlayer 変更

### 現在

- `LoadSection(json)` — 1セクション分のデータをロード
- `PlayAsync()` — ロードされた1セクションを再生→完了通知

### 変更後

- `LoadLesson(json)` — メタデータ + 全セクションを一括ロード
- `PlayAsync()` — 全セクションを順次再生→**授業全体の**完了通知
- 内部で `PlaySectionAsync` を for ループで呼ぶ（既存ロジック流用）

```csharp
public async Task PlayAsync()
{
    _playing = true;
    _state = "playing";
    _cts = new CancellationTokenSource();
    string reason = "completed";

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
    catch (OperationCanceledException) { reason = "stopped"; }
    catch (Exception ex) { reason = "error"; Log.Error(ex, "[Lesson] Playback error"); }
    finally
    {
        _playing = false;
        _state = "idle";
        // 授業全体の完了通知（reason で正常/停止/エラーを区別）
        await BroadcastEvent(new {
            type = "lesson_complete",
            lesson_id = _lessonId,
            sections_played = _currentSectionIndex + 1,
            reason
        });
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

    # 1. 全セクションのバンドルを事前生成（TTS生成フェーズ）
    all_bundles = []
    total_duration = 0
    for i, section in enumerate(self._sections):
        if self._state == LessonState.IDLE:
            return  # stop が呼ばれた場合は即座に中断
        self._notify_status(f"TTS生成中 {i + 1}/{len(self._sections)}")
        bundle = await self._build_section_bundle(section, i)
        all_bundles.append(bundle)
        total_duration += self._calc_section_duration(bundle)
        logger.info("[lesson] セクション %d/%d TTS生成完了", i + 1, len(self._sections))

    if self._state == LessonState.IDLE:
        return

    # 2. 一括送信
    await ws_request("lesson_load", timeout=30.0,
                     lesson_id=self._lesson_id,
                     total_sections=len(self._sections),
                     pace_scale=self._get_pace_scale(),
                     sections=all_bundles)

    # 3. 再生開始
    await ws_request("lesson_play")
    self._save_playback_state(total_duration=total_duration)

    # 4. 授業全体の完了を待つ（サーバーは関与しない）
    evt = get_lesson_complete_event()
    evt.clear()
    await self._wait_lesson_complete(evt, total_duration)
```

### TTS生成中のキャンセル

`_build_section_bundle()` は各ダイアログのTTS生成を行うため、1セクションあたり数秒〜数十秒かかる。`stop()` が呼ばれた場合は、ループの各反復で `self._state` をチェックし即座に中断する。TTS生成関数自体の中断は行わず、関数完了後に状態をチェックして次のセクションに進まないことで対応する。

### TTS生成失敗時の振る舞い

個別ダイアログのTTS生成が失敗した場合は、現行と同様にそのダイアログをスキップ（音声なし、durationのみのダイアログとして送信）。セクション内の全ダイアログが失敗した場合もセクション自体はスキップせず、テキスト表示＋wait_secondsのみで進行する。

## C# HttpServer アクション変更

| 現在 | 変更後 | 説明 |
|------|--------|------|
| `lesson_section_load` | `lesson_load` | 全セクション一括ロード |
| `lesson_section_play` | `lesson_play` | 全セクション再生開始 |
| `lesson_pause` | `lesson_pause` | 変更なし |
| `lesson_resume` | `lesson_resume` | 変更なし |
| `lesson_stop` | `lesson_stop` | 変更なし |
| `lesson_status` | `lesson_status` | 進捗情報を拡張（セクション+dialogue+remaining_duration） |
| — | — | `lesson_section_complete` **廃止** |
| — | — | `lesson_complete` 新設（Push通知、reason付き） |

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

stop の場合、C#は再生を中断し `lesson_complete` を送信（`reason: "stopped"` + `sections_played` で途中停止を示す）。

## lesson_complete イベントロスト対策

`lesson_complete` Push通知もWebSocket上で失われる可能性がある。現行の `_wait_section_complete()` と同等の2フェーズ待機を `_wait_lesson_complete()` にも実装する:

1. **Phase 1**: `asyncio.Event.wait(timeout=total_duration + 30s)` でイベント待ち
2. **Phase 2**: イベント未着の場合、5秒間隔でC#の `lesson_status` をポーリング
   - `state == "idle"` → イベントロストとみなし正常終了扱い
   - `state == "playing"` → 引き続きポーリング
   - 最大タイムアウト: `total_duration * 1.5 + 60s`

## サーバー再起動時の復旧

1. DBに `lesson.playback` として授業ID・セクション数・`total_duration` を保存
2. サーバー再起動後、C#に `lesson_status` を問い合わせ
3. C#がまだ再生中なら `lesson_complete` を待つ（データはC#が持っている）。タイムアウトはDB保存の `total_duration` から計算
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

- `LessonPlayer` に `LoadLesson`（一括ロード）/ `PlayAsync`（全セクション版）を実装
- `HttpServer` に `lesson_load` / `lesson_play` アクションを追加
- `lesson_complete` Push通知を実装（`reason` フィールド付き）
- `lesson_status` に `remaining_duration` を追加

### Phase B: Python LessonRunner 書き換え

- `_run_loop` を全セクション一括送信方式に変更
- `_prepare_and_send_section` → `_send_all_and_play` に置き換え
- `lesson_complete` イベント受信を `capture_client.py` に追加
- `_wait_lesson_complete()` にポーリングフォールバックを実装
- TTS生成中のプログレス通知（管理画面向け）
- テスト更新

### Phase C: コントロールパネル授業進捗表示

- `LessonPlayer` に `NotifyPanel` コールバック + `SendPanelUpdate()` 追加
- `MainForm` で `NotifyPanel` → `SendPanelMessage` 接続
- `control-panel.html` に Lesson タブ追加（状態・セクション進捗・ダイアログ一覧）

### Phase D: 旧コード整理

- `lesson_section_load` / `lesson_section_play` / `lesson_section_complete` を廃止
- 旧テストの削除・更新

### テスト戦略

- Phase A・Bは単体でのテストが困難なため、**統合テストはA+B完了後に実施**
- 旧エンドポイントはPhase D まで残しておき、新方式に問題があった場合のフォールバックとする

## リスク

| リスク | 影響 | 対策 |
|--------|------|------|
| TTS事前生成に時間がかかる | 中 | 管理画面にTTS生成プログレス表示（「セクション 3/7 生成中」）。キャッシュ済みの場合はほぼ即時 |
| 初回再生までの待ち時間増加 | 中 | 現行はセクション1のTTS完了で即再生開始だが、新方式は全セクション完了後。キャッシュ利用時は影響なし |
| TTS生成中のキャンセル | 低 | ループの各反復でstate確認。生成中の関数は完了まで待ち、次セクションに進まないことで対応 |
| 個別ダイアログのTTS失敗 | 低 | 音声なしダイアログとして送信（テキスト表示+duration待機のみ）。授業全体は中断しない |
| lesson_completeイベントロスト | 低 | 2フェーズ待機（イベント待ち→ポーリングフォールバック）で対策 |
| 大量メモリ使用（C#側） | 低 | 現状もセクション毎のWAVデータを保持。36 dialogue × ~350KB = ~12MB |
| WebSocket切断 | 低→なし | データ送信完了後はWebSocket不要。C#は独立動作 |
