# 授業モード: 字幕の消えが遅い問題の修正

## ステータス
- ステータス: 完了（案C ベース／授業モードのみ delaySeconds: 0 を渡す形で実装）
- 起票: 2026-05-05
- 実装: 2026-05-05
- TODO 起点: 「授業モードで読み上げのあとに字幕表示がなかなか消えない」

## 実装内容（2026-05-05）

ユーザー指示: 「とりあえずセリフ末尾もセクションの末尾も待ち時間０にして」

- `static/js/broadcast/panels.js` `fadeSubtitle(avatarId, opts={})` に `opts.delaySeconds` を追加。指定時は `dataset.fadeDuration` より優先。0以下の場合は `setTimeout` を経由せず即時に `.fading` クラスを付与
- `static/js/broadcast/lesson.js` `endDialogue` から `fadeSubtitle(avatarId, { delaySeconds: 0 })` を呼ぶように変更
- セクション末も `LessonPlayer.Stop()`／`PlayDialoguesAsync` のどちらも同じ `endDialogue()` 経路を通るので、セリフ末・セクション末ともに 0 待ち
- コメント応答（`speaking_end` → `fadeSubtitle()`）は引数なしのままなので従来通り `dataset.fadeDuration`（既定3秒）を使用
- CSS の `.fading` 1.5秒トランジションは維持。「待ち0」にしてもガクッとは消えず1.5秒で滑らかにフェードアウト
- テスト: `pytest -q -m "not slow"` 1282 passed

## 背景

授業モード（lesson_runner / C# `LessonPlayer`）で TTS の読み上げが終わった後、字幕が消えるまで体感で長すぎる。同じ仕組みをコメント応答（comment_reader）も使っているので、調整によってはコメント応答にも影響する点に注意。

## 現状の動作（実装確認済み）

字幕の表示・消去は `static/js/broadcast/panels.js` に集約されており、授業モード／コメント応答とも同じ関数を呼んでいる。

### 表示
- C# `LessonPlayer.PlayDialoguesAsync` (`win-native-app/WinNativeApp/Streaming/LessonPlayer.cs:488`)
  → `window.lesson.startDialogue(data)` を呼ぶ
  → `static/js/broadcast/lesson.js:63` `showSubtitle({...duration})` で字幕を表示

### 消去（問題箇所）
- C# が音声再生完了後に `window.lesson.endDialogue()` を呼ぶ (`LessonPlayer.cs:504`)
  → `static/js/broadcast/lesson.js:90` `fadeSubtitle(avatarId)`
  → `static/js/broadcast/panels.js:111-130`:
    ```js
    const duration = parseFloat(el.dataset.fadeDuration || 3) * 1000;
    setTimeout(() => { el.classList.add('fading'); el.classList.remove('visible'); }, duration);
    ```
- `el.dataset.fadeDuration` は `static/js/broadcast/settings.js:127` で DB の `subtitle.fadeDuration` から流し込まれる（既定 **3 秒**, min=1, max=10）
- `.fading` のCSSトランジションが更に **1.5 秒**（`static/css/broadcast.css:63`）

→ **音声終了から完全消去まで 約 4.5 秒**。

### 連続セリフでは問題が出にくい理由
- 次の `showSubtitle()` が冒頭で `clearTimeout(timer)` してフェード予約を取り消す（`panels.js:62`）
- そのため同一アバターで連続するセリフは即座に上書きされる

### 滞留が目立つケース（授業モード）
1. **セクションの最後のセリフ**: 次の `startDialogue` が来ないため、4.5 秒間そのまま残る
2. **セクション末の `WaitSeconds` 待機中**: `LessonPlayer.cs:447-451` で gap が入るので可視化される
3. **questionセクションの待機中**: `LessonPlayer.cs:438` の `WaitSeconds` 中に字幕が残る

### コメント応答側の状況
コメント応答も同じ `fadeSubtitle` 経由で消されるので、同じ4.5秒の遅延が起きている。
ユーザーから「コメントは気にならない」とは言われていない — コメントモードでも同じ問題があり得ることを前提に方針を考える。

## 方針案（ユーザー判断待ち）

どの方針でいくか、または組み合わせるかを選択してほしい。

### 案 A: 既定値そのものを短くする（最小修正・全モードに適用）
- `scripts/routes/items.py:91,98` の `default: 3` → `default: 1`（または 0.5）
- `static/js/broadcast/panels.js:120` のフォールバック `|| 3` → `|| 1`
- DBにすでに値が入っているユーザーは管理画面で再設定が必要

**メリット**: 実装が一行レベル、授業モード／コメント応答どちらにも効く
**デメリット**: コメント応答の余韻も短くなる。「コメントは余韻ほしい」と後から言われた場合に分けられない

### 案 B: スライダー下限を 1 → 0.2 に緩和してユーザーが調整可能にする
- `scripts/routes/items.py:91,98` の `"min": 1` → `"min": 0.2`
- 既定値は据え置きまたは併せて短く
- ユーザーが管理画面の Layout で 0.5 秒等に下げられる

**メリット**: 実装は最小、ユーザーが好みに合わせられる
**デメリット**: 授業／コメント共通設定なのでモード別に分けられない

### 案 C: モード別フェード時間（柔軟・実装はやや増える）
- `panels.js:111` の `fadeSubtitle` を `(avatarId, opts)` に拡張し、`opts.delaySeconds` があれば `dataset.fadeDuration` より優先
- `lesson.js:90` の `endDialogue` から `fadeSubtitle(avatarId, { delaySeconds: 0.5 })` のように渡す
- comment_reader 側（`websocket.js:27-28` の `speaking_end`）は既存のままにするか、別の値で渡す
- さらに DBキーを `subtitle.lessonFadeDuration` / `subtitle.commentFadeDuration` に分けて、管理画面でモード別に設定可能にする拡張も可能

**メリット**: 授業／コメントを別々にチューニングできる
**デメリット**: 実装が広がる（panels.js / lesson.js / websocket.js / 必要ならitems.py / settings.js）

### 案 D: セクション末の明示的な早期フェードのみ追加
- `LessonPlayer.PlaySectionInternalAsync` の最後（`LessonPlayer.cs:444` `hideText()` の直前）に
  `InjectJs?.Invoke("if(window.lesson)window.lesson.fadeSubtitlesNow()")` を追加し、
  panels.js に「即座に `.fading` を付けるバージョン」を新設
- セクション内の最後以外は既存の余韻のままにする

**メリット**: セクション内の連続セリフは余韻を保ちつつ、セクション境界だけ素早く消える
**デメリット**: 「最後のセリフだけ短く」になるため、各セリフ末の長さは変わらない。ユーザーの不満が「セクション境界だけ」ならピンポイントで効くが、「セリフ末すべて」ならこれでは解決しない

## 確認したいこと（実装前にユーザーに聞く）

- 不満の主な対象は **(a) 各セリフの末尾** か **(b) セクションの末尾** か
- コメント応答の字幕余韻を **同じく短くしてよい** か **据え置き** か

回答により以下のおすすめが変わる:

| 対象 | コメント余韻 | 推奨 |
|------|-----|------|
| 各セリフ末 | 短くしてよい | **案 A**（既定 3 → 1） |
| 各セリフ末 | 据え置き | **案 C**（モード別） |
| セクション末のみ | どちらでも | **案 D** |

## 実装ステップ（方針確定後に詳細化）

ユーザーの回答に応じて、上記の案 A〜D のいずれかに沿って実装する。
実装ステップの細目はこの節をその時点で書き直す（仮置きしない）。

## リスク / 注意

- `fadeSubtitle` の呼び出し箇所（grep 確認済み）: `lesson.js:90`, `websocket.js:27-28`（`speaking_end`）, `panels.js:114-115`（再帰）
- DB の `broadcast_items` にユーザーが既に値を保存している場合、案A／案Bでデフォルトを変えてもDB値が優先される。実機確認時は管理画面の `subtitle.fadeDuration` の現状値を一度確認すること
- `.fading` のCSSトランジション（1.5秒）は変えない。これを変えるとガクッと消える違和感が出る
- セクション末の `WaitSeconds` が 0 のとき、字幕が消える前に次のセクションが始まる可能性は低いが、その場合は次の `showSubtitle` が clearTimeout してくれるので問題なし

## 関連ファイル

- `static/js/broadcast/panels.js:111-130` — fadeSubtitle 本体（修正対象）
- `static/js/broadcast/lesson.js:90` — endDialogue → fadeSubtitle 呼び出し（修正対象）
- `static/js/broadcast/websocket.js:27-28` — comment_reader 側（変更しない）
- `win-native-app/WinNativeApp/Streaming/LessonPlayer.cs:488,504` — startDialogue/endDialogue 呼び出し（変更しない）
- `static/css/broadcast.css:63-64` — `.fading`（1.5秒）のCSS（変更しない）
- `scripts/routes/items.py:91,98` — fadeDuration スライダー定義（案B採用時のみ変更）
