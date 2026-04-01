# Claude Code 授業スクリプト生成ワークフロー

教材画像から授業スクリプトを生成し、APIでDBに保存する手順書。

## 概要

このワークフローでは、教師モードの授業コンテンツ（画像教材）を読み取り、対話形式の授業スクリプトを生成してDBにインポートする。

## 前提条件

- Webサーバーが起動していること（`http://localhost:${WEB_PORT:-8080}`）
- 授業コンテンツ（lesson）が教師モード管理画面で作成済みであること
- 教材画像がアップロード済みであること

---

## 手順

### Step 1: 授業情報の取得

授業のIDを確認し、教材ソース（画像パス）を取得する。

```bash
# 授業一覧
curl -s http://localhost:${WEB_PORT:-8080}/api/lessons | python3 -m json.tool

# 特定の授業の詳細（教材ソース・既存セクション含む）
curl -s http://localhost:${WEB_PORT:-8080}/api/lessons/{lesson_id} | python3 -m json.tool
```

レスポンスの `sources` から画像ファイルパスを取得する。画像は `resources/images/lessons/{lesson_id}/` に保存されている。

### Step 2: キャラクター情報の取得

授業で使用するキャラクター（teacher/student）の設定を取得する。

```bash
curl -s http://localhost:${WEB_PORT:-8080}/api/characters | python3 -m json.tool
```

レスポンスから以下を確認:
- `teacher.name` — 教師キャラクターの名前
- `teacher.system_prompt` — キャラクターの性格・話し方
- `teacher.emotions` — 使用可能な感情一覧（キー名がemotionの値になる）
- `teacher.tts_voice` / `teacher.tts_style` — TTS設定
- `student.name` — 生徒キャラクターの名前（存在する場合）
- `student.system_prompt` — 生徒の性格

### Step 3: 教材画像の読み取り

Readツールで教材画像を読み取り、内容を理解する。

```
# 画像パスの例:
resources/images/lessons/1/slide_01.png
resources/images/lessons/1/slide_02.png
```

教材から以下を抽出する:
- 主要トピック・テーマ
- 学習項目（語彙、文法、概念など）
- 具体例・例文
- 問題・演習（あれば）

### Step 4: 授業プランの策定

教材内容に基づき、授業の構成を設計する。

考慮すべき点:
- **対象**: 教材の難易度に合った想定視聴者
- **学習目標**: この授業で達成すべきこと（2-3項目）
- **セクション構成**: introduction → explanation/example → question → summary の流れ
- **エンタメ性**: 視聴者を飽きさせない工夫（驚き、ユーモア、身近な例え）
- **対話バランス**: teacher と student の掛け合いで理解を深める

### Step 5: スクリプト生成

各セクションの詳細なスクリプトを生成する。出力フォーマットは後述の「セクションJSONスキーマ」に従うこと。

**生成のポイント:**
- 各セクションは教師と生徒の対話形式（`dialogues`）で生成する
- 1セクションあたり4-8ターンの対話が目安
- 教材の具体的内容（語彙、例文、数値など）を必ず含める
- キャラクターの性格に合った口調で書く

### Step 6: 結果の保存

生成したセクションをAPIでDBにインポートする。

```bash
curl -X POST "http://localhost:${WEB_PORT:-8080}/api/lessons/{lesson_id}/import-sections?lang=ja&generator=claude" \
  -H "Content-Type: application/json" \
  -d '{
    "sections": [ ... ],
    "plan_summary": "授業プランの概要（任意）"
  }'
```

---

## セクションJSONスキーマ

`sections` 配列の各要素は以下のフォーマットに従う:

```json
{
  "section_type": "introduction",
  "title": "導入タイトル",
  "content": "このセクションの概要テキスト（タグなし、字幕用）",
  "tts_text": "TTS読み上げ用テキスト（言語タグ付き）",
  "display_text": "配信画面に表示するテキスト（教材内容、コードなど）",
  "emotion": "excited",
  "question": "",
  "answer": "",
  "wait_seconds": 3,
  "dialogues": [
    {
      "speaker": "teacher",
      "content": "発話テキスト（タグなし）",
      "tts_text": "TTS用テキスト（言語タグ付き）",
      "emotion": "excited"
    },
    {
      "speaker": "student",
      "content": "発話テキスト（タグなし）",
      "tts_text": "TTS用テキスト（言語タグ付き）",
      "emotion": "joy"
    }
  ],
  "dialogue_directions": [
    {
      "speaker": "teacher",
      "direction": "このターンの演出指示（2-3文）",
      "key_content": "このターンで必ず言及すべき教材の具体的内容"
    },
    {
      "speaker": "student",
      "direction": "生徒の反応の演出指示",
      "key_content": ""
    }
  ]
}
```

### フィールド詳細

| フィールド | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `section_type` | string | Yes | `introduction` / `explanation` / `example` / `question` / `summary` |
| `title` | string | No | セクションタイトル（10文字以内） |
| `content` | string | Yes | セクション全体の発話テキスト。タグ・マークアップ不可。対話形式の場合は概要的なテキストでよい |
| `tts_text` | string | Yes | TTS入力テキスト。`content` と同じだが、非主要言語に `[lang:xx]...[/lang]` タグを付ける |
| `display_text` | string | Yes | 配信画面に表示する実際の教材内容（コード、語彙リスト、図の説明など） |
| `emotion` | string | Yes | セクション全体の感情: `joy` / `excited` / `surprise` / `thinking` / `sad` / `embarrassed` / `neutral` |
| `question` | string | No | `question` タイプのセクションで出題する問題文 |
| `answer` | string | No | 問題の正解・解説 |
| `wait_seconds` | int | No | セクション終了後の待機秒数（デフォルト: 下表参照） |
| `dialogues` | array | Yes | 対話の配列。各要素は `speaker`, `content`, `tts_text`, `emotion` を持つ |
| `dialogue_directions` | array | No | 対話の演出指示。各要素は `speaker`, `direction`, `key_content` を持つ |

### section_type の使い分け

| タイプ | 用途 | 推奨 wait_seconds |
|--------|------|------------------|
| `introduction` | 授業の導入。トピック紹介、興味を引く | 2-3 |
| `explanation` | メインの解説。教材内容を教える | 2-3 |
| `example` | 具体例、実演、応用 | 2-3 |
| `question` | 視聴者への問いかけ。`question`/`answer` フィールドを使う | 8-15 |
| `summary` | まとめ・振り返り | 2-3 |

### emotion の使い分け

| 感情 | 使用場面 |
|------|---------|
| `joy` | 楽しい話題、ポジティブな内容 |
| `excited` | 新しい発見、ワクワクする内容、導入 |
| `surprise` | 意外な事実、驚きの展開 |
| `thinking` | 考え中、難しい問題、分析 |
| `sad` | 残念な例、よくある間違い |
| `embarrassed` | 恥ずかしい失敗談、照れ |
| `neutral` | 淡々とした説明、通常 |

### 言語タグ（tts_text用）

主要言語が日本語の場合、日本語以外の部分に言語タグを付ける:

```
content:  "Hello は英語で「こんにちは」という意味です"
tts_text: "[lang:en]Hello[/lang] は英語で「こんにちは」という意味です"
```

**対応言語コード**: `en`(英語), `ja`(日本語), `es`(スペイン語), `ko`(韓国語), `fr`(フランス語), `zh`(中国語)

**ルール:**
- `content`: タグなし。字幕表示に使用される
- `tts_text`: `content` と同じ文章だが、非主要言語の単語・フレーズを `[lang:xx]...[/lang]` で囲む
- 単語1つでもタグを付ける（例: `[lang:en]API[/lang]`）
- 主要言語のみの発話はタグ不要（`content` と `tts_text` が同じになる）

### dialogues の生成ルール

- `speaker`: `"teacher"` または `"student"`
- 1セクションあたり4-8ターンの対話が目安
- 教師が説明 → 生徒が質問/反応 → 教師が補足 というパターンが基本
- 生徒の反応は自然に（「なるほど！」「えっ、そうなんですか？」など）
- 各ターンの `emotion` は発話内容に合わせて個別に設定する

### dialogue_directions の生成ルール

- `dialogues` の各ターンに対応する演出指示
- `direction`: そのターンで何を、どう話すかの具体的な指示（2-3文）
- `key_content`: 教材の具体的な内容（語彙、例文、数値など）で、このターンで必ず言及すべきもの。不要なら空文字

---

## 品質基準

生成したスクリプトは以下の基準を満たすこと:

### 教育効果
- [ ] 教材の主要内容がすべてカバーされている
- [ ] 学習目標が達成できる構成になっている
- [ ] 具体例や演習で理解を定着させている
- [ ] 段階的に難易度が上がる構成

### エンタメ性
- [ ] 導入で視聴者の興味を引いている
- [ ] 適度なユーモアや驚きがある
- [ ] 教師と生徒の掛け合いが自然
- [ ] 視聴者が飽きない展開（5分以上の単調な解説は避ける）

### キャラクター一貫性
- [ ] 教師キャラクターの口調・性格が `system_prompt` に合っている
- [ ] 生徒キャラクターの反応が自然
- [ ] 感情（emotion）の選択が発話内容に合っている

### 技術的正確性
- [ ] `tts_text` の言語タグが正しい
- [ ] `section_type` が内容に合っている
- [ ] `question` タイプのセクションに `question`/`answer` フィールドがある
- [ ] JSON構造が正しい（配列・オブジェクトの閉じ忘れなし）

---

## 完全な出力例

```json
{
  "sections": [
    {
      "section_type": "introduction",
      "title": "今日のテーマ",
      "content": "今日は英語の挨拶を学びましょう",
      "tts_text": "今日は英語の挨拶を学びましょう",
      "display_text": "英語の挨拶 - Greetings",
      "emotion": "excited",
      "question": "",
      "answer": "",
      "wait_seconds": 2,
      "dialogues": [
        {
          "speaker": "teacher",
          "content": "みなさんこんにちは！今日は英語の挨拶について学んでいきますよ",
          "tts_text": "みなさんこんにちは！今日は英語の挨拶について学んでいきますよ",
          "emotion": "excited"
        },
        {
          "speaker": "student",
          "content": "挨拶！Hello くらいしか知らないなぁ",
          "tts_text": "挨拶！[lang:en]Hello[/lang] くらいしか知らないなぁ",
          "emotion": "thinking"
        },
        {
          "speaker": "teacher",
          "content": "大丈夫！Hello 以外にもたくさんあるんです。場面によって使い分けるのがポイントですよ",
          "tts_text": "大丈夫！[lang:en]Hello[/lang] 以外にもたくさんあるんです。場面によって使い分けるのがポイントですよ",
          "emotion": "joy"
        }
      ],
      "dialogue_directions": [
        {
          "speaker": "teacher",
          "direction": "明るく元気に授業の開始を宣言。今日のテーマが「英語の挨拶」であることを伝え、視聴者の興味を引く。",
          "key_content": "英語の挨拶"
        },
        {
          "speaker": "student",
          "direction": "Helloしか知らないと正直に告白し、学ぶ意欲を見せる。",
          "key_content": "Hello"
        },
        {
          "speaker": "teacher",
          "direction": "生徒を安心させつつ、場面による使い分けがポイントだと予告する。",
          "key_content": ""
        }
      ]
    },
    {
      "section_type": "explanation",
      "title": "基本の挨拶",
      "content": "フォーマルな挨拶とカジュアルな挨拶を学ぼう",
      "tts_text": "フォーマルな挨拶とカジュアルな挨拶を学ぼう",
      "display_text": "フォーマル: Good morning / Good afternoon / Good evening\nカジュアル: Hi / Hey / What's up",
      "emotion": "joy",
      "question": "",
      "answer": "",
      "wait_seconds": 3,
      "dialogues": [
        {
          "speaker": "teacher",
          "content": "まずはフォーマルな挨拶から。Good morning, Good afternoon, Good evening。時間帯で変わるんです",
          "tts_text": "まずはフォーマルな挨拶から。[lang:en]Good morning, Good afternoon, Good evening[/lang]。時間帯で変わるんです",
          "emotion": "joy"
        },
        {
          "speaker": "student",
          "content": "へぇ、朝昼晩で使い分けるんですね！",
          "tts_text": "へぇ、朝昼晩で使い分けるんですね！",
          "emotion": "surprise"
        },
        {
          "speaker": "teacher",
          "content": "そう！そしてカジュアルな場面では Hi とか Hey を使います。友達同士なら What's up もよく使いますよ",
          "tts_text": "そう！そしてカジュアルな場面では [lang:en]Hi[/lang] とか [lang:en]Hey[/lang] を使います。友達同士なら [lang:en]What's up[/lang] もよく使いますよ",
          "emotion": "excited"
        },
        {
          "speaker": "student",
          "content": "What's up って映画でよく聞く！かっこいい！",
          "tts_text": "[lang:en]What's up[/lang] って映画でよく聞く！かっこいい！",
          "emotion": "excited"
        }
      ],
      "dialogue_directions": [
        {
          "speaker": "teacher",
          "direction": "フォーマルな挨拶3つを紹介。時間帯による使い分けを明確に説明する。",
          "key_content": "Good morning, Good afternoon, Good evening"
        },
        {
          "speaker": "student",
          "direction": "時間帯で変わることに感心する。",
          "key_content": ""
        },
        {
          "speaker": "teacher",
          "direction": "カジュアルな挨拶を紹介。友達同士での使い方を説明。",
          "key_content": "Hi, Hey, What's up"
        },
        {
          "speaker": "student",
          "direction": "What's upに反応し、映画で聞いたことがあると共感を示す。",
          "key_content": "What's up"
        }
      ]
    },
    {
      "section_type": "question",
      "title": "クイズ",
      "content": "では問題です。朝、会社の上司に会ったらどの挨拶を使いますか？",
      "tts_text": "では問題です。朝、会社の上司に会ったらどの挨拶を使いますか？",
      "display_text": "問題: 朝、会社の上司に挨拶するとき、正しいのは？\nA) Hey!\nB) What's up?\nC) Good morning!",
      "emotion": "thinking",
      "question": "朝、会社の上司に会ったらどの挨拶を使いますか？ A) Hey! B) What's up? C) Good morning!",
      "answer": "C) Good morning! — 上司にはフォーマルな挨拶を使います。時間帯は朝なので Good morning が正解です。",
      "wait_seconds": 10,
      "dialogues": [
        {
          "speaker": "teacher",
          "content": "ここでクイズ！朝、会社の上司に会ったらどの挨拶を使う？A Hey、B What's up、C Good morning。みんなも考えてみてね",
          "tts_text": "ここでクイズ！朝、会社の上司に会ったらどの挨拶を使う？[lang:en]A Hey[/lang]、[lang:en]B What's up[/lang]、[lang:en]C Good morning[/lang]。みんなも考えてみてね",
          "emotion": "thinking"
        },
        {
          "speaker": "student",
          "content": "うーん、上司だからフォーマルで…朝だから…C の Good morning！",
          "tts_text": "うーん、上司だからフォーマルで…朝だから…[lang:en]C[/lang] の [lang:en]Good morning[/lang]！",
          "emotion": "thinking"
        },
        {
          "speaker": "teacher",
          "content": "正解！上司にはフォーマルな挨拶、朝だから Good morning ですね。Hey や What's up は友達向けですよ",
          "tts_text": "正解！上司にはフォーマルな挨拶、朝だから [lang:en]Good morning[/lang] ですね。[lang:en]Hey[/lang] や [lang:en]What's up[/lang] は友達向けですよ",
          "emotion": "joy"
        }
      ],
      "dialogue_directions": [
        {
          "speaker": "teacher",
          "direction": "3択クイズを出題。視聴者にも考える時間を促す。",
          "key_content": "Hey, What's up, Good morning"
        },
        {
          "speaker": "student",
          "direction": "考えるプロセスを見せながら正解にたどり着く。",
          "key_content": "Good morning"
        },
        {
          "speaker": "teacher",
          "direction": "正解を発表し、なぜその答えが正しいのか理由を説明。",
          "key_content": "上司にはフォーマル、朝だからGood morning"
        }
      ]
    },
    {
      "section_type": "summary",
      "title": "まとめ",
      "content": "今日学んだ挨拶をおさらいしましょう",
      "tts_text": "今日学んだ挨拶をおさらいしましょう",
      "display_text": "まとめ:\n- フォーマル: Good morning / afternoon / evening\n- カジュアル: Hi / Hey / What's up\n- 場面に合わせて使い分けよう！",
      "emotion": "joy",
      "question": "",
      "answer": "",
      "wait_seconds": 3,
      "dialogues": [
        {
          "speaker": "teacher",
          "content": "今日はフォーマルとカジュアルの挨拶を学びました！場面に合わせて使い分けてくださいね",
          "tts_text": "今日はフォーマルとカジュアルの挨拶を学びました！場面に合わせて使い分けてくださいね",
          "emotion": "joy"
        },
        {
          "speaker": "student",
          "content": "いっぱい覚えられた！明日から使ってみます！",
          "tts_text": "いっぱい覚えられた！明日から使ってみます！",
          "emotion": "excited"
        }
      ],
      "dialogue_directions": [
        {
          "speaker": "teacher",
          "direction": "学んだ内容を簡潔にまとめ、実践を促す。",
          "key_content": "フォーマル/カジュアルの使い分け"
        },
        {
          "speaker": "student",
          "direction": "学んだことへの満足感を表現し、実践への意欲を見せる。",
          "key_content": ""
        }
      ]
    }
  ],
  "plan_summary": "英語の挨拶（フォーマル/カジュアル）を対話形式で学ぶ授業。導入→解説→クイズ→まとめの4セクション構成。"
}
```

---

## 注意事項

- `dialogues` は JSON配列として直接渡す（文字列にシリアライズしない）。API側が処理する
- `dialogue_directions` も同様にJSON配列で渡す
- `order_index` はAPI側が自動付与するため、セクションJSONには不要
- `generator` はクエリパラメータ `?generator=claude` で指定するため、セクションJSONには不要
- 画像を読み取れない場合は、`extracted_text`（GET /api/lessons/{id} のレスポンス）にOCR済みテキストがある場合がある
- 既存セクションがある場合は上書きされる
