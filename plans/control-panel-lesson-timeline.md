# C#コントロールパネル Lesson タブを授業タイムラインに差し替え

## ステータス: 未着手

## 背景と動機

### 現状

`win-native-app/WinNativeApp/control-panel.html` の Lesson タブには、以下が並んでいる:

- `lessonBadge`（idle/loaded/playing/paused 表示）
- `lessonId`（#123 表示）
- `lessonSectionBar`（セクションセル一列のプログレスバー）
- `lessonProgress`（`Section 2/8 [question] Dialogue 3/5` のテキスト）
- `lessonDisplayText`（`display_text` の板書）
- `lessonCurrentSpeech`（再生中 dialogue の speaker + content）
- `lessonDialogueList`（**現在セクションの dialogue のみ**、past/current クラスで色分け）

データは `LessonPlayer.SendPanelUpdate()` → `NotifyPanel(new { type = "lesson", ... })` 経由で受信しており、**現在セクション分しか届いていない**。

### 既に broadcast.html には本格的なタイムラインがある

同じ情報ソース（`LessonPlayer._sections`）から InjectJs 経由で `window.lesson.setOutline(outline)` と `window.lesson.startDialogue({sectionIndex, dialogueIndex, kind})` を受け取り、`static/js/broadcast/lesson.js` + `panels.js` が次の機能を持つタイムラインを描画している:

- 全セクションのタブ一覧（`▶`/`✓`/active 状態）
- 選択セクションの dialogue 一覧（past/current/future の3状態）
- 回答（`question.answer_dialogues`）を `— 回答 —` ヘッダ付きで別グループ表示
- 自動追従（currentSection が変わると表示セクションも追従） + 手動選択時は5秒で復帰
- 現在行への自動スクロール

C# コントロールパネルにも同じ情報があれば、配信を見ていなくても進行全体が一目で追える。

### 欲しい形

コントロールパネルの Lesson タブを **broadcast.html の `lesson-dialogues-panel` と同等のタイムライン UI** に差し替える。旧 UI（badge/section-bar/progress/display-text/current-speech/dialogue-list）はすべて置き換える（一部は上部メタ情報として残すか、完全撤廃するかは Phase 2 で決定）。

TODO.md に別行で書かれている「配信画面の `lesson-dialogues-panel`（授業タイムライン）相当を C# サイドバーの Lesson タブに表示（既存のバッジ/セクションバー/dialogue list は置き換え）」は、本プランと同一のタスク。統合する。

## 設計方針

| 項目 | 方針 |
|------|------|
| データ供給 | 既存 `BroadcastOutline()`（broadcast.html向け InjectJs）と対をなす、`NotifyPanel` 経由の `type: "lesson_outline"` を追加。LoadLesson 時に全セクションを1回送る |
| 状態更新 | 既存 `type: "lesson"` メッセージに `kind`（"main"/"answer"）を追加する。`section_index` / `dialogue_index` / `total_sections` は既に含まれている |
| 描画 | コントロールパネル側の `updateLesson` を全面書き換え。broadcast.html の `renderLessonDialogues` と同じロジックを HTML/JS で実装（ただしパネル編集・transitionは不要） |
| スタイル | broadcast.css の `.ld-*` 相当を control-panel.html 内 `<style>` に移植。vw → px（コントロールパネルは固定サイズ） |
| 自動追従 | broadcast と同じ方針（currentSection に追従、手動選択後5秒で復帰）。control-panel で他タブに隠れている時は状態保持のみ |

### なぜ WebSocket ではなく NotifyPanel を使うか

コントロールパネルは WebView2 から `window.chrome.webview.postMessage` で C# と通信している。broadcast.html 側が `lesson_outline` を WS で受けていないのと同じく（InjectJs 経由）、コントロールパネル側も NotifyPanel 経由が一貫する。WS への依存を増やさない。

## データフォーマット

### `type: "lesson_outline"`（新規・NotifyPanel 経由）

`LoadLesson` 完了時に1回発火:

```jsonc
{
  "type": "lesson_outline",
  "lesson_id": 123,
  "total_sections": 8,
  "sections": [
    {
      "section_index": 0,
      "section_type": "introduction",
      "display_text": "Today's Topic: Greetings",
      "dialogues": [
        { "index": 0, "kind": "main", "speaker": "teacher", "content": "こんにちは…", "emotion": "joy" },
        { "index": 1, "kind": "main", "speaker": "student", "content": "お願いします！", "emotion": "excited" }
      ],
      "question": null
    },
    {
      "section_index": 1,
      "section_type": "question",
      "display_text": "",
      "dialogues": [ /* 問題文 */ ],
      "question": {
        "answer_dialogues": [
          { "index": 0, "kind": "answer", "speaker": "teacher", "content": "Hello!", "emotion": "joy" }
        ]
      }
    }
  ]
}
```

※ `avatarId` / `duration` / `gesture` / `lipsyncFrames` は不要（UIで使わない）。`BroadcastOutline` と同等のペイロードから不要フィールドを落とす。

### `type: "lesson"`（既存を拡張）

```jsonc
{
  "type": "lesson",
  "state": "playing",
  "lesson_id": 123,
  "section_index": 2,
  "total_sections": 8,
  "section_type": "question",
  "display_text": "...",
  "dialogue_index": 1,
  "total_dialogues": 3,
  "current_content": "...",
  "current_speaker": "teacher",
  "kind": "main"     // ← 新規追加（"main" | "answer"）
}

`dialogues: [...]` は**削除**（outline で既に全情報を持つため冗長）。
```

## UI 設計

### パネル構成

```
┌─ Lesson #123 ──────────────────── [playing] ─┐
│ Section 3/8 [question]  Dialogue 2/3        │  ← 上部メタ行（コンパクトに残す）
├──────────────────────────────────────────────┤
│ [§1 ✓] [§2 ✓] [§3 ▶] [§4] [§5] [§6]…       │  ← タブ（横スクロール）
├──────────────────────────────────────────────┤
│ ✓ 👩 こんにちは！今日は…                    │
│ ✓ 🧑 お願いします！                          │
│ ▶ 👩 「Hello」と言います                    │  ← current（ハイライト）
│   🧑 Hello?                                  │
│                                              │
│ — 回答 —                                     │  ← question.answer_dialogues 区切り
│   👩 そうです                                │
└──────────────────────────────────────────────┘
```

上部メタ行は `lesson-id` + `lesson-badge` + `lessonProgress` を1行にまとめる（既存要素の縮小統合）。`display_text` / `current-speech` は broadcast.html に任せ、コントロールパネルからは撤去（タイムラインで「どこを読んでいるか」は分かる）。

### 状態スタイル

broadcast.css の `.ld-row.past` / `.current` / `.future` と、`.ld-tab.active` / `.done` / `.current` を踏襲。コントロールパネルの既存色トーン（`--bg`, `--text-dim`, `--green` 等）に合わせて調整する。

## 実装フェーズ

### Phase 1: C# 側で outline と kind を送信

**ゴール**: コントロールパネルが必要な情報を受け取れる。

**変更ファイル**:

| ファイル | 変更 |
|---------|------|
| `win-native-app/WinNativeApp/Streaming/LessonPlayer.cs` | ・`SendOutlineToPanel()` を新設（既存 `BroadcastOutline()` と並置、NotifyPanel 経由で `type = "lesson_outline"` を送る）<br>・`LoadLesson` 末尾の `SendPanelUpdate(); BroadcastOutline();` の直後に `SendOutlineToPanel();` を追加<br>・`SendPanelUpdate` が組み立てる匿名型に `kind = _currentKind ?? "main"`（新フィールド `_currentKind`）を追加<br>・`PlayDialoguesAsync` の先頭で `_currentKind = kind;` を保存 |

**確認方法**: `dotnet build win-native-app/WinNativeApp/WinNativeApp.csproj` 成功。授業ロード時に control-panel.html の DevTools で `lesson_outline` メッセージを受信できる。

### Phase 2: control-panel.html のHTML/CSS/JS差し替え

**ゴール**: Lesson タブがタイムライン UI を描画する。

**変更ファイル**:

| ファイル | 変更 |
|---------|------|
| `win-native-app/WinNativeApp/control-panel.html` | ・`<div class="tab-content" id="tab-lesson">` の中身を差し替え:<br>　- 残す: `lesson-header`（id + badge）、1行に縮小した `lessonProgress`<br>　- 追加: `lessonDialoguesTabs`（タブ）、`lessonDialoguesList`（行リスト）<br>　- 削除: `lessonSectionBar`（バー）、`lessonDisplayText`、`lessonCurrentSpeech`、`lessonDialogueList`（旧リスト）<br>・`<style>` 内の `.lesson-badge` は残し、`.section-bar` / `.section-cell` / `.lesson-display-text` / `.lesson-current-speech` / `.lesson-dialogue-list` / `.lesson-dialogue` / `.lesson-empty` は削除。broadcast.css の `.ld-tab`, `.ld-row`, `.ld-marker`, `.ld-speaker`, `.ld-content`, `.ld-group-header`, `.ld-follow-hint` を移植（px 単位に変換）<br>・JS: `case 'lesson_outline':` を `wv?.addEventListener('message')` の switch に追加し `setLessonOutline(m)` を呼ぶ<br>・JS: `_timelineState`（broadcast の `lesson.js` と同じ形: `sections` / `currentSection` / `currentDialogue` / `currentKind` / `viewSection` / `autoFollow` / `followTimer`）を追加<br>・JS: `setLessonOutline` / `renderLessonTimeline` / `_selectSection` / `_setAutoFollow` を実装（broadcast の `renderLessonDialogues` 相当）<br>・JS: `updateLesson` を書き直し、`state`/`lesson_id`/`section_index`/`dialogue_index`/`kind`/上部メタ行の更新 + `renderLessonTimeline` 呼び出しに絞る |

**確認方法**:
1. `dotnet build` 成功
2. WinNativeApp 起動 → 授業をロード → Lesson タブにタブ一覧・dialogue行が表示される
3. 再生開始 → current が移動、past が ✓ に、自動追従タブ切替
4. 他セクションのタブをクリック → 5秒後に自動追従で currentSection に戻る
5. `question` セクションで `— 回答 —` ヘッダ付きで answer_dialogues が表示される

### Phase 3: 整理・削除

**ゴール**: 旧 UI に依存していた不要コードを除去する。

**変更ファイル**:

| ファイル | 変更 |
|---------|------|
| `win-native-app/WinNativeApp/Streaming/LessonPlayer.cs` | `SendPanelUpdate` の匿名型から `dialogues` / `display_text` / `current_content` / `current_speaker` を削除（outline + state で代替可能）。テストが壊れないか `tests/test_native_app_patterns.py` を確認 |
| `win-native-app/WinNativeApp/control-panel.html` | 未使用 JS 変数 (`_lastLessonSectionIdx`) などを整理 |

**確認方法**: `python3 -m pytest tests/ -q` 通過。コントロールパネルの Lesson タブが引き続き機能する。

## 既存機能との関係

| 既存 | 本プランでの扱い |
|------|----------------|
| broadcast.html `#lesson-dialogues-panel` | **そのまま残す**（配信画面のタイムライン）。コントロールパネルはこれを C# 側にも持ってくるだけ |
| broadcast.html `#lesson-text-panel` / `#lesson-progress-panel` | 配信画面側のみ。コントロールパネルには存在しない（元々） |
| `tab-design`（Lesson パネルの位置・可視性編集） | そのまま残す。本プランは別タブ |
| `SendPanelUpdate` / `type: "lesson"` メッセージ | フィールドを整理するが、メッセージ自体は引き続き送出（state/badge 更新に必要） |
| `BroadcastOutline` / `setOutline` / `startDialogue` に追加された `sectionIndex`/`dialogueIndex`/`kind` | 既に実装済み（DONE.md 記載）。本プランはこれを再利用する |

## リスク

| リスク | 影響 | 対策 |
|--------|------|------|
| NotifyPanel の JSON 直列化で匿名型ネストが壊れる | outline が届かない | 既存 `BroadcastOutline()` と同じ匿名型構造を流用。`JsonSerializer.Serialize(new {...})` は入れ子で動作確認済み |
| control-panel.html 内の JS が大きくなりメンテ負荷増 | 読みにくい | broadcast 側の `lesson.js` + `panels.js` と**関数名を揃える**（`renderLessonTimeline`、`_timelineState`、`_setAutoFollow` 等）。命名をコピーするだけでコードレビュー時に横比較できる |
| 削除した `display_text` / `current-speech` 表示を求める要望 | 機能低下に見える | Phase 2 完了時にユーザー確認。「必要なら Phase 2.5 として復活（上部メタ領域に折り畳み等）」を検討 |
| question セクションで answer 再生中のハイライト誤り | 回答行が current にならない | `_currentKind = kind` を `PlayDialoguesAsync` の先頭で更新し、`SendPanelUpdate` に含める。control-panel 側も broadcast と同じ判定式を使う |
| 横スクロールのタブが長い授業で溢れる | UI 崩れ | `.ld-tab` の `white-space: nowrap` + コンテナ `overflow-x: auto` を採用（broadcast と同じ） |

## 関連プラン

- [lesson-dialogue-timeline.md](lesson-dialogue-timeline.md) — 配信画面側の同等機能（完了済み）。本プランはその C# コントロールパネル版
- [client-driven-lesson.md](client-driven-lesson.md) — LessonPlayer が全セクションをメモリに持つ前提。本プランが成立する根拠

## 参考箇所

- C# 既存 outline 送信: `win-native-app/WinNativeApp/Streaming/LessonPlayer.cs:135-177`（`BroadcastOutline`）
- C# Panel 更新: `win-native-app/WinNativeApp/Streaming/LessonPlayer.cs:363-414`（`SendPanelUpdate`）
- C# kind 受け渡し: `win-native-app/WinNativeApp/Streaming/LessonPlayer.cs:463-496`（`PlayDialoguesAsync`）
- 配信側タイムライン state: `static/js/broadcast/lesson.js:32-42`（`_timelineState`）
- 配信側タイムライン描画: `static/js/broadcast/panels.js:387-456`（`renderLessonDialogues`）
- 配信側CSS: `static/css/broadcast.css:634-754`
- 既存 control-panel Lesson タブ: `win-native-app/WinNativeApp/control-panel.html:588-608`（HTML）、`795-880`（JS `updateLesson`）
