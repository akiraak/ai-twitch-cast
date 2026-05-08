# Topic Video #1（id=200）試聴チェックリスト

> 紹介動画モード（`topic_video`）の第1作。授業ではなくニュース／特集動画。
> プラン: [../vibe-coder-security-webapp-intro.md](../vibe-coder-security-webapp-intro.md) ／ 素材: [./topic-1-webapp-source.md](./topic-1-webapp-source.md)
> 戻ってきたらここから再開。状況: セクション投入＋TTS事前生成は完了、**試聴のみ未実施**。

## 現在の状態

- `lesson_id=200` / `lang=ja` / `generator=claude` / `version=1` / `category=topic_video`
- セクション 13 本（順番）:
  1. prologue — 現状の裏側（5 ターン）
  2. incident — Lovable BOLA（2026.4）（7 ターン）
  3. incident — Lovable + Supabase RLS（2025.5）（7 ターン）
  4. incident — tea dating（2025.7）（7 ターン）
  5. incident — Replit AIエージェント DB削除（2025.7）（7 ターン）
  6. incident — Moltbook（2026.1）（6 ターン）
  7. stats — 数字で見る現実（15 ターン）
  8. pair — ペア①②③ APIキー / RLS / 認可（15 ターン）
  9. pair — ペア④⑤ SQLi・XSS / プロンプトインジェクション（12 ターン）
  10. pair — ペア⑥⑦ Webhook偽装 / 料金暴走（10 ターン）
  11. addition — 全アプリ共通の追加対策A〜D（10 ターン）
  12. checklist — 公開前チェックリスト（8 ターン）
  13. outro — 締め: 「動いた」と「安全」は別の星（5 ターン）
- dialogues 計 **114 ターン**（ちょビ＝解説 / なるこ＝視聴者代弁）
- TTS 事前生成: `resources/audio/lessons/200/ja/claude/v1/section_*_dlg_*.wav`（gitignored）

## 試聴の手順

1. サーバー起動確認: `curl -s http://localhost:8080/api/status`
2. 管理画面 → 紹介動画タブ（または Lesson タブ・kind=topic_video） → lesson_id=200「#1 Webアプリ編：5つの事件で振り返るバイブコーディングの落とし穴」を選択
3. 各セクションを順に再生（または通し再生）。20〜23 分尺の長めなので 2〜3 セクションずつ区切って耳通しでも可

## チェック観点

> 全部に `[x]` が入って `[x] N/N` で埋まったら Step 5 完了 → Step 6（配信）に進む。

### 1. 誤読（サービス名・用語）

- [ ] **事件・サービス名**: `Lovable` / `Bolt.new` / `Replit` / `tea dating` / `Moltbook` / `v0` / `Vercel` / `Cloudflare` / `Supabase` / `Firebase` / `Auth0` / `Clerk` / `NextAuth` / `Stripe` / `OpenAI` / `Anthropic` / `Cursor` / `Claude Code` / `Aikido` / `Symbiotic` / `Vibe App Scanner` / `Veracode` / `Wiz` / `Trend Micro` / `Upstash` / `EmailJS` / `PostHog` / `reCAPTCHA` / `Helmet.js` / `DOMPurify` / `Prisma` が日本語読みされていないか
- [ ] **セキュリティ用語**: `RLS` / `BOLA` / `IDOR` / `XSS` / `SQL injection` / `CSRF` / `CORS` / `HSTS` / `CSP` / `JWT` / `HMAC-SHA256` / `OWASP Top 10` / `OWASP API Security Top 10` / `MCP` / `MFA` / `OAuth` / `PII` / `GDPR` の発音が破綻していないか
- [ ] **環境変数・コード片**: `NEXT_PUBLIC_` / `service_role` / `auth.uid()` / `dangerouslySetInnerHTML` / `zod` / `valibot` / `.env` / `.gitignore` / `npm` / `express-rate-limit` / `stripe.webhooks.constructEvent` / `X-Slack-Signature` / `ENABLE ROW LEVEL SECURITY` が変な発音で読まれていないか
- [ ] **CVE 表記**: `CVE-2025-48757` が「シーブイイー…」など意図通り読まれているか

### 2. 言語タグ漏れ（`[lang:en]` 抜け）

- [ ] **Section 2-6（incident）**: `BOLA` / `Broken Object Level Authorization` / `RLS` / `Row Level Security` / `Firebase` / `Supabase` / `anon key` / `service_role` の言語タグが抜けて変なイントネーションになっていないか
- [ ] **Section 7（stats）**: `OWASP Top 10` / `Veracode` / `GitHub` / `Wiz` / `Vercel` / `v0` の言語タグ
- [ ] **Section 8（pair①②③）**: `NEXT_PUBLIC_` / `auth.uid()` / `service_role` / `IDOR` / `BOLA`
- [ ] **Section 9（pair④⑤）**: `SQL injection` / `XSS` / `zod` / `valibot` / `DOMPurify` / `Prisma` / `dangerouslySetInnerHTML` / `MCP`
- [ ] **Section 10（pair⑥⑦）**: `Webhook` / `HMAC-SHA256` / `Stripe` / `Upstash` / `express-rate-limit` / `AWS Budgets`
- [ ] **Section 11（addition）**: `CSP` / `HSTS` / `CORS` / `Auth0` / `Clerk` / `NextAuth` / `GDPR` / `Aikido` / `Symbiotic` / `Vibe App Scanner`

### 3. 数字読み（耳通り確認）

- [ ] **大きい数字**: `1,645`（せんろっぴゃくよんじゅうご）／ `170件`（ひゃくななじゅっけん）／ `72,000枚`（ななまんにせんまい）／ `150万件`（ひゃくごじゅうまんけん）／ `3.5万件`（さんてんごまんけん）／ `17,000件`（いちまんななせんけん）／ `2,000件以上` ／ `303エンドポイント`
- [ ] **割合・倍率**: `45%` ／ `2.74倍` ／ `91.5%` ／ `20%` ／ `60%以上` ／ `約70%`
- [ ] **金額**: `30万円` ／ `50万円`（ペア⑦の暴走例）
- [ ] **日数・期間**: `48日`（よんじゅうはちにち、放置期間）／ `公開3日` ／ `5回のAPIコール`
- [ ] **年月**: `2025.5` / `2025.7` / `2026.1` / `2026.4` の年月表記が「にせんにじゅうご年5月」など自然に読まれているか

### 4. ちょビ／なるこの掛け合い

- [ ] **ちょビ**: 解説役として明るく軽快、たまに自虐。**事件解説でも暗くなりすぎていない**
- [ ] **なるこ**: 視聴者代弁役として「うわ、知らなかった」「で、結局なにすればいいの？」のリアクションが**自然に挟まる**
- [ ] **「先生／生徒」のラベルが前面に出ていない**（授業っぽくなっていないか）
- [ ] **自虐は1回だけ**（「この紹介動画もAIが書いてるから、視聴者は信じすぎないでね」相当のセリフが Section 8 付近に1回出る／2回以上出ていないか）
- [ ] **なるこの突拍子なボケは全体で1〜2回まで**（Section 9 の「`.env` ってエンって何？縁？」相当が1回だけ。多用されていないか）
- [ ] **ちょビが3連投以上で なるこ が消えるセクションがないか**（特に Section 7 stats / Section 8〜10 pair / Section 11 addition の長尺セクション）

### 5. トーン

- [ ] **怖がらせない・煽らない**。「やばい、自分のアプリ大丈夫かな」という他人事じゃない感が、軽快なテンポで出ているか
- [ ] **説教臭くない**（授業フォーマットへの先祖返りが起きていないか／ニュース特集の語り口が維持されているか）
- [ ] **攻撃手口の具体ステップが出ていない**（「こういう穴があった」までで止まっているか／コピペ可能な攻撃コードが出ていないか）
- [ ] **事実関係の言い回し**: 実在サービスについて「○○は脆弱だった」ではなく「○○で公開された事故では…」「○○の調査では…」のような事実ベースになっているか
- [ ] **tea dating の言及**: 「AIがやらかした」と決めつけていないか（AI関与は係争中）

### 6. display_text と読み上げの関係

- [ ] **prologue**: `"Vibe Coding" — Collins Word of the Year 2025` / `Anthropic CEO: 3〜6ヶ月で全コードの90%はAI生成` / `tea dating: 運転免許証 72,000枚` が画面に出ているタイミングで読まれているか
- [ ] **incident 5本**: 各事件名・年月・被害規模が画面と読み上げで揃っているか
- [ ] **stats**: 5つの数字がスライド出現と読み上げで対応しているか
- [ ] **pair**: ❌コード／✅コードの対比が画面に出ているタイミングで言語タグ込みで正しく読まれているか
- [ ] **checklist**: 🟢 / 🟡 / 🔴 の3列レイアウトが broadcast.html で破綻なく表示されているか（要 broadcast.html 側の表現確認）

### 7. emotion 切り替え

- [ ] **ちょビ**: prologue=neutral→serious / incident=serious / stats=neutral / pair=neutral→serious / addition=encouraging / checklist=encouraging / outro=warm
- [ ] **なるこ**: prologue=surprised / incident=concerned〜panic〜resigned / stats=surprised→thoughtful / pair=focused〜worried→relieved / addition=satisfied / checklist=determined / outro=thoughtful→smiling
- [ ] **不自然な感情切り替え**がないか（明るすぎる事件解説／暗すぎる checklist など）

### 8. セクション尺・全体尺

- [ ] **prologue**: 〜1分
- [ ] **incident 5本**: 各 〜1.5分（合計 〜7.5分）
- [ ] **stats**: 〜2分
- [ ] **pair 3束**: 〜3分／〜2.5分／〜2分（合計 〜7.5分）
- [ ] **addition**: 〜2分
- [ ] **checklist**: 〜2分
- [ ] **outro**: 〜1分
- [ ] **全体**: 20〜23 分に収まっているか／長すぎる場合は incident と pair を圧縮するか前後編分割を検討（200=前編 / 201=後編）

### 9. 紹介動画モード固有

- [ ] **kind=topic_video が効いている**: クイズ待ちロジックがスキップされ、無音の長い間が発生していない
- [ ] **broadcast.html の「再生中」ラベル**: 「授業: …」ではなく「紹介動画: …」になっているか
- [ ] **VALID_SECTION_TYPES のホワイトリスト**: prologue / incident / stats / pair / addition / checklist / outro が全て表示・再生される（バリデーションで弾かれていない）

## 微修正のフロー

### A. テキストだけ直す（同 version=1 を上書き）

セクションを編集（管理画面の Section 編集 UI、または `PATCH /api/lessons/200/sections/{section_id}`）→ 該当セクションの TTS だけ再生成:

```bash
# 1セクションだけ TTS キャッシュを削除（order_index は 0〜12）
curl -X DELETE "http://localhost:8080/api/lessons/200/tts-cache/0?lang=ja&generator=claude&version=1"

# 全セクション再生成したいとき
curl -X DELETE "http://localhost:8080/api/lessons/200/tts-cache?lang=ja&generator=claude&version=1"

# TTS再生成キック
curl -X POST  "http://localhost:8080/api/lessons/200/tts-pregen?lang=ja&generator=claude&version=1"
curl -s       "http://localhost:8080/api/lessons/200/tts-pregen-status?lang=ja&generator=claude&version=1" | python3 -m json.tool
```

### B. 大幅に書き直す（v1 を破棄して再投入）

素材 md（`topic-1-webapp-source.md`）を編集 → セクションを再生成 → `import-sections?version=1` で **同バージョン上書き**（`teacher.py` の import-sections は同バージョンが既に存在する場合 sections と TTS キャッシュを掃除してから書き込む）。

```bash
# import-sections に sections JSON を送る。version=1 を明示で同バージョン上書き
curl -X POST "http://localhost:8080/api/lessons/200/import-sections?lang=ja&generator=claude&version=1" \
  -H 'Content-Type: application/json' -d @sections.json
```

> **DB が正本**。再生成する場合は `prompts/topic_video_generate.md` のワークフローに沿って素材mdから組み直す。

### C. 完全に作り直す

プランの「全削除・再生成の手順」を参照（`plans/vibe-coder-security-webapp-intro.md`）。lesson_id=200 を残してセクションだけ消し、Step 4 から再開。

## エンドポイント早見表

| 用途 | 実エンドポイント |
|------|------------------|
| TTS事前生成キック | `POST /api/lessons/200/tts-pregen?lang=ja&generator=claude&version=1` |
| TTS進捗 | `GET /api/lessons/200/tts-pregen-status?...` |
| TTS中断 | `POST /api/lessons/200/tts-pregen-cancel?...` |
| セクション投入 | `POST /api/lessons/200/import-sections?lang=ja&generator=claude[&version=N]` |
| TTSキャッシュ削除 | `DELETE /api/lessons/200/tts-cache[/{order_index}]?...` |
| レッスン取得 | `GET /api/lessons/200`（sections / dialogues 込み） |

## 試聴後にやること

- 全項目 `[x]` で埋まった → TODO.md の Step 5 を `[x] N/N`（N = チェック項目数）で埋め、Step 6（配信）に進む
- 軽微な修正 → A. のフローで直し、再試聴（修正したセクションだけチェックを `[ ]` に戻す）
- 大幅修正 → B. または C.

その後 Step 6（配信）→ 反応収集 → DONE.md 更新 →プランを「完了」にして紹介動画モード第1作完結。
