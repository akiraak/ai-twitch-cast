# メインコンテンツの読み上げ方式改善（文章→先生/会話→二人で）

## ステータス: Step 2 完了

## 背景

現状、display_text の読み上げルールは「漏れなく読み上げろ」という一律の指示のみ。
コンテンツの種類によって最適な読み上げ方が異なる：

- **文章・説明文**: 先生が読み上げ、生徒がリアクションする
- **会話文・ダイアログ**: 先生と生徒で役を分けて演じる（Aさん→先生、Bさん→生徒）
- **単語リスト・フレーズ集**: 先生が読み上げ→生徒がリピートまたは使い方を質問

現状ではこの区別がないため、会話文なのに先生が一人で全部読んだり、文章なのに不自然に分割されたりする。

さらに、画像やURLからのテキスト抽出で**無駄な記号・装飾文字が大量に混入する問題**がある：
- `---------------` のような水平線がテキストの半分を占める
- `★☆★☆★` `===` `***` などの装飾記号
- HTMLの残骸（`&nbsp;` `&amp;` 等）
- 連続する空行

これらのノイズが後続のLLM処理（構造生成・セリフ生成）の品質を下げている。

## 方針

1. テキスト抽出直後に**クリーニング処理**を入れてノイズを除去
2. クリーニング済みテキストからメインコンテンツの種別を識別・構造化
3. 以降のパイプライン（構造生成・セリフ生成・監督レビュー）で活用する

## データフロー

```
画像/URL → テキスト抽出（既存） → メインコンテンツ抽出（Step 1: 新規）
  → extracted_text に構造化データを付加して保存
  → Phase B-1（構造生成）で content_type に応じた dialogue_plan 設計（Step 2）
  → Phase B-2（セリフ生成）で読み上げ方が反映される
  → Phase B-3（監督レビュー）で種別に合った読み方かチェック（Step 3）
```

## 実装ステップ

### Step 1: テキスト抽出後のクリーニング処理

`src/lesson_generator.py` に `clean_extracted_text()` を新設。
テキスト抽出直後（LLM呼び出し前）に呼び、ノイズを除去する。

```python
def clean_extracted_text(text: str) -> str:
    """抽出テキストから無駄な記号・装飾を除去する"""
```

**除去対象（正規表現ベース、LLM不要）:**
- 連続するハイフン・ダッシュ: `---+` → 空行1つに置換
- 連続する等号・アスタリスク・チルダ等: `===+`, `\*\*\*+`, `~~~+` → 除去
- 装飾記号の連続: `★☆` `●○` `■□` `◆◇` `▲△` 等が3つ以上連続 → 除去
- HTMLエンティティ残骸: `&nbsp;` `&amp;` `&lt;` `&gt;` → 対応文字に置換
- 連続する空行: 3行以上の空行 → 空行2つに圧縮
- 先頭・末尾の空白行をstrip

**呼び出し箇所:**
- `extract_text_from_image()` の `return` 前
- `extract_text_from_url()` の `return` 前

**テスト:** `tests/test_lesson_generator.py` に `clean_extracted_text` のユニットテスト追加

### Step 2: テキスト抽出時にメインコンテンツを識別・構造化

`src/lesson_generator.py` に `extract_main_content()` を新設。
抽出済みテキスト（`extracted_text`）を受け取り、メインコンテンツを識別して構造化データを返す。

```python
def extract_main_content(extracted_text: str) -> list[dict]:
    """抽出テキストからメインコンテンツを識別・分類する

    Returns:
        [
            {
                "content_type": "conversation",  # conversation / passage / word_list / table
                "content": "A: Good morning!\nB: Good morning! How are you?",
                "label": "Morning Greeting Conversation"
            },
            {
                "content_type": "passage",
                "content": "Formal greetings are used in business...",
                "label": "Explanation of formal greetings"
            },
            ...
        ]
    """
```

LLMに以下を判定させる：
- `conversation`: 会話文（A: / B: のような対話形式）
- `passage`: 文章・説明文（段落テキスト）
- `word_list`: 単語リスト・フレーズ集
- `table`: 表・比較データ

**呼び出しタイミング**: `extract_lesson_text` / `add_lesson_url` のAPIハンドラで、テキスト抽出直後に呼ぶ。
結果は `extracted_text` の末尾に `\n\n---MAIN_CONTENT---\n` 区切りでJSON付加するか、
DB に新しいカラム `main_content_json` を追加して別途保存する（後者が望ましい）。

→ **DB案を採用**: `lessons` テーブルに `main_content` TEXT カラムを追加。JSON文字列で保存。

**API変更**:
- `POST /api/lessons/{id}/extract-text` — 抽出後に `extract_main_content()` も実行、`main_content` に保存
- `POST /api/lessons/{id}/add-url` — 同上
- `GET /api/lessons/{id}` — レスポンスに `main_content` を含める

### Step 3: 構造生成プロンプトに「コンテンツ種別ごとの読み上げ方ルール」を追加

`_build_structure_prompt()` に main_content 情報を渡し、プロンプトに含める。

**ユーザープロンプトに追加**:
```
## メインコンテンツ（事前分析済み）
以下はテキストから抽出されたメインコンテンツです。content_type に応じた読み上げ方で dialogue_plan を設計してください。

1. [conversation] "Morning Greeting Conversation"
   A: Good morning!
   B: Good morning! How are you?

2. [passage] "Explanation of formal greetings"
   Formal greetings are used in business...
```

**システムプロンプトに追加するルール（英語版）:**
```
## How to handle main content by type

### conversation (会話文)
- Split roles: teacher plays one speaker, student plays the other
- After performing, teacher explains vocabulary or grammar points
- direction example: "Play Speaker A in the conversation" / "Play Speaker B and respond"

### passage (文章・説明文)
- Teacher reads the text aloud, then explains or paraphrases
- Student reacts, asks questions, or confirms understanding

### word_list (単語・フレーズ集)
- Teacher reads each item with explanation
- Student repeats or asks about usage
- Split long lists across multiple turns

### table (表・比較データ)
- Teacher walks through rows/columns
- Student comments on differences or asks about entries
```

**日本語版も同様に追加。**

### Step 4: 監督レビュープロンプトにも同ルールを追加

`_director_review()` のシステムプロンプトに、コンテンツ種別を考慮したレビュー観点を追加。

**追加するレビュー観点:**
- 会話文（conversation）なのに先生が一人で全部読んでいないか → 不合格
- 文章（passage）なのに不自然に役割分担していないか
- コンテンツの種類に合った読み上げ方になっているか
- revised_directions にも content_type に合った指示を含めること

ユーザープロンプトにも `main_content` 情報を含める（レビュー時に参照できるように）。

### Step 5: 管理画面にメインコンテンツ表示

`static/js/admin/teacher.js` のレッスン詳細画面に、抽出されたメインコンテンツを表示。
種別ごとにアイコン・色分けして折りたたみ表示。

### Step 6: テスト

- `clean_extracted_text()` のユニットテスト（記号除去・空行圧縮・HTMLエンティティ置換）
- `extract_main_content()` のユニットテスト（モックLLM応答でJSON解析を検証）
- 既存テストが通ることを確認
- `test_api_teacher.py` に抽出→クリーニング→main_content保存のテスト追加
- 手動テストで会話文を含むコンテンツで生成し、先生・生徒の役割分担を確認

## リスク

- DBマイグレーション: `main_content` カラム追加。既存レコードは NULL で問題なし（Step 2以降は main_content が無ければ従来動作）
- LLMのコンテンツ種別判定精度 → temperature=0.1 で安定させる。判定ミスは監督レビューで拾える
- テキスト抽出APIのレスポンス時間が増える（LLM呼び出し1回追加）→ 許容範囲（数秒）
