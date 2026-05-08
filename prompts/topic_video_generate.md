# Claude Code 紹介動画スクリプト生成ワークフロー

紹介動画モード（`kind=topic_video`）のスクリプトを生成し、APIでDBに保存する手順書。
既存の授業モード（`lesson_generate.md`）をベースに、**ニュース特集向け**にカスタマイズしたもの。

## 概要

紹介動画モードは、**事件・統計・対策をテンポよく紹介する特集動画**を作るためのモード。
教師×生徒の「学習」フォーマットではなく、**ちょビ（解説）×なるこ（視聴者代弁）**で、
「いま何が起きているか／自分のアプリは大丈夫か」を視聴者に届ける。

授業モードとの主な違い:

| 観点 | 授業モード（lesson） | 紹介動画モード（topic_video） |
|------|---------------------|------------------------------|
| 目的 | 体系的に学ばせる | 現況をざっと知ってもらう |
| 対話の役割 | teacher が教え、student が学ぶ | ちょビが解説、なるこが視聴者代弁（疑問・茶々・気づき） |
| `section_type` | introduction / explanation / example / question / summary | prologue / incident / stats / pair / addition / checklist / outro |
| クイズ | あり（question セクションで `question`/`answer`） | **なし**（`question`/`answer` フィールドは使わない） |
| トーン | 教育・エンタメの両立 | ニュース特集／軽快なテンポ／煽らない |
| 視聴後 | 知識・ハンズオンの足がかり | 「自分のアプリ、大丈夫かな」という気づき + 出典への誘導 |

## 前提条件

- Web サーバー起動（`http://localhost:${WEB_PORT:-8080}`）
- `topic_video` カテゴリが作成済み（`lesson_categories` テーブル、`kind='topic_video'`）
- 紹介動画コンテンツの lesson 行が予約済み（200番台、`category='topic_video'`）
- 元記事スナップショット（`plans/<series>/topic-N-source.md` 等）が用意されている

---

## 手順

### Step 1: 紹介動画コンテンツ情報の取得

```bash
# 紹介動画モードのコンテンツ一覧
curl -s "http://localhost:${WEB_PORT:-8080}/api/lessons?kind=topic_video" | python3 -m json.tool

# 特定コンテンツの詳細
curl -s "http://localhost:${WEB_PORT:-8080}/api/lessons/{lesson_id}" | python3 -m json.tool
```

### Step 2: キャラクター情報の取得

紹介動画でも `teacher` / `student` ロールのキャラクターをそのまま使う。
ただし**プロンプト側で「今日は授業ではなくニュース紹介」と指示し、ラベルとしての"先生／生徒"は前面に出さない**。

```bash
curl -s "http://localhost:${WEB_PORT:-8080}/api/characters" | python3 -m json.tool
```

- `teacher.name` — 解説役（例: ちょビ）
- `student.name` — 視聴者代弁役（例: なるこ）
- 役割は dialogues の `speaker` に `"teacher"` / `"student"` として表現する（既存DBスキーマと互換）

### Step 3: 素材mdの読み取り

`plans/<series>/topic-N-source.md` を Read で開き、以下を確認する:

- 元記事の出典 URL とアクセス日付（**スクリプトの `outro` セクションで必ず言及**）
- 紹介する事件・統計・対策の **正確な数字とサービス名**
- 図表・コード片の有無（`display_text` に流し込む）
- 注意事項（誇張表現の禁止、特定企業の名指し批判の回避など）

### Step 4: セクション構成の設計

紹介動画は **`prologue` から始まり `outro` で終わる**のが基本形。中盤は題材ごとに自由に組み合わせる。

| section_type | 用途 | 配置の目安 |
|--------------|------|-----------|
| `prologue` | 全体のフック。視聴者の興味を引く一言 + 動画全体の概要 | 必ず1個目 |
| `incident` | 個別事件の紹介。事業者・年月・被害規模・原因クラス | 中盤、複数並べてよい |
| `stats` | 統計・調査データ。出典必須 | 事件群の後がよい |
| `pair` | ❌ ダメな例 / ✅ 直した例 のペア解説（コード比較やNG/OKリスト） | 対策パートで複数 |
| `addition` | 共通対策・補足ノウハウ | 対策パートの締め |
| `checklist` | 公開前チェックリスト等のまとめチェック | 終盤 |
| `outro` | 締め + 出典記事への誘導 + 次回予告 | 必ず最後 |

> **Tip**: 7ペアあるからといって `pair` を7セクションに分けない。**2〜3個ずつ束ねた3セクションくらいに圧縮**したほうが視聴離脱を抑えやすい。

### Step 5: スクリプト生成

各セクションを「セクションJSONスキーマ」に従って生成する。

**生成のポイント:**

- `dialogues` は **ちょビ（teacher）の解説 → なるこ（student）の反応 / 質問 / 茶々 → ちょビの補足** の流れが基本
- `incident` セクションは「事件名 → 起きたこと → 被害規模 → なぜ起きたか（原因クラスのみ。**攻撃手口の具体的なステップは出さない**） → ひとこと教訓」
- `stats` セクションは生数字を読む（「4 5 パーセント」「2 . 7 4 倍」など、TTSで聞き取れる読み方を意識）
- `pair` セクションは **❌ と ✅ を必ずペアで** 出す。`display_text` で対比、`dialogues` で読み解く
- `outro` で**必ず元記事の出典 URL を言及**する（読み上げ自体はしなくていいが「動画概要欄／配信ページに元記事のリンクを置いておくよ」など）

**トーンルール:**

- **怖がらせない・煽らない**。「いま何が起きているか／自分にも起こりうる」を軽快に
- ちょビは事件解説でも軽口を残す（暗くしすぎない）
- なるこは「で、私のアプリ大丈夫？」と視聴者代弁。たまに突拍子もないボケを 1〜2回（やりすぎない）
- **特定の企業・個人を断罪しない**。「○○は脆弱だった」ではなく「○○で公開された事故では…」のように事実ベース
- **AIへの自虐は1動画に1回まで**（例: 「この動画もAIが書いてるから信じすぎないでね」）

### Step 6: DBへインポート

```bash
curl -X POST "http://localhost:${WEB_PORT:-8080}/api/lessons/{lesson_id}/import-sections?lang=ja&generator=claude" \
  -H "Content-Type: application/json" \
  -d @sections.json
```

`section_type` が `topic_video` 用ホワイトリストに含まれていない値を入れると 400 で弾かれる（`scripts/routes/teacher.py` の `SECTION_TYPES_BY_KIND`）。

---

## セクションJSONスキーマ

`sections` 配列の各要素は以下のフォーマット:

```json
{
  "section_type": "incident",
  "title": "Lovable BOLA",
  "content": "セクション概要（タグなし、字幕代替）",
  "tts_text": "TTS用テキスト（言語タグ付き）",
  "display_text": "画面表示テキスト（事件名・年月・被害規模など）",
  "emotion": "thinking",
  "dialogues": [
    {
      "speaker": "teacher",
      "content": "発話テキスト（タグなし）",
      "tts_text": "TTS用テキスト（言語タグ付き）",
      "emotion": "thinking"
    },
    {
      "speaker": "student",
      "content": "なるこの相槌",
      "tts_text": "なるこの相槌",
      "emotion": "surprise"
    }
  ],
  "dialogue_directions": [
    { "speaker": "teacher", "direction": "事件の概要をテンポよく", "key_content": "Lovable BOLA / 2026年4月" },
    { "speaker": "student", "direction": "視聴者代弁の驚き",       "key_content": "" }
  ],
  "display_properties": { "maxHeight": 35, "fontSize": 1.6 }
}
```

### フィールド詳細

授業モードと共通のフィールドはそのまま。違いは下記:

| フィールド | 紹介動画での扱い |
|-----------|-----------------|
| `section_type` | `prologue` / `incident` / `stats` / `pair` / `addition` / `checklist` / `outro` のいずれか |
| `question` | **使わない**（紹介動画モードはクイズなし）。空文字でよい |
| `answer` | **使わない**。空文字でよい |
| `wait_seconds` | **書かない**。間は `scenes.json` の `lesson_timings` で一元管理される |

### emotion の使い分け

| 感情 | 紹介動画での使用場面 |
|------|---------------------|
| `excited` | prologue、ワクワクする話題、新しい対策の紹介 |
| `surprise` | 驚きの統計、なるこの「えっそれヤバくない？」 |
| `thinking` | incident の概要説明、原因分析 |
| `sad` | 残念な失敗例、被害が大きいケース |
| `embarrassed` | AI自虐（1動画に1回まで）、なるこのボケ |
| `joy` | pair の ✅ 側、checklist の 🟢 OK |
| `neutral` | 淡々と数字を読み上げる stats、出典告知 |

### display_properties（パネルサイズ制御）

授業モードと同じガイドライン。**コード比較や複数行リストの `pair` / `checklist` では `maxHeight` を 50〜65% / `fontSize` 1.4〜1.6vw** が読みやすい。

### 言語タグ（tts_text用）

授業モードと共通ルール（主要言語＝日本語の場合、英語など非主要言語に `[lang:en]...[/lang]`）。
紹介動画特有の頻出用語例:

- セキュリティ用語: `RLS`, `BOLA`, `IDOR`, `XSS`, `SQL injection`, `CSRF`, `CORS`, `HSTS`, `CSP`, `JWT`, `HMAC-SHA256`, `OWASP Top 10`
- サービス・ツール名: `Lovable`, `Replit`, `tea dating`, `Moltbook`, `v0`, `Vercel`, `Cloudflare`, `Supabase`, `Auth0`, `Clerk`, `NextAuth`, `Stripe`, `GitHub`, `OpenAI`, `Anthropic`, `Aikido`, `Symbiotic`, `Wiz`, `Veracode`
- コード片: `NEXT_PUBLIC_`, `service_role`, `auth.uid()`, `dangerouslySetInnerHTML`, `zod`, `valibot`, `DOMPurify`, `Prisma`

数字読みは TTS の耳通りを意識する（「72,000 枚」「150 万件」など、表記ゆれは素材mdで指定する）。

### dialogues の生成ルール（紹介動画モード版）

- 1セクションあたり **3〜6 ターン** が目安（授業モードよりやや短め、テンポ重視）
- ちょビ（teacher）が事実紹介 → なるこ（student）が視聴者代弁の反応 → ちょビが補足 のリズム
- **メタ前置きを入れない**（「画面を見てね」「読み上げるよ」等は不要。授業モードと共通）
- 各セクションの最初の dialogue（teacher）で `display_text` の内容を**省略せず読み上げる**こと
- **攻撃手口の具体的なステップは絶対に書かない**（「こういう穴があった」までで止める）
- なるこのボケは1動画に1〜2回までに抑える
- AI自虐は 1 動画に 1 回まで

### dialogue_directions の生成ルール

- `direction`: そのターンで何を、どう話すか（2-3文）
- `key_content`: そのターンで必ず言及すべき具体名（事件名、サービス名、数字、コード片など）。不要なら空文字

---

## 品質基準

### 内容の正確性
- [ ] 事件・統計の **数字** が素材md と一致している
- [ ] サービス名の表記が **正式名**（`tea dating` / `Moltbook` 等の表記ゆれなし）
- [ ] 出典URL（元記事）が `outro` で言及されている
- [ ] 攻撃手口の具体的ステップが書かれていない

### トーン
- [ ] 煽り・断罪調になっていない
- [ ] 軽快なテンポを維持している（incident で説教臭くなっていない）
- [ ] AI自虐 / なるこのボケが過剰でない（各1〜2回）

### 技術的整合
- [ ] `section_type` が `topic_video` 用ホワイトリストに含まれている
- [ ] `question` / `answer` が空文字（紹介動画モードではクイズなし）
- [ ] `wait_seconds` が出力されていない
- [ ] 言語タグ（`[lang:en]...[/lang]`）が必要な箇所に付いている
- [ ] `display_properties` が全セクションで指定されている

### 構成
- [ ] 1セクション目が `prologue`、最終セクションが `outro`
- [ ] `incident` を並べる場合、**事業者の偏り**がないか（同じ事業者ばかりにしない）
- [ ] `pair` セクションで ❌ と ✅ がペアで揃っている

---

## 完全な出力例（簡略）

```json
{
  "sections": [
    {
      "section_type": "prologue",
      "title": "現状の裏側",
      "content": "AIが全コードの90%を書く時代。その裏で何が起きているか",
      "tts_text": "AIが全コードの90%を書く時代。その裏で何が起きているか、見ていくよ",
      "display_text": "Vibe Coding — Collins Word of the Year 2025\nAnthropic CEO: \"3〜6ヶ月で全コードの90%はAI生成\"",
      "emotion": "excited",
      "dialogues": [
        {
          "speaker": "teacher",
          "content": "Vibe Coding が Collins の 2025 Word of the Year に選ばれた話、知ってる？",
          "tts_text": "[lang:en]Vibe Coding[/lang] が [lang:en]Collins[/lang] の 2025 [lang:en]Word of the Year[/lang] に選ばれた話、知ってる？",
          "emotion": "excited"
        },
        {
          "speaker": "student",
          "content": "聞いたことあるけど、そんな大事になってるんだ",
          "tts_text": "聞いたことあるけど、そんな大事になってるんだ",
          "emotion": "surprise"
        }
      ],
      "dialogue_directions": [
        { "speaker": "teacher", "direction": "Vibe Coding がメインストリームになっていることを軽く紹介", "key_content": "Collins Word of the Year 2025" },
        { "speaker": "student", "direction": "視聴者代弁で軽く驚く", "key_content": "" }
      ],
      "display_properties": { "maxHeight": 28, "fontSize": 1.7 }
    },
    {
      "section_type": "outro",
      "title": "締め",
      "content": "「動いた」と「安全」は別の星",
      "tts_text": "「動いた」と「安全」は別の星。今日紹介した事件と対策、配信ページの概要欄に元記事のリンクを置いておくから、気になった人は読んでみてね",
      "display_text": "「動いた」と「安全」は別の星\n出典: 元記事リンクは概要欄へ",
      "emotion": "neutral",
      "dialogues": [
        {
          "speaker": "teacher",
          "content": "「動いた」と「安全」は別の星なんだよね",
          "tts_text": "「動いた」と「安全」は別の星なんだよね",
          "emotion": "neutral"
        },
        {
          "speaker": "student",
          "content": "今日のやつ、自分のアプリで一個ずつ確認してみる",
          "tts_text": "今日のやつ、自分のアプリで一個ずつ確認してみる",
          "emotion": "thinking"
        }
      ],
      "dialogue_directions": [
        { "speaker": "teacher", "direction": "全体を一言でまとめ、出典の在りかを案内", "key_content": "「動いた」と「安全」は別の星" },
        { "speaker": "student", "direction": "視聴者代弁で行動意欲を見せる", "key_content": "" }
      ],
      "display_properties": { "maxHeight": 25, "fontSize": 1.6 }
    }
  ],
  "plan_summary": "Webアプリ編：5つの事件で振り返るバイブコーディングの落とし穴。prologue → incident×5 → stats → pair×3 → addition → checklist → outro の13セクション構成。"
}
```

---

## 注意事項

- `dialogues` / `dialogue_directions` は JSON 配列として直接渡す（文字列にシリアライズしない）
- `order_index` と `generator` は API 側で処理。セクションJSONには不要
- 既存セクションがある場合、`?version=N` 指定なら N 版を上書き、省略時は新バージョンが自動採番される
- **生成後は必ず管理画面の「紹介動画」タブから dialogues / display_text / emotion を目視確認**してから TTS 事前生成へ進むこと
- 試聴チェックリストがシリーズに用意されている場合（`plans/<series>/topic-N-audition.md` など）、TTS 事前生成後に必ず全項目を確認する
