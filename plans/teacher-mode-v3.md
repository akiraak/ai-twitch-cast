# 授業モード v3 — 監督主導のセクション生成アーキテクチャ

## ステータス: 未着手

## 背景

現在の授業生成パイプライン（v2）は以下の4段階で構成されている:

```
Phase A: プラン生成（3人のエキスパート）
  知識先生 → 教材分析
  エンタメ先生 → 起承転結設計
  監督 → 統合して plan_sections を出力
    → [{section_type, title, summary, emotion, wait_seconds}]  ← メタデータのみ

Phase B-1: セクション構造生成（匿名の「構造デザイナー」LLM）
  → 各セクションの display_text + dialogue_plan を生成

Phase B-2: セリフ個別生成
  → dialogue_plan の各エントリごとに teacher/student のペルソナでLLM呼び出し

Phase C: TTS事前生成
Phase D: 授業再生
```

### 問題点

1. **監督とB-1が分断されている**: 監督はメタデータ（title, summary, emotion）しか出力しない。display_textとdialogue_planは別の「構造デザイナー」が独自に生成するため、監督の意図が完全には反映されない
2. **display_textの質が不安定**: 構造デザイナーはプランのsummary文から推測してdisplay_textを作るため、監督が意図した具体的な教材内容が欠落しがち
3. **dialogue_planが浅い**: 構造デザイナーの`direction`は「挨拶して」「リアクションして」レベルの抽象的な指示で、授業の流れを十分に制御できていない

## v3のゴール

**監督AIがセクションの完全な設計（display_text + dialogue流れ）まで責任を持ち、teacher/studentはそれに基づいてペルソナで肉付けするだけ、という明確な責任分離**

```
現行（v2）:
  監督 → メタデータ → 構造デザイナー → display_text + dialogue_plan → キャラ別セリフ生成

v3:
  監督 → display_text + dialogue_directions（セクション完全設計）→ キャラ別セリフ生成
```

## 新アーキテクチャ概要

```
教材テキスト + 画像
  │
  ▼
[Phase A: 教材分析]  ← 現行と同じ（知識 + エンタメの2人）
  知識先生 → 教材の要点・学習順序・注意点
  エンタメ先生 → 起承転結・オチ・演出設計
  │
  ▼
[Phase B: 監督によるセクション設計]  ← ★ここが変わる
  入力: 知識先生 + エンタメ先生の分析 + 教材テキスト + 画像
  出力: セクションごとに以下を決定
    - section_type, title, emotion, wait_seconds（現行通り）
    - display_text（配信画面に表示する具体的な教材内容）
    - dialogue_directions（各ターンの詳細な演出指示）
  → [{section_type, title, display_text, emotion, wait_seconds,
      dialogue_directions: [{speaker, direction, key_content}, ...]
     }]
  │
  ▼
[Phase C: セリフ個別生成]  ← 現行Phase B-2と同じ構造
  dialogue_directions の各エントリごとに:
    teacher/student のペルソナ + 監督の演出指示 → セリフ生成
  セクション間は並列、セクション内は順次（会話履歴蓄積）
  │
  ▼
[Phase D: TTS事前生成]  ← 現行Phase Cと同じ
[Phase E: 授業再生]    ← 現行Phase Dと同じ
```

## 各AIのモデル選定

### 現状の問題

現行は全ステップで同一モデル（`gemini-3-flash-preview`、環境変数 `GEMINI_CHAT_MODEL`）を使用。temperatureだけ変えているが、各AIの役割の複雑さとコスト/速度のバランスが考慮されていない。

### 選定方針

- **品質が下流に伝搬するステップ**: 上位モデルを使う。監督の出力品質はセリフ生成→TTS→再生まで全てに影響するため、ここに投資する価値が最も高い
- **呼び出し回数が多いステップ**: 高速・低コストモデルを使う。セリフ個別生成は1授業あたり10〜60回呼ばれるため、速度が重要
- **創造性 vs 正確性**: 創造性はtemperatureで制御できるため、モデル選定は主に推論力・構造化出力の信頼性で判断
- **廃止タイムライン**: Gemini 2.5 Pro / Flash は **2026/6/17 に廃止予定**。3ヶ月以内に3系への移行が必要になる

### 利用可能なモデル一覧（2026年3月時点）

| モデル | ステータス | 入力$/1M | 出力$/1M | 特徴 |
|--------|----------|---------|---------|------|
| `gemini-2.5-flash` | GA（6/17廃止） | $0.30 | $2.50 | 安定、高速、安い |
| `gemini-2.5-pro` | GA（6/17廃止） | $1.25 | $10.00 | 安定、高い推論力 |
| `gemini-3-flash-preview` | Preview | $0.50 | $3.00 | 現行デフォルト。Pro級の知性をFlash価格で |
| `gemini-3.1-flash-lite-preview` | Preview | $0.25 | $1.50 | 最安。単純タスク向け |
| `gemini-3.1-pro-preview` | Preview | $2.00 | $12.00 | 最高推論力（ARC-AGI-2: 77.1%、2.5 Proの31.1%から大幅向上） |

※ `gemini-3-pro-preview` は 2026/3/9 に廃止済み。後継が `gemini-3.1-pro-preview`

### 監督モデルの候補比較

監督はパイプラインの要であり、モデル選択の影響が最も大きい。3つの候補を比較する。

| 項目 | `gemini-2.5-pro` | `gemini-3-flash-preview` | `gemini-3.1-pro-preview` |
|------|-----------------|-------------------------|-------------------------|
| **推論力** | 高い（GA品質） | Flash級だがPro級に近い | 最高（ARC-AGI-2: 77.1%） |
| **構造化JSON信頼性** | ★★★★★ 最も安定 | ★★★☆☆ 200回に1回程度の不具合報告 | ★★★★☆ 改善されたがpreview |
| **安定性** | GA（本番SLAあり） | Preview（SLAなし） | Preview（SLAなし） |
| **コスト（1回8K入力/4K出力）** | ~$0.05 | ~$0.016 | ~$0.064 |
| **温度パラメータ** | 0.5で安定動作 | ⚠ 低温度でループの可能性。デフォルト1.0推奨 | ⚠ 同上。`thinking_level`パラメータ推奨 |
| **廃止リスク** | ⚠ 2026/6/17廃止 | 不明（previewは予告なく変更の可能性） | 不明（同上） |
| **プロンプト互換性** | 現行プロンプトがそのまま使える | 簡潔な指示を好む傾向。要調整 | 同上 |

### 推奨: 段階的移行戦略

**初期デフォルト: `gemini-3.1-pro-preview`、フォールバック: `gemini-2.5-pro`**

#### 理由

1. **推論力の圧倒的差**: 3.1 Proの推論力は2.5 Proを大幅に上回る（ARC-AGI-2: 77.1% vs 31.1%）。監督の仕事は「知識分析+エンタメ構成+教材を統合して最適なセクション設計を出す」複雑な推論タスクであり、この差が効く
2. **2.5系の廃止が迫っている**: 3ヶ月後にはどのみち3系に移行が必要。今から3.1 Proで検証を始めておく方が合理的
3. **コスト影響は軽微**: 監督は1授業1回しか呼ばない。$0.064/回。月100授業でも$6.4
4. **品質が悪ければ即フォールバック可能**: 環境変数で `GEMINI_DIRECTOR_MODEL=gemini-2.5-pro` に切り替えるだけ

#### 注意が必要な点

- **温度パラメータ**: Gemini 3系はtemperature低値(0.5等)でループする可能性がある。監督のtemperatureは **デフォルト(1.0)のまま** にし、代わりに `thinking_level: "medium"` で制御する
- **構造化JSON**: 3系のJSON出力は稀に壊れるため、既存の `_parse_json_response()` による自動修復 + リトライ（max_retries=3）を維持
- **プロンプト調整**: 3系は簡潔な指示を好む。監督プロンプトが冗長すぎると逆効果の可能性あり。v2のプロンプトをベースに、重複する制約を整理して簡潔化する

### モデル一覧（推奨）

| AI | 役割 | 推奨モデル | temperature | 選定理由 |
|----|------|-----------|-------------|---------|
| 知識先生 | 教材分析・要点抽出 | `gemini-3-flash-preview` | 0.5 → **1.0** | 抽出・整理タスク。現行デフォルトのまま。3系ではtemp 1.0が推奨 |
| エンタメ先生 | 起承転結・演出設計 | `gemini-3-flash-preview` | 0.8 → **1.0** | 創造性タスク。3系のデフォルト1.0が最適 |
| **監督** | **セクション完全設計** | **`gemini-3.1-pro-preview`** | **1.0** | **最高の推論力でパイプライン全体の品質を底上げ。1回しか呼ばないのでコスト影響は軽微。`thinking_level: "medium"` で安定性確保** |
| セリフ個別生成 | キャラペルソナで発話生成 | `gemini-3-flash-preview` | 0.7 → **1.0** | N回呼ばれるため速度優先。監督の具体的指示があるためFlashで十分 |
| TTS | 音声合成 | `gemini-2.5-flash-preview-tts` | — | 専用モデル（変更なし） |

※ temperature: Gemini 3系ではデフォルト1.0が推奨されており、低い値はループや品質低下のリスクがある。既存の0.5/0.7/0.8を一律1.0に変更する。thinking_levelで出力の安定性を制御

### 監督に 3.1 Pro を使う根拠

1. **出力の複雑さ**: セクション数×(display_text + dialogue_directions配列)のネストされたJSON。最高の推論力で構造の正確性を確保
2. **品質の伝搬効果**: 監督の出力品質が低い → セリフの質が下がる → 授業全体が悪化。逆に監督が良ければ下流は簡単な指示で高品質なセリフを生成できる
3. **コスト効率**: 1授業あたり1回の呼び出し。$0.064/回。全体コストの5%未満
4. **教材理解の深さ**: 知識先生 + エンタメ先生の分析 + 教材テキスト + 画像を統合して判断。ARC-AGI-2 77.1%の新規問題解決力が活きるタスク
5. **廃止リスク回避**: 2.5 Proは3ヶ月後に廃止。今から3.1 Proで検証しておくことで移行リスクを軽減

### セリフ生成に Flash を使う根拠

1. **呼び出し回数**: 10セクション × 平均4ターン = 40回。速度とコストが直接影響
2. **制約の明確さ**: v3では監督が `direction`（2〜3文の具体的指示）+ `key_content`（言及すべき内容）を提供するため、モデルは「指示に従ってキャラらしく話す」だけでよい
3. **出力の単純さ**: `{content, tts_text, emotion}` の3フィールドのみ。構造化出力の失敗リスクが低い
4. **並列実行**: セクション間は最大3並列で実行するため、レイテンシの低いFlashが有利

### 実装方法

各AIのモデルを個別の環境変数で制御する:

```bash
# .env
GEMINI_KNOWLEDGE_MODEL=gemini-3-flash-preview         # 知識先生
GEMINI_ENTERTAINMENT_MODEL=gemini-3-flash-preview      # エンタメ先生
GEMINI_DIRECTOR_MODEL=gemini-3.1-pro-preview           # 監督（★ 3.1 Pro）
GEMINI_DIALOGUE_MODEL=gemini-3-flash-preview           # セリフ個別生成
GEMINI_TTS_MODEL=gemini-2.5-flash-preview-tts          # TTS（既存）
```

フォールバック: 個別環境変数が未設定の場合は `GEMINI_CHAT_MODEL`（現行のデフォルト）を使用。既存の動作を壊さない。

```python
def _get_director_model():
    return os.environ.get("GEMINI_DIRECTOR_MODEL",
           os.environ.get("GEMINI_CHAT_MODEL", "gemini-3.1-pro-preview"))

def _get_dialogue_model():
    return os.environ.get("GEMINI_DIALOGUE_MODEL",
           os.environ.get("GEMINI_CHAT_MODEL", "gemini-3-flash-preview"))
```

### Gemini 3系への移行で必要な変更

| 変更項目 | 内容 | 影響範囲 |
|---------|------|---------|
| temperature | 0.5 / 0.7 / 0.8 → **1.0**（3系デフォルト） | 全LLM呼び出し |
| thinking制御 | 監督: `thinking_level: "medium"` 追加 | 監督の `GenerateContentConfig` |
| プロンプト簡潔化 | 冗長な制約を整理。3系は簡潔な指示を好む | 監督プロンプト |
| JSONリトライ | 3系の構造化出力バグ対策として `max_retries=3` 維持 | 既存のまま（変更不要） |

### コスト試算（1授業あたり）

前提: 10セクション、平均4ターン/セクション = 40セリフ

| ステップ | 回数 | モデル | 入力$/1M | 出力$/1M | 1授業あたりコスト |
|---------|------|--------|---------|---------|----------------|
| 知識先生 | 1 | 3 Flash | $0.50 | $3.00 | ~$0.006 |
| エンタメ先生 | 1 | 3 Flash | $0.50 | $3.00 | ~$0.009 |
| 監督 | 1 | **3.1 Pro** | $2.00 | $12.00 | ~$0.064 |
| セリフ生成 | 40 | 3 Flash | $0.50 | $3.00 | ~$0.054 |
| **合計** | 43 | — | — | — | **~$0.133** |

監督のPro呼び出し($0.064)は全体の約48%を占めるが、1授業$0.13は十分に許容範囲。2.5 Proに下げれば$0.05で全体$0.12程度になるが、品質差を考えると3.1 Proが妥当。

---

## 詳細設計

### Phase A: 教材分析（変更なし）

知識先生とエンタメ先生は現行のまま。2回のLLM呼び出し。

- 知識先生: 要点抽出、学習順序、誤解ポイント
- エンタメ先生: 起承転結、オチ、演出ポイント

### Phase B: 監督によるセクション設計（★主要変更）

現行のPhase A-監督とPhase B-1を統合。1回のLLM呼び出しで以下を全て決定する。

#### 監督への入力

```
システムプロンプト: 監督の役割定義（下記参照）
ユーザープロンプト:
  - 知識先生の分析
  - エンタメ先生の構成
  - 教材テキスト
  - 画像（あれば）
```

#### 監督の出力

```json
[
  {
    "section_type": "introduction",
    "title": "挨拶の常識？",
    "display_text": "今日のテーマ: 英語の挨拶\n\n『How are you?』の本当の意味とは？\n\n日本語の『元気？』とは全然違う！",
    "emotion": "excited",
    "wait_seconds": 2,
    "question": "",
    "answer": "",
    "dialogue_directions": [
      {
        "speaker": "teacher",
        "direction": "視聴者に元気よく挨拶。今日のテーマ『英語の挨拶の本当の意味』を紹介し、「How are you?って実はすごく奥が深い」と興味を引く",
        "key_content": "How are you? の本当の意味"
      },
      {
        "speaker": "student",
        "direction": "「え、How are you?なんて簡単じゃん！I'm fine って答えればいいんでしょ？」と自信満々に反応する",
        "key_content": "I'm fine, thank you の定型文"
      },
      {
        "speaker": "teacher",
        "direction": "「ふふ、実はそれ…ネイティブはほぼ使わないんだよ」と意外な事実を予告。この授業で秘密を解き明かすと宣言",
        "key_content": "I'm fine はネイティブが使わない"
      }
    ]
  }
]
```

#### 監督プロンプトの設計方針

現行の監督プロンプト（`director_prompt`）を拡張し、以下の責任を追加:

1. **display_text設計**: 単なるタイトルではなく、視聴者が配信画面で見る具体的な教材コンテンツ（例文・比較表・クイズ選択肢）を含める。現行B-1の制約をそのまま監督に移行
2. **dialogue_directions設計**: 「誰が何を話すか」だけでなく「どう話すか」「何の教材内容に触れるか」まで具体的に指示。`key_content`フィールドで、そのターンで必ず言及すべき教材内容を指定
3. **セクション間の繋がり**: 前セクションの内容を受けて次セクションが自然に始まるよう、流れを意識した設計

#### dialogue_directions の direction フィールドの粒度

現行B-1の `dialogue_plan[].direction` との違い:

| 項目 | 現行 B-1（構造デザイナー） | v3（監督） |
|------|--------------------------|-----------|
| 粒度 | 「挨拶して」「リアクションして」 | 「元気よく挨拶し、How are you?の本当の意味がテーマだと紹介」 |
| 教材との紐付け | なし | `key_content` で教材のどの部分に触れるか明示 |
| 感情の指定 | セクション全体で1つ | ターンごとの感情の起伏をdirectionに含める |
| 視聴者への効果 | 考慮なし | 「興味を引く」「驚かせる」等の演出意図を含む |

### Phase C: セリフ個別生成（軽微な変更）

現行Phase B-2と同じ構造だが、入力が改善される:

- `dialogue_directions[].direction` がより具体的になるため、セリフの質が向上
- `dialogue_directions[].key_content` をユーザープロンプトに含め、教材内容への言及を確実にする

```python
# ユーザープロンプト（v3での変更箇所）
user_parts = [
    f"# 授業: {lesson_name}",
    f"# セクション: {section_type}",
    f"# 画面表示: {display_text[:200]}",
]
# ★追加: key_content
if key_content:
    user_parts.append(f"# このターンで触れるべき内容: {key_content}")
user_parts.append(f"\n## このターンの演出指示\n{direction}")
# ... 以下は現行通り（会話履歴、教材テキスト）
```

### Phase D / E: TTS事前生成・授業再生（変更なし）

現行のPhase C / Phase Dをそのまま使用。

---

## 実装ステップ

### Step 0: モデルヘルパー関数の追加

**対象ファイル**: `src/lesson_generator.py`

**変更内容**:
- 既存の `_get_model()` に加え、役割別のモデル取得関数を追加:
  ```python
  def _get_knowledge_model():
      return os.environ.get("GEMINI_KNOWLEDGE_MODEL",
             os.environ.get("GEMINI_CHAT_MODEL", "gemini-3-flash-preview"))

  def _get_entertainment_model():
      return os.environ.get("GEMINI_ENTERTAINMENT_MODEL",
             os.environ.get("GEMINI_CHAT_MODEL", "gemini-3-flash-preview"))

  def _get_director_model():
      return os.environ.get("GEMINI_DIRECTOR_MODEL",
             os.environ.get("GEMINI_CHAT_MODEL", "gemini-3.1-pro-preview"))

  def _get_dialogue_model():
      return os.environ.get("GEMINI_DIALOGUE_MODEL",
             os.environ.get("GEMINI_CHAT_MODEL", "gemini-3-flash-preview"))
  ```
- 知識先生の呼び出し（行364）を `_get_knowledge_model()` に変更
- エンタメ先生の呼び出し（行475）を `_get_entertainment_model()` に変更
- 監督の呼び出し（行613）を `_get_director_model()` に変更
- セリフ個別生成の呼び出し（行1428）を `_get_dialogue_model()` に変更
- `.env.example` にも新しい環境変数を追記

### Step 1: 監督プロンプトの拡張

**対象ファイル**: `src/lesson_generator.py`

**変更内容**:
- `generate_lesson_plan()` 内の監督（Director）ステップを拡張
- 現行の出力 `[{section_type, title, summary, emotion, has_question, wait_seconds}]` を以下に変更:
  ```
  [{section_type, title, display_text, emotion, wait_seconds, question, answer,
    dialogue_directions: [{speaker, direction, key_content}]
  }]
  ```
- 監督プロンプト（`director_prompt`）に以下を追加:
  - display_textの詳細ガイドライン（現行 `_build_structure_prompt()` からの移植）
  - dialogue_directionsの設計ガイドライン
  - `key_content` フィールドの説明
- 出力MIMEは `application/json` のまま（現行通り）

**モデル**: `gemini-3.1-pro-preview`（`_get_director_model()`）。最高の推論力で複雑な構造化JSON出力の品質を確保
**温度**: Gemini 3系ではtemperature 1.0（デフォルト）を使用。`thinking_level: "medium"` で安定性を確保

### Step 2: 全LLM呼び出しに generation メタデータを付与

**対象ファイル**: `src/lesson_generator.py`

**現状の問題**:
- Phase A（知識先生・エンタメ先生・監督）はプロンプトや生出力を保存していない
- 管理画面（teacher.js）はプロンプトをJSにハードコードして表示 → Python側と乖離するリスク
- Phase B-2のセリフ個別生成だけが `generation` メタデータを返している

**変更内容**:

すべてのLLM呼び出しで、以下の `generation` メタデータを記録して戻り値に含める:

```python
generation = {
    "system_prompt": system_prompt,    # 実際に使ったシステムプロンプト全文
    "user_prompt": user_prompt,        # 実際に使ったユーザープロンプト全文
    "raw_output": response.text,       # LLMの生出力（パース前）
    "model": model_name,              # 使用モデル名
    "temperature": temperature,        # 使用temperature
}
```

`generate_lesson_plan()` の戻り値を拡張:

```python
return {
    "knowledge": knowledge_text,
    "entertainment": entertainment_text,
    "director_sections": director_sections,
    "plan_sections": plan_sections,         # 互換性維持
    # ★追加: 各ステップの generation メタデータ
    "generations": {
        "knowledge": {
            "system_prompt": knowledge_prompt,
            "user_prompt": user_text,
            "raw_output": knowledge_text,
            "model": knowledge_model,
            "temperature": 1.0,
        },
        "entertainment": {
            "system_prompt": entertainment_prompt,
            "user_prompt": user_text + knowledge_text,
            "raw_output": entertainment_text,
            "model": entertainment_model,
            "temperature": 1.0,
        },
        "director": {
            "system_prompt": director_prompt,
            "user_prompt": knowledge_text + entertainment_text,
            "raw_output": raw_director_output,  # パース前の生JSON文字列
            "model": director_model,
            "temperature": 1.0,
        },
    },
}
```

**注**: セリフ個別生成（Phase C）は既に `generation` メタデータを返しており変更不要

### Step 3: generate_lesson_script_v2() の Phase B-1 除去

**対象ファイル**: `src/lesson_generator.py`

**変更内容**:
- `generate_lesson_script_v2()` が `director_sections` を受け取る場合、Phase B-1（`_build_structure_prompt()` + LLM呼び出し）をスキップ
- 代わりに `director_sections` の `dialogue_directions` を直接 Phase C（セリフ個別生成）に渡す
- `director_sections` がない場合（旧プランからの移行）は現行のPhase B-1にフォールバック

```python
def generate_lesson_script_v2(
    lesson_name, extracted_text,
    plan_sections=None,
    director_sections=None,  # ★追加
    source_images=None,
    on_progress=None,
    teacher_config=None,
    student_config=None,
) -> list[dict]:
    if director_sections:
        # v3パス: 監督の設計をそのまま使う（Phase B-1スキップ）
        structure_sections = director_sections
    else:
        # v2フォールバック: 従来のPhase B-1
        structure_sections = _generate_structure(...)

    # Phase C: セリフ個別生成（共通）
    ...
```

### Step 4: _generate_single_dialogue() のkey_content対応

**対象ファイル**: `src/lesson_generator.py`

**変更内容**:
- `dialogue_plan_entry` に `key_content` があればユーザープロンプトに含める
- フィールド名は `dialogue_plan` → `dialogue_directions` に変更（ただし旧名も互換対応）

### Step 5: teacher.py ルートの対応

**対象ファイル**: `scripts/routes/teacher.py`

**変更内容**:

#### 5-1. プラン生成API（`/generate-plan`）

- `generate_lesson_plan()` の戻り値に含まれる `director_sections` と `generations` をDBに保存
- SSE最終イベントに `generations` を含める:
  ```python
  result = {
      "ok": True,
      "plan_sections": plan["plan_sections"],
      "director_sections": plan["director_sections"],
      "generations": plan["generations"],  # ★追加
  }
  ```

#### 5-2. スクリプト生成API（`/generate-script`）

- DBから `director_sections` を取得して `generate_lesson_script_v2()` に渡す
- v3パス（director_sectionsあり）ではPhase B-1がスキップされるため、SSE進捗もそれに合わせて更新

#### 5-3. レッスン取得API（`GET /api/lessons/{id}`）

- レスポンスに `generations`（プラン生成時のメタデータ）を含める
- 管理画面がリロードしても全プロンプトを表示できるようにする

### Step 6: DBスキーマの調整 — 監督の出力の保存先

**対象ファイル**: `src/db.py`

監督が生成するデータは3つのレベルに分かれて保存される:

#### 保存先の全体像

```
lesson_plans テーブル（言語別、1レコード/言語）
  ├── knowledge TEXT         — 知識先生の分析（現行通り）
  ├── entertainment TEXT     — エンタメ先生の構成（現行通り）
  ├── plan_json TEXT         — 互換用メタデータ（現行通り）
  ├── director_json TEXT     — ★追加: 監督の完全出力（JSON配列全体）
  └── plan_generations TEXT  — ★追加: 全LLM呼び出しのメタデータ
                               {knowledge: {system_prompt, user_prompt, raw_output, model, temperature},
                                entertainment: {...},
                                director: {...}}

lesson_sections テーブル（セクション別、1レコード/セクション）
  ├── display_text TEXT      — 監督が設計 → そのまま保存（現行カラム流用）
  ├── dialogue_directions TEXT — ★追加: 監督のそのセクションの演出指示
  │                              [{speaker, direction, key_content}, ...]
  ├── dialogues TEXT         — Phase Cで生成されたセリフ（現行カラム流用）
  │                            各エントリに generation メタデータ含む
  │                            [{speaker, content, tts_text, emotion,
  │                              direction_index: 0,  ← ★追加: dialogue_directionsの何番目か
  │                              generation: {system_prompt, user_prompt, raw_output, ...}
  │                            }, ...]
  └── (他の既存カラム: section_type, title, content, tts_text, emotion, ...)
```

#### なぜ2箇所に保存するか

| 保存先 | 内容 | 用途 |
|--------|------|------|
| `lesson_plans.director_json` | 監督の出力JSON全体 | 管理画面Phase Aの表示（監督の生出力確認）、再生成時の比較 |
| `lesson_sections.dialogue_directions` | セクション単位の演出指示 | 管理画面Phase Cの表示（指示↔セリフの対応確認）、セクション単体再生成時の入力 |

`director_json` はレッスン全体の一枚のスナップショット。`dialogue_directions` はセクション単位に分解したもの。同じデータの2つのビュー。

#### 変更内容

**`lesson_plans` テーブル**（Migration追加）:
```sql
ALTER TABLE lesson_plans ADD COLUMN director_json TEXT NOT NULL DEFAULT '';
ALTER TABLE lesson_plans ADD COLUMN plan_generations TEXT NOT NULL DEFAULT '';
```

**`lesson_sections` テーブル**（Migration追加）:
```sql
ALTER TABLE lesson_sections ADD COLUMN dialogue_directions TEXT NOT NULL DEFAULT '';
```

**`dialogues` JSON内の各エントリに `direction_index` を追加**:
- Phase Cのセリフ生成時に、何番目の `dialogue_directions` エントリから生成されたかを記録
- 管理画面で「監督の指示 → 実際のセリフ」の対応を表示するために使用
- 既存のdialoguesスキーマに1フィールド追加するだけなのでDB Migration不要（JSON内）

#### データの流れ

```
プラン生成時:
  generate_lesson_plan()
    → director_sections（監督の完全出力）
    → lesson_plans.director_json に全体を保存
    → lesson_plans.plan_generations にメタデータを保存

スクリプト生成時:
  generate_lesson_script_v2(director_sections=...)
    → 各セクションの dialogue_directions を lesson_sections.dialogue_directions に保存
    → 各セクションの display_text を lesson_sections.display_text に保存
    → Phase Cで生成された dialogues を lesson_sections.dialogues に保存
      （各エントリに direction_index + generation メタデータ付き）

管理画面表示時:
  GET /api/lessons/{id}
    → lesson_plans から plan_generations を取得（Phase A表示用）
    → lesson_sections から dialogue_directions + dialogues を取得（Phase C表示用）
    → dialogue_directions[i] と dialogues[direction_index==i] を紐付けて表示
```

### Step 7: 管理画面 — 全LLM入出力の可視化

**対象ファイル**: `static/js/admin/teacher.js`

#### 現状の問題

| 問題 | 影響 |
|------|------|
| プロンプトがJSにハードコード | Python側を変更してもUIに反映されない。二重管理のメンテコスト |
| Phase B-1（構造生成）のプロンプトが非表示 | v2で構造デザイナーが何をしたか確認不可能 |
| 非v2パスではメタデータが一切ない | 品質問題の原因特定が困難 |
| 生成方式の説明文が不正確 | 「1回のLLM呼び出し」と書いてあるがv2では個別呼び出し |

#### v3での方針: **全プロンプトをAPIから取得、JSのハードコードを廃止**

管理画面は `plan_generations`（DB保存）と各dialogueの `generation` フィールド（既存）からデータを取得し、JSにプロンプトを一切ハードコードしない。

#### UI設計: LLMデータフロー全体表示

授業コンテンツの詳細画面で、生成パイプライン全体を以下のカード形式で表示する:

```
┌─────────────────────────────────────────────────────────┐
│ 📘 Phase A: 教材分析                                      │
│                                                          │
│ ┌─ Step 1: 知識先生 ──────────────────────────────────┐  │
│ │ モデル: gemini-3-flash-preview  温度: 1.0           │  │
│ │                                                     │  │
│ │ ▶ システムプロンプト（クリックで展開）                  │  │
│ │   ┌───────────────────────────────────────────┐    │  │
│ │   │ あなたは「知識先生」です。教科主任として... │    │  │
│ │   └───────────────────────────────────────────┘    │  │
│ │                                                     │  │
│ │ ▶ ユーザープロンプト（クリックで展開）                  │  │
│ │   ┌───────────────────────────────────────────┐    │  │
│ │   │ # 授業タイトル: ...                         │    │  │
│ │   │ # 教材テキスト: ...                         │    │  │
│ │   └───────────────────────────────────────────┘    │  │
│ │                                                     │  │
│ │ ▶ 出力（クリックで展開、デフォルト展開）               │  │
│ │   ┌───────────────────────────────────────────┐    │  │
│ │   │ ### 教えるべき要点                          │    │  │
│ │   │ 1. How are you? の社会的機能...             │    │  │
│ │   └───────────────────────────────────────────┘    │  │
│ └─────────────────────────────────────────────────────┘  │
│                                                          │
│        ↓ 知識先生の出力が入力に含まれる                     │
│                                                          │
│ ┌─ Step 2: エンタメ先生 ──────────────────────────────┐  │
│ │ （同じ構造: プロンプト + 出力）                       │  │
│ └─────────────────────────────────────────────────────┘  │
│                                                          │
│        ↓ 知識 + エンタメの出力が入力に含まれる              │
│                                                          │
│ ┌─ Step 3: 監督 ──────────────────── gemini-3.1-pro ──┐  │
│ │ ▶ システムプロンプト                                  │  │
│ │ ▶ ユーザープロンプト                                  │  │
│ │ ▶ 生出力（JSON）                                     │  │
│ │                                                     │  │
│ │ 📋 パース結果: 8セクション                            │  │
│ │ ┌ セクション1 [introduction] 挨拶の常識？ ──────────┐ │  │
│ │ │ display_text: 今日のテーマ: 英語の挨拶...         │ │  │
│ │ │ dialogue_directions:                              │ │  │
│ │ │   [1] teacher: 視聴者に挨拶し...                  │ │  │
│ │ │       key_content: How are you?の本当の意味       │ │  │
│ │ │   [2] student: 自信満々にI'm fineと...            │ │  │
│ │ │       key_content: I'm fine の定型文              │ │  │
│ │ └──────────────────────────────────────────────────┘ │  │
│ │ ┌ セクション2 [explanation] ... ────────────────────┐ │  │
│ │ │ ...                                               │ │  │
│ │ └──────────────────────────────────────────────────┘ │  │
│ └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ 🎭 Phase C: セリフ個別生成                                │
│                                                          │
│ ┌ セクション1 [introduction] ─────────────────────────┐  │
│ │                                                     │  │
│ │ [1] 🎤 teacher（ちょビ）                             │  │
│ │   監督の指示: 視聴者に挨拶し、テーマを紹介...          │  │
│ │   key_content: How are you?の本当の意味              │  │
│ │                                                     │  │
│ │   ▶ システムプロンプト                                │  │
│ │   ▶ ユーザープロンプト                                │  │
│ │   ▶ 生出力（JSON）                                   │  │
│ │                                                     │  │
│ │   結果: 「みんな、いらっしゃい！...」                  │  │
│ │   感情: excited  🔊 TTS: section_00_dlg_00.wav       │  │
│ │                                                     │  │
│ │ [2] 🎤 student（なるこ）                              │  │
│ │   監督の指示: I'm fineと自信満々に...                  │  │
│ │   ...                                               │  │
│ └─────────────────────────────────────────────────────┘  │
│                                                          │
│ ┌ セクション2 ... ────────────────────────────────────┐  │
│ └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ 🔊 Phase D: TTS生成状況                                  │
│  セクション1: 3/3 生成済み (▶再生ボタン各発話)             │
│  セクション2: 2/4 生成済み                                │
│  ...                                                     │
└─────────────────────────────────────────────────────────┘
```

#### 実装詳細

**データソース（JSハードコード廃止）**:

| 表示項目 | 現行のデータソース | v3のデータソース |
|---------|-----------------|----------------|
| 知識先生のプロンプト | JSにハードコード | `plan_generations.knowledge.system_prompt` (API) |
| 知識先生の出力 | `langPlan.knowledge` (API) | `plan_generations.knowledge.raw_output` (API) |
| エンタメ先生のプロンプト | JSにハードコード | `plan_generations.entertainment.system_prompt` (API) |
| エンタメ先生の出力 | `langPlan.entertainment` (API) | `plan_generations.entertainment.raw_output` (API) |
| 監督のプロンプト | JSにハードコード | `plan_generations.director.system_prompt` (API) |
| 監督の生出力 | なし（パース後のみ） | `plan_generations.director.raw_output` (API) |
| セリフのプロンプト | `dialogue.generation.*` (API) ✓ | 同左（変更なし）|
| 使用モデル名 | 表示なし | `generation.model` (API) |

**折りたたみルール**:

| 項目 | デフォルト状態 | 理由 |
|------|-------------|------|
| システムプロンプト | 折りたたみ | 長い。確認時のみ展開 |
| ユーザープロンプト | 折りたたみ | 同上 |
| 生出力 | **展開** | 最も頻繁に確認する情報 |
| パース結果（セクション一覧） | **展開** | 監督の設計意図を一目で確認 |
| 各セリフの generation | 折りたたみ | 必要時のみ展開 |

**データフローの可視化**:
- 各ステップ間に「↓ 前ステップの出力が入力に含まれる」の矢印を表示
- 監督のdialogue_directionsの各エントリが、Phase Cのどのセリフに対応するか、番号で紐付けを表示

**変更対象ファイル**:
- `static/js/admin/teacher.js` — `buildLessonItem()` の Phase A 表示を `plan_generations` ベースに書き換え。JS内のハードコードプロンプトを全て削除
- `scripts/routes/teacher.py` — `GET /api/lessons/{id}` のレスポンスに `plan_generations` を含める

---

## LLM呼び出し回数の比較

| フェーズ | 現行（v2） | v3 |
|---------|-----------|-----|
| 知識先生 | 1回 | 1回 |
| エンタメ先生 | 1回 | 1回 |
| 監督 | 1回（メタデータのみ） | 1回（display_text + dialogue_directions含む）|
| 構造デザイナー（B-1）| 1回 | **削除** |
| セリフ個別生成 | N回（ターン数分） | N回（ターン数分） |
| **合計** | **4 + N 回** | **3 + N 回** |

LLM呼び出し回数が1回削減される。かつ、監督の出力がそのままセリフ生成の入力になるため、中間変換でのロスがなくなる。

## リスク

| リスク | 対策 |
|--------|------|
| 監督プロンプトが長くなり出力品質が下がる | display_textとdialogue_directionsの具体例を豊富にプロンプトに含める。temperatureは0.5で安定性優先 |
| 監督の出力JSONが巨大になりパース失敗が増える | `max_output_tokens` を 8192 に増やす。既存の `_parse_json_response()` で自動修復 |
| 既存プランとの互換性が崩れる | `director_sections` がない場合は現行B-1にフォールバック。段階的移行 |
| 監督が教材内容を正確にdisplay_textに反映しない | 教材テキスト + 画像を監督に直接渡す（現行の構造デザイナーと同じ）|
| dialogue_directionsの粒度が粗い/細かすぎる | プロンプトで「2〜3文の具体的な指示」と明記。生成結果を管理画面で確認できる体制を維持 |
| Gemini 3系のJSON出力バグ（200回に1回） | 既存の `_parse_json_response()` 自動修復 + `max_retries=3` で吸収。リトライ機構は現行のまま維持 |
| Gemini 3系のtemperature動作変更 | 全LLM呼び出しをtemperature 1.0に統一。監督は `thinking_level: "medium"` で安定性確保 |
| `gemini-3.1-pro-preview` がpreviewで突然変更/廃止される | 環境変数で即座に `gemini-2.5-pro` にフォールバック可能。2.5 Pro廃止(6/17)までに3系GAが出なければ再検討 |

## 検証方法

1. `python3 -m pytest tests/ -q` — 全テスト通過
2. 短い教材でプラン生成 → `director_sections` の内容確認
   - `display_text` が具体的な教材内容を含んでいるか
   - `dialogue_directions` が十分に具体的か
   - `key_content` が教材の要点を網羅しているか
3. スクリプト生成 → セリフが監督の指示通りになっているか
4. TTS + 授業再生 → 全体の流れが自然か
5. **管理画面の全データフロー検証**:
   - [ ] Phase A の3ステップ全てで、システムプロンプト・ユーザープロンプト・生出力が折りたたみで全文表示される
   - [ ] プロンプトがJSハードコードではなくAPIから取得されている（Python側を変更→管理画面に即反映）
   - [ ] 各ステップの使用モデル名とtemperatureが表示される
   - [ ] ステップ間のデータフロー（前ステップの出力→次ステップの入力）が矢印で表示される
   - [ ] 監督のパース結果がセクション一覧で展開表示される（display_text + dialogue_directions + key_content）
   - [ ] Phase C の各セリフで generation メタデータ（プロンプト全文・生出力）が折りたたみで確認できる
   - [ ] 監督の dialogue_directions と Phase C の各セリフの紐付けが番号で分かる
   - [ ] ページリロード後も全データが保持されている（DB保存が正しく動いている）
