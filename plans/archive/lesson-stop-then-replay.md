# C# Lesson タブで停止した授業を再生し直せるようにする

## ステータス: 完了

## 背景と動機

### 現象

C# ネイティブ配信アプリのコントロールパネル Lesson タブで **■停止** を押すと、タイムライン表示と ▶再生 ボタンが同時に死ぬ。以後は授業がロードされていない状態（`state=idle`）に戻り、サーバから `lesson_load` を送り直さない限り再生できない。

想定される使い方（授業のリハーサル、冒頭だけ流して止めて別の操作をしてから先頭から流し直す、など）ができない。

### 根本原因

`LessonPlayer` が **停止と同時に授業データ（`_sections`）を破棄する**ため、再生の「種」が失われる。

1. **`Stop()` の分岐 A（`_playing=false` のとき）**
   `win-native-app/WinNativeApp/Streaming/LessonPlayer.cs:280-289`
   ```csharp
   if (!_playing)
   {
       _state = "idle";
       _sections = null;           // ← ここで授業データが消える
       _currentDialogues = null;
       SendPanelUpdate();
       return;
   }
   ```

2. **`PlayAsync()` finally ブロック**
   `win-native-app/WinNativeApp/Streaming/LessonPlayer.cs:221-250`
   ```csharp
   finally
   {
       _playing = false;
       _state = "idle";
       ...
       _sections = null;           // ← 停止/完了時に毎回授業データが消える
       _currentSectionIndex = -1;
       ...
       SendPanelUpdate();
   }
   ```
   `reason` が `"completed"` / `"stopped"` / `"error"` のいずれでも同じ挙動。停止でキャンセルされた場合も同じパスを通る。

3. **`SendPanelUpdate()` の「未ロード」ブランチ**
   `win-native-app/WinNativeApp/Streaming/LessonPlayer.cs:366-381`
   `_sections == null` のとき `lesson_id=0, total_sections=0` を送る。コントロールパネル側 `updateLesson()` はこの条件（`!m.lesson_id && !total`）を **授業終了** と解釈して `_timelineState.sections = []` にリセットする（`win-native-app/WinNativeApp/control-panel.html:1080-1087`）。タイムラインから授業の骨格そのものが消える。

その結果、`CanPlay` は `_sections != null && !_playing` なので false、`_updateLessonButtons('idle')` で全ボタン disabled、タイムラインも空、という「授業消滅」状態になる。

### 欲しい挙動

- **■停止** を押すと **現在の再生を即停止**（音声・字幕・lipsync 含む）し、**授業データは保持**する。
- 停止後のコントロールパネル表示:
  - `state = "loaded"`、badge も `loaded`
  - タイムラインは残り、現在位置はセクション 1 の先頭に戻る
  - ▶再生 だけ enabled、⏸/■ は disabled
- ▶再生 を押すと **先頭から** 再生し直せる。
- 自然完了（最後まで再生しきった）でも同様に `state = "loaded"` に戻して再生できるようにする（一貫性のため。既存でも再生し直したいケースは同じ）。

## 設計方針

### 原則

「授業のロード」と「再生位置」を分離する。

| 概念 | 保持する場所 | ライフサイクル |
|------|-------------|---------------|
| 授業データ（`_sections`） | `LessonPlayer._sections` | `LoadLesson()` で設定、`LoadLesson()` で上書き。停止・完了では消さない |
| 再生位置 | `_currentSectionIndex` / `_currentDialogueIndex` / `_currentKind` / `_currentDialogues` | 停止・完了で -1 / null にリセット |
| 再生状態 | `_state` | `idle`（未ロード） → `loaded`（ロード済み非再生） → `playing` / `paused` → （停止・完了後） `loaded` |

停止で `idle` に戻すのではなく、**`loaded` に戻す**のがこの設計の中心。

### 状態遷移

```
         LoadLesson()
 idle ────────────────▶ loaded ─┬── PlayAsync() ──▶ playing ──┬── Pause()  ──▶ paused
                                │                             │
                                │                             └── Stop()/完了 ──┐
                                │                                                │
                                │                                          ┌────┘
                                │                         paused ── Resume()─▶ playing
                                │                                          │
                                └◀─────────────────── Stop()/完了 ─────────┘
                                     （loaded に戻る）

  LoadLesson()（別授業）で再度 loaded。データ解放したい場合は UnloadLesson（任意・本プランでは非スコープ）。
```

### idle は残すべきか

`idle`（授業未ロード）という状態は **起動直後〜最初の `LoadLesson` 前** でのみ必要。停止で `idle` に戻す意味はない（復帰にはサーバからの再送信が必要になり不便）。本プランでは `idle` は「起動時の初期値」および「将来 UnloadLesson を実装した場合の状態」として残す。停止・完了は全て `loaded` に行く。

### 再生完了時 (`reason == "completed"`) の扱い

完了時も `loaded` に戻す。同じ授業を再度流せる。
`lesson_complete` WebSocket イベントは従来通り broadcast する（broadcast.html が区別するため）。

### エラー時 (`reason == "error"`) の扱い

エラー時も `loaded` に戻す。リトライできるほうが便利。
エラーメッセージは Log.Error と PanelLog で出ているので、UI からも原因は追える。

### `lesson_complete` の `sections_played` との関係

従来の `sections_played = _currentSectionIndex + (reason == "completed" ? 1 : 0)` の計算は、`_currentSectionIndex` を -1 にリセットする前にやっているので変更不要。

### コントロールパネルの表示

現行の `updateLesson()` は `!m.lesson_id && !total` で「授業終了 → タイムラインクリア」と判定している。停止で `lesson_id` と `total_sections` が維持されれば、この分岐には入らず、タイムラインは残る。

ただし `section_index = -1` を受けた時の表示を確認する必要あり:
- 上部メタ行: `Section 0/N [type]` になる（`cur + 1 = 0`）→ 望ましくない
- タイムライン: `renderLessonTimeline()` が `currentSection = -1` をどう扱うか

→ メタ行表示は **「Section -/N」または空文字**、section type は 1 セクション目のものを仮表示、くらいが自然。細かいが、停止直後のプレビューとして **「まだ再生していない」** が伝わるのが良い。後述の実装ステップで対応。

## 実装ステップ

### Phase 1: `LessonPlayer.Stop()` / `PlayAsync()` finally の挙動変更

**ゴール**: 停止・完了で `_sections` を保持し、`_state = "loaded"` に戻す。再生位置だけリセットする。

**変更ファイル**: `win-native-app/WinNativeApp/Streaming/LessonPlayer.cs`

| 箇所 | 変更内容 |
|------|---------|
| `Stop()` 冒頭 `if (!_playing)` ブランチ（`:280-289`） | `_sections = null` を削除。`_state` は `_sections != null ? "loaded" : "idle"` に。再生位置を -1 / null にリセットしてから `SendPanelUpdate()` |
| `Stop()` の再生中ブランチ（`:291-299`） | ここは `_cts.Cancel()` → `PlayAsync()` の finally で state 更新が行われるので、**`_state = "idle"` の直接代入を削除**（finally で `loaded` に上書きされるように整合を取る）。ログと InjectJs は維持 |
| `PlayAsync()` finally（`:221-250`） | `_sections = null;` を削除。`_state = _sections != null && _sections.Count > 0 ? "loaded" : "idle";` に変更。`_currentSectionIndex = -1` / `_currentDialogueIndex = -1` / `_currentDialogues = null` / `_currentKind = "main"` はそのまま。`_totalDialogues = 0;` もここで明示的に 0 にしておく（停止後 `SendPanelUpdate` で `dialogues.Count` を使うが、`_sections` 経由なのでこれは表示用途のみ） |
| `SendPanelUpdate()` の未ロードブランチ（`:366-381`） | ロジック不変。`_sections == null` のとき（= 起動直後の `idle`）のみ `lesson_id=0` を送る |
| `SendPanelUpdate()` の通常ブランチ（`:383-399`） | `section_index = _currentSectionIndex` が -1 になる場合があるのを許容する（現状そのまま送れているので変更不要）|

**確認方法**:
- `dotnet build win-native-app/WinNativeApp/WinNativeApp.csproj` 成功
- ユニット相当の静的検査: `tests/test_native_app_patterns.py` に後述のテストを追加して `pytest` が通る

### Phase 2: コントロールパネルの停止後表示を整える

**ゴール**: `state=loaded` + `section_index=-1` を受けた時に、タイムライン・メタ行・ボタンがそれらしく見える。

**変更ファイル**: `win-native-app/WinNativeApp/control-panel.html`

| 箇所 | 変更内容 |
|------|---------|
| `updateLesson(m)` のメタ行更新（`:1063-1071`） | `cur < 0` のとき `Section -/N` ではなく `Section —/N` または空文字 + `[type]` を出さない。ここは「再生待ち」を伝える軽い表示にする（例: `Section ${total} 本 | 停止中` か、単に `dlgTotal` を 0 にして上部は非表示）。<br>実装としては `cur >= 0` のときのみ従来表示、それ以外は `Ready (${total} sections)` のような軽い文字列にする |
| `updateLesson(m)` のタイムライン状態更新（`:1074-1090`） | `state=loaded` で再生中でない場合、`_timelineState.viewSection` を 0 に戻す（autoFollow=true かつ `cur < 0` のケース）。既に `autoFollow && cur >= 0` の分岐があるが、`cur < 0 && total > 0` のときに `viewSection = 0` を設定する分岐を追加 |
| `_updateLessonButtons(state)`（`:870-902`） | 変更不要。`loaded` のケースが既に「▶再生 enabled、⏸/■ disabled」に対応している |

**確認方法**（実機）:
1. サーバから授業をロード → コントロールパネルに timeline 表示、`▶再生` のみ enabled
2. ▶再生 → 再生開始、badge=playing
3. ■停止 → badge=loaded、タイムラインは残り、viewSection=0、上部メタ行は「Ready (N sections)」などの停止中表示、▶再生 のみ enabled、⏸/■ disabled
4. ▶再生 を再度押す → 先頭から再生再開
5. 最後まで流しきる → 自然完了で `badge=loaded`、同様に再度 ▶再生 で頭から流せる

### Phase 3: 回帰テストの追加

**変更ファイル**: `tests/test_native_app_patterns.py`

| 追加テスト | 内容 |
|----------|------|
| `test_stop_preserves_sections` | `Streaming/LessonPlayer.cs` の `Stop()` 内に `_sections = null` を書いた行が存在しないこと（正規表現で `\b_sections\s*=\s*null` を `Stop()` のメソッド本体範囲で検出） |
| `test_play_async_finally_preserves_sections` | 同様に `PlayAsync()` の finally ブロック内で `_sections = null` が書かれていないこと |
| `test_stop_returns_to_loaded_state` | `Stop()` および `PlayAsync()` の終了時に `_state = "loaded"` を割り当てる行が存在すること。`_state = "idle"` のみで終わる経路がないこと |

静的なソース検査のため C# のビルド/実行は不要。`tests/test_native_app_patterns.py` の既存パターンを踏襲する。

**確認方法**: `python3 -m pytest tests/test_native_app_patterns.py -q` が通る

### Phase 4: ドキュメント更新

| ファイル | 変更 |
|---------|------|
| `DONE.md` | 「C#アプリ Lesson タブで停止した授業を再生し直せるように修正」を追加 |
| `TODO.md` | 該当行を削除 |
| `.claude/projects/-home-ubuntu-ai-twitch-cast/memory/` | LessonPlayer の状態遷移を記録するメモリがあれば更新（なければ不要）|

## 既存機能との関係

| 既存 | 本プランでの扱い |
|------|----------------|
| `LoadLesson()` 内の `if (_playing) Stop();` | そのまま。新 `Stop()` は `_sections` を残すが、直後に `LoadLesson()` が `_sections = new List<SectionData>()` で上書きするので問題ない |
| サーバ `src/lesson_runner.py` | 変更なし。`lesson_load` → C# 側で loaded → control-panel の ▶ で再生開始、という既存フローを維持 |
| HTTP/WebSocket `lesson_stop` エンドポイント（`Server/HttpServer.cs:727-733`）| そのまま。`LessonPlayer.Stop()` を呼ぶだけなので新挙動がそのまま反映される |
| broadcast.html の `lesson_complete` ハンドラ | 変更なし。イベント送信は維持 |
| WebSocket `lesson` push の購読側（control-panel 以外）| `state=loaded` が停止後にも来るようになる。broadcast.html がこれを誤解釈しないか要確認（`updateLesson` 相当がある場合）|

## リスク

| リスク | 影響 | 対策 |
|--------|------|------|
| 停止後のメモリ解放 | `_sections` に TTS WAV を含む大きなバイト列を保持し続けるため、長時間アプリを起動しっぱなしだとメモリ使用量が積む | 現状でも「ロード済みの授業が次のロードまで残る」状態は発生する（LoadLesson で上書きされるまで）。停止で特別にメモリ解放したいケースは将来 UnloadLesson を追加する。**本プランでは非スコープ** |
| broadcast.html が `state=loaded` を誤解釈 | 配信画面の授業表示がおかしくなる | broadcast.html の Lesson 関連ハンドラを事前に確認する（Phase 1 冒頭）。変更が必要なら Phase 1 のスコープに含める |
| 停止直後の `section_index=-1` を旧コードで参照している箇所 | 停止後一瞬だけ変な表示になる | C# 側のサイドバー・配信画面・コントロールパネルそれぞれで `section_index < 0` の扱いを確認し、必要なら「セクション 1/N の先頭」に相当する表示に寄せる（Phase 2 で対応） |
| 停止直後に ▶再生 を連打した時の多重再生 | `PlayAsync()` 二重起動で例外 | 既存の多重クリック防止（`$('lessonPlayBtn').disabled = true` を送信直後に適用）と、`PlayAsync` 冒頭の `if (_playing) throw` で防御済み |
| `_wait_lesson_complete`（サーバ側）のタイムアウト | 停止で `lesson_complete` は broadcast されるので従来通り解決される | 変更不要 |
| 自然完了後 `_sections` を残しても、次の `lesson_load` で正常に上書きされるか | `LoadLesson` 冒頭で `_sections = new List<SectionData>();` しているので問題なし | 既存動作で確認済み |

## 関連プラン

- [control-panel-lesson-buttons.md](control-panel-lesson-buttons.md) — Lesson タブに再生/一時停止/停止ボタンを追加（完了）。本プランはその続きで「停止した後も再生できる」状態を実現する
- [client-driven-lesson.md](client-driven-lesson.md) — LessonPlayer が全セクションをメモリに持つ前提設計

## 参考箇所

- `Stop()` 現行実装: `win-native-app/WinNativeApp/Streaming/LessonPlayer.cs:280-300`
- `PlayAsync()` finally: `win-native-app/WinNativeApp/Streaming/LessonPlayer.cs:221-250`
- `SendPanelUpdate()`: `win-native-app/WinNativeApp/Streaming/LessonPlayer.cs:361-399`
- `updateLesson(m)` (control-panel): `win-native-app/WinNativeApp/control-panel.html:1052-1094`
- 「授業終了判定」による outline クリア: `win-native-app/WinNativeApp/control-panel.html:1080-1087`
- 再生ボタンの有効/無効: `win-native-app/WinNativeApp/control-panel.html:870-902`
- パネル → C# のアクション分岐: `win-native-app/WinNativeApp/MainForm.cs:351-360`, `526-564`
