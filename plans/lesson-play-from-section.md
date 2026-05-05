# 授業モード: 各セクションの先頭から再生可能に（C# コントロールパネル）

ステータス: 未着手（プラン）
担当: Claude / akiraak
関連 TODO: `TODO.md` の「授業モードで各セクションの先頭から再生可能に」

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
- `"lesson_play" => HandleWsLessonPlay()` (`HttpServer.cs:564, 826-841`) — 引数なしで `PlayAsync()` を呼ぶだけ
- WebView2 → C# のメッセージは `wv.postMessage(msg)` で MainForm が受けて WebSocket / 直接呼び出しに変換する想定（要確認: コントロールパネルからの `lesson_play` 送信ルート）

### コントロールパネル (`win-native-app/WinNativeApp/control-panel.html`)
- `playLesson()` (`:986-990`) — `send({action:'lesson_play'})` のみ
- タイムライン UI: `setLessonOutline` → `renderLessonTimeline` で各セクション・各 dialogue が表示される
- `_selectSection(idx)` — 現状は表示切替のみ（再生はしない）

### サーバ → C# の送信（変更なし）
- `lesson_load`（`src/lesson_runner.py:629-635`）: 全セクションのバンドルを送信。**今回はここに一切手を入れない**。
- 進捗イベント `lesson_complete` / `lesson` (panel update) もそのまま。

## 方針

C# クライアント単独で「セクション N から再生」を実装する。改修は LessonPlayer・HttpServer ハンドラ・control-panel.html の 3 箇所のみ。

### UI（コントロールパネル）

タイムライン (`control-panel.html` の `lessonDialoguesList`) は既に**「現在表示中のセクション」をタブで切り替えて、その中の dialogue 一覧を出す** 構造になっている (`control-panel.html:968-983` / 直後のレンダラ)。
ここに次の 2 種類の ▶ ボタンを足す:

1. **画面上部の既存「▶ 再生」ボタン** (`lessonPlayBtn`)
   - 現状動作のまま: セクション 0 から再生（= 全体再生）
   - ラベルを少し変える: **「▶ 最初から再生」**
2. **タイムライン内、各セクション行 / セクションタブの先頭に「▶ ここから」ボタン**
   - クリックで `send({action:'lesson_play', section_index: N})`
   - ロード済み (`state === 'loaded'` または `'paused'`) のときだけ有効
   - 再生中 (`'playing'`) は disabled（または「セクション切替＝stop してから新規再生」にするかは検討、まず disabled）

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

`lesson_complete` の `sections_played` は **`_currentSectionIndex - startIndex + 1`** にすると「N から M セクション再生した」という意味で正確になる（要なければ既存式のままでも実害なし）。

### `HandleWsLessonPlay` 拡張

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

ディスパッチも `"lesson_play" => HandleWsLessonPlay(msg)` に変更（`HttpServer.cs:564`）。

## サーバ（Python）側

**変更なし**。
- `/api/lessons/{id}/start` のシグネチャはそのまま
- `lesson_runner._send_all_and_play` もそのまま（毎回 `_current_index = 0` で送る）
- `_save_playback_state` / restore も影響なし（C# 単独でセクションを進める運用は本プランの守備範囲外）

> 注意: 「C# 側で N から再生開始 → サーバ再起動」が起きた場合、Python 側の永続化は `section_index = 0` のままなので restore で先頭からやり直す。これは現状仕様（C# が単独で進めても Python は把握していない）と同じ。restore の精緻化が必要になったら別 TODO で扱う。

## 実装ステップ

1. **`LessonPlayer.cs`**
   - `PlayAsync(int startIndex = 0)` に変更
   - 範囲チェック（`ArgumentOutOfRangeException`）
   - `for` ループの開始 i を `startIndex` に
   - `_currentSectionIndex = startIndex` 初期化
   - （任意）`sections_played` を `_currentSectionIndex - startIndex + 1` に
2. **`HttpServer.cs`**
   - `HandleWsLessonPlay` を `(JsonElement msg)` 受けに
   - `section_index` を読み取り `PlayAsync(startIndex)` に渡す
   - ディスパッチ `"lesson_play" => HandleWsLessonPlay(msg)` を更新
3. **`control-panel.html`**
   - `playLesson()` のラベルを「▶ 最初から再生」に
   - タイムラインのセクションタブ／行頭に「▶ ここから」ボタンを追加
     - `state === 'loaded' || state === 'paused'` のときだけ enabled
     - クリック → `send({action:'lesson_play', section_index: idx})`
   - （任意）`pauseLesson` 中のラベルは既存「▶ 再開」のまま、`resume` 経路は変更しない
4. **MainForm 側のメッセージブリッジ**
   - control-panel から WebView2 経由で来る `{action:'lesson_play'}` を C# WebSocket / LessonPlayer ルートに変換している箇所（要確認: 既存 `lesson_play` の送信ルート）
   - ここで `section_index` を素通しできるように
5. **動作確認（実機）**
   - 授業をロード → 既存の「▶ 最初から再生」 → セクション 0 から完走
   - 授業をロード → タイムラインでセクション 3 に切替 → 「▶ ここから」 → セクション 3 から完走
   - 一時停止 → 別セクションの「▶ ここから」 → 停止後に新規再生（または disabled になっている）の挙動が想定どおり
   - `lesson_complete` の `sections_played` がそれっぽい数字になっている
6. **C# テスト** （`tests/test_native_app_patterns.py` がソース解析のみであることを踏まえ、必要に応じて軽量パターン検証を追加。実機動作テストが主）
7. **ドキュメント・記録**
   - `DONE.md` に追記、`TODO.md` の該当行を削除
   - C# 側のメモリ・docs に変更が及ぶなら `docs/speech-generation-flow.md` 等に追記

## リスク・代替案

| リスク | 対策 |
|--------|------|
| `lesson_play` メッセージにフィールドを追加する後方互換性 | `section_index` 未指定なら 0（既存挙動）。既存呼び出し箇所は無改修で動く |
| 再生中に「ここから」を押された場合の挙動 | まず disabled にする。要望が出たら「stop → 新規 PlayAsync(N)」を `LessonPlayer` の `Stop()` 完了後に行うラッパーを足す |
| サーバ側 `_save_playback_state` との齟齬 | 現状仕様の延長として許容。restore で先頭からになるが、配信中の挙動には影響しない |
| section_index が範囲外（DOM の古い outline を使った場合） | C# 側で `ArgumentOutOfRangeException` をログに残し、UI には「再生開始失敗」を返す（既存の `streamResult` 系と同じ流儀） |

## スコープ外（やらない）

- WebUI（管理画面 admin）にセクション再生 UI を入れる
- Python サーバ側 API (`/api/lessons/{id}/start`) の改修
- 任意の範囲指定（N..M で止める）、単発再生（N だけ）
- サーバ→クライアントの送信フォーマット変更（`lesson_load` は無改修）
- restore で「N から再開」を Python 側で記録する仕組み
