# 授業の品質分析をスクリプト生成の中に含める（2c）

## ステータス: 完了

## 背景

現在、品質分析(`analyze_content()`)はスクリプト生成パイプライン(`generate_lesson_script_v2()`)の**外側**（`teacher.py:735`）で実行されている。分析結果はDB保存されるだけで、パイプラインの出力に含まれていない。

本変更は品質分析をパイプライン内に組み込み、分析結果を戻り値に含めることで、パイプラインの出力として品質情報を一体化する。**改善アクション（再生成等）は本タスクの対象外**（別タスクで実施）。

## 変更後のパイプライン

```
Phase 1: セクション構造生成
Phase 2: セリフ個別生成（並列）
Phase B-3: 監督レビュー
Phase B-4: 不合格セクション再生成
Phase B-5: 品質分析  ← ★新規（分析のみ、改善なし）
  - analyze_content() 実行（APIコスト0、即時）
─── return（sections + analysis） ───
teacher.py: 埋め込み済み分析結果をDB保存（重複呼び出し削除）
```

## 実装ステップ

### Step 1: Phase B-5 追加 (`src/lesson_generator.py`) ✅ 完了

`generate_lesson_script_v2()` の結果組み立て（result assembly）の**後**、`return result` の前に追加:

1. `from src.content_analyzer import analyze_content` をimport追加
2. `regen_turns = 0` のデフォルト初期化（Phase B-4ブロック外でも参照するため）
3. Phase B-3/B-4 の進捗 total に +1（5箇所）— Phase B-5 ステップ分
4. Phase B-5: `analyze_content(result, lang)` を実行（resultは組み立て済みのセクションリスト）
5. 進捗コールバックで「品質分析中... / Analyzing quality...」を報告

**注**: 仮セクション構築ではなく、result assemblyで構築済みの `result` をそのまま渡す方式を採用。`dialogues` がJSON文字列化済みで `analyze_content` の期待する入力形式と一致するため。

### Step 2: 戻り値の変更 (`src/lesson_generator.py`) ✅ 完了

現在: `return result` (list[dict])
変更後: `return {"sections": result, "analysis": analysis.to_dict()}`

### Step 3: 呼び出し側の更新 (`scripts/routes/teacher.py`) ✅ 完了

**line 635:** `sections = task.result()` をアンパック
- v2パス: `gen_result = task.result()` → `sections = gen_result["sections"]`
- 非v2パス（line 603-616）: `{"sections": sections, "analysis": None}` でラップ

**line 735-742:** 重複する `analyze_content()` を削除
- 埋め込み `analysis` があればそれをDB保存
- なければフォールバックで `analyze_content()` 実行（非v2パス用）

### Step 4: テスト ✅ 完了

**新規テスト** (`tests/test_lesson_generator.py`):
- Phase B-5: `analyze_content` がモック経由で呼ばれ、戻り値dictに `analysis` が含まれることを確認

**既存テスト確認**:
- teacher.pyが `gen_result["sections"]` をアンパックしてDB保存→APIレスポンス構築するので、API応答形式は変わらない → 既存テストは修正不要のはず

## 対象ファイル

| ファイル | 変更内容 |
|---------|---------|
| `src/lesson_generator.py` | Phase B-5（分析のみ）追加、戻り値を `dict` に変更 |
| `src/content_analyzer.py` | 変更なし（読み取り専用の依存） |
| `scripts/routes/teacher.py` | 戻り値アンパック、重複分析削除 |
| `tests/test_lesson_generator.py` | Phase B-5テスト追加 |

## 技術的詳細

### analyze_content() が期待する入力形式

`sections`: list[dict] で各要素に以下が必要:
- `display_text`: 画面表示テキスト
- `tts_text` / `content`: 読み上げテキスト
- `dialogues`: JSON文字列（`{"dialogues": [...]}`形式）
- `section_type`: セクション種別
- `question` / `answer`: 質問型セクション用
- `wait_seconds`: 間の秒数

Phase B-5では `_build_section_from_dialogues()` で `content`/`tts_text` を構築し、`dialogues` をJSON文字列化して渡す。

### 進捗報告

既存のステップカウンタの total に +1 して品質分析ステップを追加（Phase B-3: 2箇所、Phase B-4: 3箇所）。
`regen_turns` はPhase B-4ブロック外でも参照するため、デフォルト `0` で初期化。
Phase B-5 の step/total は `1 + total_turns + 1 + regen_turns + 1`（常に最終ステップ）。

## 検証方法

1. `python3 -m pytest tests/ -q` で全テスト通過
2. 管理画面でスクリプト生成 → SSEに「品質分析中...」表示
3. APIレスポンスの `analysis` にスコア・ランクが含まれる
4. DBの `analysis_json` に保存される

---

## Phase 2: LLM評価の自動実行

### ステータス: 未着手

### 背景

Phase B-5では `analyze_content()`（アルゴリズムのみ、50点満点）を使っているため、LLM評価（+50点）は手動で「＋ LLM評価」ボタンを押さないと実行されない。`analyze_content_full()`（100点満点）に切り替えてLLM評価も自動で走るようにする。

### 方針

`analyze_content_full()` はasyncだが、`generate_lesson_script_v2()` は `asyncio.to_thread()` で別スレッドで実行されるため、そのスレッド内で `asyncio.run()` を使えば安全にasync関数を呼べる。

### 実装ステップ

#### Step 5: Phase B-5を `analyze_content_full` に切り替え (`src/lesson_generator.py`) ✅ 完了

1. import変更: `analyze_content` → `analyze_content_full`、`import asyncio` 追加
2. Phase B-5の呼び出しを変更:
   ```python
   # Before
   analysis = analyze_content(result, "en" if en else "ja")
   # After
   analysis = asyncio.run(analyze_content_full(
       result, lesson_name=lesson_name,
       extracted_text=extracted_text,
       lang="en" if en else "ja",
   ))
   ```
3. 進捗メッセージ更新: 「品質分析中（LLM評価含む）... / Analyzing quality (with LLM)...」

#### Step 6: teacher.py フォールバック更新 (`scripts/routes/teacher.py`)

非v2パスのフォールバックも `analyze_content_full` に統一:
```python
# Before
analysis = analyze_content(section_dicts, lang)
# After
analysis = await analyze_content_full(
    section_dicts, lesson_name=lesson["name"],
    extracted_text=lesson.get("extracted_text", ""),
    lang=lang,
)
```

#### Step 7: テスト

- 既存テスト: `analyze_content_full` をモックして戻り値形式が維持されることを確認
- 新規テスト: Phase B-5で `analyze_content_full` が呼ばれ、`llm_scores` が含まれることを確認

### 対象ファイル

| ファイル | 変更内容 |
|---------|---------|
| `src/lesson_generator.py` | `analyze_content` → `asyncio.run(analyze_content_full(...))` |
| `scripts/routes/teacher.py` | フォールバックも `analyze_content_full` に統一 |
| `tests/test_lesson_generator.py` | モック対象を `analyze_content_full` に変更 |
