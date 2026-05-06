---
ステータス: 完了
作成日: 2026-05-06
完了日: 2026-05-06
関連TODO: 「授業の流れパネルの縦幅が変更できない」
---

# 授業の流れパネル — 縦幅変更がきかない問題の修正

## 1. 現象

`/broadcast` 編集モードで `#lesson-progress-panel`（授業の流れパネル）の下端ハンドルをドラッグしてリサイズしても、視覚的に縦幅が伸びない／縮まない。値はDBに保存されているが、ページをリロードしても元のサイズに戻ってしまう。

## 2. 原因（2箇所のバグの合わせ技）

### バグA: ハードコードCSSが視覚的に縦幅をクリップ

`static/css/broadcast.css:569-589` の `#lesson-progress-panel` ルール:
```css
#lesson-progress-panel {
  position: absolute;
  top: 2%; left: 1%;
  z-index: 12;
  width: 18%;
  max-height: 26%;   /* ← 視覚クリップの主犯 */
  overflow-y: auto;
  ...
}
```

ドラッグで `el.style.height = "60%"` がインラインで付与されても、CSS仕様上 `max-height` は `height` より常に優先される。インラインで `style.maxHeight` を打ち消さない限り、**26%を超える高さは描画されない**。

### バグB: `applySettings` が `s.lesson_progress.height` を適用していない

`static/js/broadcast/settings.js:174-180`:
```js
if (s.lesson_progress) {
  const lpp = document.getElementById('lesson-progress-panel');
  if (lpp) {
    applyCommonStyle(lpp, s.lesson_progress);
    if (s.lesson_progress.width != null) lpp.style.width = s.lesson_progress.width + '%';
    if (s.lesson_progress.maxHeight != null) lpp.style.maxHeight = s.lesson_progress.maxHeight + '%';
    // height を適用する行が抜けている
```

`applyCommonStyle`（`static/js/broadcast/style-utils.js:28-165`）も `style.height` は設定しない。

結果として、ドラッグで一時的に inline `style.height` が付くが、`settings_update` が来ると `applySettings` が再走するなかで height は再適用されず、ページリロード後はDBから復元されない。

### 比較: TODOパネルは同じ問題を解決済み

`static/js/broadcast/settings.js:136-140`:
```js
if (s.todo.height != null) {
  todoPanelEl.style.height = s.todo.height + '%';
  todoPanelEl.style.maxHeight = 'none';   // CSS max-height を打ち消す
  todoPanelEl.style.overflow = 'hidden';
}
```

このパターンが正解。`lesson_progress` も同じ形に揃えるだけで解決する。

### 検証ログ

```bash
$ curl -s http://localhost:8080/api/items/lesson_progress | jq '{height, maxHeight}'
{ "height": 53.5, "maxHeight": null }
```

DBには `height` が保存されているが、broadcast 側で復元されない（バグB）うえに、復元しても CSS の `max-height: 26%` がクリップする（バグA）。
ユーザーが何度もドラッグして大きくしようとした履歴があるため、現在の保存値はCSS既定（26%）から乖離している。

## 3. 修正方針（最小変更）

`static/js/broadcast/settings.js:174-180` の `lesson_progress` ブロックを、TODOパネルと同じパターンに揃える:

```js
if (s.lesson_progress) {
  const lpp = document.getElementById('lesson-progress-panel');
  if (lpp) {
    applyCommonStyle(lpp, s.lesson_progress);
    if (s.lesson_progress.width != null) lpp.style.width = s.lesson_progress.width + '%';
    if (s.lesson_progress.height != null) {
      lpp.style.height = s.lesson_progress.height + '%';
      lpp.style.maxHeight = 'none';                  // ← CSSのmax-heightを打ち消す
    } else if (s.lesson_progress.maxHeight != null) {
      lpp.style.maxHeight = s.lesson_progress.maxHeight + '%';
    }
    // ...（既存のtitleColor/countColor等の処理はそのまま）
```

優先順位:
- height が保存されている → height を効かせ、maxHeight を `none` に上書き
- height が無く maxHeight だけ → maxHeight を効かせる（従来動作維持）
- どちらも無い → CSSの `max-height: 26%` がそのまま効く（idle初期状態）

CSS側の `max-height: 26%` は **削除しない**（未編集ユーザー向けの初期値として温存。inline 値で打ち消される設計）。

## 4. 実装ステップ

### Step 1: settings.js の lesson_progress ブロック修正
`static/js/broadcast/settings.js:174-180` を上記コードに差し替え。

### Step 2: ドラッグ中の即時反映（Step 1 と同時に実施）
edit-mode.js の resize ハンドラ（`static/js/broadcast/edit-mode.js:382-383`）はドラッグ中に `el.style.height` を直接書き込むが、CSS `max-height: 26%` がクリップするためドラッグ中の縦方向プレビューが26%超で効かない。Step 1 だけだと「ドラッグ → 離す → `editSave()` → `settings_update` の `applySettings` 再走で初めて反映」になり、UXが不自然。

→ resize 開始時（`onDown` 相当の箇所）に `el.style.maxHeight = 'none'` を付ける。対象は縦リサイズ可能な全要素（`resizeV` が真のときに付ければ十分）でよい。副作用としては「CSSで max-height を効かせていた要素が編集開始後はインラインで打ち消される」が、編集モードで触った要素だけなので影響範囲は狭い。

実装位置: `static/js/broadcast/edit-mode.js` の resize 用 `mousedown` ハンドラ内、`onMove` を登録する直前あたり。

### Step 3: 動作確認
- `/broadcast` 編集モードで進捗パネルの下端をドラッグ → リアルタイムに縦に伸びる（Step 2 で edit-mode 修正しなかった場合は1度ドラッグして離した直後の `applySettings` で反映される想定）
- ページリロード → 保存した縦幅が維持される
- DBの `lesson_progress.height` を 0 に戻す or 削除して、CSSの 26% が初期値として効くことを確認

### Step 4: TODO/DONE 更新
- TODO.md からこの行を削除
- DONE.md に変更内容を追記

## 5. 変更ファイル

| ファイル | 変更 | 規模 |
|---------|------|------|
| `static/js/broadcast/settings.js` | lesson_progress ブロックの height 適用追加 | 数行 |
| `static/js/broadcast/edit-mode.js` | リサイズ開始時に maxHeight=none（Step 2） | 数行 |
| `TODO.md` / `DONE.md` | 行の移動 | 数行 |

## 6. リスク・注意

- 現状のDB保存値は `height: 53.5`（ユーザーが大きくしようとドラッグした結果）。修正適用後は初回読み込みで進捗パネルが画面の53.5%の縦幅になる。これは**ユーザーが本来意図した値が反映される**だけなので、リスクではなく期待動作。気に入らなければ編集モードで再ドラッグして調整できる。
- `overflow-y: auto` は CSS で残るのでスクロールは維持される。
- TODOパネルは `overflow: hidden` を併用しているが、進捗パネルは項目スクロールを残したいので `overflow` は触らない。

## 7. テスト

- `tests/test_broadcast_patterns.py` に「lesson_progress の applySettings が height を適用するか」のソース解析テストを追加するかは要検討（パターン検証で再発防止になるが、過剰になるかもしれない。実装後に判断）。

## 8. 想定工数

15〜30分（Step 1 + 確認）。Step 2 を入れるなら +15分。
