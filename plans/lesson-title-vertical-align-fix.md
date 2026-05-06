---
ステータス: 完了
作成日: 2026-05-06
完了日: 2026-05-06
関連TODO: 「lesson_title の垂直側の中央ぞろえがきかない。」
---

# 授業タイトルパネル — 垂直中央揃えがきかない問題の修正

## 1. 現象

`/broadcast` の設定パネルで `lesson_title`（授業タイトル）の「垂直揃え」を `中央` / `下` に変更しても、`#lesson-title-text` の位置は変わらない。さらにパネルの高さを下端ハンドルでドラッグして広げても、リロード後に元のサイズに戻る（高さが永続化されない）。

結果として、ユーザーは「タイトルパネルだけ縦中央寄せが効かない」と認識する。

## 2. 原因（3箇所の合わせ技）

### バグA: パネルがflexコンテナでないため `justify-content` が効かない

`static/js/broadcast/style-utils.js:154-158`:

```js
if (props.verticalAlign != null) {
  const ct = el.querySelector('.custom-text-content, .child-text-content') || el;
  ct.style.justifyContent = props.verticalAlign === 'center' ? 'center' : props.verticalAlign === 'bottom' ? 'flex-end' : 'flex-start';
}
```

子要素として `.custom-text-content` も `.child-text-content` も持たない `#lesson-title-panel` の場合、フォールバックでパネル自体に `justifyContent` が設定される。しかし `static/css/broadcast.css:542-555` の `#lesson-title-panel` は `display: flex` を指定していない（デフォルト `block`）ため、`justify-content` は無視される。

```css
#lesson-title-panel {
  position: absolute;
  top: 2%; left: 35%;
  z-index: 12;
  /* display: flex も flex-direction も無い */
  padding: 0.4vw 1.5vw;
  ...
}
```

### バグB: テキスト要素にflexアイテムとしての高さが無い

仮にパネルを `display:flex; flex-direction:column;` にしても、子の `#lesson-title-text` には高さ指定が無く中身ぴったりに縮むため、`align-items` 系で中央寄せされてもユーザーから見ると「テキストが上にも下にも寄らずただ縦中央にある」のが正解。ここまでは flex で解決できる。

### バグC: 高さが永続化されないので「効かない」と体感される

`static/js/broadcast/globals.js:34`:

```js
{ id: 'lesson-title-panel', prefix: 'lesson_title', hasSize: false, defaultZ: 12, skipVisible: true },
```

`hasSize: false` のため `editSave()`（`static/js/broadcast/edit-mode.js:433-438`）はこのアイテムの `width` / `height` をDBに保存しない。さらに `applySettings`（`static/js/broadcast/settings.js:148-158`）も `height` を読み戻さない。

`#lesson-title-text` は `white-space: nowrap` の単行テキストなので、パネルはテキスト＋padding分の高さに自動収縮する。つまり編集モードで縦に広げても「保存されないし、リロードで消える」。仮にバグAを直しても、保存しない以上は再読込で初期サイズに戻り、垂直中央寄せが効いていることを確認できない。

### 比較: 既に同パターンを解決済みのアイテム

- TODOパネル: `static/js/broadcast/settings.js:136-140` で `height` を適用＋`maxHeight='none'` でCSSのクリップを打ち消す（`hasSize: true`）
- 授業の流れパネル: `plans/lesson-progress-height-fix.md`（完了）で同様の対応済み（`hasSize: true`）

`lesson_title` も同じ仲間に入れるのが自然。

## 3. 修正方針

最小の変更で3つのバグを一括解消する。

### 3.1 CSS: パネルをflexコンテナにする

`static/css/broadcast.css:542-566` を修正。

```css
#lesson-title-panel {
  position: absolute;
  top: 2%; left: 35%;
  z-index: 12;
  display: flex;            /* ← 追加 */
  flex-direction: column;   /* ← 追加: justify-content を縦方向に効かせる */
  --bg-opacity: 0.7;
  background: rgba(10, 10, 30, var(--bg-opacity));
  border: 1px solid rgba(124, 77, 255, 0.4);
  border-radius: var(--item-border-radius, 0.5vw);
  padding: 0.4vw 1.5vw;
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  opacity: 0;
  transition: opacity 0.5s ease;
}
```

`#lesson-title-text` は単行テキストでwidth/height指定なし。flexアイテムとして自然に main-axis 方向に1行分の高さで収まり、`justify-content` で上下寄せされる。

### 3.2 JS: `height` を永続化＆復元する

`static/js/broadcast/globals.js:34` を `hasSize: true` に変更。

```js
{ id: 'lesson-title-panel', prefix: 'lesson_title', hasSize: true, defaultZ: 12, skipVisible: true },
```

これで `editSave()` が `width` / `height` を保存するようになる。

`static/js/broadcast/settings.js:148-158` で `height` の復元を追加（lesson_text と同じパターン）。

```js
if (s.lesson_title) {
  const ltpanel = document.getElementById('lesson-title-panel');
  if (ltpanel) {
    applyCommonStyle(ltpanel, s.lesson_title);
    if (s.lesson_title.width != null) ltpanel.style.width = s.lesson_title.width + '%';
    if (s.lesson_title.height != null) ltpanel.style.height = s.lesson_title.height + '%';
    const lttext = document.getElementById('lesson-title-text');
    if (lttext && s.lesson_title.fontSize != null) {
      lttext.style.fontSize = s.lesson_title.fontSize + 'vw';
    }
  }
}
```

CSSに `max-height` は無いので `maxHeight='none'` で打ち消す処置は不要（lesson_progress とは異なる）。

### 3.3 (任意) `applyCommonStyle` の verticalAlign フォールバック改善

style-utils.js のセレクタは現状 `'.custom-text-content, .child-text-content'` のみを探している。今回は CSS で `#lesson-title-panel` 自体を flex コンテナ化することで「パネルにフォールバック」を機能させる方針なので、style-utils.js は **触らない**。今後 lesson_text / lesson_progress / 子パネル等でも一貫して動くよう、共通仕様を「対象要素自体を flex column にすると panel-level の縦寄せが効く」と明文化することは考慮するが、本タスクのスコープ外とする。

## 4. 実装ステップ

1. `static/css/broadcast.css:542` の `#lesson-title-panel` に `display: flex; flex-direction: column;` を追加
2. `static/js/broadcast/globals.js:34` の `hasSize: false` → `true`
3. `static/js/broadcast/settings.js:148-158` の `lesson_title` ブロックに `width` / `height` 復元行を追加
4. `python3 -m pytest tests/test_broadcast_patterns.py -q` で再発防止ガードがgreenであることを確認
5. サーバー再起動 → `/broadcast` で実機確認
   - 編集モードで `#lesson-title-panel` の下端をドラッグして縦に伸ばす
   - 設定パネルの「垂直揃え」を `中央` / `下` / `上` に切り替え、テキストが追従することを確認
   - リロード（または `applySettings` 再走）後も縦幅とverticalAlignが維持されることを確認
   - `授業生成「#1」` 等の実発話で `showLessonTitle()` 経由でも崩れないか確認
6. DONE.md / TODO.md を更新（コミット前必須）

## 5. リスク・注意点

- **既存ユーザーのDBにある `lesson_title` 設定との互換性**: `width` / `height` キーは新規追加なので、未保存ユーザーは null のまま → 既存CSS（auto sizing）にフォールバック。後方互換あり。
- **`white-space: nowrap` との干渉**: `#lesson-title-text` は単行のままなので flex でも崩れない。長文タイトルはそもそも仕様外（必要なら別タスク）。
- **`reshowLessonTitleIfHasContent()` 等の既存フロー**: `panel.style.display = 'block'` を強制している（`static/js/broadcast/panels.js:401`）。これは flex を上書きしてしまうので、`'flex'` に変更するか、display を設定せず classList のみで visibility 制御する形に整える必要がある。**実装時に必ず修正すること**（panels.js:378, 401 の2箇所）。
- 同じく `panels.js:389` の `panel.style.display = 'none'` は問題なし（hide のため）。

## 6. 受け入れ基準

- [ ] 編集モードで `#lesson-title-panel` を縦に拡大→保存→リロードで高さが復元される
- [ ] 設定パネルの「垂直揃え」を切り替えると `#lesson-title-text` の位置が上/中央/下に変わる
- [ ] 試聴チェックリスト的な観点: 授業再生時に `showLessonTitle()` でフェードインしてもレイアウトが崩れない
- [ ] `tests/test_broadcast_patterns.py` がgreen
