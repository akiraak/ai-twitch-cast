# プラン: セクションコンテンツ（display_text）の読み上げ強化

## ステータス: 未着手

## 背景

教師モードで画面中央に表示される `display_text`（セクションコンテンツ）には、例文・単語・比較表・会話文など教材の核となる情報が含まれる。しかし現状では、キャラクターの対話（dialogues）が display_text の内容を**参考にしつつも実際に読み上げない**ことがある。

例えば display_text に `"フォーマル: Good morning / Good afternoon\nカジュアル: Hi / Hey / What's up?"` と書いてあっても、先生が「フォーマルとカジュアルな挨拶がありますね」と要約するだけで、具体的な例文を読まないケースが発生する。

**視聴者は画面を見ているので、画面に表示された内容を先生/生徒が読み上げなければ、表示と音声が乖離して違和感が生まれる。**

## ゴール

- display_text に含まれる**メインコンテンツの文章・会話文は必ず読み上げる**
- その他の内容（表形式のデータ、補足情報など）もできるだけ読み上げる
- 読み上げは自然な対話の中で行う（棒読みにならない）

## 現状の仕組み

### データフロー

```
display_text → 画面表示のみ（lesson_text_show WebSocket）
dialogues[].content → 字幕表示
dialogues[].tts_text → 音声合成（TTS）
```

display_text は画面表示専用で、音声にはならない。音声になるのは dialogues の中身のみ。

### スクリプト生成パイプライン

1. **監督（Director）** が `display_text` + `dialogue_directions` を設計
   - `dialogue_directions[].key_content` で「このターンで言及すべき内容」を指定できる（既存機能）
   - しかし display_text の内容を網羅的に key_content に含める明示的なルールがない
2. **キャラクターAI** が各ターンのセリフを個別生成
   - `_generate_single_dialogue()` で `display_text[:200]` がコンテキストとして渡される
   - key_content が渡されていれば、キャラクターAIはそれを自然に含める

## 修正箇所

### 変更: 監督プロンプトに「display_text 読み上げルール」を追加

**ファイル**: `src/lesson_generator.py` — Director プロンプト（日英両方）

**追加ルール**（既存の `### display_text` セクションの末尾に追加）:
- display_text に含まれるすべての例文・会話文・重要フレーズは、必ず dialogue_directions の `key_content` に分配すること
- 特にメインコンテンツの文章・会話文は 1 つも漏らさず key_content に含めること
- 表形式データやリストは、重要な項目を key_content に含めること
- display_text の内容が多い場合は複数ターンに分けて分配する

**理由**: 監督が key_content に display_text の内容を適切に分配すれば、下流の `_generate_single_dialogue()` は既に key_content を「このターンで触れるべき内容」としてキャラクターAIに渡す仕組みが動いているため、追加変更なしで読み上げが実現される。

## 影響範囲

### 変更されるファイル
| ファイル | 変更内容 |
|---------|---------|
| `src/lesson_generator.py` | 監督プロンプト（日英）に display_text 読み上げルール追加 |

### 変更されないもの
- `prompt_builder.py` — キャラクターAIは key_content 経由で内容を受け取るため変更不要
- `lesson_runner.py` — 再生ロジックは変更不要
- `broadcast.html` — 画面表示は変更不要
- DB スキーマ — 変更不要

### 既存のTTSキャッシュへの影響
- プロンプト変更はスクリプト**再生成**時にのみ反映される
- 既存のスクリプト・TTSキャッシュは影響なし

## 別課題（TODO登録済み）
- display_text が200文字で切り詰められる問題は、表示分割等の別対策が必要（別途対応）

## リスク

### セリフが長くなりすぎる
- display_text の内容をすべて読み上げると、1ターンのセリフが長くなる可能性
- **対策**: key_content を複数ターンに分配することで、1ターンあたりの負荷を分散（監督プロンプトで指示）

### テスト
- `test_lesson_generator.py` — プロンプト文字列のテストがある場合は更新
- 手動テスト: スクリプト再生成 → display_text の内容がセリフに含まれているか確認
