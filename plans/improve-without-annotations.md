# 注釈なしでもAI自動判定で授業スクリプトを改善

## ステータス: 未着手

## 背景

現在の改善フローは、ユーザーがセクションに注釈（◎/△/✕）を付けるか、改善対象セクションを手動で選択する必要がある。注釈が一切ない状態で「改善」を実行すると、対象セクションが空のためエラーになる。

**やりたいこと**: 注釈がなくても、AIが既存スクリプトを自動評価して改善すべきセクションを判定し、改善を実行できるようにする。

## 現状の制約

- `POST /api/lessons/{id}/improve` は `target_sections` が空だとエラー（`teacher.py:1333-1334`）
- UIの改善パネルでは注釈済みセクション（△/✕）が自動チェックされるが、注釈なしだと何も選択されない
- verify結果がDBに保存されていない場合、改善の根拠情報がない

## 現状の検証の問題点

現在の `verify_lesson()` は**元教材との差分チェック（coverage/contradictions）だけ**で、以下を一切見ていない:

1. **授業としての品質** — 構成の自然さ、対話テンポ、感情選択の妥当性など
2. **カテゴリ適合性** — カテゴリ固有の要件（Pythonならコード正確性、英語なら例文の自然さ等）

## 前提変更: カテゴリプロンプトをDB保存に移行

### 現状
- `lesson_categories.prompt_file` にファイル名（例: `lesson_generate_python.md`）を保存
- プロンプト内容は `prompts/` ディレクトリにファイルとして保存
- 現時点でカテゴリ専用プロンプトファイルは**0件**（未使用）

### 問題
- カテゴリが増えるとファイルが散らかる
- カテゴリとプロンプトの紐づきが間接的（ファイル名参照）
- カテゴリ削除時にファイルの掃除が必要

### 変更: `prompt_file` → `prompt_content` （DB直接保存）

```sql
-- lesson_categories テーブルにカラム追加
ALTER TABLE lesson_categories ADD COLUMN prompt_content TEXT DEFAULT '';
```

- `prompt_content`: カテゴリ専用プロンプトの全文をDBに直接保存
- `prompt_file`: 廃止（既存データなし、移行不要）
- `create_category_prompt()`: ファイル書き出しをやめてDB保存に変更
- カテゴリ削除時にプロンプトも自動で消える（DBの行ごと削除）

**影響範囲**:
| ファイル | 変更 |
|---------|------|
| `src/db/core.py` | `prompt_content` カラム追加マイグレーション |
| `src/db/lessons.py` | `create_category()`, `update_category()` に `prompt_content` 対応 |
| `src/lesson_generator/improver.py` | `create_category_prompt()` がDB保存に変更、`improve_prompt()` がDBから読み込み |
| `scripts/routes/teacher.py` | カテゴリAPI で `prompt_content` を返す・受け取る |

## 設計

### 評価の3軸

自動判定を**3つの独立した評価軸**で行う:

| 軸 | 評価基準のソース | チェック内容 |
|----|----------------|-------------|
| **①元教材整合性** | 元教材テキスト（extracted_text / main_content） | カバレッジ・矛盾（既存verify） |
| **②授業品質** | 授業生成プロンプト（`lesson_generate.md`） | プロンプトの品質基準・生成ルールに沿っているか |
| **③カテゴリ適合性** | カテゴリ専用プロンプト（DB `lesson_categories.prompt_content`） | カテゴリ固有の要件に沿っているか |

**②と③が新規追加**。生成時に使ったプロンプト自体を評価基準として使うことで、「生成プロンプトが求めたもの」と「実際の出力」のギャップを検出する。

### 方針: 検証ステップを拡張 → 3軸の結果を統合して対象判定

```
target_sections が空で /improve が呼ばれる
  │
  ├─ ① verify_lesson() — 元教材との整合性（既存）
  │     → coverage: weak/missing, contradictions
  │
  ├─ ② evaluate_lesson_quality() — 授業品質チェック（新規）
  │     → lesson_generate.md の品質基準で評価
  │     → quality_issues: [{section_index, issue, severity}]
  │
  ├─ ③ evaluate_category_fit() — カテゴリ適合性チェック（新規）
  │     → DB lesson_categories.prompt_content の要件で評価
  │     → category_issues: [{section_index, issue, severity}]
  │
  ├─ 3軸の結果を統合 → 改善対象セクション + user_instructions を決定
  │
  └─ improve_sections() 実行 → 新バージョン
```

### ② 授業品質チェック: `evaluate_lesson_quality()`

**評価基準**: `lesson_generate.md` の「品質基準」セクション + 「生成ルール」を使う。

新プロンプト `lesson_evaluate_quality.md`:

```markdown
# 授業スクリプト 品質チェック

あなたは授業コンテンツのQAレビュアーです。
以下の**生成ルール・品質基準**と**授業スクリプト**を比較し、基準を満たしていないセクションを検出してください。

## 生成ルール・品質基準

{lesson_generate.md の内容（または品質基準セクション抜粋）}

## チェック観点

### 教育効果
- 教材の主要内容がカバーされているか
- 段階的に難易度が上がる構成か
- 具体例や演習で理解を定着させているか

### エンタメ性
- 導入で視聴者の興味を引いているか
- 5分以上の単調な解説がないか
- 教師と生徒の掛け合いが自然か

### 対話品質
- 1セクションあたり4-8ターンの対話目安を守っているか
- 生徒の反応が自然か（「なるほど！」等の画一的パターンの繰り返しでないか）
- emotionが発話内容に合っているか

### 技術的正確性
- tts_text の言語タグが正しいか
- display_text のコンテンツ量と display_properties のサイズが合っているか
- section_type が内容に合っているか

## 出力フォーマット

JSON形式で出力してください。

{
  "quality_issues": [
    {
      "section_index": 2,
      "aspect": "dialogue_quality",
      "severity": "major|minor",
      "issue": "生徒の反応が3連続で「なるほど！」系で単調"
    }
  ],
  "overall_score": 7  // 1-10のスコア（参考値）
}
```

**関数シグネチャ**:
```python
async def evaluate_lesson_quality(
    sections: list[dict],
    generation_prompt: str,  # lesson_generate.md の内容
    en: bool = False,
) -> dict:
    """授業品質チェック。生成プロンプトの品質基準に照らして評価する。"""
```

### ③ カテゴリ適合性チェック: `evaluate_category_fit()`

**評価基準**: DB `lesson_categories.prompt_content`（カテゴリ専用プロンプト）を使う。

新プロンプト `lesson_evaluate_category.md`:

```markdown
# 授業スクリプト カテゴリ適合性チェック

あなたは「{category_name}」分野の教育コンテンツ専門レビュアーです。
以下の**カテゴリ要件**と**授業スクリプト**を比較し、カテゴリ固有の基準を満たしていないセクションを検出してください。

## カテゴリ情報
- カテゴリ: {category_name}
- 説明: {category_description}

## カテゴリ専用プロンプト（生成時の要件）

{DB lesson_categories.prompt_content の内容}

## チェック観点

- カテゴリ専用プロンプトで定義された要件を満たしているか
- その分野の専門的な正確性（コード、用語、例文等）
- 分野の慣習に沿った教え方か

## 出力フォーマット

{
  "category_issues": [
    {
      "section_index": 1,
      "severity": "major|minor",
      "issue": "Pythonのコード例で非推奨のformat()を使用。f-stringを使うべき"
    }
  ]
}
```

**関数シグネチャ**:
```python
async def evaluate_category_fit(
    sections: list[dict],
    category_prompt: str,     # DB lesson_categories.prompt_content から取得
    category_name: str,
    category_description: str,
    en: bool = False,
) -> dict:
    """カテゴリ適合性チェック。DB保存のカテゴリ専用プロンプトに照らして評価する。"""
```

**`prompt_content` が空の場合**: ③はスキップ（①②のみで判定）。

### 3軸の統合判定ロジック

```python
def determine_targets(
    verify_result: dict | None,
    quality_result: dict | None,
    category_result: dict | None,
    all_sections: list[dict],
) -> tuple[list[int], str]:
    """3軸の評価結果を統合して改善対象を決定する。"""
    target_set = set()
    instructions = []

    # ① 元教材整合性（既存ロジック）
    if verify_result:
        for item in verify_result.get("coverage", []):
            if item["status"] == "weak":
                idx = item.get("section_index")
                if idx is not None:
                    target_set.add(idx)
                    instructions.append(f"[教材整合性] セクション{idx}: {item.get('detail', '説明不足')}")
        for item in verify_result.get("contradictions", []):
            idx = item.get("section_index")
            if idx is not None:
                target_set.add(idx)
                instructions.append(f"[教材整合性] セクション{idx}の矛盾: {item.get('issue', '')}")
        missing = [i for i in verify_result.get("coverage", []) if i["status"] == "missing"]
        if missing:
            for item in missing:
                instructions.append(f"[教材整合性] 不足内容を追加: {item.get('source_item', '')}")
            if not target_set:
                target_set.update(s["order_index"] for s in all_sections)

    # ② 授業品質
    if quality_result:
        for item in quality_result.get("quality_issues", []):
            if item.get("severity") == "major":
                idx = item.get("section_index")
                if idx is not None:
                    target_set.add(idx)
                    instructions.append(f"[授業品質] セクション{idx}: {item.get('issue', '')}")

    # ③ カテゴリ適合性
    if category_result:
        for item in category_result.get("category_issues", []):
            if item.get("severity") == "major":
                idx = item.get("section_index")
                if idx is not None:
                    target_set.add(idx)
                    instructions.append(f"[カテゴリ] セクション{idx}: {item.get('issue', '')}")

    return sorted(target_set), "\n".join(instructions)
```

**severity の扱い**:
- `major` → 改善対象に追加（自動改善で修正すべき）
- `minor` → user_instructionsに参考情報として含めるが、単独では改善対象にしない

## 実装ステップ

### Step 1: 新プロンプト作成

| ファイル | 内容 |
|---------|------|
| `prompts/lesson_evaluate_quality.md` | 授業品質チェックプロンプト |
| `prompts/lesson_evaluate_category.md` | カテゴリ適合性チェックプロンプト |

### Step 2: DB変更 — カテゴリプロンプトのDB保存化

`src/db/core.py` にマイグレーション追加:

```python
# Migration: lesson_categories に prompt_content カラム追加
try:
    conn.execute("ALTER TABLE lesson_categories ADD COLUMN prompt_content TEXT DEFAULT ''")
    conn.commit()
except sqlite3.OperationalError:
    pass
```

`src/db/lessons.py` の変更:
- `create_category(slug, name, description, prompt_content)` — `prompt_file` → `prompt_content`
- `update_category(id, ..., prompt_content)` — プロンプト内容の更新

`src/lesson_generator/improver.py` の変更:
- `create_category_prompt()` — ファイル書き出しをやめてDB保存に変更（`db.update_category()` でprompt_content更新）
- `improve_prompt()` — カテゴリプロンプトをDBから読み込みに変更

`scripts/routes/teacher.py` の変更:
- カテゴリ作成・更新APIで `prompt_content` を受け取り・返す
- `prompt_file` 参照を `prompt_content` 参照に置換

### Step 3: 評価関数の追加 (`src/lesson_generator/improver.py`)

- `evaluate_lesson_quality()` — 授業品質チェック
- `evaluate_category_fit()` — カテゴリ適合性チェック
- `determine_targets()` — 3軸統合判定（旧 `determine_targets_from_verify` を拡張）

`evaluate_lesson_quality()` は `lesson_generate.md` をファイルから読み込み、品質基準部分をシステムプロンプトに注入。

`evaluate_category_fit()` は **DBから** `lesson_categories.prompt_content` を取得し、カテゴリ要件をシステムプロンプトに注入。`prompt_content` が空ならスキップ。

### Step 4: `/improve` エンドポイント修正 (`scripts/routes/teacher.py`)

`target_sections` が空の場合の自動判定フロー:

```python
if not body.target_sections:
    # ① 元教材整合性
    verify_result = await _get_or_run_verify(...)
    
    # ② 授業品質（lesson_generate.md を基準に）
    generation_prompt = _load_prompt("lesson_generate.md")
    quality_result = await evaluate_lesson_quality(
        sections=src_sections,
        generation_prompt=generation_prompt,
        en=en,
    )
    
    # ③ カテゴリ適合性（DBにprompt_contentがある場合のみ）
    category_result = None
    category_row = db.get_category_by_slug(category) if category else None
    if category_row and category_row.get("prompt_content"):
        category_result = await evaluate_category_fit(
            sections=src_sections,
            category_prompt=category_row["prompt_content"],  # DBから取得
            category_name=category_row["name"],
            category_description=category_row.get("description", ""),
            en=en,
        )
    
    # 3軸統合
    auto_targets, auto_instructions = determine_targets(
        verify_result, quality_result, category_result, src_sections,
    )
```

### Step 5: 管理画面UI修正 (`static/js/admin/teacher.js`)

「AI自動判定で改善」ボタン。レスポンスに3軸の結果を含め、進捗表示:

```
AI自動判定結果:
  教材整合性: weak 1件, missing 0件
  授業品質:   major 2件 (セクション1: 対話が単調, セクション3: emotion不適切)
  カテゴリ:   major 1件 (セクション2: コード例が非推奨)
  → 改善対象: セクション 1, 2, 3
```

### Step 6: レスポンスに3軸の評価結果を追加

```json
{
    "ok": true,
    "version_number": 3,
    "improved_sections": [1, 2, 3],
    "auto_detected": true,
    "evaluation": {
        "verify_result": {"coverage": [...], "contradictions": [...]},
        "quality_result": {"quality_issues": [...], "overall_score": 7},
        "category_result": {"category_issues": [...]},
        "detection_summary": "教材整合性: weak 1 / 授業品質: major 2 / カテゴリ: major 1"
    },
    "sections": [...],
    "prompt": {...},
    "raw_output": "..."
}
```

### Step 7: テスト (`tests/test_api_teacher.py`)

- target_sections空 → 3軸評価が走ることの確認
- カテゴリ専用プロンプトなし → ①②のみで動作することの確認
- 全軸で問題なし → `no_issues: true` が返ることの確認

## LLM呼び出し回数

| モード | ①verify | ②quality | ③category | improve | 合計 |
|-------|---------|----------|-----------|---------|------|
| 手動（従来） | 0 | 0 | 0 | 1 | 1 |
| 自動判定（カテゴリなし） | 1 | 1 | 0 | 1 | 3 |
| 自動判定（カテゴリあり） | 1 | 1 | 1 | 1 | 4 |

②③は並列実行可能（依存関係なし）。①も並列可能だが、DB保存済みverifyがあればスキップ。

## ファイル変更一覧

| ファイル | 変更内容 |
|---------|---------|
| `src/db/core.py` | `lesson_categories` に `prompt_content TEXT` カラム追加マイグレーション |
| `src/db/lessons.py` | `create_category()`, `update_category()` で `prompt_content` 対応、`prompt_file` 廃止 |
| `prompts/lesson_evaluate_quality.md` | 新規: 授業品質チェックプロンプト |
| `prompts/lesson_evaluate_category.md` | 新規: カテゴリ適合性チェックプロンプト |
| `src/lesson_generator/improver.py` | `evaluate_lesson_quality()`, `evaluate_category_fit()`, `determine_targets()` 追加、`create_category_prompt()` DB保存化、`improve_prompt()` DB読み込み化 |
| `src/lesson_generator/__init__.py` | 新関数をエクスポートに追加 |
| `scripts/routes/teacher.py` | カテゴリAPI `prompt_file`→`prompt_content`、`target_sections` 空の自動判定フロー（3軸並列評価） |
| `static/js/admin/teacher.js` | 「AI自動判定で改善」ボタン、3軸結果表示、カテゴリプロンプト編集UI |
| `tests/test_api_teacher.py` | 自動判定テスト追加、カテゴリ `prompt_content` テスト |

## `auto-verify-improve-loop.md` との関係

- **このプラン**: 1回の改善で3軸評価 → 対象判定 → 改善
- **auto-refine**: この3軸評価を使って最大3回ループ
- **共通部品**: `determine_targets()` を両方で共用
- **実装順序**: このプランを先に実装 → auto-refineがこの判定ロジックを活用

## リスク・考慮事項

- **LLM呼び出し増**: 手動1回 → 自動で3-4回。ただし②③は並列実行で時間は1回分程度
- **カテゴリ `prompt_content` 未設定**: ③はスキップされるので問題なし。②だけでも授業品質は評価できる
- **評価の厳しさ調整**: majorのみ改善対象にすることで過度な改善を防止。実運用で調整
- **生成プロンプトの循環参照**: 生成プロンプトで作ったものを同じプロンプトで評価する形だが、生成（creative, temp=0.7）と評価（analytical, temp=0.1）で役割が異なるため問題は限定的
- **`prompt_file` → `prompt_content` 移行**: 現時点でカテゴリ専用プロンプトファイルは0件なので、移行は不要。`prompt_file` カラムはそのまま残して互換性維持、新規は `prompt_content` を使用
