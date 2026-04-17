# 授業Dialogueタイムライン表示

## ステータス: 未着手

## 背景と動機

### 現状の問題

現在、broadcast.html の授業表示は**再生中の1 dialogue分しか見えない**:

```
C# LessonPlayer
  ├─ startDialogue(dlg) → 字幕表示 + リップシンク + 感情
  └─ endDialogue()      → 字幕フェード + リップシンク停止
```

そのため視聴者・開発者ともに:
- **過去に何が読まれたか**を振り返れない（字幕は消える）
- **次に何が来るか**のプレビューが見えない
- 現在のセクション以外の内容が見えない（`lesson-progress-panel` はセクション見出しのみ）

### 欲しい形

1. **時系列タイムライン**: 受信（ロード済み）の全dialogueを順に並べ、再生済み/再生中/未再生を視覚的に区別
2. **セクション切替**: 現在セクション以外もプレビューできる（タブ or ドロップダウン）
3. 既存の `lesson-text-panel`（教材テキスト）/ `lesson-progress-panel`（セクション見出し）/ 字幕 は維持

## 設計方針

| 項目 | 方針 |
|------|------|
| データ供給元 | C# `LessonPlayer` は `LoadLesson` で全セクションをメモリに持つ。この構造を broadcast.html に1回で push する |
| タイムラインの状態管理 | broadcast.html 側で state を保持（currentSection / currentDialogue） |
| 状態遷移 | 既存の `window.lesson.startDialogue(data)` / `endDialogue()` をフックして past/current を更新 |
| 音声データ | 不要。content / speaker / emotion / duration のみ送信 |
| パネル編集 | 他パネル同様、レイアウト編集対応（`data-editable` + `globals.js` に登録） |

### なぜ C# から outline を push するか

- **単一情報源**: C# が既に全セクションを持っている（`LoadLesson`）。broadcast.html 側で積み上げると順序ずれ・漏れリスク。
- **再起動耐性**: C# 単独でも動くアーキテクチャ（client-driven-lesson）を壊さない。ブラウザリロード時に C# が outline を再送すればすぐ復元できる。

## データフォーマット

### C# → broadcast.html: `lesson_outline`（BroadcastEvent 経由のWSイベント、または InjectJs）

`LoadLesson` 後に即発火:

```jsonc
{
  "type": "lesson_outline",
  "lesson_id": 123,
  "total_sections": 8,
  "sections": [
    {
      "section_index": 0,
      "section_type": "introduction",
      "summary": "自己紹介",
      "display_text": "Today's Topic: Greetings",
      "dialogues": [
        { "index": 0, "speaker": "teacher", "avatar_id": "teacher", "content": "こんにちは…", "emotion": "joy", "duration": 4.2 },
        { "index": 1, "speaker": "student", "avatar_id": "student", "content": "お願いします！", "emotion": "excited", "duration": 2.1 }
      ],
      "question": null
    },
    {
      "section_index": 1,
      "section_type": "question",
      "summary": "理解度チェック",
      "display_text": "",
      "dialogues": [ /* 問題文 */ ],
      "question": {
        "wait_seconds": 8,
        "answer_dialogues": [ /* 回答 */ ]
      }
    }
  ]
}
```

※ WAV/lipsync は含めない（タイムライン表示には不要、転送量を抑える）。

### 状態遷移イベント（既存を再利用）

- `startDialogue(data)` 到着 → data に含まれる `sectionIndex` + `dialogueIndex` + 種別（main/answer）でタイムラインの該当行を "current" にマーク、前の行を "past" に変更
- `endDialogue()` → 現在行は "past" に遷移（次の startDialogue で "current" がずれる）
- `lesson_complete` → 全行を "past"

現状 `startDialogue(data)` には `sectionIndex`/`dialogueIndex`/`kind` が含まれていないため、C# 側で付与する必要がある（小変更）。

## UI 設計

### 新規パネル: `lesson-dialogues-panel`

```
┌─ 授業タイムライン ─────────────────┐
│ [§1 自己紹介 ▼] [§2 挨拶] ...      │  ← セクションタブ（横スクロール可）
├────────────────────────────────┤
│ ✓ 👩 こんにちは！今日は挨拶を…     │  ← past（薄色 + ✓）
│ ✓ 🧑 お願いします！                │
│ ▶ 👩 「Hello」と言います          │  ← current（ハイライト + ▶）
│   🧑 Hello?                        │  ← future（グレー）
│   👩 そうです。もう一度…           │
└────────────────────────────────┘
```

### タブの動作

- 初期表示: 現在再生中のセクションをアクティブ
- セクション切り替え: クリック/タップで別セクションを表示
- 自動追従トグル: デフォルトON。ユーザーが手動でタブを選んだら一時的にOFF、現在セクションが変わっても追従しない（5秒無操作でONに戻す、または「追従に戻す」ボタン）

### スタイル（案）

| 状態 | スタイル |
|------|---------|
| past | opacity 0.55, アイコン `✓` |
| current | 背景ハイライト + 左ボーダー（色はキャラに合わせる）, アイコン `▶` |
| future | 通常色 |
| section tab active | 下線 + 濃色 |
| section tab done | ✓ + 薄色 |

## 実装フェーズ

### Phase 1: C# 側で outline 送信

**ゴール**: `LoadLesson` 完了時に全セクションの軽量構造を broadcast.html に送る。

**変更ファイル**:
| ファイル | 変更 |
|---------|------|
| `win-native-app/WinNativeApp/Streaming/LessonPlayer.cs` | `LoadLesson` 末尾で `BroadcastEvent` に `lesson_outline` を発火。`startDialogue` の JSON に `section_index` / `dialogue_index` / `kind`（"main" or "answer"）を追加 |

**確認方法**: WebSocket モニタで `lesson_outline` が届く・`startDialogue` に index 群が含まれることを確認。

### Phase 2: broadcast.html にタイムラインパネル追加

**ゴール**: outline を受信してセクションタブとdialogueリストを描画し、startDialogue で状態を更新する。

**変更ファイル**:
| ファイル | 変更 |
|---------|------|
| `static/broadcast.html` | `<div id="lesson-dialogues-panel" data-editable="lesson_dialogues" data-managed-visibility style="display:none;">` 追加 |
| `static/css/broadcast.css` | `.lesson-dialogues-*`（タブ・row・past/current/future スタイル） |
| `static/js/broadcast/lesson.js` | outline 保持・startDialogue/endDialogue で state 更新・DOM更新 |
| `static/js/broadcast/websocket.js` | `case 'lesson_outline':` / `case 'lesson_complete':` ハンドラ追加 |
| `static/js/broadcast/globals.js` | PANEL_DEFS に `lesson-dialogues-panel` 追加（他の lesson パネル同様 `skipVisible: true`） |
| `static/js/broadcast/settings.js` | 他 lesson パネル同様、設定反映を追加 |
| `static/js/broadcast/panels.js` | `showLessonDialogues(outline)` / `updateLessonDialoguesState(sectionIdx, dialogueIdx, kind)` / `hideLessonDialogues()` / `setLessonMode` で出し入れ |

**確認方法**: 授業を再生し、タイムラインが正しくマーキングされ、currentが進むことを確認。

### Phase 3: セクションタブ切替 UI

**ゴール**: セクションタブで表示セクションを切り替えられる。

**変更ファイル**:
| ファイル | 変更 |
|---------|------|
| `static/js/broadcast/panels.js` | タブクリックで表示中 section を切替。自動追従 toggle を実装（5秒無操作で復帰） |
| `static/css/broadcast.css` | タブのスタイル（横スクロール可） |

**確認方法**: 現在のセクションと異なるタブを選んでも再生に影響せず、選んだセクションの dialogue 一覧が表示される。5秒後に自動追従に戻る。

### Phase 4: レイアウト編集対応 + DB保存

**ゴール**: 他パネル同様、位置・サイズ・ZIndex・可視性を編集して保存できる。

**変更ファイル**:
| ファイル | 変更 |
|---------|------|
| `scripts/routes/overlay.py` / 関連 DB 設定キー | `lesson_dialogues_*` キーの読み書き（他パネルの設定機構を踏襲） |
| `static/index.html` / `static/js/broadcast/settings-panel.js` | 設定パネルに `lesson_dialogues_*` の調整UI（フォントサイズ・色など） |

**確認方法**: `/broadcast` でドラッグ＆リサイズ→保存→リロード後に位置が維持される。

### Phase 5: 再起動・リロード時の復元

**ゴール**: ブラウザリロードやサーバー再起動後も outline が復元される。

**変更ファイル**:
| ファイル | 変更 |
|---------|------|
| `win-native-app/WinNativeApp/Streaming/LessonPlayer.cs` | broadcast.html からの `lesson_outline_request`（新 JS interop イベント or WS message）を受けたら現在の `_sections` から outline を再送 |
| `static/js/broadcast/lesson.js` | 起動時（または `setLessonMode(true)` 時）に outline 要求を送る |

**確認方法**: 授業再生中に broadcast.html をリロード → タイムラインが即復元される。

## 既存機能との関係

| 既存 | 役割 | 本プランとの関係 |
|------|------|----------------|
| `lesson-text-panel` | 教材テキスト表示 | そのまま残す |
| `lesson-progress-panel` | セクション見出し + 現在位置 | そのまま残す。**補完**の関係（セクション単位 vs dialogue単位） |
| 字幕（subtitle） | 再生中の1 dialogue テキスト | そのまま残す。タイムラインはログ、字幕は現在地 |
| `client-driven-lesson.md` | クライアント主導再生アーキテクチャ | 本プランは Phase 5 扱いの小機能。既存 Phase 1-4 を壊さない |

## リスク

| リスク | 影響 | 対策 |
|--------|------|------|
| outline が startDialogue と順序ずれ | タイムラインのマーキング失敗 | C#で `section_index` + `dialogue_index` + `kind` を付与し、broadcast.html 側で厳密マッチング |
| 長いdialogueでパネル溢れ | 表示崩れ | `overflow-y: auto` + 行を折り畳み（行クリックで全文展開） |
| 画面占有面積の増加 | デザイン悪化 | 既存の編集モードで位置・サイズ調整可能。デフォルトは画面右側の縦長にする |
| 自動追従 vs 手動選択の競合 | UX混乱 | 手動選択後5秒で自動復帰（タイマーで制御） |
| 答え（question.answer_dialogues）の扱い | kind 分岐漏れ | outline で `kind: "answer"` の dialogue はセクション内で別グループ表示（「回答:」ヘッダ下） |

## 関連プラン

- [client-driven-lesson.md](client-driven-lesson.md) — 親アーキテクチャ。LessonPlayer の全セクション保持があるから本プランが成立する
- [lesson-panel-size-control.md](lesson-panel-size-control.md) — 既存のパネル編集機構。本プランのPhase 4 でも同じ仕組みを踏襲する
