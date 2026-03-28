# 教師モード コンテンツ品質分析（数値化）

## 背景

教師モードではコンテンツ生成時にDirector Review（Phase B-3）がpass/failのゲートとして機能するが、**生成済みコンテンツが「配信として面白いか」を客観的に数値で評価する仕組みがない**。

現状の課題:
- Director Reviewはdisplay_textカバー率のみ重視し、エンタメ性を定量評価していない
- 生成されたコンテンツ間の比較ができない
- 「どこが弱いか」の具体的な改善指針が出ない

## 目的

生成済みの授業コンテンツを**客観的な指標で数値化**し、弱点を特定して改善に繋げる分析モードを追加する。

## 評価指標設計

### A. アルゴリズム指標（LLM不要・即時計算）

| # | 指標名 | 計算方法 | 配点 |
|---|--------|----------|------|
| A1 | **display_textカバー率** | display_textの単語/フレーズがtts_textに何%含まれるか（形態素 or トークン単位） | 20点 |
| A2 | **対話バランス** | teacher/studentの発話回数・文字数比率。偏りすぎは減点 | 10点 |
| A3 | **セクション構成多様性** | section_typeの種類数とバランス（intro/explanation/example/question/summary）| 10点 |
| A4 | **質問・クイズ充実度** | question型セクションの有無と割合 | 5点 |
| A5 | **ペーシング適正度** | セクション長のばらつき（極端に長い/短いセクションの検出）、wait_secondsの適正範囲 | 5点 |

**アルゴリズム指標合計: 50点**

### B. LLM評価指標（Gemini呼び出し）

| # | 指標名 | 評価内容 | 配点 |
|---|--------|----------|------|
| B1 | **エンタメ性** | 視聴者を引きつける展開か。意外性・ユーモア・フック | 15点 |
| B2 | **教育効果** | 学習目標が明確か。段階的に理解が深まるか | 15点 |
| B3 | **キャラクター活用** | キャラの個性が活きているか。掛け合いが自然か | 10点 |
| B4 | **全体構成力** | 導入→展開→転→まとめの流れ。起承転結がある | 10点 |

**LLM評価合計: 50点**

### 総合スコア: 100点満点

| ランク | 点数 | 判定 |
|--------|------|------|
| S | 85+ | 配信映えする優秀コンテンツ |
| A | 70-84 | 十分なクオリティ |
| B | 55-69 | 改善の余地あり |
| C | 40-54 | 要改善 |
| D | 0-39 | 作り直し推奨 |

## 実装ステップ

### Step 1: アルゴリズム指標の計算エンジン（`src/content_analyzer.py`）

新規ファイル `src/content_analyzer.py` に分析ロジックを実装。

```python
# 主要関数
def analyze_content(lesson_id: int, lang: str = "ja") -> AnalysisResult:
    """コンテンツを分析し、全指標のスコアを返す"""

def _calc_display_text_coverage(sections) -> ScoreDetail:
    """A1: display_textのtts_text内カバー率"""

def _calc_dialogue_balance(sections) -> ScoreDetail:
    """A2: teacher/student発話バランス"""

def _calc_section_diversity(sections) -> ScoreDetail:
    """A3: セクション構成の多様性"""

def _calc_question_richness(sections) -> ScoreDetail:
    """A4: クイズ・質問セクションの充実度"""

def _calc_pacing(sections) -> ScoreDetail:
    """A5: ペーシング（セクション長・wait_seconds分布）"""
```

**データ構造:**
```python
@dataclass
class ScoreDetail:
    score: float        # 獲得点
    max_score: float    # 満点
    details: str        # 説明（例: "teacher 65% / student 35%"）
    suggestions: list[str]  # 改善提案

@dataclass
class AnalysisResult:
    lesson_id: int
    lang: str
    algorithmic_scores: dict[str, ScoreDetail]  # A1-A5
    llm_scores: dict[str, ScoreDetail] | None   # B1-B4（LLM評価後）
    total_score: float
    max_score: float
    rank: str           # S/A/B/C/D
    suggestions: list[str]  # 改善提案まとめ
    analyzed_at: str
```

### Step 2: LLM評価エンジン（同ファイル内）

```python
async def _evaluate_with_llm(sections, extracted_text, lesson_name, en: bool) -> dict[str, ScoreDetail]:
    """B1-B4: LLMによるエンタメ性・教育効果・キャラ活用・構成力の評価"""
```

- **1回のLLM呼び出し**で4指標をまとめて評価（コスト削減）
- 各指標にスコア（0-max）+ 根拠 + 改善提案を返させる
- モデル: Director model（`GEMINI_DIRECTOR_MODEL`）を使用
- Temperature: 0.5（評価の安定性のため低め）

**プロンプト設計:**
- システムプロンプト: 配信コンテンツの品質評価者として各指標の基準を明示
- ユーザープロンプト: セクション構成 + display_text + 生成セリフ + 教材テキスト
- 出力: JSON `{ "entertainment": {score, reasoning, suggestions}, ... }`

### Step 3: APIエンドポイント

`scripts/routes/teacher.py` に追加:

```
POST /api/lessons/{id}/analyze
```

- パラメータ: `lang` (デフォルト "ja"), `include_llm` (デフォルト true)
- レスポンス: `AnalysisResult` のJSON
- `include_llm=false` でアルゴリズム指標のみの高速分析も可能

### Step 4: 管理画面UI

`static/js/admin/teacher.js` に分析セクションを追加:

- 各レッスンカードに「品質分析」ボタンを追加
- クリック → APIコール → 結果表示
- **表示内容:**
  - 総合スコア（大きな数字 + ランクバッジ S/A/B/C/D）
  - レーダーチャート（6-8軸の指標可視化）… は過剰なので**棒グラフ or プログレスバー**で各指標のスコアを表示
  - 各指標のスコア + 詳細 + 改善提案
  - 「LLM評価も実行」ボタン（デフォルトはアルゴリズムのみで即時表示、LLMは追加実行）

### Step 5: テスト

`tests/test_content_analyzer.py`:
- アルゴリズム指標のユニットテスト（各計算関数）
- モックデータでの統合テスト
- LLM評価はGeminiモック + レスポンス形式のテスト

`tests/test_api_teacher.py` に追加:
- `/api/lessons/{id}/analyze` エンドポイントテスト

## 実装順序

1. **Step 1** → アルゴリズム指標（LLM不要で即時テスト可能）
2. **Step 5（アルゴリズム部分）** → テスト先行
3. **Step 3** → APIエンドポイント（アルゴリズムのみで動作確認）
4. **Step 4** → UI（アルゴリズムスコアの表示）
5. **Step 2** → LLM評価追加
6. **Step 5（LLM部分）** → LLM評価テスト
7. UI更新（LLM評価結果の表示追加）

## ファイル変更一覧

| ファイル | 変更内容 |
|---------|---------|
| `src/content_analyzer.py` | **新規** — 分析エンジン |
| `scripts/routes/teacher.py` | APIエンドポイント追加 |
| `static/js/admin/teacher.js` | 品質分析UI追加 |
| `tests/test_content_analyzer.py` | **新規** — 分析テスト |
| `tests/test_api_teacher.py` | APIテスト追加 |

## リスク・注意点

- **display_textカバー率の計算精度**: 日本語は形態素解析が必要だが、外部ライブラリ追加を避けるなら文字列マッチングベースでも実用的（n-gramマッチ等）
- **LLM評価の再現性**: Temperature=0.5でも多少ブレるが、相対比較としては十分
- **コスト**: LLM評価1回 = Director model 1コール。必要時のみ実行する設計で抑制

## ステータス: 完了
