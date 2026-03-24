# Step 5: スクリプト生成の対話化

## ステータス: 未着手

## ゴール

LLMのプロンプトに生徒キャラを追加し、先生と生徒の掛け合い（dialogues）を含むスクリプトを自動生成する。

## 変更対象

| ファイル | 変更内容 |
|---------|---------|
| `src/lesson_generator.py` | プロンプト変更・dialogues後処理 |

## 前提

- Step 4（dialoguesカラム）完了済み

## 実装

### 5-1. プロンプトに追加する内容（日本語版）

```
## 登場キャラクター
この授業には2人のキャラクターが登場します:

### 先生: ちょビ（teacher）
- メインの講師。知識を教える役割
- 明るく楽しい口調で教える

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

### 5-2. 生成結果の後処理

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

### 5-3. 生徒無効時

`student.enabled == "false"` の場合、プロンプトから生徒を除外→従来形式で生成。

## 完了条件

- [ ] スクリプト生成で dialogues 形式のセクションが生成される
- [ ] 後処理で content/tts_text/emotion が自動構築される
- [ ] `student.enabled=false` で従来形式生成
- [ ] 英語モードでも対話スクリプトが生成される
