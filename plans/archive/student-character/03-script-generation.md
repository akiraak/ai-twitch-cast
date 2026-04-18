# Step 3: スクリプト生成の対話化

## ステータス: 完了

## ゴール

`lesson_sections` に `dialogues` カラムを追加し、LLMで先生と生徒の掛け合いスクリプトを自動生成する。

## 変更対象

| ファイル | 変更内容 |
|---------|---------|
| `src/db.py` | `lesson_sections` に `dialogues` カラム追加・マイグレーション |
| `src/lesson_generator.py` | プロンプト変更・dialogues後処理 |

## 前提

- なし

## 実装

### 3-1. DB: dialogues カラム追加

```sql
ALTER TABLE lesson_sections ADD COLUMN dialogues TEXT DEFAULT '';
```

`create_tables()` と `_migrate()` の両方に追加。`get_lesson_sections()` / `save_lesson_sections()` で dialogues を JSON文字列として読み書き。

### 3-2. プロンプトに追加する内容

```
## 登場キャラクター
この授業には2人のキャラクターが登場します:

### 先生: ちょビ（teacher）
- メインの講師。明るく楽しい口調で教える

### 生徒: まなび（student）
- 視聴者の代弁者。好奇心旺盛で素直
- リアクション（「へぇ〜！」「なるほど！」「え、そうなの？」）
- 素朴な疑問を投げかける（先生が補足説明するきっかけ）
- たまに間違った答えを言う（先生が優しく正す）
- questionセクションでは生徒が考えて答える（正解 or 惜しい回答）

## dialogues フィールド
各セクションに dialogues 配列を含めてください。
- 1セクションあたり2〜6発話
- teacher と student が交互に、または自然な流れで発話
- 全セクションで生徒が登場する必要はない（説明が続くところは先生だけでもOK）
- introduction と summary には生徒を必ず入れる（挨拶・感想）
- question セクションでは生徒が答える役（先生が出題→生徒が回答→先生が解説）
```

### 3-3. 生成結果の後処理

```python
def _build_section_from_dialogues(section):
    """dialoguesからトップレベルのcontent/tts_text/emotionを自動構築"""
    dialogues = section.get("dialogues", [])
    if not dialogues:
        return section

    section["content"] = "".join(d["content"] for d in dialogues)
    section["tts_text"] = "".join(d.get("tts_text", d["content"]) for d in dialogues)
    teacher_dlgs = [d for d in dialogues if d["speaker"] == "teacher"]
    section["emotion"] = teacher_dlgs[0]["emotion"] if teacher_dlgs else "neutral"
    return section
```

### 3-4. 生徒無効時

characters テーブルに student ロールがない場合、プロンプトから生徒を除外→従来形式で生成。

## 完了条件

- [x] `dialogues` カラムが存在し、既存DBのマイグレーションが動作する
- [x] スクリプト生成で dialogues 形式のセクションが生成される
- [x] 後処理で content/tts_text/emotion が自動構築される
- [x] 生徒キャラなしで従来形式生成
- [x] 英語モードでも対話スクリプトが生成される
