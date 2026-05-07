---
ステータス: 完了（実装のみ。Windows実機での試聴確認は要オペレーター）
作成日: 2026-05-07
完了日: 2026-05-07
関連TODO: 「C#アプリのセリフ毎に再生（dialogue 単位試聴）後、Lesson タブが第一セクションに戻ってしまう」
---

# 授業 — dialogue 単位試聴後にタブが第一セクションへ戻る問題の修正

## 1. 症状

コントロールパネル（`win-native-app/.../control-panel.html`）の Lesson タブで、dialogue 行の ▶ ボタン（single 再生）をクリックすると、その dialogue が属するセクションタブが選択された状態で 1 件だけ再生される。**しかし再生終了直後に、タブ表示が強制的に第一セクション（index 0）に戻ってしまう。**

ユーザーが今レビューしていた dialogue の続きを確認しようとしても、タブが先頭に戻るので毎回ナビゲートし直す必要があり、試聴フローが分断される。

通常再生の終了・停止でも同じ挙動になっている（こちらは従来「停止直後はセクション 1 をプレビュー」という意図的設計だが、dialogue 試聴のケースでは明らかに不便）。

## 2. 原因

C# 側 `LessonPlayer.PlayAsync` の `finally` ブロックで再生位置を完全にリセットしており、それを受けたパネルがタブを 0 に戻している。

### 2.1 C# 側（`win-native-app/WinNativeApp/Streaming/LessonPlayer.cs:401-431`）

```csharp
finally
{
    _playing = false;
    _cts = null;

    // 授業全体の完了通知
    if (BroadcastEvent != null) { ... lesson_complete を送る ... }

    // 授業データは保持したまま再生位置だけリセットし、loaded に戻す
    _currentSectionIndex = -1;     // ← ここで -1 に
    _currentDialogueIndex = -1;
    _currentDialogues = null;
    _currentKind = "main";
    _totalDialogues = 0;
    _state = (_sections != null && _sections.Count > 0) ? "loaded" : "idle";

    SendPanelUpdate();   // → section_index = -1, state = "loaded" がパネルに飛ぶ
}
```

`single = true` の試聴でも、通常再生でも、この finally を必ず通る。

### 2.2 パネル側（`control-panel.html:1326-1331`）

```js
} else if (_timelineState.autoFollow && cur >= 0) {
    _timelineState.viewSection = cur;
} else if (_timelineState.autoFollow && cur < 0 && total > 0) {
    // 停止直後・ロード直後はセクション 1 をプレビュー表示
    _timelineState.viewSection = 0;   // ← ここで第一セクションに戻る
}
```

`cur = -1`（C# からの section_index）+ `autoFollow = true` + `total > 0` の3条件で、**毎回**セクション 0 に戻している。dialogue 試聴の場合も例外なく当てはまる。

### 2.3 流れまとめ

1. ユーザーが dialogue 行 ▶ をクリック
2. `lesson_play` `{section_index: N, dialogue_index: K, kind, single: true}` を C# へ送信
3. C# `PlayAsync(N, K, kind, single=true)`: `_currentSectionIndex = N` でパネル `viewSection = N`
4. dialogue 1 件再生完了
5. C# `finally`: `_currentSectionIndex = -1` → `SendPanelUpdate()`
6. パネル `updateLesson(m)`: `cur = -1` → `viewSection = 0`（**バグ**）

## 3. 修正方針

**パネル側で「playing/paused → loaded への遷移」では `viewSection` を維持する。** `setLessonOutline()` 受信時点ですでに `viewSection = 0` がセットされるので、「ロード直後の初期プレビューはセクション 1」という挙動はそのまま担保できる。

具体的には `control-panel.html:1328-1331` を以下に置き換える:

```js
} else if (_timelineState.autoFollow && cur < 0 && total > 0) {
    // viewSection 未設定時のみセクション 1 をプレビュー。
    // 再生終了・dialogue 試聴後・停止後はユーザーが見ていたタブを維持する
    // （第一セクションに勝手に戻らないようにする）
    if (_timelineState.viewSection < 0) {
        _timelineState.viewSection = 0;
    }
}
```

### 3.1 なぜ C# 側ではなくパネル側を直すか

- C# 側 `_currentSectionIndex = -1` は「次に Play ボタン（引数なし）を押したら先頭から再生する」という再生位置リセットの意味も持つ。これを変えると「Play で先頭から開始」というデフォルト挙動が崩れる
- 「再生位置の権威ソースは C#」という設計（`plans/lesson-play-from-dialogue.md` §2.1）は維持したい。`-1` リセット自体は C# として正しい。**問題は「再生位置が -1」を「タブ表示を 0 に強制」と解釈しているパネル側のロジック**

### 3.2 副作用の検討

| ケース | 修正前 | 修正後 |
|---|---|---|
| 授業ロード直後 | viewSection = 0（initial preview） | 同左（`setLessonOutline` で 0 がセットされる） |
| dialogue 試聴後（single） | viewSection = 0 に戻る（バグ） | 試聴したセクションのまま留まる |
| 通常再生 完走後 | viewSection = 0 に戻る | 最後に再生していたセクションのまま留まる |
| 停止ボタン押下 | viewSection = 0 に戻る | 直前のタブのまま留まる |
| 授業アンロード（lesson_id=0 & total=0） | viewSection = -1 にクリア | 同左（`!m.lesson_id && !total` 分岐で別処理） |

通常再生 完走後と停止後の挙動が変わるが、ユーザーが見ていたタブが勝手に先頭に飛ぶよりも、留まる方が自然と判断する（停止後にユーザーが Play を押せば C# 側は idx=0 から再生されるので、再生開始位置とタブ位置は分離されている）。

## 4. 実装ステップ

### Step 1: コントロールパネルの修正

**ファイル**: `win-native-app/WinNativeApp/control-panel.html`

1. `updateLesson()` 内の `cur < 0 && total > 0` 分岐（`control-panel.html:1328-1331`）を上記コードに置き換え
2. コメントを「viewSection 未設定時のみ初期プレビュー」へ更新

### Step 2: 動作確認（要 Windows ビルド）

1. `dotnet build` （`win-native-app/`）が通ること
2. 配信アプリ起動 → 授業ロード（コントロールパネルで Lesson タブを開く）
3. **初期プレビュー**: ロード直後にセクション 1 タブが表示されること（既存挙動）
4. **dialogue 試聴（single）**:
   - セクション 3 の中盤の dialogue ▶ をクリック → 1 件再生
   - **再生終了後もセクション 3 のタブが維持されていること**
   - 続けて同セクションの別 dialogue ▶ がスムーズに押せること
5. **通常再生**: セクション 3 ▶（▶ ここから再生）でセクション 3 から最後まで再生 → 完走後 セクション最後のタブが維持されていること
6. **停止ボタン**: 再生中に Stop → 直前のタブのまま留まること
7. **手動タブ切替 + autoFollow OFF**: タブを手動でセクション 5 に移してから、別セクションの再生を行う場合の挙動が壊れていないこと（autoFollow が false ならそもそも 1326-1331 の分岐に入らない or `viewSection` が手動選択のまま）
8. **授業アンロード**: 別の授業をロードした際にタブ初期化が正しく走ること（`!m.lesson_id && !total` 分岐に入って `viewSection = -1` 後、新 `setLessonOutline` で 0 にセット）

### Step 3: ドキュメント更新

1. このプラン `ステータス: 完了` に変更
2. `DONE.md` に変更内容を追記
3. `TODO.md` から該当行を削除

## 5. リスク・注意点

### 5.1 `autoFollow = false` 時の挙動

`autoFollow` は `_setAutoFollow(false)` で OFF になる（手動でタブを選んだとき等）。OFF のときは 1326-1331 の autoFollow 分岐に入らないので、本修正の影響はない。

### 5.2 `lesson_complete` イベント

C# 側は `lesson_complete` を `BroadcastEvent` 経由で broadcast.html 向けに送っている。コントロールパネルは `NotifyPanel`（`type: "lesson"`）のみを購読しているので、`lesson_complete` 自体はパネルでは扱わない。本修正でも触らない。

### 5.3 既存テスト

C# テストは無い。Python 側の `test_*` は今回の変更に関与しない（変更は `control-panel.html` のみ）。`tests/test_native_app_patterns.py` がソース解析でガードしているパターンに該当しないか念のため確認する。

## 6. 受け入れ基準

- [ ] dialogue 行 ▶（single 再生）後、再生していたセクションのタブが維持される
- [ ] 通常再生の完走後、最後に再生していたセクションのタブが維持される
- [ ] Stop ボタン押下後、直前のタブが維持される
- [ ] 授業ロード直後はセクション 1 のタブがプレビュー表示される（既存挙動の維持）
- [ ] 別の授業をロードしたときにタブが正しく初期化される
- [ ] `autoFollow` OFF 時の手動タブ選択が壊れない
