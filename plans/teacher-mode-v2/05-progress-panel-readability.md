# 授業進捗パネル表示改善プラン

## ステータス: 完了

## 現状の問題

進捗パネルの各項目は `content`（発話テキスト）の先頭40文字を表示している。

```
lesson_runner.py _notify_status():
  "summary": (s.get("content") or "")[:40]
```

### 現在の表示例
```
🎬 みなさん、こんにちは！ちょビです！今日はね、英語での『初めまして
📖 はい、では早速、今日の教材の主人公、Kenjiさんの自己紹介文を見てい
📖 次に、Kenjiさんへのインタビュー音声を聞いて、情報を効率的にキ
❓ さあ、リスニングで得た情報をもとに、Kenjiさんに関する質問に答え
🏁 今日のレッスン、どうでしたか？自己紹介の仕方、キーワードで情報を
```

問題点:
- 発話テキストの冒頭は「みなさん、こんにちは！」等の挨拶で内容が伝わらない
- 40文字で途中で切れる
- 各セクションが何について話すのか一目でわからない

### 根本原因

監督（Director）がプラン生成時に各セクションの `title` と `summary` を作成しているが、スクリプト生成→DB保存の過程で**捨てられている**。

```
監督のプラン: { section_type, title, summary, emotion, has_question, wait_seconds }
                                  ↓ スクリプト生成
DBに保存:     { section_type, content, tts_text, display_text, emotion, ... }
                              ^^^  title/summaryが消失
```

## 改善案

監督の `title` をDBに保存し、進捗パネルで使う。

### 改善後の表示イメージ（監督のtitleを使用）
```
🎬 英語の「初めまして」を攻略しよう！
📖 自己紹介の基本テクニック
📖 リスニングで情報をキャッチする方法
❓ 初対面のNG質問クイズ
🏁 今日のまとめ
```

## 実装ステップ

### 1. DB: `lesson_sections` に `title` カラム追加

`src/db.py`:
- テーブル定義に `title TEXT DEFAULT ''` を追加
- `add_lesson_section()` に `title` 引数追加
- `update_lesson_section()` の `allowed` に `title` 追加
- マイグレーション: ALTER TABLE で既存DBに `title` カラム追加

### 2. スクリプト生成時に監督の `title` を保持

`scripts/routes/teacher.py` のスクリプト生成→DB保存処理:
- `generate_lesson_script_from_plan()` 呼び出し時、`plan_sections` の `title` を取得
- `db.add_lesson_section()` に `title` を渡す

### 3. 進捗パネルのsummaryをtitleに変更

`src/lesson_runner.py` の `_notify_status()`:
```python
# Before
"summary": (s.get("content") or "")[:40],

# After — 監督のtitleを優先
"summary": s.get("title") or (s.get("content") or "")[:40],
```

### 影響範囲
- `src/db.py` — カラム追加 + API変更
- `scripts/routes/teacher.py` — title保存
- `src/lesson_runner.py` — summary表示ロジック（1行）
- フロントエンド変更なし
- 既存レッスン: titleが空なので従来通りcontent先頭40文字にフォールバック
