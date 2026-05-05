# 授業中テキストパネルのサイズ・文字サイズ改善

## 背景

授業モード（lesson）でセクションごとに表示される `#lesson-text-panel`（`display_text` を出すパネル）について、視聴体験で2つの問題が出ている。

- **パネルが大きすぎることがある** — 内容に対して幅・高さが広く、余白が目立つセクションがある
- **文字が小さい** — デフォルト時もLLM指定時も、配信解像度から見ると文字が読みづらい

### 現状の値

| レイヤー | 値 | 場所 |
|---------|----|------|
| CSS デフォルト幅 | `width: 55%` | `static/css/broadcast.css:511` `#lesson-text-panel` |
| CSS デフォルト最大高さ | `max-height: 60%` | 同上 |
| CSS デフォルト フォント | `font-size: max(0.8vw, 1.4vw)` （実質 1.4vw） | `#lesson-text-content` (broadcast.css:533) |
| クランプ範囲 | `maxHeight 10–90%` / `width 10–95%` / `fontSize 0.5–3.0vw` | `static/js/broadcast/panels.js:198–209` |
| LLMガイドライン | 短: `maxH 20–30 / fs 1.4–1.8` / 中: `35–50 / 1.2–1.4` / 長: `55–70 / 1.0–1.2` | `prompts/lesson_generate.md:200–204`, `prompts/lesson_improve.md:75–76` |

データの流れ:

1. `lesson_generate.md` / `lesson_improve.md` に従って LLM がセクションごとに `display_properties` を生成（省略可）
2. DB（`lesson_sections.display_properties` JSON文字列）に保存
3. `lesson_runner._parse_display_properties()` がパース → `lesson_load.sections[].display_properties` でC#へ
4. `LessonPlayer.cs` が `window.lesson.showText(text, displayProperties)` を呼ぶ
5. `panels.js:showLessonText()` で `panel.style.{maxHeight,width}` / `content.style.fontSize` をオーバーライド。`displayProperties` が `null/undefined` ならCSSデフォルトに戻す

### 問題点の切り分け

- **文字が小さい**: CSSデフォルト 1.4vw も、LLMガイドラインの下限 1.0vw も、1080p (1vw=10.8px) 換算で 11–15px 相当。配信視聴では小さい
- **パネルが大きすぎる**: デフォルト `width 55% / maxH 60%` は短文セクションでは過剰。`display_properties` 未指定のセクションがそのままデフォルトを引いてしまう
- **不均一**: LLMが付けた値、未指定セクション、CSSデフォルトが混在し、見た目に揺れがある

## 方針

3層で改善する。

### 1. CSSデフォルトの底上げ（最小コストで効く）

`#lesson-text-content` のフォントを **1.4vw → 1.7vw** に上げる。`max(...)` 構文は不要なので外す。

`#lesson-text-panel` のデフォルトは `width: 55% / max-height: 60%` のままだが、**コンテンツに応じて縮む** ように `width` を `min(55%, max-content)` 系に変更検討（または height/width を auto + max-* で制限）。
→ `width: max-content` は配置崩れリスクが高いので、デフォルトは現状維持にして「LLMが必ず `display_properties` を出す」運用に倒す方が安全。

採用案: **fontSizeデフォルトのみ上げる。width/maxHeight はLLM側で必ず指定させる**。

### 2. プロンプトのガイドライン更新

`prompts/lesson_generate.md` と `prompts/lesson_improve.md` を更新:

- **`display_properties` を必須化**（省略しない）
- フォントサイズの下限を引き上げ:
  - 短い (1-2行): `maxH 20–28 / fontSize 1.8–2.2` （現: 1.4–1.8）
  - 中程度 (3-5行): `maxH 32–45 / fontSize 1.6–1.8` （現: 1.2–1.4）
  - 長い (コード/リスト): `maxH 50–65 / fontSize 1.4–1.6` （現: 1.0–1.2）
- `width` も指定するよう追加（短: 35–45 / 中: 45–55 / 長: 55–70）
- 「**パネルは内容に対して過剰に大きくしない。視聴者は1080p画面で見るので、フォントは小さくしすぎない**」という方針コメントを追加

### 3. 自動フォールバック（クライアント側）

`panels.js:showLessonText()` で、`displayProperties` が空/未指定のときに **テキスト長から自動推定** する補正を入れる。

```js
function _autoSizeFromText(text) {
  const len = (text || '').length;
  const lines = (text || '').split('\n').length;
  // 概算: 文字数 + 行数で長さを推定
  if (len < 60 && lines <= 2)      return { maxHeight: 25, width: 40, fontSize: 2.0 };
  if (len < 200 && lines <= 5)     return { maxHeight: 40, width: 50, fontSize: 1.7 };
  return { maxHeight: 60, width: 60, fontSize: 1.5 };
}
```

`displayProperties` の各フィールドが欠けていれば、自動推定値で補完する（明示指定があればそれを優先）。
これでLLMが `display_properties` を付け忘れた既存セクションでも見栄えが揃う。

### 4. 既存セクションへの遡及（必要に応じて）

`lesson_id=100` の Step 4 試聴中なので、その授業の各セクションの見た目を確認し、不適切な値があれば管理画面から手動で修正、または `prompts/lesson_improve.md` 経由で再生成。

一括スクリプトは作らず、運用で対応する（教材によって最適値が違うため）。

## 実装ステップ

1. **CSS更新**: `static/css/broadcast.css` の `#lesson-text-content` フォントを 1.7vw に上げる
2. **自動フォールバック**: `static/js/broadcast/panels.js:showLessonText()` に `_autoSizeFromText()` を追加し、欠けたフィールドを補完
3. **プロンプト更新**: `prompts/lesson_generate.md` と `prompts/lesson_improve.md` のガイドラインテーブルを更新（fontSize底上げ + width追加 + 必須化）
4. **動作確認**: lesson_id=100 を再生して各セクションの見た目を確認
5. **テスト**: `python3 -m pytest tests/test_broadcast_patterns.py tests/test_lesson_*.py -q` がパスすることを確認

## 影響範囲

| ファイル | 変更内容 |
|---------|---------|
| `static/css/broadcast.css` | `#lesson-text-content` の `font-size` 引き上げ |
| `static/js/broadcast/panels.js` | `showLessonText()` に自動フォールバック追加 |
| `prompts/lesson_generate.md` | display_properties ガイドライン更新 |
| `prompts/lesson_improve.md` | display_properties ガイドライン更新 |

C#側 (`LessonPlayer.cs`) と `lesson_runner.py` は変更不要。`display_properties` の流れはそのまま。

## リスク

- **既存の授業の見た目が変わる**: lesson_id=100 を含む全授業に影響。事前に試聴で確認する
- **自動フォールバックが想定外のセクションに当たる**: コードブロック中心など特殊なケースで意図と違う見た目になる可能性 → LLM指定があれば必ず優先するため、明示指定でカバーできる
- **プロンプト変更で新規生成のスタイルが変わる**: 想定通り。確認した上で本採用

## ステータス

起案中（2026-05-05）。実装着手前。
