# 授業モード: 各セクションの先頭から再生可能に（C# コントロールパネル）

ステータス: 完了（実装・テスト済 / 実機動作確認は別 TODO で残置）
担当: Claude / akiraak
関連 TODO: `TODO.md` の「授業モードで各セクションの先頭から再生可能に」（実機確認のみ残）

## 実装結果

- `LessonPlayer.PlayAsync(int startIndex = 0)`: 範囲チェック (`ArgumentOutOfRangeException`)、ループ開始 i・`_currentSectionIndex` 初期化を `startIndex` に
- `MainForm.HandlePanelLessonPlay(JsonElement msg)`: `section_index` 未指定 + `paused` のみ Resume、それ以外は `PlayAsync(idx)` 直行。範囲外は `BeginInvoke(() => PanelLog(...))` で UI 通知
- `HttpServer.HandleWsLessonPlay(JsonElement msg)`: 外部 WS も `section_index` を受け付け（Resume 分岐なし、レスポンスに `section_index` を含める）
- `control-panel.html`: メイン ▶ ボタンのラベルを `loaded` 時「▶ 最初から再生」に / 各タブに「▶ ここから」ボタン追加（`state==='loaded'` のみ enable、`event.stopPropagation()`）。`_timelineState.state` に再生状態を保持
- `tests/test_native_app_patterns.py`: PlayAsync の startIndex プラミングと両ハンドラのディスパッチを静的検証。既存 `PlayAsync\(\)` regex を `PlayAsync\([^)]*\)` に拡張

## 背景・目的

授業モードは現状、C# 側コントロールパネルの **▶ 再生 / ⏸ 一時停止 / ■ 停止** の 3 ボタンしかなく、再生は常にセクション 0 から始まる (`control-panel.html:638-640`, `LessonPlayer.cs:195`)。
配信中に「直前のセクションをもう一度流したい」「特定のセクションだけ試したい」「途中から再開したい」というシーンで、毎回先頭から流し直すのは現実的でない。

ゴール: **既存のサーバ→クライアント データ送信（lesson_load で全セクション一括）はそのまま維持**し、C# コントロールパネルに「全体再生」と「各セクションの先頭から再生」を選べる UI を入れる。Python サーバ側 API・WebUI（管理画面）の改修はしない。

## なぜ C# 側で完結できるか

`LessonPlayer.LoadLesson` は受け取った全セクションのバンドル（WAV/lipsync 含む）を `_sections` にメモリ保持する (`LessonPlayer.cs:101-137`)。再生本体は

```csharp
for (int i = 0; i < _sections.Count; i++) { ... }
```

の単純ループ (`LessonPlayer.cs:195`)。**開始 i を引数で受けるだけ** で「セクション N から再生」が成立する。Python とのラウンドトリップも、TTS の再送もない。

コントロールパネルも `setLessonOutline` で全セクションの outline をすでに描画している (`control-panel.html:968-983`, タイムラインは `lessonDialoguesList`)。各行クリックで `_selectSection(idx)` が走り、いまは「ビューだけ移動」する。ここに **▶ ボタンを足して `lesson_play` を section_index 付きで送る** だけで UI が成立する。

## 現状の関連コード

### C# (`win-native-app/WinNativeApp/Streaming/LessonPlayer.cs`)
- `PlayAsync()` — 引数なし、常に `_currentSectionIndex = 0` から開始 (`LessonPlayer.cs:180-252`)
- `LoadLesson(json)` — 全 `_sections` をメモリにロード（再ロード不要）
- `Pause/Resume/Stop` — section_index に依存しない
- `SendOutlineToPanel()` — outline 送信時に各 section に `section_index` を含めている (`LessonPlayer.cs:140-177`)

### C# (`win-native-app/WinNativeApp/Server/HttpServer.cs`)
- `"lesson_play" => HandleWsLessonPlay()` (`HttpServer.cs:564, 826-841`) — 引数なしで `PlayAsync()` を呼ぶだけ。**外部 WebSocket クライアント向けルート**（`/ws/control`）
- 再生中なら `Already playing`、未ロードなら `No lesson loaded` を返すだけで Resume 機能は持たない

### C# (`win-native-app/WinNativeApp/MainForm.cs`) ← **コントロールパネルからの実ルートはこちら**
- `control-panel.html` の `send({action:'lesson_play'})` は `wv.postMessage()` で `OnPanelMessage` (`MainForm.cs:312-401`) に届く
- `case "lesson_play"` (`:384-386`) → `HandlePanelLessonPlay()` (`:622-649`) を呼ぶ
- **既に分岐ロジックを持つ**: `IsPlaying && IsPaused` なら `Resume()`、それ以外なら `PlayAsync()`
- 現状シグネチャは `HandlePanelLessonPlay()`（引数なし）。`section_index` を扱うにはここを `(JsonElement msg)` 化する必要がある

### コントロールパネル (`win-native-app/WinNativeApp/control-panel.html`)
- `playLesson()` (`:986-990`) — `send({action:'lesson_play'})` のみ
- `_updateLessonButtons(state)` (`:1000-1032`) — 状態別にボタンラベル切替:
  - `loaded`: ▶ 再生 (enabled), ⏸ disabled, ■ disabled
  - `playing`: ▶ 再生 (disabled), ⏸ enabled, ■ enabled
  - `paused`: **▶ 再開** (enabled), ⏸ disabled, ■ enabled  ← 同じボタンが Resume を兼ねる
- タイムライン UI: `setLessonOutline` → `renderLessonTimeline` (`:1110-`) で各セクションをタブ化、選択セクションの dialogue を一覧表示
- `_selectSection(idx)` (`:1051-1055`) — 現状は表示切替のみ（再生はしない）
- タブの click handler は `:1140`

### サーバ → C# の送信（変更なし）
- `lesson_load`（`src/lesson_runner.py:629-635`）: 全セクションのバンドルを送信。**今回はここに一切手を入れない**。
- 進捗イベント `lesson_complete` / `lesson` (panel update) もそのまま。

## 方針

C# クライアント単独で「セクション N から再生」を実装する。改修は **LessonPlayer・MainForm.OnPanelMessage の Lesson ハンドラ・HttpServer.HandleWsLessonPlay・control-panel.html** の 4 箇所。

### UI（コントロールパネル）

タイムライン (`control-panel.html` の `lessonDialoguesList`) は既に**「現在表示中のセクション」をタブで切り替えて、その中の dialogue 一覧を出す** 構造になっている (`control-panel.html:968-983` / 直後のレンダラ)。
ここに次の 2 種類の ▶ ボタンを足す:

1. **画面上部の既存「▶ 再生」ボタン** (`lessonPlayBtn`)
   - 現状動作のまま（`HandlePanelLessonPlay` の Resume 分岐込み）:
     - `loaded` のとき → セクション 0 から再生（= 全体再生）
     - `paused` のとき → 現セクションから Resume
   - ラベルは状態に応じて切り替える既存仕様を維持: `loaded` なら「**▶ 最初から再生**」、`paused` なら「▶ 再開」
2. **タイムラインのセクションタブ先頭に「▶ ここから」ボタン**
   - クリックで `send({action:'lesson_play', section_index: N})`
   - **enable 条件**:
     - `loaded` → そのまま `PlayAsync(N)` を呼べる
     - `paused` → 「再開」とは別物の「N から再生し直し」。**まず disabled とし、要望が出てから「内部で Stop → PlayAsync(N)」のラッパを足す**（Stop は非同期で `_playing` が false になるのを待つ必要があるためロジックがやや増える）
     - `playing` → disabled
   - 配置: タブ (`:1131-1142`) の中に小さい ▶ アイコンを並べる。既存の `addEventListener('click', () => _selectSection(i))` は据え置き、▶ アイコンは `event.stopPropagation()` でタブ切替と分離する

### C# 側プロトコル

`lesson_play` メッセージに **オプションの `section_index`** を追加する（互換維持: 未指定なら 0）。

```jsonc
// 既存
{ "type": "lesson_play" }
// 拡張
{ "type": "lesson_play", "section_index": 3 }
```

### `LessonPlayer.PlayAsync` 拡張

```csharp
public async Task PlayAsync(int startIndex = 0)
{
    if (_sections == null || _sections.Count == 0) throw ...;
    if (startIndex < 0 || startIndex >= _sections.Count)
        throw new ArgumentOutOfRangeException(nameof(startIndex));
    if (_playing) throw ...;

    _playing = true;
    _paused = false;
    _state = "playing";
    _cts = new CancellationTokenSource();
    _currentSectionIndex = startIndex;
    string reason = "completed";
    try
    {
        for (int i = startIndex; i < _sections.Count; i++) { ... }  // 既存ループの開始だけ変更
    }
    ...
}
```

`lesson_complete` の `sections_played` は既存式 `_currentSectionIndex + (reason == "completed" ? 1 : 0)` のまま据え置く。**意味的には「再生した区間の長さ」ではなく「最終的な絶対 section_index（+1）」になるが、grep で確認した結果このフィールドの消費者は無し**:

- `LessonPlayer.cs:239` のログ出力
- `scripts/services/capture_client.py:248-251` で `_lesson_complete_payload` にバッファされる → `get_lesson_complete_payload()` は定義のみで呼び出し箇所なし

→ 仕様変更の波及リスクは無い。式変更で混乱を招くより、絶対 index を返す現仕様のほうが将来の restore 連携にも向くので**変更しない**。

### `HandlePanelLessonPlay` 拡張（**MainForm.cs — 主要改修点**）

コントロールパネルからの `{action:'lesson_play', section_index?: N}` を受け取り、Resume 分岐と新規再生分岐を整理する。

```csharp
case "lesson_play":
    HandlePanelLessonPlay(msg);  // ← msg を渡す
    break;

private void HandlePanelLessonPlay(JsonElement msg)
{
    var player = _lessonPlayer;
    if (player == null) { PanelLog("授業未ロード", "error"); return; }

    int? startIndex = null;
    if (msg.TryGetProperty("section_index", out var si) && si.ValueKind == JsonValueKind.Number)
        startIndex = si.GetInt32();

    // Resume 分岐: section_index 未指定で paused のときのみ Resume（既存「▶ 再開」の挙動）
    if (startIndex == null && player.IsPlaying && player.IsPaused)
    {
        player.Resume();
        return;
    }

    if (!player.CanPlay)
    {
        PanelLog(player.IsPlaying ? "授業は既に再生中です" : "授業がロードされていません", "info");
        return;
    }

    var idx = startIndex ?? 0;
    _ = Task.Run(async () =>
    {
        try { await player.PlayAsync(idx); }
        catch (Exception ex) { Log.Error(ex, "[Lesson] Panel PlayAsync failed"); }
    });
}
```

> ポイント: `section_index` が**指定されているときは Resume を経由しない**。これにより「paused 中にタブの ▶ ここから が押された場合の動作」も将来の Stop+Play ラッパで一元的に扱える（現バージョンでは UI 側で disabled）。

### `HandleWsLessonPlay` 拡張（HttpServer.cs — 外部 WS クライアント向け、副次的改修）

```csharp
private object HandleWsLessonPlay(JsonElement msg)
{
    if (LessonPlayer == null) return new { ok = false, error = "LessonPlayer not available" };
    if (!LessonPlayer.CanPlay)
        return new { ok = false, error = LessonPlayer.IsPlaying ? "Already playing" : "No lesson loaded" };

    int startIndex = 0;
    if (msg.TryGetProperty("section_index", out var si) && si.ValueKind == JsonValueKind.Number)
        startIndex = si.GetInt32();

    _ = Task.Run(async () =>
    {
        try { await LessonPlayer.PlayAsync(startIndex); }
        catch (Exception ex) { Log.Error(ex, "[Lesson] PlayAsync failed"); }
    });
    return new { ok = true, section_index = startIndex };
}
```

ディスパッチも `"lesson_play" => HandleWsLessonPlay(msg)` に変更（`HttpServer.cs:564`）。こちらは Resume 分岐を持たない既存方針のまま（`HandlePanelLessonPlay` と非対称だが、外部 WS 向けは「Resume したいなら明示的に lesson_resume」が筋）。

## サーバ（Python）側

**変更なし**。
- `/api/lessons/{id}/start` のシグネチャはそのまま
- `lesson_runner._send_all_and_play` もそのまま（毎回 `_current_index = 0` で送る）
- `_save_playback_state` / restore も影響なし（C# 単独でセクションを進める運用は本プランの守備範囲外）

> 注意: 「C# 側で N から再生開始 → サーバ再起動」が起きた場合、Python 側の永続化は `section_index = 0` のままなので restore で先頭からやり直す。これは現状仕様（C# が単独で進めても Python は把握していない）と同じ。restore の精緻化が必要になったら別 TODO で扱う。

## 実装ステップ

1. **`LessonPlayer.cs`**
   - `PlayAsync(int startIndex = 0)` に変更
   - 範囲チェック（`startIndex < 0 || startIndex >= _sections.Count` で `ArgumentOutOfRangeException`）
   - `for` ループの開始 i を `startIndex` に
   - `_currentSectionIndex = startIndex` 初期化
   - `sections_played` の式は据え置き（消費者なし、絶対 index 表現のままで OK）
2. **`MainForm.cs` — 主要改修**
   - `HandlePanelLessonPlay()` を `HandlePanelLessonPlay(JsonElement msg)` に
   - `section_index` を読み取って分岐:
     - `section_index` 未指定 + `paused` → 既存の `Resume()`
     - それ以外 → `PlayAsync(idx)`（`idx = section_index ?? 0`）
   - `OnPanelMessage` の `case "lesson_play"` で `HandlePanelLessonPlay(msg)` に msg を渡す
3. **`HttpServer.cs` — 副次的改修（外部 WS クライアント向け）**
   - `HandleWsLessonPlay` を `(JsonElement msg)` 受けに
   - `section_index` を読み取り `PlayAsync(startIndex)` に渡す
   - ディスパッチ `"lesson_play" => HandleWsLessonPlay(msg)` を更新
   - Resume 分岐は持たせない（外部クライアントは `lesson_resume` を使う方針）
4. **`control-panel.html`**
   - `_updateLessonButtons` の `loaded` 分岐でメインボタンのラベルを「**▶ 最初から再生**」に変更（`paused` 分岐は「▶ 再開」のまま）
   - `renderLessonTimeline` のタブ生成 (`:1131-1142`) に「▶ ここから」アイコンを追加
     - `state === 'loaded'` のときだけ enabled（`paused`/`playing` は disabled）
     - クリック → `event.stopPropagation()` した上で `send({action:'lesson_play', section_index: i})`
     - タイムラインのタブ click（`_selectSection`）はそのまま
   - 多重クリック防止: `playLesson()` と同様、送信直後に該当ボタンを disabled に
5. **動作確認（実機）**
   - 授業をロード → 「▶ 最初から再生」 → セクション 0 から完走、`lesson_complete` 受信
   - 授業をロード → タブ「§3」の「▶ ここから」 → セクション 3 から完走（`section_index` がメッセージに乗っていることを `[Panel] Action:` ログで確認）
   - 一時停止 → メインボタンが「▶ 再開」になり、押下で Resume すること（既存挙動の非リグレ）
   - 一時停止 → タブの「▶ ここから」が disabled になっていること
   - 再生中 → タブの「▶ ここから」が disabled になっていること
   - 範囲外（DOM 古い outline 等）で section_index が大きすぎる場合: C# 側 `ArgumentOutOfRangeException` がログに出て UI には PanelLog で通知される
6. **C# テスト** （`tests/test_native_app_patterns.py` がソース解析のみであることを踏まえ、必要に応じて軽量パターン検証を追加。実機動作テストが主）
7. **Python テスト** — 影響なし。`tests/test_lesson_runner.py` 等は `lesson_complete` payload の中身を見ていないので変更不要（消費者がいないことを grep で確認済み）
8. **ドキュメント・記録**
   - `DONE.md` に追記、`TODO.md` の該当行を削除
   - 本プランの**ステータスを「完了」に更新**
   - 必要なら `docs/speech-generation-flow.md` の授業フロー記述に「セクション N から再生可能」を 1 行追記

## リスク・代替案

| リスク | 対策 |
|--------|------|
| `lesson_play` メッセージにフィールドを追加する後方互換性 | `section_index` 未指定なら従来挙動（0 から再生 or paused なら Resume）。既存呼び出し箇所は無改修で動く |
| `HandlePanelLessonPlay` の Resume 分岐との衝突 | `section_index` 指定時は Resume を経由せず `PlayAsync(idx)` に直行。これで「paused 中に N から再生」と「paused 中に再開」を意図で区別できる |
| 再生中／一時停止中に「ここから」を押された場合の挙動 | まず UI 側で disabled にする。要望が出たら「Stop → `_playing == false` を待って → PlayAsync(N)」のラッパーを `LessonPlayer` か `MainForm` に足す |
| サーバ側 `_save_playback_state` との齟齬 | 現状仕様の延長として許容。restore で先頭からになるが、配信中の挙動には影響しない |
| section_index が範囲外（DOM の古い outline を使った場合） | C# 側で `ArgumentOutOfRangeException` をログに残し、`PanelLog("セクション N が範囲外", "error")` で UI に通知 |
| `sections_played` の意味変更 | **しない**（grep で消費者なしと確認済み。`get_lesson_complete_payload()` は定義のみで未使用） |

## スコープ外（やらない）

- WebUI（管理画面 admin）にセクション再生 UI を入れる
- Python サーバ側 API (`/api/lessons/{id}/start`) の改修
- 任意の範囲指定（N..M で止める）、単発再生（N だけ）
- サーバ→クライアントの送信フォーマット変更（`lesson_load` は無改修）
- restore で「N から再開」を Python 側で記録する仕組み
