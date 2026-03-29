# プラン: メインコンテンツ読み上げ機能

ステータス: 完了

## コンテキスト

教師モードで、メインコンテンツが授業全体の基盤となっている場合（例: 最初に出てくる会話文や文章で、それを使って授業全体を構成している場合）、キャラクターがその内容を実際に読み上げる/演じるようにしたい。

### 現状の問題
1. **コンテンツが200文字で切り詰められている** — `_format_main_content_for_prompt()` がpreviewを200文字に制限しており、LLMが全文を見られない
2. **「読み上げ」の概念がない** — content_typeごとの扱い方（conversation→役割分担、passage→先生が読む）は定義されているが、「実際に内容を読み上げる/演じる」かどうかの判断がない
3. **プロンプトの指示が弱い** — display_textカバー率80%のルールはあるが、メインコンテンツの原文を忠実に読み上げる明示的な指示がない

## 方針

`extract_main_content()`の段階で**LLMが`read_aloud`フラグを判定**し、後続のプロンプトに反映する。

- `read_aloud: true` → 授業の基盤コンテンツ。キャラが原文を読み上げる/演じる
- `read_aloud: false` → 参照用コンテンツ。解説・議論の素材として使うが、逐語的な読み上げは不要

## 実装ステップ

### Step 1: `_EXTRACT_MAIN_CONTENT_PROMPT` に `read_aloud` フィールド追加
**ファイル**: `src/lesson_generator.py` (L282-322)

- JSON出力に `read_aloud` (boolean) を追加
- 判定基準: 「この内容は授業全体の基盤であり、キャラクターが実際に読み上げる/演じる必要があるか？」
  - conversation (会話文) で role=main → 通常 true（授業がこの会話を中心に構成される）
  - passage (文章) で role=main → true（本文を読み上げる必要がある）
  - word_list / table → 通常 false（解説の中で触れればよい）
- `_normalize_roles()` で `read_aloud` のデフォルト値も補完

### Step 2: `_format_main_content_for_prompt()` の切り詰め緩和
**ファイル**: `src/lesson_generator.py` (L1519-1539)

- `read_aloud: true` かつ `role: "main"` → 全文を含める（上限2000文字）
- その他 → 従来通り200文字preview
- `🔊 読み上げ対象` / `🔊 READ ALOUD` マーカーを付与

### Step 3: `_build_structure_prompt()` に読み上げ指示を追加
**ファイル**: `src/lesson_generator.py` (L1542-1768)

EN/JP両方のプロンプトに以下を追加:

```
## メインコンテンツの読み上げ（🔊マーク付き）
🔊マークが付いたコンテンツは授業の核となる教材です。
キャラクターが原文を忠実に読み上げる/演じるセクションを授業序盤に設けること。

- conversation: 先生と生徒で役割を分けて会話を「演じる」。原文のセリフをそのまま使う
- passage: 先生が原文を読み上げ、その後解説する
- directionに原文の該当部分を含めること（例: 「会話のAの台詞 "Good morning!" を読む」）
```

### Step 4: `_director_review()` のレビュー観点に追加
**ファイル**: `src/lesson_generator.py` (L1988-2149)

- 🔊読み上げ対象コンテンツが実際にセリフの中で読み上げられているかチェック
- 読み上げ対象が省略されていたら不合格

### Step 5: テスト追加
**ファイル**: `tests/test_lesson_generator.py`

- `extract_main_content` が `read_aloud` フィールドを返すことを確認
- `_format_main_content_for_prompt` で `read_aloud=true` 時に全文が含まれることを確認
- `_build_structure_prompt` で `read_aloud=true` のコンテンツがある時に読み上げ指示が含まれることを確認

## 変更ファイル一覧

| ファイル | 変更内容 |
|---------|---------|
| `src/lesson_generator.py` | Step 1-4: プロンプト・フォーマット関数の更新 |
| `tests/test_lesson_generator.py` | Step 5: テスト追加 |

## 検証方法

1. `python3 -m pytest tests/test_lesson_generator.py -q` — 既存テスト + 新規テストが通ること
2. `python3 -m pytest tests/ -q` — 全テストが通ること
3. 手動テスト: 会話文メインの授業で「スクリプト生成」→ キャラが会話を演じるセクションが含まれることを確認（TODO 1.2に記載済み）

---

# Phase 2: 読み上げ導入の自然化

ステータス: 完了（Step 6-8 全完了）

## コンテキスト

Phase 1 で🔊読み上げ機能を実装したが、実際の授業で **唐突に読み上げが始まる** 問題が発生している。

例（現状の問題）:
```
ちょビ: 今日は英語の挨拶を学ぼう！じゃあ読むよ。"Good morning! How are you?" "I'm fine, thank you."
```

期待される自然な流れ:
```
ちょビ: 今日は英語の挨拶を学ぶよ！まずは教科書の会話を見てみよう。
ちょビ: AさんとBさんの会話だよ。先生がAさん役、なるこちゃんがBさん役ね！
なるこ: はーい！
ちょビ: じゃあいくよ。"Good morning! How are you?"
なるこ: "I'm fine, thank you. And you?"
ちょビ: "I'm great!" …っていう感じ！どうだった？
```

### 原因分析

現在の `_build_structure_prompt()` の読み上げ指示は「授業序盤に読み上げセクションを設ける」とだけ書いており、**導入の仕方**について指示がない:

```
授業序盤にキャラクターが原文を忠実に読み上げる/演じるセクションを設けること。
```

これだけだとLLMは「読み上げろ」という指示に従い、文脈の準備なくいきなり原文を読み始めてしまう。

## 方針

プロンプトに **読み上げ前の導入パターン** を明示する。構造デザイナー（`_build_structure_prompt`）とセリフ生成（`_generate_single_dialogue`）の両方に手を入れる。

## 実装ステップ

### Step 6: `_build_structure_prompt()` の読み上げ指示に導入パターンを追加
**ファイル**: `src/lesson_generator.py`

現在の読み上げ指示ブロックを以下のように拡張:

**EN版:**
```
## Reading aloud main content (🔊 marked items)
Items marked 🔊 READ ALOUD are the core teaching material for this lesson.

### Natural lead-in (IMPORTANT)
Do NOT jump straight into reading. Always include a lead-in turn BEFORE the read-aloud section:
1. **Context setting**: Teacher explains what they're about to read/perform ("Let's look at today's conversation", "Here's a passage about...")
2. **Role assignment** (conversation only): Teacher assigns roles ("I'll be Speaker A, you be Speaker B")
3. **Then read**: The actual read-aloud starts in the NEXT turn after setup

### Read-aloud rules by content_type
- conversation: Split roles between teacher and student to "perform" the conversation. Use the original lines verbatim
- passage: Teacher reads the original text aloud, then explains afterward
- Include the relevant original text in the direction (e.g., "Read Speaker A's line: 'Good morning!'")
- Do NOT paraphrase or summarize 🔊 content — use the original wording

### dialogue_plan structure for 🔊 content
Example for a conversation:
  1. teacher direction: "Introduce that they'll practice the conversation. Assign roles."
  2. teacher direction: "Read Speaker A's line: 'Good morning! How are you?'"
  3. student direction: "Read Speaker B's line: 'I'm fine, thank you.'"
  4. teacher direction: "React to the conversation. Transition to explanation."
```

**JP版:**
```
## メインコンテンツの読み上げ（🔊マーク付きアイテム）
🔊 読み上げ対象 と記されたアイテムは、この授業の核となる教材です。

### 自然な導入（重要）
いきなり読み上げを始めないこと。読み上げの前に必ず導入ターンを設けること:
1. **文脈の説明**: これから何を読む/演じるか説明する（「今日の会話を見てみよう」「こんな文章があるよ」）
2. **役割分担**（会話文のみ）: 役割を割り振る（「先生がAさん役、なるこちゃんがBさん役ね」）
3. **読み上げ開始**: 導入の次のターンから実際の読み上げを始める

### content_type ごとの読み上げルール
- conversation: 先生と生徒で役割を分けて会話を「演じる」。原文のセリフをそのまま使う
- passage: 先生が原文を読み上げ、その後解説する
- directionに原文の該当部分を含めること（例: 「会話のAの台詞 "Good morning!" を読む」）
- 🔊コンテンツを要約・言い換えしないこと — 原文のまま使う

### 🔊コンテンツ用の dialogue_plan 構成例
会話文の場合:
  1. teacher direction: 「会話の練習をすることを紹介。役割分担を説明する」
  2. teacher direction: 「Aの台詞を読む: 'Good morning! How are you?'」
  3. student direction: 「Bの台詞を読む: 'I'm fine, thank you.'」
  4. teacher direction: 「会話の感想を言い、解説に移る」
```

### Step 7: `_director_review()` のレビュー観点に導入チェックを追加
**ファイル**: `src/lesson_generator.py`

🔊レビュー観点に以下を追加:

```
- If 🔊 content reading starts without any lead-in (no context-setting, no role assignment) → mark as NOT approved
- The turn immediately before the first 🔊 read-aloud line should set up what is about to be read
```

### Step 8: テスト追加
**ファイル**: `tests/test_lesson_generator.py`

- `_build_structure_prompt` に🔊コンテンツがある場合、導入パターンの指示（"lead-in" / "導入"）が含まれることを確認
- `_director_review` に導入チェック観点（"lead-in" / "導入"）が含まれることを確認

## 変更ファイル一覧

| ファイル | 変更内容 |
|---------|---------|
| `src/lesson_generator.py` | Step 6-7: 読み上げ指示の拡張・レビュー観点追加 |
| `tests/test_lesson_generator.py` | Step 8: テスト追加 |

## 検証方法

1. `python3 -m pytest tests/ -q` — 全テスト通過
2. 手動テスト: 会話文メインの授業でスクリプト生成 → 読み上げ前に導入ターン（文脈説明・役割分担）が含まれること
