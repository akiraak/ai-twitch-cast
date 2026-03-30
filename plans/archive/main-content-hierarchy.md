# メインコンテンツ階層構造導入

## ステータス: 完了

## 背景

現在 `extract_main_content()` はフラットなリストを返し、すべてのコンテンツブロックが同レベル扱い。教科書ページをスキャンした場合、通常は主要コンテンツ（メイン会話文など）1つと補助コンテンツ（語彙リスト・文法説明など）がある。これを明確に区別し、授業スクリプト生成時にメインコンテンツを優先的にカバーさせたい。

## 方針

既存の配列構造に `role` フィールドを追加（フラット構造を維持、ネストしない）。

- ネストJSON（children）はLLMの出力精度が下がり、全消費箇所で再帰処理が必要になるため不採用
- `role: "main"` は必ず1つだけ。残りはすべて `role: "sub"`

```json
[
  {"content_type": "conversation", "content": "...", "label": "メイン会話", "role": "main"},
  {"content_type": "word_list", "content": "...", "label": "関連語彙", "role": "sub"},
  {"content_type": "passage", "content": "...", "label": "文法補足", "role": "sub"}
]
```

## 対象ファイル

| ファイル | 変更内容 |
|---------|---------|
| `src/lesson_generator.py` | プロンプト・抽出・フォーマット・構造生成・監督レビュー |
| `static/js/admin/teacher.js` | UI表示（主要/補助の視覚区別） |
| `tests/test_lesson_generator.py` | テスト更新・追加 |
| `tests/test_api_teacher.py` | テスト更新 |

## 実装ステップ

### Step 1: `_normalize_roles()` ヘルパー追加 + `extract_main_content()` 更新
**ファイル**: `src/lesson_generator.py`

LLMがroleを正しく出力しなかった場合のバリデーション関数を追加：
- main が0個 → 最初のアイテムを main に
- main が2個以上 → 最初の1つだけ残し、残りを sub に
- role フィールドなし → 補完

`extract_main_content()` の戻り値に `_normalize_roles()` を適用。

### Step 2: `_EXTRACT_MAIN_CONTENT_PROMPT` 更新
**ファイル**: `src/lesson_generator.py`

プロンプトに `role` フィールドの指示を追加：
- `"main"`: 教材の主要コンテンツ（必ず1つだけ）
- `"sub"`: 補助的コンテンツ
- JSONサンプルにも role を含める

### Step 3: `_format_main_content_for_prompt()` 更新
**ファイル**: `src/lesson_generator.py`

役割に応じたタグを付与：
- main → `★ 主要` / `★ PRIMARY`
- sub → `補助` / `supplementary`
- 後方互換: `role` フィールドなし → 最初=main, 残り=sub

### Step 4: `_build_structure_prompt()` に優先度ガイダンス追加
**ファイル**: `src/lesson_generator.py`

英語/日本語両方のプロンプトに追加：
- ★ 主要アイテムは dialogue_plan で完全カバー必須
- 補助アイテムは自然な箇所で取り入れるが優先度低

### Step 5: `_director_review()` にロール対応レビュー基準追加
**ファイル**: `src/lesson_generator.py`

英語/日本語両方に追加：
- ★ 主要アイテムの未カバーは不合格
- 補助アイテムは部分カバーで可

### Step 6: Teacher UI 更新
**ファイル**: `static/js/admin/teacher.js`

- main: 太い左ボーダー（5px）、ゴールド背景、★マーク
- sub: 現状のスタイルを維持（若干控えめに）
- 後方互換: role なし → 最初=main, 残り=sub

### Step 7: テスト更新
**ファイル**: `tests/test_lesson_generator.py`, `tests/test_api_teacher.py`

- 既存テストのモックレスポンスに `role` フィールド追加
- `_normalize_roles()` のテスト追加（main なし、複数 main、正常ケース）
- プロンプトに `PRIMARY`/`主要` が含まれることの確認
- API テストのモックに role 追加

## 後方互換性

DBスキーマ変更なし。既存データ（role フィールドなし）は消費側のフォールバックで対応：
- `_format_main_content_for_prompt()`: 最初=main扱い
- `teacher.js`: 最初=main扱い
- 新規抽出時は `_normalize_roles()` が必ず role を付与

## リスク

- **LLM出力精度**: Geminiが `role` を正しく付けない可能性 → `_normalize_roles()` がセーフティネット
- **プロンプト長**: 優先度ガイダンス追加は3-4行/言語 → 影響軽微

## 検証方法

```bash
# テスト実行
python3 -m pytest tests/test_lesson_generator.py tests/test_api_teacher.py -q

# 手動: 既存レッスンのテキスト再抽出 → role フィールド付与を確認
# 手動: UIで★主要コンテンツが視覚的に区別されることを確認
```
