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
