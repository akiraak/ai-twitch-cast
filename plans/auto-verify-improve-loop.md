# 授業スクリプト自動検査・改善ループ（3回）

## ステータス: 未着手

## 背景

現在、授業スクリプトの生成後、検査（verify）と改善（improve）はすべてユーザーが手動で個別に実行する必要がある。生成→検査→改善を自動でループさせることで、初回生成の品質を大幅に向上させる。

## 目標

- `import_sections` 後に **verify → improve を最大3回自動ループ** する
- 問題なしなら早期終了（3回未満でも停止）
- 進捗をリアルタイムで追跡可能にする
- 管理画面UIからも手動トリガーできる

## 設計方針

### 新エンドポイント方式

`import_sections` に直接組み込むのではなく、独立した新エンドポイントを作る。理由:
- インポートは高速に完了させたい（既存動作を壊さない）
- 管理画面からも任意のバージョンに対してトリガーしたい
- 進捗追跡のロジックをTTS事前生成と同じパターンで実装できる

### ループの判定ロジック

```
verify結果から改善対象を自動判定:
  1. coverage で "weak" → そのsection_indexを改善対象に追加
  2. coverage で "missing" → user_instructionsに追加情報として記載
  3. contradictions → そのsection_indexを改善対象に追加
  
  → 改善対象セクションが0件 = 問題なし → ループ終了（早期終了）
  → 改善対象セクションが1件以上 → improve実行 → 新バージョン → 次のループ
```

### "missing" 項目の扱い

"missing" は特定のセクションに紐づかないため:
- **weak/contradictions のセクションがある場合**: そのセクションの改善時に `user_instructions` として "missing" 内容を含める（AIが最適なセクションに組み込む）
- **weak/contradictions がなくmissingだけの場合**: 全セクションを改善対象にし、`user_instructions` でmissing内容の追加を指示する

## 実装ステップ

### Step 1: バックエンド — `auto_refine` 関数 (`src/lesson_generator/improver.py`)

新しい関数 `auto_refine()` を追加:

```python
async def auto_refine(
    lesson_id: int,
    lang: str,
    generator: str,
    version_number: int,
    max_iterations: int = 3,
    on_progress: Callable | None = None,
) -> dict:
    """verify→improveを最大max_iterations回自動ループする。
    
    Returns:
        {
            "iterations": [
                {
                    "iteration": 1,
                    "verify_result": {...},
                    "issues_found": {"weak": [...], "missing": [...], "contradictions": [...]},
                    "target_sections": [0, 2],
                    "improved_version": 2,  # or None if no issues
                },
                ...
            ],
            "final_version": int,
            "total_iterations": int,
            "early_stop": bool,  # True = 問題なしで早期終了
        }
    """
```

処理フロー:
1. DBから授業データ・セクション・元教材を取得
2. ループ開始（最大3回）:
   a. `verify_lesson()` を呼ぶ
   b. verify結果を解析 → 改善対象セクションを判定
   c. 改善対象が0件 → 早期終了
   d. `improve_sections()` を呼ぶ
   e. 新バージョンをDBに保存
   f. on_progress コールバックで進捗通知
   g. 次イテレーションの version_number を更新
3. ループ終了後、最終バージョンでTTS事前生成を開始

### Step 2: APIエンドポイント (`scripts/routes/teacher.py`)

```python
@router.post("/api/lessons/{lesson_id}/auto-refine")
async def auto_refine_content(lesson_id: int, body: AutoRefineRequest):
    """自動検査・改善ループ（最大3回）をバックグラウンドで開始する"""
```

**リクエスト**:
```python
class AutoRefineRequest(BaseModel):
    lang: str = "ja"
    generator: str = "claude"
    version_number: int | None = None  # 省略時は最新バージョン
    max_iterations: int = 3
```

**レスポンス** (即座に返す):
```json
{"ok": true, "task_key": "refine_123_ja_claude_1"}
```

**進捗確認エンドポイント** (既存のTTS事前生成と同パターン):
```python
@router.get("/api/lessons/{lesson_id}/auto-refine/status")
async def get_auto_refine_status(lesson_id: int, lang: str = "ja", generator: str = "claude"):
    """自動改善の進捗を取得"""
```

**レスポンス**:
```json
{
    "ok": true,
    "state": "running",  // "running" | "completed" | "stopped" | "error"
    "current_iteration": 2,
    "max_iterations": 3,
    "iterations": [
        {
            "iteration": 1,
            "verify_result": {"coverage": [...], "contradictions": [...]},
            "weak_count": 2,
            "missing_count": 1,
            "contradiction_count": 0,
            "target_sections": [0, 3],
            "improved_version": 2
        },
        {
            "iteration": 2,
            "verify_result": {"coverage": [...], "contradictions": [...]},
            "weak_count": 0,
            "missing_count": 0,
            "contradiction_count": 0,
            "target_sections": [],
            "improved_version": null  // 問題なし→早期終了
        }
    ],
    "final_version": 2,
    "early_stop": true
}
```

### Step 3: バックグラウンドタスク管理 (`scripts/routes/teacher.py`)

TTS事前生成と同じパターンでタスクレジストリを追加:

```python
# --- 自動改善タスクレジストリ ---
_auto_refine_tasks: dict[str, dict] = {}

def _start_auto_refine(lesson_id, lang, generator, version_number, max_iterations=3) -> str:
    """バックグラウンドで自動改善タスクを起動"""
    # 既存タスクがあればキャンセル
    # asyncio.create_taskで起動
    # statusオブジェクトで進捗管理
```

### Step 4: `import_sections` へのオプション追加

既存の `import_sections` に `auto_refine` パラメータを追加:

```python
@router.post("/api/lessons/{lesson_id}/import-sections")
async def import_sections(
    lesson_id: int, body: SectionImport,
    lang: str = "ja", generator: str = "claude",
    version: int | None = None,
    auto_refine: bool = False,  # 新規追加
):
```

`auto_refine=True` の場合:
- 通常のインポート処理後
- TTS事前生成**ではなく**自動改善タスクを起動
- 自動改善の最終バージョンでTTS事前生成が走る

### Step 5: 管理画面UI (`static/js/admin/teacher.js`)

バージョン表示エリアに「自動改善」ボタンを追加:

```
[検証] [改善を実行] [自動改善(3回)] ← 新規追加
```

ボタンクリック → `POST /api/lessons/{id}/auto-refine` → ポーリングで進捗表示:

```
自動改善中... (2/3)
  ラウンド1: weak 2件, missing 1件 → v2作成 ✓
  ラウンド2: weak 0件, missing 0件 → 問題なし ✓ (早期終了)
```

### Step 6: `lesson_generate.md` への指示追加

Claude Code用の生成プロンプトの Step 6 の後に Step 7 を追加:

```markdown
### Step 7: 自動検査・改善

インポート後、自動検査・改善ループを実行する。

```bash
curl -X POST "http://localhost:${WEB_PORT:-8080}/api/lessons/{lesson_id}/auto-refine?lang=ja&generator=claude" \
  -H "Content-Type: application/json" \
  -d '{"version_number": <インポートしたバージョン番号>}'
```

完了まで待機（最大3回の検査・改善が自動実行される）:

```bash
curl -s "http://localhost:${WEB_PORT:-8080}/api/lessons/{lesson_id}/auto-refine/status?lang=ja&generator=claude" | python3 -m json.tool
```
```

## verify結果 → 改善対象の判定ロジック（詳細）

```python
def _determine_targets_from_verify(verify_result: dict, all_sections: list[dict]) -> tuple[list[int], str]:
    """verify結果から改善対象セクションとuser_instructionsを決定する。
    
    Returns:
        (target_indices, user_instructions)
    """
    target_set = set()
    instructions = []
    
    # weak → そのsection_indexを対象に
    for item in verify_result.get("coverage", []):
        if item["status"] == "weak":
            idx = item.get("section_index")
            if idx is not None:
                target_set.add(idx)
                instructions.append(f"セクション{idx}: {item.get('detail', '説明不足')}")
    
    # contradictions → そのsection_indexを対象に
    for item in verify_result.get("contradictions", []):
        idx = item.get("section_index")
        if idx is not None:
            target_set.add(idx)
            instructions.append(f"セクション{idx}の矛盾修正: {item.get('issue', '')}")
    
    # missing → user_instructionsに追記
    missing_items = [item for item in verify_result.get("coverage", []) if item["status"] == "missing"]
    if missing_items:
        for item in missing_items:
            instructions.append(f"不足している内容を追加: {item.get('source_item', '')} — {item.get('detail', '')}")
        # missing だけで target が空の場合、全セクションを対象に
        if not target_set:
            all_indices = [s["order_index"] for s in all_sections]
            target_set.update(all_indices)
    
    user_instructions = "\n".join(instructions) if instructions else ""
    return sorted(target_set), user_instructions
```

## ファイル変更一覧

| ファイル | 変更内容 |
|---------|---------|
| `src/lesson_generator/improver.py` | `auto_refine()` 関数、`_determine_targets_from_verify()` ヘルパー追加 |
| `src/lesson_generator/__init__.py` | `auto_refine` をエクスポートに追加 |
| `scripts/routes/teacher.py` | `POST /auto-refine`、`GET /auto-refine/status` エンドポイント、タスクレジストリ、`import_sections` に `auto_refine` パラメータ追加 |
| `static/js/admin/teacher.js` | 「自動改善」ボタン、進捗表示UI |
| `prompts/lesson_generate.md` | Step 7（自動検査・改善）追加 |
| `tests/test_api_teacher.py` | auto-refine エンドポイントのテスト追加 |

## リスク・考慮事項

- **LLM API コスト**: 最大3回のverify + 3回のimproveで6回のLLM呼び出し。1回あたり数秒〜十数秒かかるため、全体で30秒〜2分程度
- **無限ループ防止**: max_iterations で厳密に制限（デフォルト3）
- **改善が逆効果になる場合**: verify→improveの繰り返しで品質が下がる可能性は低いが、各イテレーションの結果を保存して追跡可能にする
- **同時実行**: 同一授業への複数タスク起動は既存タスクをキャンセルして新規起動（TTS事前生成と同パターン）
- **verify結果の保存**: 各イテレーションのverify_jsonをバージョンに保存するため、あとから確認可能
