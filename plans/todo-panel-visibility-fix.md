# TODOパネル 非表示制御の修正

## 背景

管理者が配信中にTODOパネルを非表示にしたいケース（授業以外でも画面を広く使いたい等）がある。
現状、設定パネル（右クリック→「表示」トグル）で `visible=0` を保存しても、授業を1回再生するだけで再表示されてしまい、実質「非表示にできない」状態になっている。

報告された症状は2つだが、調査の結果、いずれも `setLessonMode()` が DB の永続化された visible を無視して display を上書きしていることが原因と判明した。

- [ ] TODOパネルを非表示にできない
- [ ] TODOパネルを非表示にしていても授業が終わると必ず表示されてしまう

## 現状分析

### 関連ファイル
- `static/broadcast.html:55-59` — TODOパネルのDOM。`data-editable="todo"` あり、`data-managed-visibility` **無し**
- `static/js/broadcast/panels.js:343-360` — `setLessonMode(active)`。授業開始時に `todo.style.display='none'`、終了時に `todo.style.display=''` を**無条件に**設定
- `static/js/broadcast/websocket.js:180-194` — `lesson_status` イベントを受けて `setLessonMode()` を呼ぶ
- `static/js/broadcast/style-utils.js:29-46` — `applyCommonStyle()`。`data-managed-visibility` が付いた要素は visible 適用をスキップする仕組み
- `static/js/broadcast/edit-mode.js:413-436` — `editSave()`。`el.style.display !== 'none' ? 1 : 0` から visible を計算して DB に保存
- `static/js/broadcast/globals.js:33` — ITEM_REGISTRY の todo エントリ（`skipVisible` 無し → editSave 対象）
- `scripts/routes/items.py:14-19, 230-241` — 共通スキーマに `visible` トグルあり。`/api/items/{id}/visibility` で更新可能
- `src/db/items.py:87` — `broadcast_items.visible` カラム（DB 永続化済み）

### バグの連鎖
1. ユーザが設定パネルで TODO の「表示」をオフ → `PUT /api/items/todo` → DB `visible=0` 保存 → `settings_update` ブロードキャスト → `applyCommonStyle` で `display:none` 適用 ✓ ここまでは正常
2. 授業開始 → `setLessonMode(true)` → display='none'（変化なし）
3. **授業終了 → `setLessonMode(false)` → `todo.style.display = ''` で DB の visible=0 を無視して強制再表示** ← Bug #2
4. ユーザは「非表示にしたつもりが復活した」と感じる ← Bug #1 の正体
5. 仮にこの状態で編集モードに入って保存すると、`editSave` が現在の `display` から visible=1 を再計算して DB を上書きしてしまう（二次被害）

## 方針

「授業モードは TODO の表示状態に干渉しない」を原則にする。授業中に TODO を隠したいかどうかはユーザの永続設定（DB visible）に委ねる。

具体的には、`setLessonMode()` から TODO パネル（および custom-text）の display 操作を削除する。代わりに、ユーザが「授業中だけ非表示」を選びたい場合は、設定パネルの visible トグルで自分の意思で切り替えれば良い（DB に保存されるので次回以降も維持される）。

なお、`custom-text-container` も同様の上書きをしているが、こちらは別途扱う必要がある（カスタムテキストは複数あり、各要素が `broadcast_items` に登録されているため visible は個別管理されている）。本プランでは TODO に絞り、custom-text の挙動はスコープ外として現状維持する（変更前にユーザ確認）。

### 採用しない案
- 「`setLessonMode(false)` で DB を読み直して visible を反映する」案: 非同期 fetch が増え、`applyCommonStyle` との二重適用になる。そもそも授業モードが TODO に触らなければ済む。
- 「`data-managed-visibility` を TODO に追加する」案: managed-visibility の意味が「授業ライフサイクルが管理する」なので、ユーザ設定で管理したい TODO には不適切。

## 実装ステップ

1. **`static/js/broadcast/panels.js:343-360` の修正**
   - `setLessonMode()` 内の TODO 操作を削除：`if (todo) todo.style.display = 'none';` と `if (todo) todo.style.display = '';` の2行を削除
   - コメントも更新（「授業に関係ないパネル」の説明を修正）
   - custom-text の操作は据え置き（別タスク）

2. **編集モード保存の保護（二次被害の予防）**
   - 現状でも問題は起きにくいが、念のため `static/js/broadcast/edit-mode.js:427-429` を確認
   - `editSave` は明示的にユーザがレイアウト編集をしたときのみ走る想定なので、display=none の状態のままレイアウト編集→保存は通常起きない
   - 必要なら ITEM_REGISTRY の todo に `skipVisible: true` を付ける選択肢もあるが、これは設定パネル側の visible トグルで保存するルートと重複するので保留

3. **手動動作確認**
   - 配信画面で TODO パネルを設定パネルから非表示に → 即座に消えること
   - そのまま授業を1本再生 → 終了後も非表示のままであること
   - リロードして DB から復元 → 引き続き非表示であること
   - 設定パネルで再表示 → すぐ表示されること
   - 授業中に表示状態が変わらないこと（visible=1 の状態でも、visible=0 の状態でも、授業開始/終了で display が変化しないこと）

4. **テスト**
   - `tests/test_broadcast_patterns.py` に「`setLessonMode` が `todo-panel` の display を直接操作していない」ことを確認する正規表現アサートを追加（再発防止ガード）
   - `python3 -m pytest tests/ -q -m "not slow"` を実行してリグレッションが無いことを確認

5. **ドキュメント更新**
   - `DONE.md` に修正内容を追記
   - `TODO.md` から該当2行を削除

## リスク

- **既存運用への影響**: これまで「授業中は TODO が自動で消える」挙動に慣れていたユーザがいる場合、挙動変更に違和感を覚える可能性。→ ユーザは TODO 表示を保ったまま授業を見たいケースもあると思われ、その場合は今回の修正でむしろ改善する。逆に「授業中は消したい」運用なら、設定パネルで visible=0 にしておけば DB に永続化されて常に消えるので運用可能。
- **custom-text の挙動差異**: TODO だけ授業干渉から外れ、custom-text は引き続き授業中に消える。一貫性が崩れるが、custom-text は授業画面と用途が衝突しやすい（複数のテロップが重なる）ため、現状維持に合理性がある。気になればフォローアップで揃える。

## 完了条件

- 配信画面で TODO の表示/非表示が設定パネルのトグルだけで完全に制御できる
- 授業の開始・終了で TODO の表示状態が変化しない
- リロード後も DB の visible 値どおりに復元される
- `tests/test_broadcast_patterns.py` に再発防止アサートが追加され通過
- `pytest -m "not slow"` 全件パス

## ステータス

完了（2026-05-05）

- `static/js/broadcast/panels.js` の `setLessonMode()` から `todo-panel` の display 操作と要素取得を削除
- `tests/test_broadcast_patterns.py` に `TestLessonModeDoesNotTouchTodo` を追加（再発防止）
- `python3 -m pytest tests/ -q -m "not slow"` 1282 passed
- 実機確認はユーザ側で実施予定（配信画面でトグル→授業1本→終了→非表示維持の確認）
