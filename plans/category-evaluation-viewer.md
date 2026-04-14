# カテゴリ別評価ビューア（管理画面）

## ステータス: 完了

## 背景

現在、各セクションには ◎良い / ✕悪い / ↻作り直し の注釈（`annotation_rating` + `annotation_comment`）が付けられるが、これらの情報は**個々の授業パネルの中でしか見られない**。学習ダッシュボードは集計数（◎3 / △2 / ✕1）を表示するだけで、**具体的にどのセクションがどう評価されたか**をカテゴリ横断で一覧・閲覧する手段がない。

「何が悪いのか」を把握するには、各セクションの**対話内容（dialogues）・発話テキスト（tts_text）・表示テキスト（display_text）・コメント**を一覧できる必要がある。

## 目標

- カテゴリの学習ダッシュボードから、**注釈付きセクションを個別に閲覧**できるようにする
- 各セクションの**会話内容（dialogues）・コンテンツを全文表示**し、何が良い/悪いか分かるようにする
- 評価（◎/✕/↻）と評価コメントで**フィルタリング・一覧表示**できる

## 設計方針

### 既存コードの活用

- バックエンドの `_collect_annotated_sections()` (`src/lesson_generator/improver.py:412`) が既にカテゴリ別注釈付きセクション収集ロジックを持っている。ただし、これはAI分析用でプロンプト向けにcontentを300文字に切り詰めている
- 管理画面向けには**切り詰めなし**の完全データを返す新APIが必要

### UIの配置

学習ダッシュボードの各カテゴリカード内に「注釈セクション一覧」ボタンを追加。クリックで展開し、rating別にフィルタ可能な一覧を表示する。

## 実装ステップ

### Step 1: APIエンドポイント追加 (`scripts/routes/teacher.py`)

```python
@router.get("/api/lessons/annotated-sections")
async def api_get_annotated_sections(category: str = "", rating: str = ""):
    """カテゴリ別に注釈付きセクションを返す（会話内容含む完全データ）

    Query params:
        category: カテゴリslug（空文字=未分類）
        rating: "good" | "needs_improvement" | "redo" | "" (空=全部)

    Returns:
        {
            "ok": true,
            "sections": [
                {
                    "lesson_id": 5,
                    "lesson_name": "Python入門",
                    "version_number": 1,
                    "section_id": 42,
                    "order_index": 0,
                    "section_type": "explanation",
                    "title": "変数とは",
                    "emotion": "neutral",
                    "content": "...",
                    "tts_text": "...",
                    "display_text": "...",
                    "dialogues": [...],  // パース済みJSON
                    "annotation_rating": "needs_improvement",
                    "annotation_comment": "説明が抽象的すぎる",
                }
            ],
            "counts": { "good": 3, "needs_improvement": 2, "redo": 1 }
        }
    """
```

処理:
1. `db.get_all_lessons()` でカテゴリフィルタ
2. 各授業のセクションを取得（全バージョン）
3. `annotation_rating` が空でないセクションを収集
4. `rating` パラメータがあればさらにフィルタ
5. dialoguesはJSON文字列のままではなくパース済みで返す
6. countsも同時に返す（UIのフィルタタブ表示用）

### Step 2: 管理画面UI — カテゴリカード内に一覧ボタン追加 (`static/js/admin/teacher.js`)

学習ダッシュボードの各カテゴリカード（`_renderLearningSection` → `loadLearningsDashboard`）の統計行の隣に「注釈セクション一覧」ボタンを追加。

```
┌─ カテゴリカード ────────────────────────────────┐
│ プログラミング          5授業 / 注釈12件         │
│ ◎ 5 / △ 4 / ✕ 3   最終分析: 2026-04-10        │
│ [分析を実行] [プロンプトを改善] [注釈一覧 ▼]    │  ← ボタン追加
│                                                  │
│ ┌─ 注釈セクション一覧（展開時）──────────────┐ │
│ │ [全て(12)] [◎良い(5)] [✕悪い(4)] [↻作直(3)] │ │  ← フィルタタブ
│ │                                              │ │
│ │ ┌─ #5 Python入門 > S1 explanation ─────┐   │ │
│ │ │ ✕ 悪い — 説明が抽象的すぎる           │   │ │
│ │ │ ▶ 会話内容                            │   │ │  ← 折りたたみ
│ │ │   🎓先生: 今日は変数について...        │   │ │
│ │ │   🙋生徒: 変数ってなんですか？         │   │ │
│ │ │ ▶ 表示テキスト (display_text)         │   │ │
│ │ │   x = 10                              │   │ │
│ │ │ ▶ 発話テキスト (tts_text)             │   │ │
│ │ └──────────────────────────────────────┘   │ │
│ │ ┌─ #5 Python入門 > S3 example ─────────┐   │ │
│ │ │ ◎ 良い — コード例が具体的で分かりやすい│   │ │
│ │ │ ...                                    │   │ │
│ │ └──────────────────────────────────────┘   │ │
│ └──────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────┘
```

### Step 3: セクション詳細表示コンポーネント

各注釈セクションカードに表示する内容（折りたたみで全文閲覧可能）:

1. **ヘッダ**: 授業名 + セクション番号 + section_type + emotion
2. **評価**: ◎/✕/↻ バッジ + annotation_comment
3. **会話内容** (`dialogues`): 折りたたみ内に発話一覧
   - speaker（🎓先生 / 🙋生徒）ごとに色分け
   - emotion表示
   - レビュー結果（review）があれば表示
4. **表示テキスト** (`display_text`): 折りたたみ内に全文
5. **発話テキスト** (`tts_text`): 折りたたみ内に全文
6. **コンテンツ** (`content`): 折りたたみ内に全文（dialoguesと被る場合は省略可）

CLAUDE.mdの「LLM生成パイプラインの検証可能性」ルールに従い、切り詰めず全文表示する。長い場合はdetails/summaryで対応。

### Step 4: フィルタリング

フィルタタブのクリックでAPI再取得（`rating` パラメータ指定）。タブにはカウントを表示して素早く状況把握できるようにする。

## ファイル変更一覧

| ファイル | 変更内容 |
|---------|---------|
| `scripts/routes/teacher.py` | `GET /api/lessons/annotated-sections` エンドポイント追加 |
| `static/js/admin/teacher.js` | 注釈一覧ボタン・展開UI・セクション詳細表示・フィルタタブ |
| `tests/test_api_teacher.py` | annotated-sections エンドポイントのテスト追加 |

## 既存コードとの関係

- `_collect_annotated_sections()` (improver.py:412) は学習分析AI用。今回のAPIは管理画面の人間用で、**切り詰めなし・dialoguesパース済み**の完全データを返す点が異なる
- 注釈の保存・トグルは既存の `setAnnotationRating()` / `PUT /api/lessons/{id}/sections/{id}/annotation` をそのまま使用（変更不要）
- 学習ダッシュボードの集計表示（◎X/△Y/✕Z）は既存のまま維持。一覧は追加機能

## UI設計の補足

- セクションカードの評価バッジは既存の注釈UIと同じ色を使用（good=#2e7d32, needs_improvement=#c62828, redo=#e65100）
- 授業名をクリックするとその授業パネルにジャンプできるリンクがあると便利（将来追加可）
- 一覧は新しい順（created_at DESC）でソート
