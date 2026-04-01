# 授業コンテンツ バージョニング機能

## ステータス: Step 6 完了

## 背景

現在、教師モードで授業スクリプト（セクション）をインポートすると、同じ `(lang, generator)` の既存セクションが置き換わる。過去のスクリプトは失われ、比較や改善の起点にできない。

**目的**: 1つの授業で複数バージョンのスクリプトを保持し、既存コンテンツを検証しながらバージョンアップできるようにする。

## 設計方針

### コアコンセプト

- **バージョン = セクション群のスナップショット**。1つの `(lesson_id, lang, generator)` に対して複数バージョンが存在できる
- 各バージョンに `version_number`（1, 2, 3...）を付与
- **どのバージョンでも再生できる**。授業開始時にバージョンを指定する
- **どのバージョンからでも改善を生成できる**。v1→v3 のように飛ばすことも可能
- ロールバック・アクティブの概念は不要。バージョンは全て対等で、再生や改善の起点として選択するだけ

### 既存の lang × generator 軸との関係

現在のDBは `(lesson_id, lang, generator)` の組み合わせでセクション・プランを管理している。バージョンはこの軸に直交する3番目の次元として追加する:

```
lesson_id × lang × generator × version_number
```

## DBスキーマ変更

### 0. `lessons` テーブルに `category` カラム追加

```sql
ALTER TABLE lessons ADD COLUMN category TEXT NOT NULL DEFAULT '';
```

- 教材の種類を表す（例: `"english_natgeo"`, `"programming_python"`, `"math_basics"`）
- 学習ループでカテゴリ別にパターンを蓄積・適用する軸になる
- 空文字 = 未分類（学習対象外ではないが、カテゴリ特化の学習には使われない）
- カテゴリ一覧は `lesson_categories` テーブルで管理（後述）

### 0.5 新テーブル: `lesson_categories`

```sql
CREATE TABLE IF NOT EXISTS lesson_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,           -- 'english_natgeo', 'programming_python' 等
    name TEXT NOT NULL,                  -- '英語（ナショジオ）', 'プログラミング（Python）' 等
    description TEXT DEFAULT '',         -- カテゴリの説明（生成プロンプトに含められる）
    prompt_file TEXT DEFAULT '',         -- カテゴリ専用プロンプト（例: 'lesson_generate_english_natgeo.md'）
    created_at TEXT NOT NULL
);
```

- `slug`: コード内で使うキー
- `name`: UI表示名
- `description`: このカテゴリ特有の注意点（例: 「ナショジオの英語教材。自然・科学のトピックが多い。英語フレーズの発音指導が重要」）
- `prompt_file`: カテゴリ専用の生成プロンプトファイル名。空ならデフォルト（`lesson_generate.md`）を使用

### 1. 新テーブル: `lesson_versions`

```sql
CREATE TABLE IF NOT EXISTS lesson_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lesson_id INTEGER NOT NULL,
    lang TEXT NOT NULL DEFAULT 'ja',
    generator TEXT NOT NULL DEFAULT 'gemini',
    version_number INTEGER NOT NULL DEFAULT 1,
    note TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (lesson_id) REFERENCES lessons(id) ON DELETE CASCADE,
    UNIQUE(lesson_id, lang, generator, version_number)
);
```

- `note`: バージョンの説明（「初版」「説明を追加」等）。自動生成 or 手動入力
- アクティブ/デフォルトの概念なし。再生・改善時にバージョンを明示指定する

### 2. `lesson_sections` に `version_number` カラム追加

```sql
ALTER TABLE lesson_sections ADD COLUMN version_number INTEGER NOT NULL DEFAULT 1;
```

- 既存データは全て `version_number = 1` になる
- `(lesson_id, lang, generator, version_number, order_index)` がセクションの一意識別

### 3. `lesson_plans` に `version_number` カラム追加

```sql
ALTER TABLE lesson_plans ADD COLUMN version_number INTEGER NOT NULL DEFAULT 1;
```

- UNIQUE制約を `(lesson_id, lang, generator)` → `(lesson_id, lang, generator, version_number)` に変更

### マイグレーション

`src/db/core.py` の `_migrate()` で:
1. `lesson_versions` テーブル作成
2. `lesson_sections` に `version_number` カラム追加（DEFAULT 1）
3. `lesson_plans` の UNIQUE 制約更新
4. 既存データから `lesson_versions` レコードを自動生成（各 `(lesson_id, lang, generator)` に v1 を作成）

## API変更

### 新規エンドポイント

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/api/lessons/{id}/versions` | バージョン一覧取得（lang, generator でフィルタ可） |
| POST | `/api/lessons/{id}/versions` | 新バージョン作成（既存バージョンをコピー or 空で作成） |
| PUT | `/api/lessons/{id}/versions/{version_number}` | バージョンメモ更新 |
| DELETE | `/api/lessons/{id}/versions/{version_number}` | バージョン削除 |

### 既存エンドポイントの変更

| エンドポイント | 変更内容 |
|--------------|---------|
| `GET /api/lessons/{id}` | レスポンスに `versions` リストを追加。`version` パラメータで表示バージョン指定（省略時は最新） |
| `POST /api/lessons/{id}/import-sections` | `version` パラメータ追加。省略時は新バージョンを自動作成してインポート |
| `POST /api/lessons/{id}/start` | `version` パラメータ必須化。再生するバージョンを明示指定 |
| `DELETE /api/lessons/{id}/tts-cache` | `version` パラメータ対応 |

### セクションインポート時のバージョン作成フロー

```
POST /api/lessons/{id}/import-sections
  ├─ version パラメータ指定あり → そのバージョンのセクションを置換
  └─ version パラメータなし → 新バージョン(max+1)を作成してインポート
```

## TTSキャッシュ

### ディレクトリ構造変更

```
resources/audio/lessons/{lesson_id}/{lang}/{generator}/
  ├─ v1/                    # バージョン1
  │   ├─ section_00_part_00.wav
  │   └─ ...
  ├─ v2/                    # バージョン2
  │   └─ ...
  └─ (legacy: バージョニング前の旧ファイル → v1扱い)
```

- `lesson_runner.py` の `_cache_path()` に `version_number` を追加
- 旧互換: `v1/` サブディレクトリがなければ親ディレクトリのファイルをv1として扱う

## UI変更（teacher.js）

### Step 3（セクション確認・編集）にバージョン管理UIを追加

```
┌─────────────────────────────────────────────┐
│ Step 3: セクション確認・編集                    │
│                                               │
│ [ja] [en]  ← 言語タブ（既存）                   │
│                                               │
│ バージョン: [v1] [v2] [v3 ▼]                    │
│   メモ: 「説明セクション追加版」 [編集]           │
│   [▶ 再生] [改善を生成] [比較...]               │
│                                               │
│ ── gemini ──────────────────────────           │
│ [セクション一覧...]                             │
│                                               │
│ ── claude ──────────────────────────           │
│ [セクション一覧...]                             │
└─────────────────────────────────────────────┘
```

- バージョンボタン: クリックで表示切替
- 選択中のバージョンから直接「再生」「改善を生成」が可能
- どのバージョンも対等。最新だけでなく、古いバージョンからも改善を生成できる

### Step 2（スクリプト生成）のインポート動作

- インポートは常に新バージョンとして追加される

## コンテンツ改善パイプライン

### 過去の失敗からの教訓

以前実装した `content_analyzer.py`（コミット `497d38e` で削除）は汎用スコアリング方式だったが、**「80%が30%にしか感じない」問題**が発生して削除された。失敗の原因:

1. 汎用的な「エンタメ性」「教育効果」等のスコアは主観と乖離する
2. 数値スコアだけでは「何をどう直せばいいか」がわからない
3. 全セクション一律評価では、良い部分と悪い部分の区別がつかない

**本設計ではスコアリングを廃止し、「具体的に何が問題で、どう直すか」に特化する。**

### 設計原則

1. **スコアを出さない**。代わりに具体的な問題点と改善案を出す
2. **元教材に照らした検証**が核心。「なんとなく良い/悪い」ではなく「元教材のこの内容が抜けている」「この説明は元教材と矛盾する」
3. **セクション単位の部分改善**。良いセクションはそのまま残し、問題のあるセクションだけ再生成
4. **ユーザーの知見を構造的に取り込む**。配信後の「ここは長かった」「ここはウケた」をセクションに紐づけて記録
5. **授業を横断して学習する**。個別授業の改善で終わらず、全授業の注釈と改善差分を分析し、「この配信でウケるパターン」を抽出して次の生成に反映する

### 改善の3つの入口

```
入口1: 元教材との整合性チェック（自動検証）
  → 「元教材にあるのにスクリプトに含まれていない内容」を検出
  → 「スクリプトの説明が元教材と矛盾している箇所」を検出

入口2: ユーザーのセクション注釈（配信後フィードバック）
  → 各セクションに ◎良い / △要改善 / ✕作り直し + コメント
  → 「ここが長かった」「この例えがウケた」等の具体メモ

入口3: 改善指示による部分再生成
  → 問題セクションのみAIが再生成（良いセクションは保持）
  → ユーザーの追加指示も反映
```

### 入口1: 元教材との整合性チェック

**API**: `POST /api/lessons/{id}/verify`

入力:
- `version_number`（省略時は最新バージョン）
- `lang`, `generator`

処理:
1. 元教材（`extracted_text`, `main_content`）を「カバーすべき内容リスト」に分解
2. 各内容が対象バージョンのどのセクションでカバーされているかをマッピング
3. 抜け・矛盾・不足を検出

レスポンス:
```json
{
  "coverage": [
    {
      "source_item": "変数のスコープ（ローカル変数とグローバル変数の違い）",
      "status": "missing",
      "detail": "元教材で重要ポイントとして記載されているが、どのセクションでも触れていない"
    },
    {
      "source_item": "for文の基本構文",
      "status": "covered",
      "section_index": 3,
      "detail": null
    },
    {
      "source_item": "配列のインデックスは0から始まる",
      "status": "weak",
      "section_index": 5,
      "detail": "display_textに記載はあるが、対話で具体例を使った説明がない"
    }
  ],
  "contradictions": [
    {
      "section_index": 2,
      "issue": "元教材では「Pythonの変数は宣言不要」と説明しているが、セクションでは「変数を宣言します」と表現している"
    }
  ]
}
```

**汎用スコアとの違い**: 「元教材に書いてある事実」に対して検証するので、主観に依存しない。

### 入口2: ユーザーのセクション注釈

**API**: `PUT /api/lessons/{id}/sections/{section_id}/annotation`

各セクションにユーザーがフィードバックを紐づける:

```json
{
  "rating": "needs_improvement",  // "good" | "needs_improvement" | "redo"
  "comment": "説明が長くて視聴者が離脱していた。具体例を1つに絞って短くしたい"
}
```

**DB**: `lesson_sections` に `annotation_rating`, `annotation_comment` カラム追加

**UI**: Step 3のセクション一覧で、各セクション横に ◎/△/✕ ボタン + コメント入力欄

```
┌──────────────────────────────────────────────┐
│ セクション 2: 変数の説明                        │
│ [◎良い] [△要改善] [✕作り直し]                   │
│ コメント: [説明が長い。例を1つに絞って_______]   │
│                                                │
│ ── 対話 ──                                     │
│ 👩‍🏫 変数というのは...                           │
│ 👨‍🎓 なるほど〜                                  │
│ ...                                            │
└──────────────────────────────────────────────┘
```

この注釈は改善時の入力として使われ、バージョンをまたいで参照できる。

### 入口3: 特定バージョンからの部分再生成

**API**: `POST /api/lessons/{id}/improve`

**任意のバージョンを改善元に指定できる**。v3が最新でも、v1を元に改善を生成してv4を作ることが可能。

入力:
```json
{
  "source_version": 1,
  "lang": "ja",
  "generator": "claude",
  "target_sections": [2, 5],
  "verify_result": { ... },
  "user_instructions": "セクション2は例を1つに絞って短く。セクション5はスコープの説明を追加"
}
```

処理:
1. **指定バージョン（`source_version`）の全セクション**をコンテキストとしてAIに渡す
2. `target_sections` で指定されたセクションのみ再生成を指示
3. 検証結果（`verify_result`）のcoverage/contradictionsを改善の根拠として渡す
4. 各セクションの注釈（annotation）も改善指示として渡す
5. カテゴリ別学習結果（`prompts/learnings/{category}.md` + `_common.md`）を注入
6. **変更していないセクションはそのままコピー**して新バージョンを作成

```
元バージョン v1:
  [sec0: 導入]     [sec1: 基本]     [sec2: 変数]     [sec3: ループ]   [sec4: まとめ]
       ↓ そのまま      ↓ そのまま      ↓ 再生成         ↓ そのまま       ↓ そのまま

新バージョン v2:
  [sec0: 導入]     [sec1: 基本]     [sec2: 変数★]    [sec3: ループ]   [sec4: まとめ]
                                     ↑ 改善済み
```

**全再生成との違い**: 良いセクションが劣化するリスクがない。差分が明確。

### 改善サイクルの全体フロー

```
[v1 作成]（通常のスクリプト生成・インポート）
    ↓
[配信で再生]
    ↓
[ユーザーが注釈を付ける]（入口2: ◎/△/✕ + コメント）
  「セクション2長い」「セクション5で視聴者が質問してた」
    ↓
[元教材との整合性チェック]（入口1: 自動検証）
  「変数スコープの説明が抜けている」「for文の説明が元教材と矛盾」
    ↓
[改善対象セクションを選択]（注釈△/✕ + 検証で問題あり のセクション）
    ↓
[部分再生成]（入口3: target_sectionsに問題セクションのみ指定）
    ↓
[v2 作成]（変更セクションのみ差し替え）
    ↓
[差分確認]（v1 ↔ v2 で変更箇所を並べて表示）
    ↓
[v2で再生 or v1で再生]（どちらも選べる）
```

## 授業横断の学習ループ

個別授業の改善（入口1〜3）だけでなく、**全授業にわたる注釈と改善差分をAIが分析し、「この配信で実際にウケるパターン」を抽出して次の授業生成に反映する**仕組み。

### カテゴリ別学習: なぜ必要か

英語教材の「発音指導はゆっくり繰り返すと◎」という学習が、プログラミング教材の生成に混入したら害になる。学習は**教材カテゴリ別に分離**して蓄積・適用する。

```
lesson_categories:
  english_natgeo    →  prompts/learnings/english_natgeo.md
  programming_python → prompts/learnings/programming_python.md
  math_basics       →  prompts/learnings/math_basics.md
  (共通)            →  prompts/learnings/_common.md
```

- 各カテゴリが独立した学習ファイルを持つ
- カテゴリをまたいで共通するパターン（テンポ、感情の使い方等）は `_common.md` に
- 授業生成時は `_common.md` + 該当カテゴリの学習ファイルをプロンプトに注入

### 学習データ: 何を蓄積するか

全授業の注釈（◎/✕ + コメント）と、バージョン間の改善差分:

```
[english_natgeo]
  授業A v1 sec2 [✕]「発音の説明が文字だけで伝わらない」
  授業A v2 sec2 [◎]「カタカナ発音ガイドを入れたらわかりやすい」
  授業C v1 sec0 [◎]「ナショジオの写真の話題から入ると掴みが強い」

[programming_python]
  授業B v1 sec3 [✕]「教師のモノローグが5発話続いて間延びした」
  授業B v2 sec3 [◎]「生徒のツッコミを挟んだらテンポ良くなった」
  授業D v1 sec1 [✕]「display_textにコード例がなく伝わらなかった」
```

注目すべきデータ:
- **◎セクション**: そのまま「良いパターン」の実例
- **✕→◎ペア**: 改善前後の差分から「何を変えたら良くなったか」が抽出できる
- **コメント**: ユーザーが書いた理由が最も価値が高い

### 分析: カテゴリ別パターン抽出

**API**: `POST /api/lessons/analyze-learnings`

パラメータ:
- `category`（省略時は全カテゴリ一括分析）

処理:
1. 指定カテゴリの注釈付きセクションを収集
2. ✕→◎ の改善ペアを抽出
3. AIに以下を渡して分析:
   - カテゴリ情報（`lesson_categories.description`）
   - ◎セクション群（内容 + コメント）
   - ✕セクション群（内容 + コメント）
   - 改善ペア群（before/after + 何が変わったか）
   - 現在の学習ファイルの内容（差分更新のため）
4. AIが出力する2つのもの:
   - **カテゴリ別学習結果** → `prompts/learnings/{category}.md`
   - **カテゴリ共通パターン** → `prompts/learnings/_common.md` に追記候補

カテゴリ別出力例（`prompts/learnings/english_natgeo.md`）:
```markdown
## 英語（ナショジオ）学習結果
最終分析: 2026-04-01 / 注釈18件

### introduction
- ◎ ナショジオの写真や動物の話題から入ると視聴者の興味を引ける
- ✕ いきなり文法説明から入ると離脱する

### explanation
- ◎ 英語フレーズの後にカタカナ発音ガイドをdisplay_textに表示すると好評
- ◎ 「こういう場面で使う」と具体シチュエーションを添えると定着する
- ✕ 単語リストを読み上げるだけのセクションは退屈

### question
- ◎ 「この場面で何て言う？」形式のクイズは盛り上がる
- ◎ 不正解選択肢に「ネイティブはこう聞こえる」解説があると学びが深い
```

共通出力例（`prompts/learnings/_common.md`）:
```markdown
## 共通パターン
### テンポ
- ◎ 教師のモノローグは3発話以内に生徒が割り込むとテンポが良い
- ✕ 1セクション内の対話が8発話を超えると間延び

### 感情
- ◎ 導入のemotionがexcited/joyだと掴みが強い
- ✕ neutralが3セクション以上続くと単調
```

### 2段階の反映: 学習注入 + プロンプト自体の改善

学習結果の反映は**2段階**で行う。

#### 段階1: 学習結果の注入（自動）

スクリプト生成・部分改善時に、プロンプトのコンテキストとして学習結果を自動注入:

```
[生成プロンプト本文]
  +
[prompts/learnings/_common.md の内容]
  +
[prompts/learnings/{category}.md の内容]
```

これは「参考情報」としてAIに渡すだけで、プロンプト自体は変わらない。

#### 段階2: 生成プロンプト自体の改善（手動確認付き）

学習が十分溜まったら、**生成プロンプト（`lesson_generate.md` またはカテゴリ専用プロンプト）自体を改善**する:

**API**: `POST /api/lessons/improve-prompt`

パラメータ:
- `category`（対象カテゴリ。空なら共通プロンプト `lesson_generate.md`）

処理:
1. 現在の生成プロンプトファイルの内容を読む
2. 該当カテゴリの学習結果 + 注釈データを渡す
3. AIが「このプロンプトのここを変えれば学習パターンが構造的に反映される」と提案
4. **diff形式**で変更案を返す（既存のAI編集機能と同じUX）
5. ユーザーが確認→承認で適用

例: 英語カテゴリの学習から、カテゴリ専用プロンプトの改善提案:

```diff
 ## 品質基準（英語教材）

 ### 教育効果
 - 主要なフレーズ・語彙をすべてカバーする
 - 段階的に難易度を上げる
+- 英語フレーズの直後にカタカナ発音ガイドをdisplay_textに含める
+- 「こういう場面で使う」と具体的なシチュエーションを必ず添える

 ### エンタメ性
 - 視聴者の興味を引くフックで始める
+- ナショジオの写真・動物・自然科学の話題を導入に活用する
+- 「この場面で何て言う？」形式のクイズを最低1つ入れる

 ### 避けるべきパターン
+- 単語リストを読み上げるだけのセクションは作らない
+- いきなり文法説明から入らず、具体的な場面設定から入る
```

**段階1との違い**:
- 段階1（注入）: 毎回コンテキストに追加。プロンプトが肥大化していく
- 段階2（プロンプト改善）: 学習をプロンプトの構造に取り込む。注入が不要になる分、プロンプトがスリムに保てる
- 理想のサイクル: 注入で効果を確認 → 確立したパターンはプロンプト自体に昇格 → 学習ファイルから該当項目を削除

### カテゴリ専用プロンプトの仕組み

カテゴリごとに専用の生成プロンプトを持てる:

```
prompts/
  lesson_generate.md                      # ベースプロンプト（共通）
  lesson_generate_english_natgeo.md       # 英語（ナショジオ）専用
  lesson_generate_programming_python.md   # プログラミング専用
  learnings/
    _common.md                            # 共通学習結果
    english_natgeo.md                     # カテゴリ別学習結果
    programming_python.md
```

プロンプト解決順序:
1. カテゴリ専用プロンプト（`lesson_categories.prompt_file`）があればそれを使う
2. なければベースプロンプト（`lesson_generate.md`）を使う
3. いずれの場合も学習結果（`_common.md` + カテゴリ別）を注入

カテゴリ専用プロンプトの初期作成:
- ベースプロンプトをコピーして、カテゴリの `description` に合わせた調整を加える
- 管理画面から「カテゴリ専用プロンプトを作成」ボタンで自動生成（ベース + description → AI生成）

### 学習のライフサイクル

```
[授業を配信]（カテゴリ: english_natgeo）
    ↓
[各セクションに ◎/✕ + コメントを付ける]
    ↓
[カテゴリ別に注釈が溜まったら分析を実行]（手動）
    ↓
[AIがカテゴリ別パターン + 共通パターンを抽出]
    ↓
[prompts/learnings/english_natgeo.md を更新]
    ↓  管理画面で学習結果を確認・手動修正
    ↓
┌─ 段階1: 次の英語授業生成時に学習結果を自動注入
│
└─ 段階2: 学習が安定したら生成プロンプト自体を改善（diff確認→承認）
    ↓
[生成品質が向上] → [配信] → [注釈] → [分析] → ...
```

- 分析は**手動トリガー**。自動実行しない（コスト制御 + 意図しない学習を防ぐ）
- 段階2（プロンプト改善）も**手動確認付き**。AIの提案をdiffで見て承認する
- ユーザーが「この学習は間違い」と判断したら、学習ファイルから手動削除・修正

### 管理画面: 学習ダッシュボード

教師モードに「学習」タブを追加:

```
┌──────────────────────────────────────────────────┐
│ 学習ダッシュボード                                  │
│                                                    │
│ カテゴリ: [全体] [英語ナショジオ ●18] [Python ●12]   │
│                                                    │
│ ── 英語（ナショジオ）────────────────────────        │
│ 注釈: ◎ 12件 / △ 4件 / ✕ 2件（全3授業）            │
│ 最終分析: 2026-03-28                               │
│ 専用プロンプト: lesson_generate_english_natgeo.md   │
│                                                    │
│ [分析を実行] [プロンプトを改善]                      │
│                                                    │
│ ▸ 学習結果（5パターン）                              │
│   ◎ カタカナ発音ガイドをdisplay_textに...           │
│   ◎ ナショジオの話題から導入...                      │
│   ✕ 単語リスト読み上げだけは...                      │
│                                                    │
│ ▸ 注釈付きセクション一覧                             │
│   授業A sec2 [✕→◎]「発音説明→カタカナガイド追加」    │
│   授業C sec0 [◎]「ナショジオ写真の導入」             │
│                                                    │
│ [学習結果を編集]                                     │
│                                                    │
│ ── 共通 ─────────────────────────────────           │
│ ▸ 共通パターン（3パターン）                          │
│   ◎ モノローグは3発話以内に割り込み...               │
│   ✕ neutral 3セクション連続は...                    │
└──────────────────────────────────────────────────┘
```

### DBの追加

学習分析の履歴を保存するテーブル:

```sql
CREATE TABLE IF NOT EXISTS lesson_learnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL DEFAULT '',    -- カテゴリslug（空文字 = 共通）
    analysis_input TEXT DEFAULT '',       -- 分析に使った注釈データ（JSON、再現性のため）
    analysis_output TEXT DEFAULT '',      -- AIの分析結果（生テキスト）
    learnings_md TEXT DEFAULT '',         -- 整形後の学習結果（Markdown）
    prompt_diff TEXT DEFAULT '',          -- プロンプト改善提案のdiff（段階2用）
    section_count INTEGER DEFAULT 0,     -- 分析対象の注釈数
    created_at TEXT NOT NULL
);
```

- `category` でカテゴリ別に履歴を管理
- 分析のたびにレコード追加（履歴を残す）
- 最新の `learnings_md` が `prompts/learnings/{category}.md` に書き出される
- `prompt_diff` は段階2のプロンプト改善提案を記録

### バージョン差分表示（UI）

管理画面Step 3で、2つのバージョンを並べて差分を確認:

```
┌───────────────────────────────────────────────┐
│ バージョン比較: v1 ↔ v2                         │
│                                                 │
│ セクション 0: 導入  — 変更なし                    │
│                                                 │
│ セクション 2: 変数の説明  ← 再生成               │
│ ┌─ v1 ──────────────────────────────────┐      │
│ │ 👩‍🏫 変数というのは値を入れる箱です...    │      │
│ │ [注釈: △ 説明が長い]                    │      │
│ └────────────────────────────────────────┘      │
│ ┌─ v2 ──────────────────────────────────┐      │
│ │ 👩‍🏫 変数って何？ゲームのスコアを        │      │
│ │    覚えておきたいとき...                 │      │
│ │ [改善: 具体例で短縮、元教材の注意点反映]  │      │
│ └────────────────────────────────────────┘      │
│                                                 │
│ [▶ v2を再生] [▶ v1を再生] [v1から改善を生成]      │
└───────────────────────────────────────────────┘
```

### プロンプト管理

検証・改善のプロンプトは既存の教師モードと同様、管理画面で全文表示（CLAUDE.md「LLM生成パイプラインの検証可能性」に準拠）:
- 検証プロンプト（システム/ユーザー）を折りたたみで全文表示
- 検証結果（AI出力）を全文表示
- 改善プロンプトも同様に全文表示
- 前ステップの出力が次ステップの入力に含まれる関係を明示

### lesson_versions テーブルへの追加カラム

```sql
verify_json TEXT DEFAULT '',      -- 元教材との整合性チェック結果（JSON）
improve_source_version INTEGER,   -- 改善元バージョン番号（NULLなら手動作成）
improve_summary TEXT DEFAULT '',  -- AI改善サマリ（何をどう直したか）
improved_sections TEXT DEFAULT '', -- 改善対象セクションのorder_indexリスト（JSON配列）
```

### lesson_sections テーブルへの追加カラム

```sql
annotation_rating TEXT DEFAULT '',   -- ユーザー評価: 'good' | 'needs_improvement' | 'redo' | ''
annotation_comment TEXT DEFAULT '',  -- ユーザーのフィードバックコメント
```

これにより:
- 各バージョンが「何を元に、どのセクションをどう改善したか」のトレーサビリティを持つ
- 各セクションにユーザーの評価・コメントが紐づき、改善の根拠になる

## 実装ステップ

### Step 1: DBスキーマ & マイグレーション（全テーブル一括） ✅ 完了
- `src/db/core.py` のマイグレーション:
  - `lesson_categories` テーブル作成
  - `lessons` に `category` カラム追加
  - `lesson_versions` テーブル作成（`verify_json`, `improve_source_version`, `improve_summary`, `improved_sections` 含む）
  - `lesson_sections` に `version_number`, `annotation_rating`, `annotation_comment` カラム追加
  - `lesson_plans` に `version_number` カラム追加 + UNIQUE制約更新（テーブル再作成方式）
  - `lesson_learnings` テーブル作成（`category` カラム付き）
  - 既存データから `lesson_versions` v1 を自動生成（`_migrate_lesson_versions_v1()`）
- `src/db/lessons.py`: CRUD関数追加・修正
  - カテゴリ: `get_categories()`, `create_category()`, `get_category_by_slug()`, `delete_category()`
  - バージョン: `get_lesson_versions()`, `get_lesson_version()`, `create_lesson_version()`, `update_lesson_version()`, `delete_lesson_version()`
  - 検証: `save_version_verify()`
  - 注釈: `update_section_annotation()`
  - 学習: `save_learning()`, `get_latest_learning()`, `get_learnings()`
  - 既存関数: `add_lesson_section()`, `get_lesson_sections()`, `delete_lesson_sections()`, `get_lesson_plan()`, `upsert_lesson_plan()`, `delete_lesson_plans()` に `version_number` パラメータ追加
- テスト: `tests/test_db.py` にスキーマ確認 + カテゴリ・バージョン・注釈・学習関連テスト追加（+30テスト、全624通過）

### Step 2: API実装（バージョン管理 + カテゴリ + 注釈） ✅ 完了
- `scripts/routes/teacher.py`:
  - カテゴリCRUD API（`GET/POST/DELETE /api/lesson-categories`）
  - バージョンCRUD API（`GET/POST/PUT/DELETE /api/lessons/{id}/versions/...`）
    - `POST` に `copy_from` パラメータ追加（セクション・プランをコピーして新バージョン作成）
  - セクション注釈API（`PUT /api/lessons/{id}/sections/{section_id}/annotation`）
  - 既存エンドポイントの `version_number` パラメータ対応
  - `import-sections` のバージョン自動作成ロジック（version未指定→新バージョン、指定→置換）
  - `POST /api/lessons/{id}/start` の `version` パラメータ対応（省略時は最新バージョンを自動選択、後方互換維持）
  - `POST /api/lessons` と `PUT /api/lessons/{id}` に `category` フィールド対応
  - `GET /api/lessons/{id}` に `versions` 一覧追加 + `?version=N` でセクションフィルタ
  - `src/lesson_runner.py`: `start()` に `version_number` パラメータ追加
- テスト: `tests/test_api_teacher.py` に +27テスト追加（TestCategoryAPI 7件、TestVersionAPI 11件、TestImportWithVersioning 4件、TestAnnotationAPI 5件）、全651通過

### Step 3: 検証 & 部分改善API ✅ 完了
- `src/lesson_generator/improver.py`: 検証・改善・学習結果注入のコアロジック
  - `verify_lesson()`: 元教材との整合性チェック（Gemini API呼び出し → coverage/contradictions JSON）
  - `improve_sections()`: 指定セクションの部分再生成（全セクションコンテキスト + 検証結果 + 注釈 + 学習結果 + ユーザー指示）
  - `load_learnings(category)`: `prompts/learnings/_common.md` + `prompts/learnings/{category}.md` を結合して返す
- `scripts/routes/teacher.py`:
  - `POST /api/lessons/{id}/verify`: version_number省略時は最新バージョン自動選択。結果を `lesson_versions.verify_json` に保存。プロンプト全文 + raw_output を返す（検証可能性）
  - `POST /api/lessons/{id}/improve`: source_version → target_sections のみ再生成 → 新バージョン作成。未変更セクション・プランはソースからコピー。improve_source_version/improve_summary/improved_sections をバージョンメタに記録
- プロンプト:
  - `prompts/lesson_verify.md`: 検証用プロンプト（coverage status: covered/weak/missing + contradictions）
  - `prompts/lesson_improve.md`: 改善用プロンプト（改善対象セクションのみ出力指示）
  - `prompts/learnings/`: カテゴリ別学習結果格納ディレクトリ
- テスト: `tests/test_api_teacher.py` に +20テスト追加（TestVerifyAPI 8件、TestImproveAPI 9件、TestLoadLearnings 3件）、全670通過

### Step 4: 授業横断の学習ループAPI ✅ 完了
- `src/lesson_generator/improver.py`: 学習ループのコアロジック追加
  - `_collect_annotated_sections(category)`: カテゴリ別に注釈付きセクション・改善ペア（✕→◎）を収集
  - `analyze_learnings()`: 収集データをAIに渡しパターン抽出（Gemini API）
  - `save_learnings_to_files()`: `prompts/learnings/{category}.md` + `_common.md` に書き出し
  - `improve_prompt()`: 学習結果をもとに生成プロンプト改善案をdiff形式で生成
  - `apply_prompt_diff()`: diff_instructionsを実際にプロンプトファイルに適用（add/replace）
  - `create_category_prompt()`: ベースプロンプト + カテゴリdescription → AIでカテゴリ専用プロンプト生成
- `scripts/routes/teacher.py`: 6エンドポイント追加（`{lesson_id}`パスより前に配置）
  - `POST /api/lessons/analyze-learnings`: 学習分析実行→ファイル書き出し＋DB保存
  - `GET /api/lessons/learnings`: カテゴリ別の学習結果・注釈統計（◎/△/✕件数、授業数、最新分析日）
  - `POST /api/lessons/improve-prompt`: プロンプト改善提案生成（diff_instructions + summary）
  - `POST /api/lessons/apply-prompt-diff`: diff承認適用（ユーザー確認後に呼ぶ）
  - `POST /api/lesson-categories/{slug}/create-prompt`: カテゴリ専用プロンプト生成＋prompt_file自動更新
- プロンプト:
  - `prompts/lesson_analyze.md`: 学習分析用プロンプト（◎/✕パターン抽出、改善ペア分析）
  - `prompts/lesson_improve_prompt.md`: プロンプト改善提案用プロンプト（diff_instructions形式出力）
- テスト: `tests/test_api_teacher.py` に +26テスト追加（TestAnalyzeLearningsAPI 6件、TestLearningsDashboardAPI 4件、TestImprovePromptAPI 4件、TestApplyPromptDiffAPI 4件、TestCreateCategoryPromptAPI 4件、TestCollectAnnotatedSections 2件、TestSaveLearningsToFiles 2件）、全696通過

### Step 5: 授業再生エンジン対応 ✅ 完了
- `src/lesson_runner.py`: TTSキャッシュパスをバージョン別サブディレクトリ `v{N}/` に変更
  - `_cache_path()` / `_dlg_cache_path()`: `version_number` パラメータ追加、3段階フォールバック（`v{N}/` → generator直下 → lang直下、v1のみ）
  - `clear_tts_cache()`: `version_number` パラメータ追加（特定バージョンのみ削除可能、v1時はレガシーファイルも削除）
  - `get_tts_cache_info()`: `version_number` パラメータ追加（バージョン別キャッシュ情報取得）
  - `LessonRunner`: `_version_number` を保持し、TTS生成時にバージョン別パスにキャッシュ保存、`get_status()` に `version_number` 含む
- `scripts/routes/teacher.py`: TTSキャッシュAPI（GET/DELETE）で `version` パラメータをキャッシュ関数に渡す、セクション編集/削除時もバージョン指定でキャッシュ削除
- テスト: `tests/test_lesson_runner.py` に +12テスト追加（TestVersionedTtsCache 9件、既存テスト更新3件）、全708通過

### Step 6: UI実装 ✅ 完了
- `static/js/admin/teacher.js`（1,238行→1,830行）:
  - 状態管理: `_lessonVersionTab`（バージョン選択）、`_lessonCategories`（カテゴリキャッシュ）
  - カテゴリ管理UI（折りたたみ一覧 + 追加/削除） + レッスンヘッダーにカテゴリ `<select>`
  - バージョンセレクタ（Step 3先頭: バージョンボタン列、メモ編集、コピー/削除、改善メタ表示）
  - `buildLessonItem()` で `?version=N` 付きAPI呼び出し、TTS cache/startLessonにもversion伝搬
  - セクション注釈UI（◎良い/△要改善/✕作り直し ボタン + コメントinput、rating即保存/comment blur保存）
  - 整合性チェック: verifyボタン → coverage/contradictions表示 + プロンプト・raw_output折りたたみ
  - 部分改善: 改善元version選択 + 対象セクションcheckbox（△/✕自動チェック）+ 追加指示textarea → 新version自動切替
  - バージョン差分比較: 2version間のsection-by-section grid差分表示（変更なし折りたたみ、AI改善ハイライト）
  - `_buildLlmCallDisplay()` 共通ヘルパー（全LLM呼び出しのプロンプト・出力を折りたたみ全文表示、CLAUDE.md準拠）
- `static/index.html`:
  - 「学習」サブタブ追加（`conv-sub-learnings`）
  - 学習ダッシュボード: カテゴリ別注釈統計、分析実行、学習結果Markdown表示、プロンプト改善提案→diff表示→適用/却下、カテゴリ専用プロンプト作成
  - script cache bust v19→v20
- テスト: 全708通過（UI変更のためバックエンドテストへの影響なし）

### Step 7: テスト & 動作確認
- 全テスト通過確認
- 手動テスト:
  - カテゴリ作成→授業にカテゴリ設定
  - インポート→バージョン作成→バージョン切替→バージョン指定再生
  - セクション注釈（◎/✕）→検証→特定バージョンから部分改善→差分確認
  - 複数授業で注釈蓄積→学習分析実行→学習結果確認
  - 学習結果のプロンプト注入確認（段階1）
  - プロンプト改善提案→diff確認→承認（段階2）

## リスク

| リスク | 対策 |
|-------|------|
| マイグレーションで既存データ破損 | DEFAULT 1 で安全にカラム追加。既存データから lesson_versions v1 を自動生成 |
| TTSキャッシュの互換性 | 旧パスのフォールバック処理。v1ディレクトリがなければ親ディレクトリをv1扱い |
| UIの複雑化 | バージョンUI は折りたたみ可能にし、1バージョンしかない場合は最小表示 |
| lesson_plans の UNIQUE 制約変更 | SQLiteでは ALTER TABLE で制約変更不可。テーブル再作成 or 新テーブルで対応 |
| 整合性チェックの精度 | 汎用スコアではなく元教材との事実ベース照合なので、主観ズレが起きにくい。過去の content_analyzer.py の轍を踏まない |
| 部分再生成が文脈を壊す | 全セクションをコンテキストとして渡し、対象セクションのみ再生成を指示。前後の流れを維持 |
| 改善版が改悪になる可能性 | 元バージョンも残っているので、そちらを再生すればよい。差分比較で改善効果を確認してから使う |
| 注釈の蓄積コスト | 注釈は任意。付けなくても検証・改善は機能する。配信後に気づいた点だけメモする運用 |
| 学習結果が偏る（少数の注釈で一般化しすぎ） | 分析時に注釈件数を明示。件数が少ない段階では「仮説」として表示。ユーザーが手動修正可能 |
| 学習が誤った方向に進む | 学習結果はprompts/learnings/にカテゴリ別に平文Markdown保存。ユーザーが読んで修正・削除できる。分析履歴もDBに残る |
| 注釈を付ける運用が続かない | ◎/✕のワンクリック + 任意コメントに簡略化。配信直後に気になったセクションだけでOK |
