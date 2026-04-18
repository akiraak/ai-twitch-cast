# C#コントロールパネル Lesson タブに再生/一時停止/停止ボタンを追加

## ステータス: 完了

## 背景と動機

### 現状

`win-native-app/WinNativeApp/control-panel.html` の Lesson タブには、授業タイムライン（上部メタ行 + セクションタブ + dialogue一覧）が表示されるのみで、**再生を制御するボタンが存在しない**。授業の再生/停止/一時停止は、いまは Web UI（`/teacher` 等）からしか操作できない。

また、サーバ側の `src/lesson_runner.py` は授業開始時に `lesson_load` を送った直後に**続けて自動で `lesson_play` を送信している**（`src/lesson_runner.py:629-647`）。このため、サーバで「授業開始」を押すと C# 側は即座に再生に入る。

一方、再生エンジン側（C# 内部）にはすべての機能が揃っている:

- `LessonPlayer.PlayAsync()` / `Pause()` / `Resume()` / `Stop()`（`win-native-app/WinNativeApp/Streaming/LessonPlayer.cs:178,252,265,278`）
- HTTP/WebSocket では `lesson_play` / `lesson_pause` / `lesson_resume` / `lesson_stop` が既に実装済み（`win-native-app/WinNativeApp/Server/HttpServer.cs:471-733`）

ということは、**コントロールパネル（WebView2 → C#）側の配線だけ**が欠けている状態。

### 欲しい形

Lesson タブの上部メタ行の隣、またはその下に **再生 / 一時停止 / 停止** の3ボタンを配置し、クライアント（C# 配信アプリ）の手元で授業の開始/一時停止/停止を操作できるようにする。既存の WebSocket 経路ではなく、control-panel の他のアクション（`goLive` / `stopStream` / `startCapture` 等）と同じく `window.chrome.webview.postMessage` 経路で C# 側に届ける。

さらに、**サーバから授業を開始した場合、クライアント側は自動再生せず「停止状態（state=loaded）」で待機**させる。配信者は C# 側の control-panel の ▶ ボタンを自分のタイミングで押して再生を開始する。これにより「台本・TTS の準備はサーバで、再生開始のトリガはクライアントで」という責務分担が明確になり、配信中に意図せず授業が走り始める事故も防げる。

## 設計方針

### 全体フロー（サーバ起点 → クライアント再生）

```
[サーバ Web UI]                 [C# 配信アプリ]          [control-panel]
授業開始ボタン押下
  ├─ TTS生成
  └─ ws: lesson_load  ───────▶  LessonPlayer.LoadLesson
                                 state=loaded ───────▶  ▶ボタン enabled
                                                        ⏸/■ disabled
                                                        （再生は始まらない）

                                                        [配信者が手元で ▶ 押下]
                                  ◀──────── action:lesson_play
                                 PlayAsync() ────────▶  ⏸/■ enabled、▶ disabled
                                 （再生開始）
```

### ボタンの動作

| ボタン | 動作 | 有効条件 |
|--------|------|----------|
| ▶ 再生 | `state=loaded` なら `PlayAsync()`、`state=paused` なら `Resume()` | state ∈ {loaded, paused} |
| ⏸ 一時停止 | `Pause()` | state == playing |
| ■ 停止 | `Stop()` | state ∈ {playing, paused} |

「再生」と「再開」は UI では 1 つのボタン（▶）に統合する。`paused` から押した場合は `Resume()`、`loaded` なら `PlayAsync()`。こうすることでユーザーは「いま押せる先頭のボタン」を覚えるだけで済む。

※ 授業未ロード（`state=idle`）の時は全ボタン disabled（何も操作できない）。授業のロード（TTS生成 + `lesson_load` 送信）は引き続きサーバ Web UI 経由で行う（本プランのスコープ外）。

### C# 側のアクション

control-panel → C# のメッセージで、以下3アクションを追加:

```jsonc
{"action": "lesson_play"}
{"action": "lesson_pause"}
{"action": "lesson_stop"}
```

`lesson_resume` は別アクションにせず、`lesson_play` 内で `state=paused` を判定して `Resume()` を呼ぶ（`HttpServer.HandleWsLessonPlay` と同じように `CanPlay` を見て分岐）。

### 状態同期

ボタンの enable/disable は、既存の `type: "lesson"` メッセージに含まれる `state` を `updateLesson(m)` で見て切り替える。新しいメッセージタイプは不要。

- `state` フィールドは既に `SendPanelUpdate()` が送っている（`LessonPlayer.cs:363` 付近）。`control-panel-lesson-timeline.md` プランで `kind` も追加済み
- `setLessonOutline()` が呼ばれた直後は `state` メッセージが未到着のことがあるため、outline 受信時に state を "loaded" と仮置きする

### なぜ WebSocket 経由ではないか

control-panel は C# 内部の WebView2 にホストされており、他のアクション（capture 制御・音量・配信開始）はすべて `chrome.webview.postMessage` → `OnPanelMessage` 経由。授業制御だけ WebSocket に逃がすと一貫性が壊れる。C# 内部では `_lessonPlayer` を直接参照できるため、WebSocket を挟む必要もない。

## UI 設計

### レイアウト

上部メタ行（既存: `lesson-id` + `lessonBadge` + `lessonProgress`）の下に、ボタン行を追加する:

```
┌─ Lesson #123 ──────────── [playing] ─┐
│ Section 3/8 [question]  Dialogue 2/3 │
│ [▶ 再生] [⏸ 一時停止] [■ 停止]       │  ← NEW
├──────────────────────────────────────┤
│ [§1 ✓] [§2 ✓] [§3 ▶] [§4]…          │
│ ...（既存のタイムライン）            │
```

ボタンは既存の `.btn` / `.btn-go`（緑）/ `.btn-stop`（赤）クラスを流用:

- ▶ 再生: `btn btn-go`
- ⏸ 一時停止: `btn`（標準のグレー）
- ■ 停止: `btn btn-stop`

### 状態別の見え方

| state | ▶ 再生 | ⏸ 一時停止 | ■ 停止 |
|-------|--------|------------|--------|
| idle（未ロード） | disabled | disabled | disabled |
| loaded | enabled | disabled | disabled |
| playing | disabled | enabled | enabled |
| paused | enabled（文言「再開」に変更） | disabled | enabled |

※ `playing → paused` を切り替える「一時停止」ボタン1つで再開まで兼ねる案も検討したが、disabled の 3 ボタン並びよりトグル 1 つの方が小さく映え、視認性の面で捨てがたい反面、**再開を押した時に「何が起こるか」の予測が難しくなる**（アイコンが ▶/⏸ に変わるだけ）。本プランでは「▶再生」が再開も兼ねる形に統一する（文言切替で示す）。

## 実装ステップ

### Phase 0: サーバ側の自動 lesson_play を止める

**ゴール**: `src/lesson_runner.py` が `lesson_load` の後に `lesson_play` を自動送信しないようにする。C# 側は load 後 `state=loaded` で停止状態になる。

**変更ファイル**:

| ファイル | 変更 |
|---------|------|
| `src/lesson_runner.py` | `lesson_load` 直後の `lesson_play` 送信ブロック（`src/lesson_runner.py:641-650`）を削除。合わせて、その後の `_wait_lesson_complete`（`:656`）も意味が変わる — 再生が始まる前に待ち始めてしまうため、**完了待ちは残すが、再生開始は control-panel の ▶ ボタンに委ねる**旨のコメントを追加 |
| 同上 | `_save_playback_state` の呼び出し順序を見直し: 再生開始時刻の基準が「load 完了時」か「play 開始時」かで DB 記録が変わる。load 完了時に仮記録し、クライアントが再生開始したら改めて更新する…のは複雑なので、**当面は「load 完了で _save_playback_state を呼ぶ」だけに留める**（本プランでは詳細は追わない。必要なら別プランで「実再生開始時刻の記録」を切り出す） |
| `src/lesson_runner.py` docstring | 「lesson_load で一括送信 → lesson_play で再生開始」→「lesson_load で一括送信（再生は C# 側 control-panel の ▶ で開始）」に更新 |

**確認方法**:

1. `python3 -m pytest tests/test_lesson_runner.py -q` が通る（`lesson_play` 送信を期待していたテストがあれば削除・修正する）
2. Web UI から授業を開始 → C# のログに `lesson_load` は届くが `lesson_play` は届かない
3. broadcast.html / control-panel の Lesson タブは授業タイムラインを表示しているが、再生は始まっていない（badge=loaded）

### Phase 1: C# 側にアクションハンドラを追加

**ゴール**: control-panel から送った `lesson_play` / `lesson_pause` / `lesson_stop` を C# が受け取り、`LessonPlayer` を操作できる。

**変更ファイル**:

| ファイル | 変更 |
|---------|------|
| `win-native-app/WinNativeApp/MainForm.cs` | `OnPanelMessage` の `switch (action)` に `case "lesson_play"` / `case "lesson_pause"` / `case "lesson_stop"` を追加。それぞれ `HandlePanelLessonPlay/Pause/Stop` を呼ぶ |
| 同上 | `HandlePanelLessonPlay()`: `_lessonPlayer` が null なら無視。`CanPlay` なら `Task.Run(() => _lessonPlayer.PlayAsync())`。`IsPlaying && state=paused` の場合は `Resume()`（`LessonPlayer.GetStatus()` 経由で state を取るか、`LessonPlayer` に `IsPaused` プロパティを1つ追加） |
| 同上 | `HandlePanelLessonPause()`: `_lessonPlayer?.Pause()` |
| 同上 | `HandlePanelLessonStop()`: `_lessonPlayer?.Stop()` |
| `win-native-app/WinNativeApp/Streaming/LessonPlayer.cs` | `IsPaused` プロパティを追加（`_paused` を晒す）。MainForm から再生/再開を判別するために使う |

**確認方法**:

1. `dotnet build win-native-app/WinNativeApp/WinNativeApp.csproj` 成功
2. Web UI 経由で授業をロード → コントロールパネルを開いて DevTools から手動で `window.chrome.webview.postMessage({action:'lesson_play'})` を実行 → 再生が始まる

### Phase 2: control-panel.html にボタンを追加

**ゴール**: Lesson タブに3ボタンが並び、クリックで C# にアクションが届く。状態に応じて有効/無効が切り替わる。

**変更ファイル**:

| ファイル | 変更 |
|---------|------|
| `win-native-app/WinNativeApp/control-panel.html` | `<div class="tab-content" id="tab-lesson">` の `lesson-header` と timeline の間に `<div class="btn-row" id="lessonControls">` を追加。3ボタンを配置（id: `lessonPlayBtn` / `lessonPauseBtn` / `lessonStopBtn`） |
| 同上 | JS: `playLesson()` / `pauseLesson()` / `stopLesson()` の3関数。それぞれ `send({action: 'lesson_play' / 'lesson_pause' / 'lesson_stop'})` |
| 同上 | JS: `updateLesson(m)` の末尾で `_updateLessonButtons(m.state)` を呼ぶ。`_updateLessonButtons` は state に応じて `disabled` と `textContent` を切り替える<br>　- state=idle/loaded/playing/paused の各場合で上の表の通り設定<br>　- paused 時は `lessonPlayBtn.textContent = '▶ 再開'`、それ以外は `'▶ 再生'` |
| 同上 | JS: `setLessonOutline(m)` の末尾で `_updateLessonButtons('loaded')` を呼ぶ（outline 到着 → ロード完了と見なす） |
| 同上 | 初期表示: HTML の時点で全ボタン `disabled`（授業未ロード状態） |

**確認方法**:

1. WinNativeApp を起動、コントロールパネルを開く
2. Web UI で授業を開始 → コントロールパネルに timeline が表示され、**▶再生 のみ enabled**（⏸/■ は disabled、badge=loaded、再生は始まっていない）
3. ▶再生 をクリック → 再生開始、badge が playing に、⏸一時停止 と ■停止 が enabled に、▶再生 が disabled に
4. ⏸一時停止 をクリック → badge が paused、▶再生 の文言が「▶ 再開」に変わり enabled、⏸一時停止 は disabled に
5. ▶再開 をクリック → playing に戻る
6. ■停止 をクリック → idle に戻り、3ボタン全て disabled に

### Phase 3: テストとドキュメント

**変更ファイル**:

| ファイル | 変更 |
|---------|------|
| `tests/test_native_app_patterns.py` | `control-panel.html` に `lessonPlayBtn` / `lessonPauseBtn` / `lessonStopBtn` が存在すること、`lesson_play` / `lesson_pause` / `lesson_stop` アクションが `MainForm.cs` の `OnPanelMessage` で分岐されていることを静的検査（簡易テスト追加） |
| `DONE.md` | Phase 2 完了時に記載（`win-native-app/...` のコントロールパネルに授業再生操作を追加） |
| `TODO.md` | 該当行を削除（本プランへのリンクも同時に削除） |

## 既存機能との関係

| 既存 | 本プランでの扱い |
|------|----------------|
| Web UI の授業開始ボタン | そのまま残す。意味が「授業開始（ロード + 即再生）」→「授業ロード（TTS生成 + C#への転送、再生開始は手元）」に変わる。ボタン文言の変更は任意（本プランでは変えない。Phase 3 以降で検討） |
| `src/lesson_runner.py` の自動 `lesson_play` 送信 | **Phase 0 で削除**。サーバは `lesson_load` まで、再生開始は control-panel の ▶ に委ねる |
| `lesson_load` アクション | そのまま流用（サーバ → C# の転送経路）。control-panel からは叩かない |
| `SendPanelUpdate` が送る `state` | そのまま流用。ボタン有効/無効のトリガとして使う |
| `lesson_outline` メッセージ | そのまま流用。受信時に state を "loaded" と仮置き |
| HTTP/WebSocket の `lesson_play` / `lesson_pause` / `lesson_stop` | エンドポイントは引き続き残す（テストや外部ツール用）。ただし通常運用では control-panel → `OnPanelMessage` 経由が主になる |

## リスク

| リスク | 影響 | 対策 |
|--------|------|------|
| ボタンの state 遷移中に多重クリック | `PlayAsync` が二重起動し例外 | クリック直後に該当ボタンを即 disabled にし、次の `lesson` メッセージ到着までそのまま |
| 配信者が ▶ を押し忘れる | 授業が延々と始まらない | Web UI 側に「C#側で ▶ を押すと開始します」旨の説明テキストを表示（Phase 3 で対応）。また control-panel の Lesson タブを授業 load 時に自動で前面化することも検討（本プランでは非スコープ）|
| `_wait_lesson_complete` が load 直後から待ち始める（再生開始前） | サーバ側の「完了」判定が遅延する（実質 play を押すまで +α） | 本プランの挙動変更として受け入れる。サーバ側のタイムアウトは `total_duration` 基準のため、ユーザーが ▶ を押すのが十分遅れると誤タイムアウトの可能性あり → Phase 0 で「完了待ちは再生開始通知後から計測」に変更するか、タイムアウトを load からの猶予を含めた値に変えるか検討する |
| `state=idle` の状態判定漏れ（授業完了後に outline は残るがボタンが disabled に戻らない） | ユーザーが押しても何も起こらない | `updateLesson(m)` で state=idle を受けたら全 disabled に戻す。`lesson_complete` WS を受けた時の経路は broadcast.html 用で control-panel には届かないため、`SendPanelUpdate` の finally 呼び出しに依存する（既存動作）|
| paused 中に再生を押して Resume が発火しない（state 取得漏れ） | UI が固まる | C# 側で `CanPlay` と `IsPaused` の両方をチェック。どちらでもなければエラーログを出す |
| `Task.Run` の例外が飲まれる | 再生失敗がユーザーに見えない | 既存 `HandleWsLessonPlay` と同じく `Log.Error` のみ。PanelLog で `授業再生失敗` を通知する追加も検討 |

## 関連プラン

- [control-panel-lesson-timeline.md](control-panel-lesson-timeline.md) — Lesson タブをタイムライン表示に差し替え（完了済み）。本プランはその継続で「表示はできた → 操作もできる」にする
- [client-driven-lesson.md](client-driven-lesson.md) — LessonPlayer が全セクションをメモリに持つ前提

## 参考箇所

- C# LessonPlayer の再生/停止/一時停止/再開: `win-native-app/WinNativeApp/Streaming/LessonPlayer.cs:178,252,265,278`
- WS 側の同等ハンドラ: `win-native-app/WinNativeApp/Server/HttpServer.cs:694-733`
- control-panel から C# へのアクション分岐: `win-native-app/WinNativeApp/MainForm.cs:291-350`
- `SendPanelUpdate` が送る匿名型: `win-native-app/WinNativeApp/Streaming/LessonPlayer.cs:363-414`
- サーバ側の自動 `lesson_play` 送信箇所（Phase 0 で削除対象）: `src/lesson_runner.py:641-650`
- 既存ボタンクラス（色・disabled）: `win-native-app/WinNativeApp/control-panel.html:106,122-125`
