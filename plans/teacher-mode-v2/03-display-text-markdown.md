# 授業テキストパネルの書式対応

## ステータス: 未着手

## 背景

授業中に配信画面に表示される `display_text` は `.textContent` でプレーンテキスト表示のみ。
箇条書き・太字・コードブロック等の構造的情報を表現できない。

## 現状のコード

### broadcast.html側（`static/js/broadcast/panels.js:77-87`）

```javascript
function showLessonText(text) {
  const content = document.getElementById('lesson-text-content');
  content.textContent = stripLangTags(text);  // ← プレーンテキスト
  panel.style.display = 'block';
}
```

### スクリプト生成プロンプト

`display_text` の説明が「画面に表示するテキスト（要点・例文など自由形式）」とだけあり、Markdownが使えることを知らない。

## 改善内容

### 1. 軽量Markdownパーサー（panels.js内に自前実装）

外部ライブラリ不要で、以下の記法のみ対応する:

| 記法 | 変換先 |
|------|--------|
| `**太字**` | `<strong>太字</strong>` |
| `*斜体*` | `<em>斜体</em>` |
| `` `コード` `` | `<code>コード</code>` |
| `- リスト` | `<li>リスト</li>`（`<ul>`で囲む） |
| `1. 番号リスト` | `<li>番号リスト</li>`（`<ol>`で囲む） |
| 空行 | `<br>` |
| `### 見出し` | `<h3>見出し</h3>` |

### 2. XSS対策

- まずテキスト全体を `esc()` でHTMLエスケープ
- その後にMarkdown記法のみを変換
- `innerHTML` で設定（変換後は安全なタグのみ）

### 3. CSS追加

`broadcast.html` の `#lesson-text-content` にリスト・見出し・コード用のスタイル追加。

### 4. プロンプト更新

`lesson_generator.py` のスクリプト生成プロンプトに `display_text` でMarkdown記法が使えることを明記。

### 変更対象

- `static/js/broadcast/panels.js` — `showLessonText()` にMarkdownパース追加
- `static/broadcast.html` — `#lesson-text-content` のCSS追加
- `src/lesson_generator.py` — スクリプト生成プロンプトにMarkdown記法の指示追加

## リスク

- 自前パーサーの限界: テーブルやネスト等の複雑な記法は非対応 → 必要になったら marked.js 等に移行
- LLMがMarkdown以外の書式を出力する可能性 → プロンプトで制約
