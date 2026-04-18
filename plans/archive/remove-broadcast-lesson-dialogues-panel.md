# 配信画面の授業タイムラインパネル削除（サイドバーに統一）

## ステータス: 完了

## 背景と動機

### 現状: 授業タイムラインの表示が 2 箇所に重複

C# ネイティブ配信アプリで授業再生中、「全セクションの dialogue タイムライン」（タブ列 + 全会話の past/current/future 表示）を **2 箇所** に表示している:

1. **配信画面のパネル** — `broadcast.html` の `#lesson-dialogues-panel`（右サイドバー。タイトル「授業タイムライン」＋ `§1 §2 ...` のタブ列 ＋ 全 dialogue 行を ✓/▶/未再生で色分け ＋ 手動選択中の「→ 現在地へ」ヒント）
2. **コントロールパネルのサイドバー** — `control-panel.html` の Lesson タブ（broadcast と同構造の `#lessonDialoguesTabs` + `.ld-row` タイムライン。プラン [control-panel-lesson-timeline.md](control-panel-lesson-timeline.md) で追加済）

サイドバーのタイムライン化が完了した時点で、配信画面側の `lesson-dialogues-panel` は **オペレータがすでにサイドバーで同じ情報を見ており、視聴者にとっても情報量過多（全会話が常時並ぶ）** なため、配信画面から取り除く。

### 欲しい形

配信画面の `lesson-dialogues-panel` と、そのためだけに存在する「broadcast 用 outline ブロードキャスト機構」（`BroadcastOutline` / `window.lesson.setOutline` / `window.lesson.onComplete` / startDialogue payload の `sectionIndex/dialogueIndex/kind` / `_lessonOutlineRequest` postMessage）を削除する。授業の進行把握は以下に集約:

- オペレータ: C# サイドバー Lesson タブ（`SendOutlineToPanel` + `SendPanelUpdate` で引き続き駆動）
- 視聴者: `#lesson-progress-panel`（左サイドバーの「授業の流れ」）・`#lesson-title-panel`・`#lesson-text-panel`・字幕

### 残すもの（誤って触らない対象）

| パネル/機構 | 扱い | 理由 |
|------------|------|------|
| `#lesson-progress-panel` | **残す** | 視聴者に「どのセクションを再生中か」を示す役割。サイドバーのタブ列とは向き先が違う（視聴者 vs オペレータ） |
| `#lesson-title-panel` / `#lesson-text-panel` | 残す | 役割が別（タイトル表示・板書） |
| C# `control-panel.html` の Lesson タブ（`#lessonDialoguesTabs` / `.ld-row` 等） | 残す | 本プランで統一先となるオペレータ向け表示 |
| C# `LessonPlayer.SendOutlineToPanel()` / `SendPanelUpdate()` / `NotifyPanel` 経由の `lesson_outline` イベント | 残す | control-panel のタイムラインを駆動する |

## 設計方針

| 項目 | 方針 |
|------|------|
| スコープ | `lesson_dialogues` という broadcast アイテム種別を**完全撤廃**する。関連コードも一緒に消す。後方互換のエイリアスやマイグレーションは残さない |
| broadcast ↔ C# 間 | `window.lesson.setOutline` / `window.lesson.onComplete` は broadcast 側でしか使っていないため、C# 側の `BroadcastOutline` ごと削除する。`SendOutlineToPanel`（コントロールパネル向け）は残す |
| startDialogue payload | `sectionIndex` / `dialogueIndex` / `kind` は broadcast `_timelineState` 更新にしか使われていないため、削除する。control-panel には別経路（`SendPanelUpdate`）で渡されているので影響なし |
| `_lessonOutlineRequest` postMessage | broadcast.html の init.js がリロード復元用に投げていたが、broadcast 側の outline 受信口を消すので送信・受信どちらも削除 |
| WS / REST ペイロード | Python 側（`src/lesson_runner.py`・`scripts/routes/overlay.py`）は `lesson_dialogues` の描画データを送っていない（C# が全部やる）。設定保存で `lesson_dialogues` 名の broadcast_items レコードを書くだけなので、defaults 定義と `fixed_items` から外すだけで済む |
| DB レコード | `broadcast_items` に既存の `lesson_dialogues` 行があれば削除する（1 回限りの SQL）。レイアウト設定のみなのでマイグレーションは不要 |

## 実装フェーズ

### Phase 1: フロントエンド削除（broadcast.html / CSS / JS）

**ゴール**: 配信画面から `lesson-dialogues-panel` の描画・制御・outline 受信口が完全に消え、C# からの関連 InjectJs を受けても何も起きない状態にする。

**変更ファイル**:

| ファイル | 変更 |
|---------|------|
| `static/broadcast.html` | `<div id="lesson-dialogues-panel">…</div>` ブロック（行 77–82）を削除 |
| `static/css/broadcast.css` | `#lesson-dialogues-panel` / `#lesson-dialogues-panel.visible` / `#lesson-dialogues-title` / `#lesson-dialogues-tabs` / `.ld-tab{,:hover,.active,.done,.current}` / `#lesson-dialogues-list` / `.ld-group-header` / `.ld-row{,.past,.current,.future}` / `.ld-marker{,.past::before,.current::before}` / `.ld-speaker` / `.ld-content` / `.ld-follow-hint` 系（634 行以降）を削除 |
| `static/js/broadcast/panels.js` | `_speakerIcon` / `showLessonDialogues` / `hideLessonDialogues` / `_setAutoFollow` / `_selectSection` / `renderLessonDialogues` / `_renderDialogueGroup`（341–493 行相当）を削除。`setLessonMode(false)` 内の `hideLessonDialogues()` 呼び出し（515 行）も削除 |
| `static/js/broadcast/lesson.js` | `_timelineState` 定数 / `_FOLLOW_RESET_MS` 定数 / `window.lesson.setOutline` / `window.lesson.onComplete`（32–76 行相当）を削除。`window.lesson.startDialogue` 内の `_timelineState` 更新ブロック（84–92 行相当）も削除 |
| `static/js/broadcast/globals.js` | `ITEM_REGISTRY` 配列から `{ id: 'lesson-dialogues-panel', prefix: 'lesson_dialogues', ... }`（58 行）を削除 |
| `static/js/broadcast/settings.js` | `if (s.lesson_dialogues) { ... }` ブロック（219–238 行）を削除 |
| `static/js/broadcast/init.js` | `_lessonOutlineRequest` postMessage（102 行）を削除 |

**確認方法**:
1. 授業再生 → 配信画面右側に「授業タイムライン」パネルが出ない
2. `lesson-title-panel` / `lesson-text-panel` / `lesson-progress-panel`（左サイドバーの「授業の流れ」）は従来通り表示される
3. DevTools コンソールに `showLessonDialogues is not defined` / `setOutline is not a function` 等のエラーが出ない
4. C# コントロールパネル Lesson タブのタイムラインは引き続き動作（タブ切替・past/current/future の色分け・「現在地へ」ヒント）

### Phase 2: Python サーバー側（overlay defaults）

**ゴール**: `lesson_dialogues` をアイテム定義から外し、設定保存 API で扱われないようにする。

**変更ファイル**:

| ファイル | 変更 |
|---------|------|
| `scripts/routes/overlay.py` | ・`_OVERLAY_DEFAULTS` から `"lesson_dialogues": _make_item_defaults({...})`（392–398 行）を削除<br>・`fixed_items` セット（599 行）から `"lesson_dialogues"` を除外 |

`src/db/items.py` の `_ITEM_SPECIFIC_KEYS` / `scripts/routes/items.py` の `_ITEM_SPECIFIC_SCHEMA` / `_SCHEMA_ITEM_LABELS` には `lesson_dialogues` は登録されていないため変更不要。

**確認方法**:
1. `python3 -m pytest tests/ -q` 全通過
2. 授業再生開始 → サーバーログにエラー無し
3. `curl -s http://localhost:$WEB_PORT/api/items` のレスポンスに `lesson_dialogues` が含まれない（現状 `broadcast_items` DB 行が残っている場合は Phase 4 で削除）

### Phase 3: C# ネイティブ配信アプリの outline 送信削除

**ゴール**: broadcast.html に outline を流す機構を止め、コントロールパネル向け (`SendOutlineToPanel`) だけを残す。

**変更ファイル**:

| ファイル | 変更 |
|---------|------|
| `win-native-app/WinNativeApp/Streaming/LessonPlayer.cs` | ・`LoadLesson` 末尾の `BroadcastOutline();` 呼び出し（134 行）を削除<br>・`BroadcastOutline()` メソッド本体（138–180 行）を丸ごと削除<br>・授業完了時の `InjectJs?.Invoke($"if(window.lesson&&window.lesson.onComplete)window.lesson.onComplete({...})")`（281 行）を削除<br>・`PlayDialoguesAsync` の startDialogue InjectJs payload（513–525 行）から `sectionIndex` / `dialogueIndex = i` / `kind` の 3 フィールドを削除 |
| `win-native-app/WinNativeApp/MainForm.cs` | WebMessage 受信ハンドラの `if (msg.TryGetProperty("_lessonOutlineRequest", out JsonElement _)) { ... _lessonPlayer?.BroadcastOutline(); ... }` ブロック（678–681 行）を削除 |

**確認方法**:
1. `dotnet build win-native-app/WinNativeApp/WinNativeApp.csproj` 成功
2. WinNativeApp 起動 → 授業再生 → コントロールパネルの Lesson タブタイムラインが従来通り動作（タブ・past/current/future・完了時の全 past 化は `SendPanelUpdate` で引き続き駆動される）
3. broadcast.html リロード中に `_lessonOutlineRequest` が飛ばなくなる（init.js 側も削除済）

### Phase 4: DB 残留データの掃除（必要に応じて）

**ゴール**: 本番 DB の `broadcast_items` に残っている `lesson_dialogues` 行を削除する。

- Phase 1–3 完了後、本番サーバーの DB を確認
- 残っていれば `DELETE FROM broadcast_items WHERE type = 'lesson_dialogues'` を 1 回手動実行
- レイアウト設定のみなのでマイグレーションは不要

## 既存機能との関係

| 既存 | 本プランでの扱い |
|------|----------------|
| `#lesson-progress-panel`（左サイドバーの進捗表示） | **残す**（視聴者向けで役割が別） |
| `#lesson-title-panel` / `#lesson-text-panel` | 残す |
| C# コントロールパネル Lesson タブのタイムライン | 残す（`SendOutlineToPanel` + `SendPanelUpdate` で駆動） |
| `lesson_status` WS イベント（`sections` / `current_index` 含む） | 変更なし（`lesson-progress-panel` が使う） |
| `LessonPlayer.SendPanelUpdate` の `kind` フィールド | 残す（control-panel が読む） |

## リスク

| リスク | 影響 | 対策 |
|--------|------|------|
| `_timelineState` / `_FOLLOW_RESET_MS` を他所が参照している | 削除後に JS エラー | Phase 1 着手時に `grep -r "_timelineState\|_FOLLOW_RESET_MS"` で確認。現状は `lesson.js` と `panels.js` のみ |
| `window.lesson.setOutline` / `onComplete` を他所が呼んでいる | 授業再生でエラー | C# 側 `BroadcastOutline` と一緒に削除するので呼ばれない。他の HTML/JS からは呼ばれていない（要 grep 再確認） |
| startDialogue の `sectionIndex` 等を他フロントが読む | 他表示が壊れる | broadcast 以外の消費者はなし（control-panel は `NotifyPanel` 経由で別送信されるため無影響） |
| DB に `lesson_dialogues` 行が残った状態で `_OVERLAY_DEFAULTS` から消えると、起動時の defaults マージで警告等が出る | 起動失敗 | 既存 `overlay.py` の defaults マージは `_OVERLAY_DEFAULTS` を軸にしているので、未定義キーは単に読み飛ばされる。安全側なら Phase 4 で `DELETE` |
| 視聴者が「セクション間の細かい dialogue 進行」を把握しづらくなる | UX 変化 | 視聴者向けには `lesson-progress-panel`（セクション単位の流れ）＋ `lesson-title-panel`（現在セクション名）＋ 字幕で十分とする。本プランはその前提 |
| 前回コミット前に誤って `lesson_progress` 側の DB レコードを削除してしまった（今回の手戻り分） | `lesson-progress-panel` の保存済みレイアウトが消えた | `_OVERLAY_DEFAULTS.lesson_progress` のデフォルト値でフォールバック表示される。ユーザーが微調整していた場合のみ再調整が必要。実装本体（HTML/CSS/JS/Python/C#）は `git restore` で復旧済 |

## 関連プラン

- [control-panel-lesson-timeline.md](control-panel-lesson-timeline.md) — サイドバーにタイムラインを追加した前提プラン（完了）。本プランはその成果を前提に、配信画面側の重複を削る
- [lesson-dialogue-timeline.md](lesson-dialogue-timeline.md) — 今回削除対象となる `lesson-dialogues-panel` を追加したプラン。本プラン完了時にステータスを「取り下げ」に更新する

## 参考箇所（現行コード）

- 配信画面 HTML: `static/broadcast.html:77-82`
- 配信画面 CSS: `static/css/broadcast.css:634` 以降（`#lesson-dialogues-panel` 〜 `.ld-follow-hint` まで）
- 配信画面 JS（描画・操作）: `static/js/broadcast/panels.js:341-493` + `515`
- 配信画面 JS（outline 受信）: `static/js/broadcast/lesson.js:32-76, 84-92`
- 配信画面 JS（登録）: `static/js/broadcast/globals.js:58`
- 配信画面 JS（スタイル適用）: `static/js/broadcast/settings.js:219-238`
- 配信画面 JS（リロード復元要求）: `static/js/broadcast/init.js:102`
- サーバー: `scripts/routes/overlay.py:392-398, 599`
- C# LessonPlayer: `win-native-app/WinNativeApp/Streaming/LessonPlayer.cs:132-180, 281, 513-525`
- C# MainForm: `win-native-app/WinNativeApp/MainForm.cs:678-681`
