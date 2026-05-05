# バイブコーダーのためのセキュリティ講座

> TODO原文: 「バイブコーダーのためのキュリティー口座 / 非エンジニアがWebアプリ開発時に気を付けること」
> 表記ゆれ修正: 「セキュリティ講座」（タイトルでは原文の遊びを残すかは要相談）

## ステータス: 未着手

## 背景

AIコーディングアシスタント（Claude Code / Cursor / v0 / Bolt 等）の普及で、非エンジニアいわゆる「バイブコーダー」が自分でWebアプリを書いて公開するケースが急増している。一方で、

- `.env` や APIキーを GitHub に push してしまう
- `innerHTML = userInput` で雑にXSSを開ける
- Supabase/Firebase の Row Level Security を無効のまま本番に出す
- フロントエンドに Stripe シークレットキーを書く
- AIが生成したコードを読まずにそのままデプロイする

といった「自分はやらないつもりだったが、知らなかったので踏んだ」事故が後を絶たない。これは「教材があれば防げた」種類の事故であり、本プロジェクトの**授業モード**（教師×生徒の対話形式で楽しく学ぶ）と相性が良い。

## 目的

**バイブコーダー向けのセキュリティ講座を、本リポジトリの授業モードで配信できる教材として作成する。**

- 対象視聴者: AIで開発を始めた非エンジニア。ターミナル・Git・HTTPの基礎は知っているが、セキュリティを体系的に学んだことはない層
- 配信目的: 楽しく見ているうちに「最低限ここだけは押さえる」が頭に残る
- 構成: 1カテゴリ「バイブコーダーセキュリティ」配下に複数lessonを配置（連続した授業シリーズ）

## 方針

1. **既存仕組みをそのまま使う**。`lesson_generator/` のLLM駆動パイプラインや `prompts/lesson_generate.md` のワークフローを変更しない。新コンポーネントは作らない
2. **教材ソースは「テキスト要点」で済ませる**。スライド画像は必須ではないので、まずは概念だけ整理して `extracted_text` 相当の素材から `dialogues` を生成する。必要に応じて後から図解スライドを追加する
3. **1テーマ＝1lesson**。長くなりすぎないよう各lesson 5〜7分（4〜6セクション）に収める。シリーズ全体で6lesson程度
4. **キャラ設定は既存の teacher / student をそのまま使う**。新キャラは作らない（必要が出たら別プラン）
5. **「怖がらせる」より「お得感」**。事故の悲惨さを煽るのではなく、「これだけ守れば守備力が上がる」というポジティブなトーンで書く

## カリキュラム（lesson 構成案）

カテゴリ: **「Vibe Coding」**（既存カテゴリでなければ新規作成）

**lesson_id は決め打ちで予約する**。既存lesson_idは `[1, 3]` で、AUTOINCREMENTに任せると番号が散らばってしまうため、本シリーズは **100〜105** を確保して Claude Code が順次コンテンツを生成していく運用にする。連番で覚えやすく、他カテゴリと衝突しないブロックとして十分離れている。

| lesson_id | # | タイトル | 学習目標 | 主要キーワード |
|-----------|---|---------|---------|----------------|
| `100` | 1 | シークレットの守り方 | APIキー・パスワード・トークンを漏らさない最低限のルールが分かる | `.env` / `.gitignore` / git history scrub / フロント露出 / GitHub secret scanning |
| `101` | 2 | ユーザー入力は全部疑え | XSS / SQLi の仕組みと、ライブラリで自動的に防ぐ方法が分かる | エスケープ / パラメータ化クエリ / `innerHTML` の罠 / DOMPurify |
| `102` | 3 | 認証は自作しない | 認証・パスワード保存・セッション管理を「ちゃんとした既製品」に任せるべき理由が分かる | bcrypt/argon2 / Auth0 / Supabase Auth / Clerk / セッション固定攻撃 |
| `103` | 4 | データベース権限とRLS | Supabase / Firebase で「全公開DB」状態を作らないための初期設定が分かる | Row Level Security / Firestore rules / 公開バケット |
| `104` | 5 | デプロイ前チェックリスト | 本番に出す前に最低限見るポイントが分かる | HTTPS強制 / CORS / レート制限 / デバッグログ / 環境変数の本番分離 |
| `105` | 6 | AI生成コードを信用しない | AIのコードを"読む"観点と、危険な提案の見分け方が分かる | ハルシネーションされたパッケージ / 古いAPI推奨 / 過剰な権限要求 / コピペ前の3秒チェック |

> **MVPとしては #1〜#3 をまず作る**（lesson_id 100〜102）。配信反応を見て #4〜#6 を追加するか判断する。

### lesson_id 予約のやり方

`POST /api/lessons` は AUTOINCREMENT で id を採番するため、決め打ちIDで作るには SQL を直接叩く（または明示id対応のAPIを足す）。本プランでは前者で済ませる:

```bash
sqlite3 data/twitch.db <<'SQL'
INSERT INTO lessons (id, name, category) VALUES
  (100, '#1 シークレットの守り方',         'Vibe Coding'),
  (101, '#2 ユーザー入力は全部疑え',       'Vibe Coding'),
  (102, '#3 認証は自作しない',             'Vibe Coding'),
  (103, '#4 データベース権限とRLS',         'Vibe Coding'),
  (104, '#5 デプロイ前チェックリスト',      'Vibe Coding'),
  (105, '#6 AI生成コードを信用しない',      'Vibe Coding');
-- AUTOINCREMENT のシーケンスを 105 以降に進めて、後続lessonが106から振られるようにする
UPDATE sqlite_sequence SET seq = 105 WHERE name = 'lessons';
SQL
```

予約後は **空のlessonレコードに対して Claude Code が順次セクション生成 → `import-sections` で投入** していく。途中で生成順を入れ替えても lesson_id は変わらないので、シリーズ内のクロスリファレンス（「#3で説明したように…」のような言及）が安全に書ける。

## 各lessonのセクション構成（共通テンプレ）

`prompts/lesson_generate.md` に従い、以下の流れを基本形とする。

1. `introduction`: 「今日のテーマ」+ 視聴者を引き込むフック（ヒヤッとする実例 1つ）
2. `explanation`: 仕組みの説明（なぜ危険か）
3. `example`: 具体例（よくあるダメコード → 直したコード のbefore/after）
4. `question`: 視聴者への3択クイズ
5. `summary`: 「今日のポイント3つ」

`display_text` には実コード断片やコマンドを表示し、`dialogues` の最初の teacher ターンで全文読み上げる（`prompts/lesson_generate.md` のルール準拠）。

## 生成・保存されるアーティファクト

授業データは **DB** と **ファイルシステム** の両方に分散保存される。本プランで何がどこに作られるかを先に整理しておく。

### SQLite DB（`data/twitch.db`、`src/db/lessons.py` 経由）

| テーブル | 何が入る | 本プランで作る行 |
|----------|---------|-----------------|
| `lesson_categories` | カテゴリ定義 | 1行（「Vibe Coding」、未存在時のみ作成） |
| `lessons` | 授業本体（id / name / category） | **lesson_id 100〜105 を決め打ち予約**。MVPで3行（100〜102）、最終的に6行（〜105） |
| `lesson_sources` | 教材ソースのメタ情報（`file_path` で実体ファイルを参照） | **0行**（スライド画像なし方針のため作らない） |
| `lesson_versions` | lang × generator × version のバージョンメタ | lesson × 言語 × generator ごとに1行 |
| `lesson_sections` | セクション本体（content / tts_text / display_text / dialogues / dialogue_directions / emotion 等、**対話の中身はここ**） | lessonあたり4〜6行 × MVP3lesson |
| `lesson_plans` | `plan_summary` 等のプランサマリー | lesson × バージョンごとに1行 |

### ファイルシステム（`resources/` 配下）

| パス | 何が置かれる | 本プランでの扱い |
|------|-------------|-----------------|
| `resources/images/lessons/{lesson_id}/` | アップロードした教材画像本体 | **作らない**（画像なし方針） |
| `resources/audio/lessons/{lesson_id}/{lang}/{generator}/v{version}/*.wav` | TTS事前生成キャッシュ（`tts_pregenerate.py` / `lesson_runner.py` が書き出す） | 自動生成。再生前に `pregenerate-tts` API で一括生成し、不要になれば削除して再生成可能 |

### プロジェクト内の中間ファイル（リポジトリにコミット）

| パス | 何が置かれる | 役割 |
|------|-------------|------|
| `plans/vibe-coder-security-lesson.md` | 本プラン | 設計の正本 |
| `plans/vibe-coder-security/lesson-{N}-source.md` | 各lessonの要点メモ（カバーすべき具体例・キーワード・参照リンク） | **制作中の中間物**。配信時はDBから読まれる。次回改訂時に再利用するためコミットしておく |

> **配信時の正本はDB**。素材mdはセクション生成のためのインプットであり、配信実行時には参照されない。素材mdを更新しただけではDBは変わらないので、変更後は `import-sections` で再投入すること。

> **全削除する場合の流れは下記「全削除・再生成の手順」を参照**。

## 全削除・再生成の手順

シリーズ全体を作り直すケースを想定する（カリキュラム再構成・トーン大幅変更・ライブラリ名アップデート・公開前のクリーンアップ等）。状況に応じて2パターン使い分ける。

`db.delete_lesson()` は `lesson_sections / lesson_sources / lesson_plans / lesson_versions / lessons` を全部消してくれる（`src/db/lessons.py:48-56`）。`DELETE /api/lessons/{id}` ルートはこれを呼ぶ前に `clear_tts_cache()` も走らせるので、ファイルとDBが揃ってクリーンアップされる。

### パターン A: コンテンツだけリセット（lesson_id 100〜105 は維持）

セクション・対話・プラン・全バージョン・TTSキャッシュを消し、**lesson行とID予約は残す**。文章を作り直すだけのケース。

```bash
# 各lessonの全バージョンを順に削除（バージョンAPIは行ごとなので一覧→ループ）
for id in 100 101 102 103 104 105; do
  versions=$(curl -s "http://localhost:${WEB_PORT:-8080}/api/lessons/${id}" \
    | python3 -c "import sys,json; d=json.load(sys.stdin); [print(f\"{v['lang']} {v['generator']} {v['version_number']}\") for v in d.get('versions', [])]")
  while read -r lang gen ver; do
    [ -z "$ver" ] && continue
    curl -X DELETE "http://localhost:${WEB_PORT:-8080}/api/lessons/${id}/versions/${ver}?lang=${lang}&generator=${gen}"
  done <<< "$versions"
done

# 念のためTTSキャッシュとDB残骸を掃除（API漏れがあった場合の保険）
sqlite3 data/twitch.db <<'SQL'
DELETE FROM lesson_sections WHERE lesson_id BETWEEN 100 AND 105;
DELETE FROM lesson_plans    WHERE lesson_id BETWEEN 100 AND 105;
DELETE FROM lesson_versions WHERE lesson_id BETWEEN 100 AND 105;
SQL
rm -rf resources/audio/lessons/{100,101,102,103,104,105}
```

完了後、**Step 3（セクション生成）から再開**。lesson_id・カテゴリは予約済みのまま。

### パターン B: 完全リセット（lesson行ごと削除して予約からやり直し）

カリキュラム自体を組み直すとき。**lesson_id 予約をやり直すので、他カテゴリのlessonを巻き込まないか確認してから実行**。

```bash
# 各lessonを完全削除（行・ソース・セクション・全バージョン・TTSキャッシュ一括）
for id in 100 101 102 103 104 105; do
  curl -X DELETE "http://localhost:${WEB_PORT:-8080}/api/lessons/${id}"
done

# AUTOINCREMENT を 99 に巻き戻し、次の予約INSERTが100から始まるようにする
sqlite3 data/twitch.db "UPDATE sqlite_sequence SET seq = 99 WHERE name = 'lessons';"

# キャッシュフォルダの残骸を掃除（DELETE APIが消し漏らした場合の保険）
rm -rf resources/audio/lessons/{100,101,102,103,104,105}
```

完了後、**Step 1（カテゴリ作成 + lesson_id 予約）から再開**。

### パターン C（参考）: 同バージョン上書き

「特定のlessonだけ全部書き直したい」「履歴を綺麗に保ちたい」場合は、削除せず `POST /api/lessons/{id}/import-sections?version=N` で **同バージョンを上書き** する。`import-sections` は `version` 指定時に該当バージョンのセクションとTTSキャッシュをクリアしてから書き込むので、A/Bよりも安全（`teacher.py:946-956`）。差し替え運用の基本はこちら。

### 削除前チェック

- **配信中・TTS事前生成中は削除しない**。`GET /api/lessons/{id}` の `pregen_status` を見て待つか、`POST /api/lessons/{id}/cancel-tts-pregeneration` で停止
- カテゴリ「Vibe Coding」自体は**消さない**（他のlessonが将来使う可能性）。消すときは `DELETE /api/lesson-categories/{category_id}`
- 本番配信のスケジュール直前に B を実行しない（再生成に時間がかかる）

## 実装ステップ

### Step 1: カテゴリ作成 + lesson_id 予約

```bash
# カテゴリ作成（既存なら不要）
curl -X POST http://localhost:${WEB_PORT:-8080}/api/lesson-categories \
  -H 'Content-Type: application/json' \
  -d '{"name":"Vibe Coding","description":"AIで開発する非エンジニア向けの実践講座（セキュリティ等）","prompt_content":""}'

# lesson_id 100〜105 を決め打ちで予約（上記「lesson_id 予約のやり方」のSQLを実行）
sqlite3 data/twitch.db < /tmp/reserve_vibe_coding_lessons.sql
```

`POST /api/lessons` は使わない（AUTOINCREMENTでIDが取れないため）。予約後 `curl /api/lessons | jq` で `id: 100〜105` が並んでいることを確認する。

### Step 2: 教材素材（要点メモ）を用意

各lessonの「要点メモ」を `plans/vibe-coder-security/lesson-{N}-source.md` のような中間ファイルに書き、
- カバーすべき具体例（ダメコードと直したコード）
- 必ず触れるキーワード
- 視聴者に持って帰ってほしいメッセージ
を箇条書きで整理する。これが Claude Code が `dialogues` を組むときの素材になる。

> **画像スライドは作らない**（MVP段階）。教材抽出APIを通さず、素材mdを Read してそのままセクション生成する。

### Step 3: セクション生成

`prompts/lesson_generate.md` のワークフローに従い、Claude Code が以下を実施:

1. キャラクター情報を取得（`/api/characters`）
2. 用意した素材mdを Read
3. `dialogues` / `dialogue_directions` / `display_text` を含むセクションJSONを生成
4. `POST /api/lessons/{lesson_id}/import-sections?lang=ja&generator=claude` でDB保存

### Step 4: TTS事前生成と試聴

```bash
# TTS事前生成（管理画面 or API）
curl -X POST "http://localhost:${WEB_PORT:-8080}/api/lessons/{lesson_id}/pregenerate-tts?lang=ja&generator=claude"

# 管理画面の Lesson タブで再生し、以下を確認:
# - 各セクションの display_text が読みやすいか
# - 対話のテンポ（teacher 連投で生徒が空気になっていないか）
# - 言語タグ（[lang:en]...[/lang]）が正しく英単語に付いているか
# - クイズの選択肢が紛らわしすぎないか / 簡単すぎないか
```

### Step 5: 改善ループ（必要に応じて）

`lesson_generator` の improver / evaluator を使い、品質評価で弱いセクションだけ再生成する。詳細は `prompts/lesson_improve.md` / `prompts/lesson_evaluate_quality.md` 参照。

### Step 6: 配信本番でのフィードバック反映

- 配信中のコメントで反応が薄かったセクションは `lesson_improve_prompt.md` のフローでプロンプト側を調整
- 視聴者から指摘された誤りは即時 `import-sections` で上書き（既存セクションは上書きされる仕様）

## 中身の品質ポイント（書くときに気をつけること）

- **「正しい用語」より「動く感覚」**。CSRF/XSS/SQLi の頭文字を覚えさせるより、「この一行があれば防げる」という実用パターンを示す
- **before/after コードは短く**。`display_text` は5〜10行で収まるサイズに切る（長いと視聴者が読みきれない）
- **AI生成コードを叩かない**。「AIが悪い」ではなく「使う側のチェックポイント」というスタンスにする。本講座自体がAIで作られる以上、自虐ネタとして1〜2回触れると締まる
- **生徒キャラの役割**: 視聴者の「えっ、それダメなんですか？」を代弁する。teacher が一方的に喋る授業にしない
- **"とりあえずこれ"で終わらせる**。各lessonの summary は「今日からこの3つだけ」で締めて、深追いしない

## リスク・留意点

- **素材mdの正確性**: 筆者（プラン作成者）がセキュリティ専門家ではない場合、素材段階で誤情報が混入するとそのまま視聴者に広まる。素材mdは公開セキュリティガイド（OWASP Top 10、MDN、各サービス公式ドキュメント）への参照リンクを必ず併記し、生成後に1lessonずつレビューする
- **ライブラリ・サービス名の固有名詞**: 「Supabase」「Auth0」「Clerk」等は時期によって状況が変わる（買収・終了・価格変更）。授業の中で**サービスを推奨しすぎない**。「○○のような認証サービス」という言い回しを基本にする
- **言語混在のTTS**: 英語のコード片やコマンド名が多くなるため `[lang:en]` タグを丁寧に付ける必要がある。漏れるとTTSが日本語読みして混乱する
- **長尺化リスク**: 1セクション内のdialogueが10ターンを超えると視聴維持率が落ちる。`lesson_generate.md` の「4〜8ターン」を守る
- **同じ事例の繰り返し**: シリーズ通して「APIキー漏洩」が3回出てきたりしないように、シリーズ全体の素材mdを先にまとめてから個別生成に入る

## 完了条件

- [ ] カテゴリ「Vibe Coding」が作成されている
- [ ] lesson_id 100〜105 が予約済み（空でもDBに行が存在する）
- [ ] lesson #1〜#3（MVP、id=100〜102）にセクションが投入されている
- [ ] 各lessonのセクションが `import-sections` 経由で投入され、TTS事前生成が完了している
- [ ] 管理画面の Lesson タブから3lessonとも最後まで再生でき、明らかな誤読・崩れがない
- [ ] 素材mdが `plans/vibe-coder-security/` 配下に保存され、参照元リンクが付いている
- [ ] 全削除・再生成手順（パターンA/B/C）が手元で動作確認できている（少なくとも1回はパターンAで通しリセット→再投入を試す）
- [ ] DONE.md に記録、本プランを「完了」に更新（MVP3本までは「フェーズ1完了」とし、#4〜#6 は別タスクとして切り出してもよい）

## 参考

- 既存ワークフロー: `prompts/lesson_generate.md`（**着手前に必ず再読**）
- 改善パイプライン: `prompts/lesson_improve.md`, `prompts/lesson_evaluate_quality.md`
- API仕様: `scripts/routes/teacher.py`
- 発話フロー: `docs/speech-generation-flow.md`
