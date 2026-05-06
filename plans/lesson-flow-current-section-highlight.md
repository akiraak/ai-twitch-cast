# 授業の流れパネル: 現在セクションのハイライト修復

## 背景

配信画面の「授業の流れ」パネル（`#lesson-progress-panel`）は、授業再生中に現在進行中のセクションを `.current` クラスでハイライトする仕様。初期描画（パネル全体の表示と先頭セクションのハイライト）は動作しているが、再生が次のセクションに進んでもハイライトが先頭から動かない。

- 仕様: `static/js/broadcast/panels.js:308-342`（`showLessonProgress` / `updateLessonProgress`）
- CSS: `static/css/broadcast.css:622-627`（`.lesson-progress-item.current`）
- WSハンドラ: `static/js/broadcast/websocket.js:181-195`（`lesson_status` 受信時に `data.sections` がなければ `updateLessonProgress(data.current_index)` のみ呼ぶ）

クライアントの受信ロジックと CSS は揃っており、データ契約（`current_index` = 0始まりインデックス）も合致している。問題は **再生中に `current_index` 更新の `lesson_status` イベントが broadcast.html まで届いていない** こと。

## 原因（チェーンが切れている箇所）

### イベント経路の整理

broadcast.html は **Python サーバー** の `/ws/broadcast`（`scripts/routes/overlay.py:64`）に接続している。このソケットへ書き込めるのは Python 側 `state.broadcast_clients` に対する `state._broadcast(...)` 系のみ。

C# 側 `HttpServer.BroadcastWsEvent`（`win-native-app/.../Server/HttpServer.cs:929`）は `_controlClients` にしか送らない。`_controlClients` は `/ws/control`（`HttpServer.cs:457` で path 限定）に接続したクライアントの集合で、つまり Python サーバーが `scripts/services/capture_client.py` から張る制御チャンネル専用。**broadcast.html は `/ws/control` には接続しないので、C# が `BroadcastWsEvent` を呼んでも broadcast.html に直接は届かない。**

既存の `lesson_complete`（`LessonPlayer.cs:227-236`）も同じく `_controlClients` 向けで、`capture_client.py:248-251` が受けて `_lesson_complete_event.set()` を発火する Python 内部用イベントになっている（`lesson_runner.py:587, 641` がこれを await）。broadcast.html へ届く流路ではない。

### 1. Python `src/lesson_runner.py`
- `_notify_status()`（989-1009行）は `current_index` 付き `lesson_status` を `_on_overlay`（→ `state.broadcast_clients`）に送る。これは broadcast.html まで届く。
- ただし呼ばれるのは状態遷移時のみ（resume復旧 433 / start 481 / pause 498 / resume 513 / stop 555 / complete 567 / error 582）。
- 実再生は C# 側が担当するため、Python は再生中の `current_index` を知らず、進行イベントを発火できない。
- 結果: start 直後に `current_index=0` で 1 回だけ送られ、以降沈黙。

### 2. C# `win-native-app/.../LessonPlayer.cs`
- `PlayAsync` のセクション進行ループ（195-207行）で `_currentSectionIndex = i;`（199行）を更新し `SendPanelUpdate()`（205行）を呼ぶが、これは制御パネル（管理画面）向け（`NotifyPanel`）。
- `BroadcastEvent` 経由で送る `lesson_complete`（227-236行）も上述のとおり `/ws/control` 止まりで broadcast.html には届かない。
- セクション切替を C# は知っているが、broadcast.html まで伝わらない。

## 方針

**C# を進行の権威ソースとし、PlayAsync で `lesson_status` を `BroadcastEvent` に流す。Python `capture_client.py` の `/ws/control` 受信ループでそれを拾い、`state.broadcast_overlay()` で broadcast.html にリレーする。** 既存の `lesson_complete` と同じ流路パターンを踏襲する。

選定理由:
- C# が実再生位置を最も正確に知っている（音声再生の wall-clock に同期）。
- Python ポーリング案（既存の 5秒間隔 `_wait_lesson_complete` を流用）だと最大 5 秒のハイライト遅延が出る。
- 既存クライアントハンドラ（`websocket.js:181`）はインクリメンタル更新（`data.sections` なし、`current_index` のみ）に対応済みで、追加の JS 改修は不要。
- リレー処理は `lesson_complete` と同じく `_read_capture_ws` への分岐追加のみで、既存パターンに沿う。

データ契約（クライアントが期待する形）:
```json
{ "type": "lesson_status", "state": "running" | "paused", "current_index": <int> }
```
- `state` は `running` / `paused`（Python `LessonState.value` 準拠）。C# 内部状態は `"playing"` / `"paused"` だが、broadcast 向けには `"playing"` → `"running"` にマッピングして送る（既存 Python 契約と揃える）。
- `sections` は省略 → クライアントは `updateLessonProgress(current_index)` のみ呼ぶ（軽量）。
- `lesson_id` / `total_sections` も Python の既存 `_notify_status` と揃えて含めると、リレー側で型分岐しやすく将来拡張も楽。

## 実装ステップ

### 1. C# 側: `LessonPlayer.cs` でセクション進行イベントを送出
`PlayAsync`（195-207行）の `for` ループ内、`_currentSectionIndex = i;`（199行）の直後（`SendPanelUpdate()` と並べる）で:
```csharp
if (BroadcastEvent != null)
{
    _ = BroadcastEvent(new {
        type = "lesson_status",
        state = "running",
        lesson_id = _lessonId,
        current_index = i,
        total_sections = _sections.Count,
    });
}
```
fire-and-forget（`_ =`）で再生ループをブロックしない。

### 2. C# 側: `Pause()` / `Resume()` で state 変化を送出
`Pause()`（255-265行）と `Resume()`（268-278行）の末尾で同形イベントを送る。`state` をそれぞれ `"paused"` / `"running"`、`current_index = _currentSectionIndex`、`total_sections = _sections.Count`。

### 3. Python 側: `capture_client.py` でリレー分岐を追加
`_read_capture_ws()`（`scripts/services/capture_client.py:238-275`）の Push 通知分岐に `lesson_status` ケースを追加:
```python
if data.get("type") == "lesson_status":
    # broadcast.html へリレー（C# が権威ソースの再生進行を反映）
    from scripts import state
    asyncio.create_task(state.broadcast_overlay(data))
    continue
```
- 関数内 import で `state` 循環参照を避ける（`state.py` 側も `capture_client` を関数内 import している既存パターンに合わせる）。
- `asyncio.create_task` で投げて受信ループを止めない。

### 4. テスト
- `tests/test_native_app_patterns.py` に「`PlayAsync` ループ内で `BroadcastEvent` が `lesson_status` 型を送出している」「`Pause` / `Resume` も `lesson_status` を送出している」ことを文字列マッチで検証するパターンを追加（再発防止ガード）。
- `tests/test_capture_client.py` に「`lesson_status` Push 通知を受けたら `state.broadcast_overlay` が呼ばれる」テストを追加（`state.broadcast_overlay` をモックして `_read_capture_ws` の分岐を駆動）。

### 5. 動作確認
- WSL2 で `./server.sh` 起動 → Windows で `stream.sh` 起動。
- 既存の授業（例: lesson_id=100）をロード → 再生開始。
- broadcast.html を別ブラウザで開いて DevTools の Network → WS タブで `/ws/broadcast` を監視し、セクション切替ごとに `lesson_status` フレーム（`current_index` 増加）が流れることを確認。
- 配信画面で `.lesson-progress-item.current` の紫ハイライトがセクション進行に追従することを目視確認。
- Pause / Resume でハイライト位置が保持されること、state が `paused` ↔ `running` で切り替わることを確認。

## リスク・トレードオフ

- **重複イベント**: 起動直後は Python の `_notify_status`（start 481行）と C# の section 0 開始イベントが両方届く可能性がある。クライアントは冪等に `.current` クラスを更新するだけなので無害。
- **fire-and-forget の例外**: `_ = BroadcastEvent(...)` だと内部例外が握り潰される。`HttpServer.BroadcastWsEvent`（929-955行）は各 `Send` を `try/catch {}` で包んでおり、致命例外は表に出にくい。送信先 0 件は早期 return するため例外要因は薄い。問題が出たら `try/catch` でラップする。
- **state 文字列の不整合**: C# 内部状態は `"playing"` だが broadcast 向けに `"running"` に変換する。今後 C# 側で別の broadcast イベントを追加するときも同じマッピングが必要 → 将来的に定数化を検討（今回は最小修正で見送り）。
- **Python 側 `_current_index` との乖離**: C# 経由のイベントだけで進めると Python の `self._current_index` は古いまま。これは現時点でも DB 永続化（`_save_playback_state` = pause/stop ハンドラ起点）にしか使われておらず、その時点では Python の状態遷移ハンドラが走るので実害は少ない。再生中に Python が読み取る箇所が増えたら別途同期処理を検討する。
- **lesson_status の他フィールド**: Python の既存 `_notify_status` は `lesson_name` や `phase`（`_notify_tts_progress` 経由）も送る。C# 経由のイベントにはそれらがないが、クライアント側 `websocket.js:181-195` は欠落に耐性あり（`data.lesson_name` は条件付きで読む）。
- **`lesson_complete` 後のパネル後始末**: 現状 `static/js/broadcast/websocket.js` には `lesson_complete` ケースがなく、Python の `_notify_status()`（`_run_loop` 完了後の 567行、state=IDLE）でクライアントが `setLessonMode(false)` でパネルを閉じる挙動に依存している。本修正の範囲外。

## ステータス

完了

- C#: `LessonPlayer.PlayAsync` のセクション進行ループ内＋ `Pause()` / `Resume()` で `BroadcastEvent` に `lesson_status` を送出（`Streaming/LessonPlayer.cs`）
- Python: `capture_client._read_capture_ws()` に `lesson_status` リレー分岐を追加し `state.broadcast_overlay()` で broadcast.html へ流す
- テスト: `tests/test_native_app_patterns.py`（PlayAsync / Pause / Resume の送出パターン）と `tests/test_capture_client.py`（リレーと受信ループ非ブロック）を追加。`pytest -q -m "not slow"` 1282 passed
- 実機動作確認は Windows 側で `stream.sh` 経由で実施予定
