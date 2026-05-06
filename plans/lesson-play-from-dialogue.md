---
ステータス: 提案
作成日: 2026-05-06
更新日: 2026-05-06（仕様変更: dialogue ▶ は「クリックした 1 メッセージだけ再生」に修正。後続 dialogue / 待機 / 後続セクションは再生しない試聴用途）
関連TODO: 「セクションの途中の会話から再生できるように。クライアントアプリのlessonタブの会話一覧からクリックすると再生できる」
---

# 授業 — セクション途中の会話（dialogue）から再生する

## 1. 目的

クライアントアプリ（`win-native-app/` のコントロールパネル）の **Lesson タブ → 会話一覧** で、任意の dialogue 行をクリックすると、その dialogue から授業を再生開始できるようにする。現在は「セクション単位」（▶ ここから再生）までしか開始位置を指定できない。

## 2. 既存実装の把握

### 2.1 再生フローと権威ソース

C# 側 `LessonPlayer` が **再生位置の唯一の権威ソース**。Python は授業データ（セクション・dialogue・TTS wav）を C# に渡すだけで、再生中の進行は C# が握る。

コントロールパネル（`control-panel.html`）の再生ボタンは Python を経由しない。送信は `send()` 関数（`control-panel.html:730`）の `wv.postMessage(msg)` で、これは **WebView2 の host messaging**（WebSocket ではない）。受信は C# 側 `MainForm.OnPanelMessage`（`MainForm.cs:312`）→ `HandlePanelLessonPlay`（`MainForm.cs:619-662`）の経路。

`HttpServer` 側 `/ws/control` の `HandleWsLessonPlay`（`HttpServer.cs:828-847`）は **外部 WS クライアント向け**（Python 等が使う想定の経路）であり、コントロールパネル経由の再生はここを通らない。本タスクでは MainForm 側を主役として扱い、HttpServer 側は「外部クライアントとの整合のため任意で揃える」位置づけ。

### 2.2 セクション単位の開始は既に実装済み

`win-native-app/WinNativeApp/Streaming/LessonPlayer.cs:177-266` の `PlayAsync(int startIndex = 0)` は **section 単位の開始** をすでにサポートしている。

```csharp
public async Task PlayAsync(int startIndex = 0)
{
    ...
    for (int i = startIndex; i < _sections.Count; i++) {
        _currentSectionIndex = i;
        _currentDialogueIndex = -1;
        ...
        await PlaySectionInternalAsync(_sections[i], _cts.Token);
    }
}
```

その内部 `PlaySectionInternalAsync`（`LessonPlayer.cs:441-481`）はセクションを次の順で再生する:

1. `showText(section.DisplayText, section.SectionType)` で教材テキスト表示
2. `PlayDialoguesAsync(section.Dialogues, "main", ct)` でメインdialogue再生
3. `question` セクションなら、`section.Question.WaitSeconds` 待機 → `PlayDialoguesAsync(section.Question.AnswerDialogues, "answer", ct)`
4. `hideText()` → セクション間 `WaitSeconds` 待機

`PlayDialoguesAsync`（`LessonPlayer.cs:483-538`）は **常に `for (int i = 0; i < dialogues.Count; i++)`** で先頭から再生しており、ここに開始オフセットの概念がない。

### 2.3 再生コマンドのハンドラ（2系統）

#### 2.3.1 コントロールパネル経由（主役）

`win-native-app/WinNativeApp/MainForm.cs:619-662` の `HandlePanelLessonPlay`:

```csharp
int? startIndex = null;
if (msg.TryGetProperty("section_index", out var si) && si.ValueKind == JsonValueKind.Number)
    startIndex = si.GetInt32();

// Resume 分岐: section_index 未指定で paused のときのみ Resume
if (startIndex == null && player.IsPlaying && player.IsPaused)
{
    player.Resume();
    return;
}
...
var idx = startIndex ?? 0;
_ = Task.Run(async () => { try { await player.PlayAsync(idx); } catch { ... } });
```

→ ここが本タスクで dialogue_index / kind を受け取る本命の地点。**Resume 分岐の発火条件**は新パラメータ追加時に「3つすべて未指定」に拡張する必要がある（後述 §3.6）。

#### 2.3.2 外部 WS クライアント経由（オプション）

`win-native-app/WinNativeApp/Server/HttpServer.cs:828-847` の `HandleWsLessonPlay`:

```csharp
int startIndex = 0;
if (msg.TryGetProperty("section_index", out var si) && si.ValueKind == JsonValueKind.Number)
    startIndex = si.GetInt32();
_ = Task.Run(async () => { await LessonPlayer.PlayAsync(startIndex); });
return new { ok = true, section_index = startIndex };
```

→ こちらは Resume 分岐を持たず、純粋に section_index で開始する。本タスクでは外部クライアントとの整合のため任意で揃える（必須ではない）。

### 2.4 コントロールパネル UI

`win-native-app/WinNativeApp/control-panel.html`:

- `playLessonFromSection(idx, btn)` (1065-1069): WSに `{action:'lesson_play', section_index: idx}` を送る
- `_renderDialogueGroup(listEl, dialogues, kind, isCurrentSection, ...)` (1094-1145): 各 dialogue を `.ld-row` として描画。`kind` は `'main'` / `'answer'`
- セクションタブに ▶ ボタン (1184-1195): `state==='loaded'` のときだけ enable

→ **dialogue 行ごとに ▶ ボタンを足す UI 拡張は容易**。`kind` も既に各行が持っているのでそのまま渡せる。

### 2.5 Python 側

`scripts/routes/teacher.py:1047-1067` の `POST /api/lessons/{id}/start` と `src/lesson_runner.py:437` の `start()` も section 単位の開始のみ。**ただし今回のクリック導線は C# WS 直結のため、Python に変更は不要**（管理画面 UI からの再生開始も dialogue 単位を欲しがるか？ → 現状はセクション単位ですら無いので、本タスクでは Python は触らない）。

## 3. 設計方針

### 3.1 オフセットの表現

開始位置を **3 タプル** で表現する:

- `section_index: int`（必須・既存）
- `dialogue_index: int = 0`（その section 内での 0-始まり dialogue 位置。新規）
- `kind: "main" | "answer" = "main"`（main / answer のどちらから再生開始するか。新規）

`question` セクションでは「メインの問いかけ」と「回答」の 2 グループがあるため、`kind` を指定しないと `dialogue_index = 0` だけでは曖昧（main の 0 番目か answer の 0 番目か）になる。

### 3.2 振る舞い

`PlayAsync(startSection, startDialogueIndex = 0, startKind = "main")` を呼んだとき:

- `startSection` 未満のセクションはスキップ（既存挙動どおり）
- `startSection` のセクションを再生するが、**最初のセクションだけは特別扱い**:
  - **`startKind = "main"`**: `showText` → main dialogues を `startDialogueIndex` から再生 → questionなら待機 → answer 再生 → 後続セクションは通常通り
  - **`startKind = "answer"`**: `showText` → main をスキップ → 待機もスキップ → answer dialogues を `startDialogueIndex` から再生 → 後続セクションは通常通り
- 2 番目以降のセクションは offset を引き継がない（先頭から再生）

`showText` の DisplayText 表示は **両方の kind で必須**。アバターの背景となる教材テキストが消えるのは違和感が大きい。

### 3.3 既存の `for` ループの扱い

`PlaySectionInternalAsync` と `PlayDialoguesAsync` を **必要最小限の引数追加で改造する**。完全に別関数に分けると DRY が崩れるので、既定値付きパラメータでオーバーロード相当にする。

```csharp
// PlaySectionInternalAsync(section, ct, startDialogueIndex = 0, startKind = "main")
// PlayDialoguesAsync(dialogues, kind, ct, startIndex = 0)
```

呼び出し側:

```csharp
for (int i = startSection; i < _sections.Count; i++) {
    int dlgOffset = (i == startSection) ? startDialogueIndex : 0;
    string kindOffset = (i == startSection) ? startKind : "main";
    await PlaySectionInternalAsync(_sections[i], _cts.Token, dlgOffset, kindOffset);
}
```

### 3.4 UI 配置

`_renderDialogueGroup` の **メイン行（`.ld-row`）の右端のみ** に ▶ ボタンを追加。同関数が生成する **TTS サブ行（`.ld-row.ld-tts`、1128-1143行目）には ▶ を付けない**（同じ dialogue を再生するだけなので冗長）。条件は section タブの ▶ と同じ（`_timelineState.state === 'loaded'` のときだけ enable）。

クリックハンドラは:

```js
playFrom.addEventListener('click', (ev) => {
    ev.stopPropagation();  // 既存タブ ▶ と同じ防御。将来 .ld-row にクリックハンドラが付いても巻き込まれない
    if (playFrom.disabled) return;
    send({action:'lesson_play', section_index: viewSection, dialogue_index: i, kind: kind});
});
```

- **section インデックス** は `_renderDialogueGroup` の引数 `viewSection`（最後の引数。1094行目シグネチャ参照）をそのまま使う
- **`kind`** は同関数の引数 `kind`（`'main'` / `'answer'`）
- **`i`** は `dialogues.forEach((dlg, i) => ...)` の index

### 3.5 入力バリデーション

C# 側 `PlayAsync` 入口で:

- `startDialogueIndex < 0` → エラー
- `startKind` が `"main"` / `"answer"` 以外 → エラー
- `startKind = "main"` で `startDialogueIndex >= section.Dialogues.Count` → エラー
- `startKind = "answer"` で **section.SectionType が `"question"` 以外、または section.Question == null** → エラー（実コード `LessonPlayer.cs:460` の判定と整合させる）
- `startKind = "answer"` で `startDialogueIndex >= section.Question.AnswerDialogues.Count` → エラー

エラー時の応答:
- `HandlePanelLessonPlay`（MainForm）では既存パターンに従い `PanelLog($"...", "error")` でパネルにエラー表示し、`PlayAsync` を呼ばない
- `HandleWsLessonPlay`（HttpServer、揃える場合）は `{ok:false, error:"..."}` を返す（既存パターン）

### 3.6 Resume 分岐の発火条件（重要）

`HandlePanelLessonPlay`（MainForm.cs:638-643）には既存の Resume 分岐がある:

```csharp
if (startIndex == null && player.IsPlaying && player.IsPaused) {
    player.Resume();
    return;
}
```

新パラメータ `dialogue_index` / `kind` を導入したとき、この発火条件は **`section_index`・`dialogue_index`・`kind` の3つすべてが未指定** に拡張する。dialogue 単位の途中再生は明示的な開始位置指定なので、絶対に Resume には流さない（paused 中の dialogue ▶ は disabled で押せないため UI 側でもブロックされるが、サーバ側でも防御）。

```csharp
bool hasOffset = startIndex.HasValue
                 || msg.TryGetProperty("dialogue_index", out _)
                 || msg.TryGetProperty("kind", out _);
if (!hasOffset && player.IsPlaying && player.IsPaused) {
    player.Resume();
    return;
}
```

## 4. 実装ステップ

### Step 1: C# 再生エンジン拡張

**ファイル**: `win-native-app/WinNativeApp/Streaming/LessonPlayer.cs`

1. `PlayAsync` に `int startDialogueIndex = 0, string startKind = "main"` を追加（177行目シグネチャ）
2. 入力バリデーション追加（181-183行目の startIndex バリデーションの直後）:
   - `startKind` が `"main"` / `"answer"` 以外なら ArgumentException
   - その他 §3.5 の項目
3. メインループで section ごとにオフセットを計算（195行目の for ループを §3.3 のとおり改造）
4. `PlaySectionInternalAsync(section, ct, int startDialogueIndex = 0, string startKind = "main")` のシグネチャを拡張（441行目）
   - `startKind == "main"` の場合: `PlayDialoguesAsync(section.Dialogues, "main", ct, startIndex: startDialogueIndex)`
   - `startKind == "answer"` の場合: main 再生と question 待機をスキップ、`PlayDialoguesAsync(section.Question.AnswerDialogues, "answer", ct, startIndex: startDialogueIndex)`
   - **いずれの場合も `showText` は実行**（DisplayText 表示は維持）
5. `PlayDialoguesAsync(..., int startIndex = 0)` のループ開始を `for (int i = startIndex; i < dialogues.Count; i++)`（489行目）

### Step 2: C# 再生コマンドハンドラ拡張

#### Step 2-A: コントロールパネル経由（必須）

**ファイル**: `win-native-app/WinNativeApp/MainForm.cs`

1. `HandlePanelLessonPlay`（619-662行目）で `dialogue_index` / `kind` を抽出
2. **Resume 分岐の条件を §3.6 のとおり拡張**（3つすべて未指定のときのみ Resume）
3. `player.PlayAsync(idx, dialogueIndex, kind)` に渡す
4. バリデーション例外（`ArgumentOutOfRangeException` / `ArgumentException`）は既存パターンに合わせて `BeginInvoke(() => PanelLog(...))` でパネルにエラー表示

#### Step 2-B: 外部 WS クライアント経由（任意・整合用）

**ファイル**: `win-native-app/WinNativeApp/Server/HttpServer.cs`

1. `HandleWsLessonPlay`（828-847行目）で `dialogue_index` / `kind` を抽出
2. `LessonPlayer.PlayAsync(startIndex, dialogueIndex, kind)` に渡す
3. 戻り値に `dialogue_index`, `kind` を含める
4. 入力バリデーション失敗時は `{ok:false, error:"..."}` を返す（既存パターン）

※ 現状 Python 側から `lesson_play` は送っていないため Step 2-B はスキップしても動作する。**実装するなら API 不整合を残さないため両方やる**のが望ましい。

### Step 3: コントロールパネル UI

**ファイル**: `win-native-app/WinNativeApp/control-panel.html`

1. `_renderDialogueGroup` (1094-1145) の **メイン行（`.ld-row`）にだけ** ▶ ボタンを追加（TTS サブ行 `.ld-row.ld-tts` には付けない）
   - 既存 `.ld-tab-play` と同じスタイルを再利用（CSS は `.ld-row-play` として新規追加、もしくは `.ld-tab-play` を共用）
   - `_timelineState.state === 'loaded'` のときだけ enable（`renderLessonTimeline` 冒頭の `canPlayFromSection` フラグを流用してよい）
   - クリックハンドラ:
     ```js
     playFrom.addEventListener('click', (ev) => {
         ev.stopPropagation();
         if (playFrom.disabled) return;
         playLessonFromDialogue(viewSection, i, kind, playFrom);
     });
     ```
   - `viewSection` は `_renderDialogueGroup` の引数（最後の引数）
2. `playLessonFromDialogue(sectionIdx, dialogueIdx, kind, btn)` という小さなヘルパを `playLessonFromSection`（1065-1069）の隣に追加:
     ```js
     function playLessonFromDialogue(sectionIdx, dialogueIdx, kind, btn) {
         if (btn) btn.disabled = true;
         send({action:'lesson_play', section_index: sectionIdx, dialogue_index: dialogueIdx, kind});
     }
     ```
3. CSS: `.ld-row-play` を `.ld-tab-play`（413-435行目）と揃える形で追加（`.ld-row` 内で `flex` 末尾の小さな ▶ ボタン。既存 `.ld-row` は `display: flex` なので `margin-left: auto` で右寄せ）

### Step 4: 動作確認

1. `dotnet build` (win-native-app) が通ること
2. 配信アプリ起動 → 授業ロード → コントロールパネルで Lesson タブを開く
3. **section ▶**: 既存挙動のリグレッションが無いことを確認
4. **main 中盤の dialogue ▶**: 該当 dialogue から再生開始 → 後続 dialogue → セクション末尾まで → 次セクション
5. **answer 先頭の dialogue ▶**（question セクションで）: main をスキップ → 待機なしで answer 開始
6. **answer 中盤の dialogue ▶**: answer の途中から再生
7. **playing 中の ▶ クリック**: `CanPlay = false` で disabled になっているはず（既存パターン）→ 押せないこと
8. **broadcast.html 側の表示**:
   - `lesson_status` イベント（C# → Python → broadcast.html）の `current_index` が正しい
   - 進捗パネル（`#lesson-progress-panel`）の現在セクションハイライトが追従する

### Step 5: ドキュメント更新

1. `DONE.md` に変更内容を追記
2. `TODO.md` から該当行を削除
3. このプランの `ステータス: 完了` に変更

## 5. リスク・注意点

### 5.1 「途中再生」と「進捗表示」の整合性

`broadcast.html` 側の進捗パネル（`#lesson-progress-panel`）はセクション単位でハイライトする。dialogue 単位の途中再生では、ハイライトは「再生開始したセクション」に即座に乗るべき → C# の `BroadcastEvent(lesson_status)` は **セクションループ突入時に発火**（既存195-218行目）しているので追加実装不要。

ただし、`lesson_status` の payload に `dialogue_index` / `kind` を含めて broadcast.html 側で使えるようにするかは別検討（本タスクのスコープ外。現状 `current_index` だけで十分）。

### 5.2 TTS pre-generation との関係

授業再生前に Python 側で全 dialogue の TTS wav を事前生成済み。途中再生でも、開始 dialogue 以降の wav は既に存在するため特別な対応不要。`PlaySectionInternalAsync` 内の `PlayAudio` は `dlg.WavData` を渡すだけで、その dialogue の wav を読み出す。

### 5.3 question セクションの `WaitSeconds` スキップ

`startKind = "answer"` で開始した場合、main 再生と質問待機（`section.Question.WaitSeconds`）をスキップする。これは「ユーザーが意図的に answer から再生したい」ケース（試聴・微調整用途）を想定しているため、待機を入れずに即座に answer に入る方が自然。仕様として明文化する。

### 5.4 後続セクションの先頭再生

`startSection` 以降のセクションは offset を引き継がず先頭から再生する。これは仕様。「セクション 2 の dialogue 5 から開始 → セクション 2 末尾 → セクション 3 の先頭から」 という動きになる。

### 5.5 状態遷移

`_state == "loaded"` のときだけ ▶ を有効にする（既存セクション ▶ と同条件）。`playing` / `paused` 中は disabled。これは「途中で別の dialogue にジャンプしたい」要件には応えていないが、現状の停止 → 再生開始のフローで十分（セクション ▶ も同じ制約）。

### 5.7 Resume 分岐との混同リスク

`HandlePanelLessonPlay` には既存の Resume 分岐があり、`section_index` 未指定時は paused 状態を Resume する。新パラメータ追加時、**`dialogue_index` / `kind` のどちらかが指定された時点で Resume 分岐に入らない**ようガードする必要がある（§3.6 参照）。UI 側でも `state === 'loaded'` 限定の enable で防御しているが、外部 WS や手動 JSON 送信時のフェイルセーフとしてサーバ側でも条件を厳密に書く。

### 5.6 Python 側の管理画面 UI

管理画面（ブラウザ）から授業を再生する `POST /api/lessons/{id}/start` 経由のフローでは、現状 dialogue 単位の指定は無い。本タスクでは触らないが、将来「管理画面の dialogue 一覧からも ▶ できる」を追加する場合は別タスク。

## 6. 受け入れ基準

- [ ] コントロールパネルの Lesson タブ → 各 dialogue **メイン行**の右端に ▶ ボタンが出る（TTS サブ行には付かない）
- [ ] `_timelineState.state === 'loaded'` のときだけ ▶ が押せる（playing / paused では disabled）
- [ ] section の main dialogue 中盤の ▶ → 該当 dialogue から再生 → 後続 → 次セクション
- [ ] question セクションの answer dialogue 中盤の ▶ → main / 待機をスキップ → answer 中盤から再生
- [ ] 不正な offset（範囲外、kindと整合しない section など）は MainForm 側で `PanelLog(..., "error")` 表示、HttpServer 側（揃えた場合）は `{ok:false, error}` を返し、いずれもクラッシュしない
- [ ] **paused 状態で `lesson_play` に `dialogue_index` / `kind` を含めて送ると Resume されず、明示開始位置で再生される**（Resume 分岐の混入なし）
- [ ] **既存の `lesson_play`（引数なし）の Resume 分岐挙動は変わらない**
- [ ] 既存のセクション ▶（▶ ここから再生）にリグレッションが無い
- [ ] `tests/test_broadcast_patterns.py` および C# の既存テスト（あれば）が green
