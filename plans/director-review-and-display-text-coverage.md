# プラン: 監督レビュー（ダメ出し→再生成）+ display_text 読み上げ強化

## ステータス: 完了

## 背景

### 問題1: セリフの品質管理がない
現在のパイプラインでは、キャラクターAIが生成したセリフはそのままTTS→再生に直行する。人間の番組制作では「監督がリハーサルを見てダメ出し→修正」というフィードバックループがあるが、現状はそれがない。結果として:
- 不自然な言い回し、キャラに合わないセリフがそのまま配信される
- display_text に書いてある内容を読み上げない（後述の問題2と直結）
- セクション間の文脈のつながりが弱い
- 情報の漏れ（教材の重要ポイントが触れられない）

### 問題2: display_text が読み上げられない
画面中央に表示される `display_text` には例文・単語・比較表・会話文などの核となる情報が含まれるが、キャラクターの対話がこれを**要約するだけで具体的に読まない**ことがある。視聴者にとって画面と音声が乖離する違和感が生まれる。

### 2つの問題の関係
監督レビューに「display_text のカバー率チェック」を組み込めば、問題2は問題1の解決の一部として自然に解決される。さらに、監督プロンプトの改善で事前に display_text カバーを強制することで、レビューで引っかかる頻度自体を下げられる。

## ゴール

1. セリフ生成後に監督がレビュー → フィードバック → 再生成（1回）のフィードバックループを追加
2. display_text のメインコンテンツ（文章・会話文・例文）は**必ず**セリフで読み上げる
3. その他の display_text 内容（表・リスト・補足）もできるだけ読み上げる
4. 管理画面でレビュー結果を全文確認できる（LLM検証可能性の原則）

## 現状のパイプライン

```
Phase A: プラン生成（知識先生 → エンタメ先生 → 監督）
    ↓ director_sections（セクション構造 + dialogue_directions）
Phase B-1: セクション構造生成（※ Phase A があればスキップ）
    ↓ structure_sections（dialogue_plan/dialogue_directions 付き）
Phase B-2: セリフ個別生成（キャラクターAIが各ターンを生成）
    ↓ dialogues[]（content, tts_text, emotion）
Phase C: TTS事前生成
    ↓ WAVファイル
再生
```

## 変更後のパイプライン

```
Phase A: プラン生成（知識先生 → エンタメ先生 → 監督）  ※変更なし
    ↓ director_sections（display_text 読み上げルール強化済み）
Phase B-1: セクション構造生成  ※変更なし
    ↓ structure_sections
Phase B-2: セリフ個別生成  ※display_text を全文渡すよう修正
    ↓ dialogues[]（初版）
Phase B-3: 監督レビュー（NEW）
    ↓ レビュー結果（approved/feedback/revised_directions セクション別）
Phase B-4: 再生成（NEW）— フィードバックを受けたセクションのみ
    ↓ dialogues[]（改善版）
Phase C: TTS事前生成  ※変更なし
再生  ※変更なし
```

## 実装ステップ

### Step 1: 監督プロンプト強化（display_text 読み上げルール）

**ファイル**: `src/lesson_generator.py` — `generate_lesson_plan()` 内の Director プロンプト（日英両方）

既存の `### display_text` セクション末尾に追加:

```
### display_text の読み上げルール（必須）
- display_text に含まれるすべての例文・会話文・重要フレーズを、dialogue_directions の key_content に分配すること
- 特にメインコンテンツの文章（会話文・例文・キーフレーズ）は1つも漏らさず key_content に含めること
- 表形式データやリストの重要項目も key_content に含めること
- display_text の内容が多い場合は、複数ターンに分けて分配する
- 目安: display_text の文字情報の 80% 以上が何らかの key_content でカバーされていること
```

**同様に** `_build_structure_prompt()` にも同じルールを追加（Phase B-1 フォールバック時用）。

### Step 2: display_text 切り詰め緩和

**ファイル**: `src/lesson_generator.py` — `_generate_single_dialogue()`

現状:
```python
user_parts.append(f"# 画面表示: {display_text[:200]}")
```

変更:
```python
user_parts.append(f"# 画面表示（視聴者に見えるテキスト — この内容を読み上げること）:\n{display_text}")
```

- 200文字制限を撤廃し、全文を渡す
- 説明文を追加して「読み上げるべきテキスト」であることを明示
- `extracted_text` は引き続き 2000 文字制限（教材全文であり参照用のため）
- max_output_tokens は 4096 のままで十分（display_text が長くてもセリフ自体は短い）

### Step 3: 監督レビュー関数の実装（Phase B-3）

**ファイル**: `src/lesson_generator.py` — 新関数 `_director_review()`

```python
def _director_review(
    client,
    sections_with_dialogues: list[dict],  # セクション + 生成済みdialogues
    extracted_text: str,
    lesson_name: str,
    en: bool,
) -> dict:
    """監督が生成済みセリフをレビューし、改善フィードバックを返す

    Returns:
        {
            "reviews": [
                {
                    "section_index": 0,
                    "approved": true/false,
                    "feedback": "改善点の具体的な指摘",
                    "revised_directions": [  # approvedがfalseの場合のみ
                        {"speaker": "teacher", "direction": "...", "key_content": "..."},
                        ...
                    ]
                },
                ...
            ],
            "overall_feedback": "全体を通してのコメント",
            "generation": { system_prompt, user_prompt, raw_output, model, temperature }
        }
    """
```

**監督レビューのシステムプロンプト内容:**

```
あなたは「監督」です。キャラクターAIが生成したセリフを監修し、ダメ出しを行ってください。

## レビュー観点

### 1. display_text カバー率（最重要）
- 各セクションの display_text に含まれるメインコンテンツ（例文・会話文・キーフレーズ）が
  セリフの中で実際に読み上げられているか確認する
- 「画面に表示されているのに読まれていない内容」があれば不合格
- 表・リストの重要項目もセリフ内で言及されているか

### 2. 自然さ・キャラらしさ
- 先生と生徒の口調がそれぞれのキャラクターに合っているか
- 不自然な言い回しやぎこちない表現がないか

### 3. セクション間の繋がり
- 前後のセクションとの文脈が途切れていないか
- 情報の流れが自然か

### 4. 情報の正確性・網羅性
- 教材の重要ポイントが漏れていないか
- 事実関係に誤りがないか

## 出力形式
各セクションについて:
- approved が true なら修正不要
- approved が false なら revised_directions（修正版の演出指示）を必ず含める
- revised_directions は元の dialogue_directions と同じ形式
```

**ユーザープロンプト内容:**

```
# 授業: {lesson_name}

# セクション一覧
{各セクションの display_text + 生成されたセリフ全文}

# 教材テキスト（参考）
{extracted_text[:3000]}
```

### Step 4: 再生成ロジック（Phase B-4）

**ファイル**: `src/lesson_generator.py` — `generate_lesson_script_v2()` に追加

Phase B-2 完了後:
1. `_director_review()` を呼び出す
2. `approved: false` のセクションについて、`revised_directions` を使って `_generate_section_dialogues()` を再呼び出し
   - revised_directions は dialogue_directions と同じ形式なので、既存の仕組みがそのまま動く
3. 再生成結果で dialogues を差し替え

**再生成は1回のみ**（無限ループ防止）。

### Step 5: generate_lesson_script_v2() の統合

**ファイル**: `src/lesson_generator.py`

`generate_lesson_script_v2()` に Phase B-3 / B-4 を統合:

```python
# --- Phase B-2: セリフ個別生成 ---（既存）
# ... 省略 ...

# --- Phase B-3: 監督レビュー ---（NEW）
_progress(step, total, "監督がセリフをレビュー中...")

# セクション + dialogues を組み合わせてレビューに渡す
sections_for_review = []
for i, s in enumerate(structure_sections):
    sections_for_review.append({
        **s,
        "dialogues": section_dialogues[i] or [],
    })

review_result = _director_review(
    client, sections_for_review, extracted_text, lesson_name, en
)

# --- Phase B-4: 再生成（不合格セクションのみ） ---（NEW）
rejected = [r for r in review_result["reviews"] if not r.get("approved")]
if rejected:
    _progress(step, total, f"監督のフィードバックに基づき{len(rejected)}セクションを再生成中...")
    for r in rejected:
        idx = r["section_index"]
        revised = r.get("revised_directions", [])
        if revised:
            # dialogue_directions を差し替えて再生成
            structure_sections[idx]["dialogue_directions"] = revised
            section_dialogues[idx] = _generate_section_dialogues(
                client, teacher_config, student_config,
                structure_sections[idx], extracted_text, lesson_name, en,
            )
```

### Step 6: レビュー結果の保存と管理画面表示

**DB**: `lesson_sections` テーブルに新カラム追加は**しない**。レビュー結果は `dialogues` JSON 内に `review` フィールドとして埋め込む。

各セクションの dialogues JSON（v4形式）:
```json
{
  "dialogues": [...],
  "review": {
    "approved": false,
    "feedback": "display_textの例文「Good morning」が読み上げられていません",
    "is_regenerated": true
  },
  "review_generation": { "system_prompt": "...", "user_prompt": "...", "raw_output": "...", "model": "...", "temperature": 1.0 },
  "review_overall_feedback": "全体を通してのコメント"
}
```

※ `review_generation` はレビュー全体で共通（セクション別ではなく1回のLLM呼び出し）のため、`review` の外に配置。

**管理画面（`static/js/admin/teacher.js`）**: スクリプト表示セクションに「監督レビュー」パネルを追加。
- 合格/不合格バッジ + 再生成済みラベル
- フィードバック全文
- レビュープロンプト折りたたみ（System/User/Raw Output）

**互換対応**: dialogues JSON の消費箇所（`lesson_runner.py`, `teacher.py` TTS生成部）に新旧形式（listまたは`{dialogues: [...]}` dict）の両方をサポートするパース処理を追加。

### Step 7: 進捗表示（SSE）の更新

**ファイル**: `scripts/routes/teacher.py`

既存のSSE進捗に Phase B-3 / B-4 のステップを追加:
- `"監督がセリフをレビュー中..."`
- `"監督のフィードバック: X セクションが不合格"`
- `"フィードバックに基づきセクション X を再生成中..."`

total ステップ数を動的に更新（レビュー+再生成分を加算）。

## 影響範囲

### 変更されたファイル
| ファイル | 変更内容 |
|---------|---------|
| `src/lesson_generator.py` | 監督プロンプト強化、display_text 切り詰め撤廃、`_director_review()` 新設、`generate_lesson_script_v2()` に Phase B-3/B-4 追加 |
| `src/lesson_runner.py` | dialogues JSON の新形式（v4 dict）パース対応 |
| `scripts/routes/teacher.py` | dialogues JSON の新形式パース対応（TTS生成部） |
| `static/js/admin/teacher.js` | レビュー結果の表示UI（バッジ＋折りたたみ）、新形式パース対応 |
| `tests/test_api_teacher.py` | レビューレスポンスモック追加、新形式アサーション |

### 変更されないもの
| ファイル | 理由 |
|---------|------|
| `src/prompt_builder.py` | key_content 経由の仕組みで十分 |
| `src/speech_pipeline.py` | TTS処理は変更不要 |
| DB スキーマ | dialogues JSON 内にレビュー結果を埋め込むため |
| `broadcast.html` | 配信画面は変更不要 |

## LLMコスト・時間の見積もり

| Phase | LLM呼び出し | 備考 |
|-------|------------|------|
| B-2（既存） | セクション数 × ターン数 回 | 変更なし |
| B-3 レビュー | **1回** | 全セクション一括レビュー |
| B-4 再生成 | 不合格セクション × ターン数 回 | 0〜全セクション分（通常は少数） |

最悪ケース（全セクション不合格）でも、Phase B-2 の 2 倍 + 1 回の追加。
通常ケースでは Phase B-2 の 1.2〜1.5 倍程度の増加を見込む。

## リスク

### レビューで全セクション不合格になり時間が倍増
- **対策**: 再生成は1回のみ（2回目のレビューはしない）。監督プロンプト強化により初版の品質を上げ、不合格率自体を下げる

### display_text が長いセクションでセリフも長くなる
- **対策**: 監督の dialogue_directions で複数ターンに分配するルールを明記。1ターンあたりの key_content は適度な量にする

### レビュー結果のJSON構造でパースエラー
- **対策**: `_parse_json_response()` の既存エラーハンドリング + リトライ（最大3回）

## 実装上のプランからの差異

| 項目 | プラン | 実装 |
|------|--------|------|
| 再生成の並列化 | `for r in rejected` 逐次ループ | `ThreadPoolExecutor(max_workers=3)` で並列再生成 |
| review_generation の配置 | `review.generation` 内 | `review_generation`（review と同階層）。レビューは全セクション一括1回のLLM呼び出しのため、セクションごとに持つ意味がない |
| 初版/改善版 diff | 折りたたみ内で diff 表示 | 未実装（再生成フラグ `is_regenerated` のみ表示）。初版データはDBに保持しないため |
| UI ファイル | `static/teacher.html` | `static/js/admin/teacher.js`（実際のレンダリング箇所） |
| lesson_runner.py | 変更不要 | dialogues JSON 新形式パースの互換対応が必要だった |

## テスト

### 自動テスト（実施済み）
- `tests/test_api_teacher.py` のスクリプト生成テスト2件を更新
  - レビューレスポンスのモック追加（全セクション合格パターン）
  - dialogues 新形式（v4 dict）のパース検証
- 全599テスト合格

### 手動テスト
1. スクリプト生成 → 管理画面でレビュー結果を確認
2. display_text の内容がセリフに含まれているか確認
3. 再生成されたセクションの品質が初版より改善されているか確認
4. 授業再生 → 画面表示と音声の一致を確認
