# バイブコーディング×セキュリティ Webアプリ編 紹介動画

> 元記事: [非エンジニアがバイブコーディングで気を付けるセキュリティ ― Webアプリ編](https://akiraak.github.io/deep-pulse/articles/2026-05-06_%E9%9D%9E%E3%82%A8%E3%83%B3%E3%82%B8%E3%83%8B%E3%82%A2%E3%81%AE%E3%83%90%E3%82%A4%E3%83%96%E3%82%B3%E3%83%BC%E3%83%87%E3%82%A3%E3%83%B3%E3%82%B0_%E3%82%BB%E3%82%AD%E3%83%A5%E3%83%AA%E3%83%86%E3%82%A3Web%E3%82%A2%E3%83%97%E3%83%AA%E7%B7%A8.html)
> 関連: [vibe-coder-security-lesson.md](vibe-coder-security-lesson.md)（10話授業シリーズ・別物）

## ステータス: 完了（2026-05-10）

## 背景

- 既存の「バイブコーダーセキュリティ講座（10話）」は **教師×生徒の授業フォーマット**で、各テーマを深堀る構成
- 一方、本コンテンツは **「2025〜2026年の事件・統計を踏まえて、いま何が起きているのかを紹介する動画」**。授業でも教科書でもなく、**ニュース／特集動画**に近い
- 元記事は5つの実事件・各種統計・7つのペア（落とし穴×対策）・公開前チェックリストを1本にまとめた特集記事。これを動画として翻案する
- 既存の lesson モードは「introduction → explanation → example → question → summary」の学習フローを前提にしているため、ニュース特集の語り口にはやや窮屈。**新しい再生モード（紹介動画モード）を1本立て**、本作をその第1作とする

## 目的

1. **新モード「紹介動画」の最小限の枠組みを作る**（既存lesson基盤を最大限流用しつつ、授業ではない別カテゴリとして独立）
2. **第1作として元記事を動画化**：ちょビ（解説）×なるこ（疑問・茶々）の対話で、5事件→統計→7ペア→追加対策→チェックリストの流れを紹介
3. 配信して反応を見る。今後 #2「モバイル編」「LLMアプリ編」「ノーコード編」等が出てきたら、本モードに同じカテゴリで追加していく前提の土台とする

## 「紹介動画モード」とは

### lesson モードとの違い

| 観点 | lesson モード（既存） | 紹介動画モード（本プラン） |
|------|---------------------|--------------------------|
| 目的 | 体系的に学ばせる | 現況をざっと知ってもらう |
| 対話の役割 | teacher が教え、student が学ぶ | ちょビが**解説**、なるこは**視聴者代弁**（「えっそれヤバくない？」「で、結局どうすれば？」） |
| セクション種別 | introduction / explanation / example / question / summary | prologue / incident / stats / pair / addition / checklist / outro（クイズ無し） |
| 進行 | 学習用に各論を深掘る | テンポ良く話題を切り替える |
| 視聴後に残るもの | 知識・ハンズオンの足がかり | 「やばい、自分のアプリ大丈夫かな」という気づき + 出典記事へ誘導 |

### モードの構成要素（最小）

- カテゴリ: 新カテゴリ `topic_video`（slug）／ name `紹介動画`
- 1作 = 1 lesson 行（DB上は lessons テーブルを流用）
- 識別子: `lessons.kind`（または `lesson_categories.kind`）に `topic_video` を入れて lesson モードと区別
- セクション: `lesson_sections` を流用。`section_type` に `prologue` / `incident` / `stats` / `pair` / `addition` / `checklist` / `outro` を許容（既存の introduction 等は維持）
- TTS事前生成・runner・配信中の表示は既存の lesson 系をそのまま使う（クイズ機能だけ無効化）

### 話者構成（既存キャラを据え置き）

- **ちょビ**：解説役。事件の概要・統計・対策のキモを説明。トーンは明るく軽快、たまに自虐
- **なるこ**：視聴者代弁役。「うわ、知らなかった」「それうちのアプリも当てはまるかも」「で、結局なにすればいいの？」のような感想・質問・茶々
- 役割は lesson と**同じ**だが、ラベルとしての「先生／生徒」は前面に出さない（プロンプト側で「**今日は授業ではなくニュース紹介**」と指示する）

### UI

- 管理画面に「**紹介動画**」タブを新設（既存「Lesson」タブの隣）
- 一覧／編集／TTS事前生成／試聴ボタンは Lesson タブと同じUIを流用（kind=`topic_video` で絞り込み）
- broadcast.html での再生時、画面上の「いま再生中」表示は「授業: …」ではなく「紹介動画: …」に分岐

## データモデル & 実装方針

### 推奨案: lesson_* 流用 + `kind` 識別子

- `lesson_categories` に `kind TEXT NOT NULL DEFAULT 'lesson'` カラムを追加。`'lesson'` / `'topic_video'` の2値
- **kind の解決経路**: `lessons.category` は slug 文字列（例: `vibe_coding`）。kind は `lesson_categories` 側に持つので、レッスン単体から kind を引くには `lessons.category → lesson_categories.slug → lesson_categories.kind` の JOIN ルックアップが必要。`src/db/lessons.py` に `get_lesson_kind(lesson_id) -> str` のようなヘルパを足し、各所はそれを使う
- `topic_video` カテゴリのレッスンには quiz セクション生成プロンプトを使わない（`prompts/topic_video_generate.md` を新設）
- `lesson_runner.py` は **kind ヘルパを呼んでクイズ待ち時間ロジックを分岐**（quiz が来ない前提なら `question_answer_wait_sec` 不要）
- 管理画面 Lesson タブ：`kind='lesson'` のみ表示
- 管理画面 紹介動画タブ：`kind='topic_video'` のみ表示
- API: `/api/lessons/*` をそのまま使うが、一覧APIに `?kind=` フィルタを足す
- TTS事前生成・配信制御は lesson と同じ経路

**理由**: 紹介動画モードは「セクションを順に dialogue で再生する」点で lesson と同じ。テーブルを別に切ると TTS 事前生成・runner・admin UI を二重実装する羽目になり保守コストが跳ね上がる。`kind` 1カラム追加で大半の差分を吸収できる。

### 代替案（参考）: 専用テーブル新設

- `topic_videos` / `topic_video_sections` を別テーブルとして切る
- メリット: lesson の制約に縛られない（後で大きく形を変えやすい）
- デメリット: TTS事前生成・runner・admin UI を全部もう1セット書く必要があり、現時点ではオーバーキル
- → **将来 lesson と紹介動画の差が大きくなったら検討**。今は推奨案で進める

### lesson_id 帯域

- 紹介動画は **200番台** を予約（lesson は 100番台）
- 第1作 = `id=200` 「Webアプリ編」
- AUTOINCREMENT は触らず、決め打ちINSERTで予約（既存プランの「lesson_id 予約のやり方」と同じ手順）

## 第1作: 「現状のバイブコード×セキュリティ Webアプリ編」

### タイトル候補

- A: `#1 現状のバイブコード×セキュリティ：Webアプリ編`
- B: `Webアプリ編：5つの事件で振り返るバイブコーディングの落とし穴`
- C: `バイブコードの裏で何が起きていたか：2025-2026 Webアプリ事件簿`

→ B か C を推奨（ニュース特集トーン）。最終決定は素材md作成時に。

### セクション構成（13セクション、尺は気にしない方針で全部入り）

| # | section_type | テーマ | 想定尺 |
|---|-------------|-------|--------|
| 1 | `prologue` | フック：「AIが全コードの90%を書く時代」の裏側 | 〜1分 |
| 2 | `incident` | Lovable BOLA（2026.4）：ソースコード・DB認証情報・チャット履歴流出 | 〜1.5分 |
| 3 | `incident` | Lovable RLS（2025.5）：1,645アプリ中170件で個人情報漏洩 | 〜1.5分 |
| 4 | `incident` | tea dating（2025.7）：運転免許証72,000枚流出 | 〜1.5分 |
| 5 | `incident` | Replit DB削除（2025.7）：AIが本番DBを消した | 〜1.5分 |
| 6 | `incident` | Moltbook（2026.1）：APIトークン150万件・メール3.5万件 | 〜1.5分 |
| 7 | `stats` | 統計：AI生成コードの45%脆弱性・2.74倍リスク・v0が30日17,000件ブロック | 〜2分 |
| 8 | `pair` | 7つのペア①〜③：APIキー漏洩／DB直露出／認可バグ | 〜3分 |
| 9 | `pair` | 7つのペア④〜⑤：SQLi・XSS／プロンプトインジェクション | 〜2.5分 |
| 10 | `pair` | 7つのペア⑥〜⑦：Webhook偽装／料金暴走 | 〜2分 |
| 11 | `addition` | 全アプリ共通の追加対策A〜D（ヘッダ・認証外注・ログ・自動スキャン） | 〜2分 |
| 12 | `checklist` | 公開前チェックリスト：🟢OK / 🟡要警戒 / 🔴絶対NG | 〜2分 |
| 13 | `outro` | 締め：「動いた」と「安全」は別の星／出典記事への誘導／次回予告 | 〜1分 |

合計 約20〜23分の長尺。

> 「7ペア＝1セクション×7」も検討したが、過剰に細切れになって視聴離脱を招きそうなので **2〜3個ずつ束ねた3セクション** に圧縮する。クイズは置かないが、各 incident セクションの最後で「これ、自分のアプリで起きうると思う？」みたいな問いかけを混ぜて視聴者参加感を出す。

### display_text 候補（読み上げ＋画面表示）

| section | 候補 |
|---------|------|
| prologue | `"Vibe Coding" — Collins Word of the Year 2025`<br>`Anthropic CEO: "3〜6ヶ月で全コードの90%はAI生成"` |
| Lovable RLS | `1,645 アプリ調査 → 170件で個人情報漏洩 (約10%)` |
| tea dating | `運転免許証 72,000枚 (バケット公開設定ミス)` |
| stats | `AI生成コード: 45%が OWASP Top 10 該当`<br>`AI共著コード: 脆弱性発生率 2.74倍` |
| pair① | `❌ NEXT_PUBLIC_OPENAI_API_KEY=...`<br>`✅ 環境変数 + サーバ側APIルート経由` |
| pair② | `❌ allow read, write: if true;`<br>`✅ auth.uid() = user_id` |
| pair④ | `❌ db.query(\`SELECT * FROM users WHERE id=${id}\`)`<br>`✅ db.query('SELECT * FROM users WHERE id=?', [id])` |
| pair⑤ | `❌ system: "あなたは...\n\nユーザー入力: " + userInput`<br>`✅ messages: [{role:'system'...}, {role:'user', content: userInput}]` |
| checklist | 🟢🟡🔴 の3列レイアウト（要broadcast.html側の表現確認） |

各 incident セクションでは事件名と被害規模を**画面に出した状態で1セクション通す**ほうが印象に残る。display_text の出し方は試聴段階で詰める。

### 言語タグ運用（必須）

- `[lang:en]xxx[/lang]` を必ず付ける対象:
  - 用語: `RLS`, `BOLA`, `IDOR`, `XSS`, `SQL injection`, `CSRF`, `CORS`, `HSTS`, `CSP`, `JWT`, `HMAC-SHA256`, `OWASP Top 10`
  - サービス・ツール: `Lovable`, `Replit`, `tea dating`, `Moltbook`, `v0`, `Vercel`, `Cloudflare`, `Supabase`, `Auth0`, `Clerk`, `NextAuth`, `Stripe`, `GitHub`, `OpenAI`, `Anthropic`, `Aikido`, `Symbiotic`, `Vibe App Scanner`, `Veracode`, `Wiz`, `Trend Micro`, `Upstash`
  - 環境変数・コード: `NEXT_PUBLIC_`, `service_role`, `auth.uid()`, `dangerouslySetInnerHTML`, `zod`, `valibot`, `DOMPurify`, `Prisma`
- **数字読み**: 「72,000枚」「150万件」など大きな数字はTTS耳通り確認必須。表記ゆれ（"1,645" vs "千六百四十五"）は素材mdで指定する

### トーン指示

- **怖がらせない、煽らない**。「うわー、これは知らないとやられるな」という**他人事じゃない感**を、軽快なテンポで出す
- ちょビは事件解説でも軽口を残す（暗くしない）
- なるこは「で、私のアプリ大丈夫？」と視聴者代弁。たまに突拍子もないボケ（例:「`.env` って、エンって何？縁？」）を1〜2回入れる
- 自虐は1回だけ：「この紹介動画もAIが書いてるから、視聴者は信じすぎないでね」
- **攻撃手口の具体的なステップは出さない**。「こういう穴があった」までで止める

## 実装ステップ

### Step 1: 紹介動画モードの最小実装（コード）

1. `lesson_categories` に `kind TEXT NOT NULL DEFAULT 'lesson'` を追加するマイグレーション（`src/db/core.py` の既存マイグレーションブロックに `ALTER TABLE` を追記）
2. `topic_video` カテゴリを作成（`POST /api/lesson-categories` で `kind='topic_video'`）。**カテゴリ関数は `src/db/lesson_categories.py` ではなく `src/db/lessons.py` (L261+) にある**ので、そこの `create_category()` (L270) と `update_category()` に `kind` 引数を追加し、`__init__.py` の re-export と `scripts/routes/teacher.py` のカテゴリ系APIも揃える
3. **`VALID_SECTION_TYPES` の kind別拡張** — `scripts/routes/teacher.py:907` の現状は `{introduction, explanation, example, question, summary}` のみで、新 section_type を `import-sections` するとバリデーションエラーになる。kind別ホワイトリスト（lesson用 / topic_video用 = `{prologue, incident, stats, pair, addition, checklist, outro}`）を導入し、`import_sections` でそのレッスンの kind を引いて分岐する
4. `prompts/topic_video_generate.md` を新設（`prompts/lesson_generate.md` をベースに、クイズ無し・ニュース特集トーン・section_type 拡張）
5. `src/db/lessons.py` に `get_lesson_kind(lesson_id) -> str` ヘルパを追加（lessons.category → lesson_categories.kind を JOIN で解決、不明時は `'lesson'`）
6. `lesson_runner.py`：上記ヘルパで kind を読み、`topic_video` の場合は quiz 待ち時間ロジックを skip。それ以外は既存ロジックのまま
7. **broadcast 側の section_type 表示**: `static/js/broadcast/panels.js` の `baseFs` (L213) と `PROGRESS_ICONS` (L280) は現5種のみ対応。新7種のアイコンとフォントサイズを追記（最低限デフォルト値で落ちないが、見栄えと意味性のため明示推奨）
8. 管理画面に「紹介動画」タブを追加（実装は Lesson タブ = `static/js/admin/teacher.js` のコピーではなく、kind フィルタを引数化した**共通モジュール**に切り出す方向で）
9. broadcast.html の「再生中」ラベルを kind で分岐（「授業: …」/「紹介動画: …」）
10. テスト追加（`tests/test_api_teacher.py` の VALID_SECTION_TYPES 周りの拡張＋ `test_db.py` で `get_lesson_kind` のJOIN検証）

### Step 2: lesson_id 200 を予約

```bash
python3 - <<'PY'
import sqlite3, datetime
NOW = datetime.datetime.now(datetime.timezone.utc).isoformat()
conn = sqlite3.connect('data/app.db')
conn.execute(
    "INSERT INTO lessons (id, name, category, created_at, updated_at) VALUES (?,?,?,?,?)",
    (200, '#1 Webアプリ編：5つの事件で振り返るバイブコーディングの落とし穴', 'topic_video', NOW, NOW),
)
conn.execute("UPDATE sqlite_sequence SET seq = MAX(seq, 200) WHERE name = 'lessons'")
conn.commit()
PY
```

### Step 3: 素材md作成

- `plans/vibe-coder-security/topic-1-webapp-source.md` に元記事を**全文書き起こし＋整理**して保存
  - 5事件のメタ情報（年月・被害件数・原因クラス・出典）
  - 統計の生数字と出典
  - 7ペアそれぞれの「ダメコード／直したコード」具体例
  - 4つの追加対策の具体名
  - 公開前チェックリストの3色分類
- 各セクションのアウトライン（dialogues 何ターン、display_text 候補、emotion）
- 元記事は時間と共に更新される可能性があるので、**素材md化した時点でのスナップショット**として保存しておく（出典URLとアクセス日付を必ず併記）
- **記事公開日とアクセス日**: 元記事は 2026-05-06 公開・本プラン策定 2026-05-07 → 素材mdの先頭に `published: 2026-05-06 / accessed: 2026-05-07` を明記する

### Step 4: セクション生成 → DB投入

1. `prompts/topic_video_generate.md` のワークフローに従い、Claude Code が素材md を読んで sections JSON を生成
2. `POST /api/lessons/200/import-sections?lang=ja&generator=claude&version=1` で投入
3. 管理画面で各セクションの dialogues / display_text / emotion を目視確認

### Step 5: TTS事前生成 → 試聴

```bash
curl -X POST "http://localhost:${WEB_PORT:-8080}/api/lessons/200/tts-pregen?lang=ja&generator=claude&version=1"
curl -s      "http://localhost:${WEB_PORT:-8080}/api/lessons/200/tts-pregen-status?lang=ja&generator=claude&version=1" | python3 -m json.tool
```

試聴チェックリストは `plans/vibe-coder-security/topic-1-webapp-audition.md` に作成（lesson-1-audition.md がテンプレ）。観点：

- 事件名・サービス名・統計用語の誤読
- 数字の読み方（「1,645」「72,000」「2.74倍」「91.5%」）
- 言語タグ漏れ
- ちょビの解説テンポ／なるこの相槌の間
- ニュース特集トーンが維持されているか（説教臭くなっていないか）

### Step 6: 配信

- 通常の lesson 配信フローと同じ（管理画面 → 再生）
- 配信時にチャットで反応を見て、後段の「現状のバイブコード×セキュリティ」シリーズ（モバイル編／LLMアプリ編等）を作るか判断

## 今後の候補（紹介動画モードの将来作）

紹介動画モードを使い回せる題材の例：

- `#2 モバイルアプリ編`（同様の事件・対策をモバイル文脈で）
- `#3 LLMアプリ編`（プロンプトインジェクション・データ漏洩を深掘り）
- `#4 ノーコード／ローコード編`
- `#5 直近30日のバイブコーディング事件まとめ`（定期更新型）
- セキュリティ以外: 開発トレンド／新ツール紹介／論文レビュー

## リスク・留意点

- **元記事の正確性**: 引用統計や事件詳細が誤っていた場合、動画でそのまま広めてしまう。**素材md化の段階で出典を1次ソースまで辿って検証**する（例: Veracode 45%、GitHub PR 2.74倍、v0 17,000件、Wiz 20% は各社の公式発表/ブログを確認）
- **事件名と表記ゆれ**: `tea dating` / `Moltbook` などサービス名の正式表記を確認。誤字は致命的
- **時間経過による陳腐化**: 半年後には新しい事件が出てくる。動画タイトルに `2025-2026版` と入れて時期を明示する
- **法的配慮**: 実在サービスの事故を取り上げるので、**事実関係の誤りや誹謗中傷にならない言い回し**にする（「○○は脆弱だった」ではなく「○○で公開された事故では…」のように事実ベース）
- **kind カラム追加マイグレーション**: 既存の lesson 行は `kind='lesson'` でデフォルト埋まる。配信中・TTS事前生成中はマイグレーションを当てない
- **管理画面の二重実装回避**: Lesson タブと紹介動画タブのUIをコピペすると保守地獄。**共通コンポーネント化**を最初から意識する
- **長尺リスク**: 20分超は視聴離脱しやすい。試聴で耐えられない長さなら、incident と pair を圧縮するか、**前後編に分割**（200=前編・5事件＋統計／201=後編・7ペア＋チェックリスト）する選択肢を残す

## 完了条件

- [x] `lesson_categories.kind` カラム追加マイグレーションが実装・テストされている
- [x] `topic_video` カテゴリが DB に登録されている
- [x] `prompts/topic_video_generate.md` が作成され、ワークフローが書かれている
- [x] 管理画面に「紹介動画」タブが表示され、kind=`topic_video` の lesson のみ並ぶ
- [x] `lesson_runner` が kind=`topic_video` でクイズ待ちロジックをスキップする
- [x] lesson_id=200 が予約され、第1作のセクション（13本想定）が `import-sections` 経由で投入されている
- [x] TTS事前生成が完了し、管理画面から通しで再生できる
- [x] 試聴チェックリスト（topic-1-webapp-audition.md）が**全項目チェック済み**形式（`[x] N/N`）で埋まっている
- [x] 配信1回実施し、視聴者反応を記録した
- [x] 素材md（topic-1-webapp-source.md）に出典URL・アクセス日付付きで保存されている
- [x] DONE.md に記録、本プランを「完了」に更新

## 参考

- 元記事: 上記URL（要素材md化時点でアクセス日付を記録）
- 既存の授業シリーズプラン: [vibe-coder-security-lesson.md](vibe-coder-security-lesson.md)
- 既存の授業生成ワークフロー: `prompts/lesson_generate.md`（紹介動画用 prompt のベース）
- 発話フロー: `docs/speech-generation-flow.md`
- API仕様: `scripts/routes/teacher.py`
- 出典の1次ソース確認に使う候補:
  - Veracode: AI 生成コード脆弱性レポート
  - GitHub: PR 470件の脆弱性発生率分析
  - Wiz: AI コード脆弱性調査
  - Trend Micro: AI コーディングセキュリティ提言
  - 各事件の事業者発表・報道（Lovable／tea dating／Replit／Moltbook）
