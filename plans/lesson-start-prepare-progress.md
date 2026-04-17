# 授業開始ボタン: TTS生成中の進捗表示

## ステータス: 未着手

## 背景

授業再生のクライアント主導型移行（[client-driven-lesson.md](client-driven-lesson.md)）後、次の UX 問題が残っている。

### 現象（2026-04-16 検証）

18:50:44 に「授業開始」ボタンを押下 → 18:51:54 にユーザーが「始まらない」と判断して停止。この 70 秒間、C# 側には `lesson_load` が一度も届いていなかった。

原因は Python 側の `lesson_runner._send_all_and_play()`（`src/lesson_runner.py:584-638`）が、セクション毎にインライン TTS 生成を行う設計になっており、キャッシュミスがあると `lesson_load` 送信前に数分間ブロックするため。その間、管理画面には何も表示されず、ユーザーは「システムが壊れている」と判断する。

### 関連コード（現状）

- `POST /api/lessons/{id}/start`（`scripts/routes/teacher.py:1072-1092`）: `runner.start()` を呼んですぐ `ok:true` を返す
- `_send_all_and_play`（`src/lesson_runner.py:584-638`）: セクション毎に `_build_section_bundle()` → インライン TTS 生成
- `_notify_tts_progress`（`src/lesson_runner.py:765-777`）: 進捗を配信オーバーレイ（broadcast.html）にだけ送っている。管理画面には届かない
- `get_status()`（`src/lesson_runner.py:1062-1072`）: `state`, `current_index`, `total_sections` のみ。phase・tts_progress を含んでいない
- `startLesson()`（`static/js/admin/teacher.js:1012-1025`）: 成功トーストを出して `loadLessons()` を呼ぶだけ

既存の TTS 事前生成システム（`/api/lessons/{id}/tts-pregen`）もあるが、これはセクション import 時のバックグラウンド処理で、「授業開始」ボタンとは連動していない。

## 修正方針

**管理画面の「授業開始」ボタンに、再生直前のインライン TTS 生成進捗をリアルタイム表示する。**

配信画面側の追加表示は本プランのスコープ外（既存の overlay 通知は残すのみ）。

## 設計

### バックエンド

**1. `LessonRunner` に phase/tts_progress を保持**

```python
# src/lesson_runner.py
class LessonRunner:
    def __init__(...):
        ...
        self._phase: str = "idle"  # "idle" | "preparing" | "playing"
        self._tts_progress: dict = {"current": 0, "total": 0}
```

**2. `_send_all_and_play` の開始で preparing、`lesson_load` 成功時に playing へ**

```python
async def _send_all_and_play(self):
    self._phase = "preparing"
    self._tts_progress = {"current": 0, "total": len(self._sections) - self._current_index}
    ...
    for i in range(start_index, len(self._sections)):
        ...
        self._tts_progress["current"] = i - start_index + 1
        await self._notify_tts_progress(i, len(self._sections))
        bundle = await self._build_section_bundle(section, i)
        ...

    # lesson_load 成功後
    if load_result.get("ok"):
        self._phase = "playing"
```

停止時・IDLE 遷移時は `_phase = "idle"`、`_tts_progress = {"current": 0, "total": 0}` にリセット。

**3. `get_status()` に `phase`, `tts_progress` を追加**

```python
def get_status(self) -> dict:
    return {
        ...既存フィールド...,
        "phase": self._phase,
        "tts_progress": dict(self._tts_progress),
    }
```

### フロントエンド

**1. `startLesson()` 改修**（`static/js/admin/teacher.js:1012`）

- 成功トーストの後、`startLessonStatusPolling(lessonId)` を呼ぶ

**2. ポーリング関数追加**

```javascript
let _lessonStatusTimer = null;

function startLessonStatusPolling(lessonId) {
    if (_lessonStatusTimer) return;
    _lessonStatusTimer = setInterval(async () => {
        const res = await api('GET', '/api/lessons/status');
        if (!res || !res.ok) return;
        const s = res.status;
        if (s.state === 'idle') {
            stopLessonStatusPolling();
            await loadLessons();
            return;
        }
        // UIの部分更新（再描画せず該当要素だけ更新）
        _updateLessonStartLabel(lessonId, s);
        // preparing から playing に遷移したら再描画
        if (s.phase === 'playing') {
            stopLessonStatusPolling();
            await loadLessons();
        }
    }, 1000);
}

function stopLessonStatusPolling() {
    if (_lessonStatusTimer) {
        clearInterval(_lessonStatusTimer);
        _lessonStatusTimer = null;
    }
}
```

**3. STEP 4 レンダリング改修**（`teacher.js:424-445`）

`isPreparing = runningThisLesson && lState === 'running' && s.phase === 'preparing'` を追加。

- `isPreparing` の時: 開始ボタンは「授業準備中 TTS生成 (3/8)」として無効化表示、終了ボタンは押せる、再生中ラベルは「準備中」に
- `isRunning && phase === 'playing'` の時: 従来通り「再生中」

### WebSocket イベント（既存）

`_notify_tts_progress` が送る `lesson_status` イベントは従来通り broadcast.html に届く。本プランでは管理画面は使わず、純粋にポーリングベースでシンプルに実装する。

## 実装ステップ

1. `src/lesson_runner.py`
    - `_phase`, `_tts_progress` 属性追加
    - `_send_all_and_play` で phase 遷移 + `_tts_progress` 更新
    - stop() / 完了 / エラーで phase を "idle" にリセット
    - `get_status()` に新フィールド追加
2. `tests/test_lesson_runner.py` に状態遷移テスト追加
3. `static/js/admin/teacher.js`
    - `startLessonStatusPolling` / `stopLessonStatusPolling` 追加
    - `startLesson()` でポーリング開始
    - `stopLesson()` でポーリング停止
    - STEP 4 レンダリングに preparing 状態のUI分岐追加
4. `tests/test_api_teacher.py` で `/api/lessons/status` が phase/tts_progress を返すことを確認
5. 動作確認:
    - 全キャッシュ済み授業: `preparing` フェーズが一瞬、即 `playing`
    - キャッシュ未生成授業: `preparing N/M` が進み、`playing` に遷移
    - 停止ボタンで preparing 中にも止められる
6. DONE.md / TODO.md 更新

## リスク

| リスク | 影響 | 対策 |
|--------|------|------|
| ポーリング 1秒 × 複数クライアント | 負荷微増（JSON 1本/秒） | 停止条件を phase=playing / state=idle で明確化、孤児タイマーを防ぐ |
| 既存テスト `test_lesson_runner.py` の get_status 期待値 | フィールド追加で失敗の可能性 | 期待値を緩く書き直す（含む条件で検証） |
| preparing 中に stop() された場合の phase リセット漏れ | UI が「準備中」のまま固まる | stop() で明示的に `_phase = "idle"` を設定、ポーリング側は state=idle で停止 |
| 複数授業を連続開始した場合のポーリング孤児 | タイマー複数起動 | `_lessonStatusTimer` を単一インスタンスにして重複起動を防ぐ |

## 完了条件

- キャッシュミスのある授業で「授業開始」を押すと、即座に「授業準備中 TTS生成 (1/8)」のようなラベルが表示され、進捗が更新される
- `lesson_load` が送られて再生が始まると「再生中」に遷移する
- 準備中に停止ボタンで止められる
- 既存の pytest が全て通る
