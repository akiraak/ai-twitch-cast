# 字幕パネルのオーバーフロー対策

## ステータス: 未着手

## 背景

授業モードでセクション開始時の長いセリフが字幕パネルに表示されると、パネルが縦に無制限に拡大し、教材コンテンツ（lesson-text-panel）を覆い隠してしまう。

### スクリーンショット
`debug-ss/over-chat.png` — 「Kenjiの自己紹介文を出すね。読み上げるよ。Hi. My name is Kenji...」という長いセリフが字幕パネルを巨大化させ、教材テキストが全く読めなくなっている。

### 根本原因

- `.subtitle-panel` CSS に `max-height` がない → 長文でパネルが無制限に拡大
- 字幕 z-index: 20 > 教材パネル z-index: 12 → 字幕が教材を完全に覆う
- `split_sentences()` は `。！？` でのみ分割 → 英語の長文は分割されない

### 関連ファイル

| ファイル | 役割 |
|---------|------|
| `static/css/broadcast.css` (行42-93) | `.subtitle-panel` CSS |
| `static/js/broadcast/panels.js` (行17-44) | `showSubtitle()` |
| `src/lesson_runner.py` (行509-567) | `_play_single_speaker()` — セリフ分割・再生 |
| `src/speech_pipeline.py` (行38-55) | `split_sentences()` — 文分割ロジック |

---

## 対策案

### 案A: CSS max-height 制限

**概要**: 字幕パネルにCSSで高さ上限を設け、超過分は非表示にする。

**変更箇所**: `static/css/broadcast.css`
```css
.subtitle-panel {
  max-height: 25vh;
  overflow: hidden;       /* スクロールバーは出さない */
}
```

| メリット | デメリット |
|---------|----------|
| 最小限の変更（CSS 2行） | テキストの下部が見切れる |
| 既存ロジックに影響なし | 見切れていることが視聴者にわからない |
| 確実に被りを防げる | 長文の後半が読めない |

---

### 案B: フォントサイズ自動縮小

**概要**: テキスト長に応じて字幕のフォントサイズを段階的に縮小し、パネルサイズを抑える。

**変更箇所**: `static/js/broadcast/panels.js` の `showSubtitle()`
```javascript
const len = speechEl.textContent.length;
if (len > 200)      speechEl.style.fontSize = '1.0vw';
else if (len > 100) speechEl.style.fontSize = '1.4vw';
else                 speechEl.style.fontSize = '';  // デフォルト 1.875vw
```

| メリット | デメリット |
|---------|----------|
| テキスト全文が表示される | 文字が小さすぎると読めない |
| CSS max-heightと組み合わせ可能 | 極端に長い文は縮小しても収まらない |
| 実装が簡単 | フォントサイズの閾値チューニングが必要 |

---

### 案C1: テキスト分割表示（TTS も分割）

**概要**: 長い字幕テキストを一定文字数ごとに分割し、各チャンクごとにTTS生成・字幕表示・再生を行う。

**変更箇所**: `src/speech_pipeline.py` の `split_sentences()` または `src/lesson_runner.py`

- `split_sentences()` を拡張し、英語のピリオド `.` でも分割する
- あるいは文字数ベースで最大N文字ごとに分割（句読点の位置で調整）
- 各チャンクごとにTTS生成・字幕表示・再生を行う

| メリット | デメリット |
|---------|----------|
| 全文が順番に表示される | TTS分割が増え、音声の自然さが低下する可能性 |
| 字幕サイズが常に適切 | 分割位置が不自然だと読みにくい |
| 読み上げと字幕が同期する | 実装が中程度の複雑さ |

---

### 案C2: 字幕のみ分割表示（TTSは1つ）

**概要**: TTSは長文のまま1つの音声として生成し、字幕表示だけを時間ベースで分割切り替えする。音声の自然さを維持しつつ、字幕の被りを防ぐ。

**変更箇所**: `static/js/broadcast/panels.js` の `showSubtitle()`

- 長文テキストを一定文字数（例: 80文字）ごとに句読点位置でチャンク分割
- 音声の再生時間を均等割りし、タイマーで字幕チャンクを順次切り替え表示
- 例: 240文字 → 3チャンク、音声10秒 → 3.3秒ごとに字幕切り替え

```javascript
function showSubtitle(data) {
  const text = stripLangTags(data.speech);
  if (text.length <= 80) {
    // 短文: 従来通り一括表示
    showSubtitleSimple(el, data);
    return;
  }
  // 長文: チャンク分割 → タイマーで順次表示
  const chunks = splitIntoChunks(text, 80);
  const interval = (data.duration || 5000) / chunks.length;
  chunks.forEach((chunk, i) => {
    setTimeout(() => {
      el.querySelector('.speech').textContent = chunk;
    }, interval * i);
  });
}
```

| メリット | デメリット |
|---------|----------|
| TTSは分割しないので音声品質に影響なし | 字幕と読み上げ箇所がズレる可能性 |
| 字幕サイズが常に適切 | 音声の再生時間をJS側が知る必要がある |
| Python側の変更が不要（JS完結） | 均等割りは読み上げ速度と一致しない |
| 短文は従来通りの表示 | 切り替え時に一瞬ちらつく可能性 |

---

### 案D: display表示中は字幕を出さない

**概要**: 教材コンテンツ（lesson-text-panel）が表示されている間は、字幕パネルを非表示にする。音声のみで伝える。

**変更箇所**: `static/js/broadcast/panels.js` または `src/lesson_runner.py`

- 方法1（JS側）: `showSubtitle()` で lesson-text-panel が表示中なら字幕を出さない
- 方法2（Python側）: `_play_single_speaker()` で `display_text` がある場合、字幕の `speech` を空にする

| メリット | デメリット |
|---------|----------|
| 被り問題が完全に解消 | 字幕がないと聞き取れないときに困る |
| 実装がシンプル | 教材と字幕の両方を見たい場面もある |
| 画面がスッキリする | 耳が不自由な視聴者への配慮が減る |

---

### 案E: display表示中は字幕を縮小・移動

**概要**: 教材コンテンツが表示されている間は、字幕を画面下部に小さく表示する（位置・サイズを動的に変更）。

**変更箇所**: `static/css/broadcast.css` + `static/js/broadcast/panels.js`

- 教材パネル表示中は `.subtitle-panel` に `.compact` クラスを付与
- `.compact` 時: フォントサイズ縮小、max-width縮小、max-height制限、下部に固定
- 教材パネル非表示時は通常サイズに戻る

```css
.subtitle-panel.compact {
  max-height: 12vh;
  max-width: 45%;
  overflow: hidden;
}
.subtitle-panel.compact .speech {
  font-size: 1.1vw;
}
```

| メリット | デメリット |
|---------|----------|
| 字幕は常に表示される | コンパクト時の可読性が下がる |
| 教材との被りを大幅に軽減 | 教材パネルの表示状態を字幕側が知る必要がある |
| 状況に応じた見せ方ができる | 実装がやや複雑 |

---

### 案F: 字幕を教材パネル内に統合表示

**概要**: 教材パネルが表示されている間は、字幕を独立パネルではなく教材パネルの下部に「現在のセリフ」として埋め込む。

**変更箇所**: `static/broadcast.html` + `static/css/broadcast.css` + `static/js/broadcast/panels.js`

- lesson-text-panel の下部に字幕表示エリアを追加
- 教材パネルの `max-height` 内で字幕と教材が共存
- スクロールは教材パネルの既存 `overflow-y: auto` で処理

| メリット | デメリット |
|---------|----------|
| z-index問題が根本解消 | 教材パネルの設計変更が必要 |
| 教材と字幕が一体で見やすい | 教材パネル非表示時の字幕表示をどうするか |
| スクロールが自然 | 実装コストが高い |

---

### 案G: display_text読み上げ時のみ字幕を出さない

**概要**: 教材テキスト（display_text）の読み上げ部分に限り、字幕を出さない。教材テキストは既に画面上の lesson-text-panel に表示されているため、同じ内容を字幕で重ねて表示する必要がない。導入セリフ（「じゃあ画面に出すね」等）やdisplay_text以外のセリフは通常通り字幕を表示する。

**変更箇所**: `src/lesson_runner.py` の `_play_single_speaker()` / `_play_dialogues()`

- セクションに `display_text` がある場合、content のうち display_text と重複する部分の字幕表示をスキップ
- 具体的には、content が display_text を含む（または display_text そのものである）パートで `subtitle` の `speech` を空にする、または `notify_overlay` を呼ばない
- display_textと無関係なセリフ（導入の一言、感想など）は通常通り字幕を出す

**判定方法の例**:
```python
# split後の各パートが display_text に含まれるかで判定
for part in content_parts:
    is_display_reading = display_text and part.strip() in display_text
    subtitle_speech = "" if is_display_reading else part
    await self._speech.speak(part, subtitle={
        "speech": subtitle_speech, ...
    }, ...)
```

| メリット | デメリット |
|---------|----------|
| 被る場面だけピンポイントで解消 | display_textと完全一致しない場合の判定が難しい |
| 短いセリフの字幕は維持される | 教材を見ていない視聴者には読み上げ内容がわからない |
| 教材テキストが画面に出ているので情報欠落なし | 判定ロジックの実装・テストが必要 |
| 他の場面（コメント応答等）に影響なし | |

---

## 推奨

- **案G**: 問題が起きる場面（display_text読み上げ）だけをピンポイントで対処。教材が画面に出ているので字幕を省略しても情報欠落がない。最も合理的
- **案A+B**: 汎用的な保険。案Gと組み合わせると堅牢（Gで大半を防ぎ、A+Bで想定外の長文もカバー）
- **案C**: 根本的にセリフの分割単位を適切にすれば、字幕が大きくなること自体がなくなる。ただしTTS分割の品質影響を要検証
- **案D**: 案Gのより広範な版。display_text以外のセリフも全部消すので副作用が大きい
- **案E**: 案A+Bに近いが、教材パネルの表示状態連携が必要でやや複雑
- **案F**: 理想的だが工数が大きい

ユーザーの判断で選択する。
