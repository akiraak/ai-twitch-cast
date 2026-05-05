# Lesson #1 素材メモ — 全体マップ：バイブコーダーのセキュリティ早わかり

> 対応 lesson_id: **100** / category: `vibe_coding`
> このメモは Claude Code が `dialogues` / `display_text` を組むための素材。視聴者には届かない。
> DB に投入するときは `POST /api/lessons/100/import-sections?lang=ja&generator=claude`。素材を更新しても DB は変わらないので、再生成 → 再投入が必要。

## シリーズ全体像（仮、全10回）

| ID | # | タイトル |
|----|---|---------|
| 100 | 1 | 全体マップ：バイブコーダーのセキュリティ早わかり ← **本レッスン** |
| 101 | 2 | シークレットを守る：`.env`とAPIキーが漏れたら何が起こるか |
| 102 | 3 | ユーザー入力は全部疑え：XSSとSQLインジェクションの止め方 |
| 103 | 4 | 認証は自作しない：Auth0・Clerk・Supabase Authの選び方 |
| 104 | 5 | データベースの初期設定の罠：RLSとFirestore Rules |
| 105 | 6 | 通信を守る：HTTPS強制・CORS・CSRFを正しく扱う |
| 106 | 7 | レート制限と乱用対策：公開直後に始まるBotの叩き |
| 107 | 8 | デプロイ前チェックリスト：本番に出す前の10項目 |
| 108 | 9 | 漏らした時の最初の30分：インシデント対応の型 |
| 109 | 10 | AI生成コードを信用しない：「動いた」を疑う3秒チェック |

## 学習者像
- AIアシスタント（Claude Code / Cursor / v0 / Bolt 等）でWebアプリを書き始めた非エンジニア
- 「とりあえず動いた」から「公開」まで自分でやろうとしている
- セキュリティを体系的に習ったことはない

## このレッスンのゴール
- これからのシリーズ全 10 回で扱うテーマの "名前と全体像" を頭に入れる
- 「自分のアプリにも該当しそう」と思って次回以降を見たくなる
- 怖がらせるより「これだけ守れば守備力が上がる」というポジティブなトーン
- **本レッスンは "概論"。各トピックは深追いしない**（次回以降の予告で締める）

## 持ち帰ってほしいメッセージ（summary 用 3 つ）
1. **公開前に 5 分立ち止まる** — AIで5分で書けるからこそ、最後の確認に5分使う価値がある
2. **専門の道具に乗る** — 認証・DB権限・サニタイズは「自作しない・既製品を使う」が基本
3. **シリーズで全体像** — 各トピックの詳細は次回以降。今日は名前を覚えて帰る

## セクション構成案（5 セクション、6〜8 分）

### Section 1: introduction
- フック例: 「AIに頼んで5分でログイン画面を作れる時代。でも、その『5分後』のサイトが半日で乗っ取られたら？」
- 今日の趣旨: 「これからの全 10 回で扱うセキュリティテーマを、駆け足でサクッと紹介する回」
- 例え: お店を開く前のチェックリスト紹介の回。鍵のかけ方、レジの管理、防犯カメラ、それぞれは別の動画で詳しく
- やり取りの感じ:
  - student: 「セキュリティって、なんか難しそうで後回しにしてました…」
  - teacher: 「それでOK。今日は『何が問題か知ってるだけで防げる』を、まずざっくり紹介するだけだから」

### Section 2: explanation — なぜ "バイブコーダー" がやられやすいか
- 主張: AI が書いたコードは「動く」けれど「安全」とは限らない
- ポイント:
  - AI はセキュリティを最優先には書かない（プロンプトで明示しない限り）
  - 「動いたから完成」だと罠を見落とす
  - 攻撃側も AI で自動化されている — 公開した瞬間に bots が探りにくる
- 例え: 自動運転の車は走らせてくれるけど、シートベルトを締めるのは自分。最後は人間
- display_text 候補:
  ```
  AIが得意 : 動くコードを書く
  AIが苦手 : 「これ本番で大丈夫？」の判断
  ```

### Section 3: ツアー — 全 9 テーマを「アプリのライフサイクル」順に紹介
本セクションは長くなるので、9 テーマを **3 つのフェーズ + メタ** に整理して順に紹介する。
1テーマあたり: **概要1行 → 噛み砕いた例え → 有名な道具/サービス → 「次回以降詳しく」で締める**。

#### Phase 1: 「開発中」のセキュリティ
> 「自分の手元でコードを書いている時間」に決まること。

##### 3-1. シークレットを漏らさない（→ #2）
- 概要: APIキー・パスワード・トークンを漏らさない最低限のルール
- 例え: 家の鍵を Twitter に写真付きで上げるようなもの
- 典型的事故: `.env` を git に push、フロントに Stripe シークレット鍵を直書き、AWS キー流出で数十万円請求
- 道具: `.gitignore` / GitHub secret scanning / `git-secrets` / `dotenv` / Vercel・Netlify の環境変数設定

##### 3-2. ユーザー入力は全部疑う（→ #3）
- 概要: 入力されたテキストには悪意があり得る。何も考えず表示・DB保存すると穴
- 例え: 知らない人から渡された手紙を、確認せず家中に貼って回るようなもの
- 典型的事故: `innerHTML = userInput` で JS が実行される、文字列連結クエリで `' OR 1=1 --`
- 道具: React/Vue/Svelte の自動エスケープ / DOMPurify / parameterized query / Prisma などの ORM

##### 3-3. 認証は自作しない（→ #4）
- 概要: ログイン・パスワード保存・セッション管理は既製品に任せる
- 例え: 玄関の鍵を 100 均の木材で自作するようなもの。本物の鍵屋に頼む
- 典型的事故: パスワードを平文保存、SHA256 だけでハッシュ、JWT の `alg: none` を受理してしまう
- 道具: Auth0 / Clerk / Supabase Auth / Firebase Auth / NextAuth.js / bcrypt / argon2

##### 3-4. データベースの初期設定の罠（→ #5）
- 概要: Supabase / Firebase は初期設定だと「全公開・全アクセス可能」になり得る
- 例え: 銀行の金庫を「鍵かけ忘れ」のままで開店するようなもの
- 典型的事故: Firestore のルール `allow read, write: if true;` のまま本番、Supabase で RLS 有効化忘れ → 他人のデータが全部見える
- 道具: Supabase Row Level Security / Firestore Security Rules / Postgres GRANT

#### Phase 2: 「公開直前」のセキュリティ
> 「ローカルで動いた、いざデプロイ」の前後でやること。

##### 3-5. 通信を守る（→ #6）
- 概要: 通信レイヤー（HTTPS / CORS / CSRF）の最低ライン。設定 1 個で大穴が空くゾーン
- 例え: 玄関は鍵がかかってても、窓が開けっ放しならそこから入られる
- 典型的事故: HTTP のままサービスを出して中継経路でパスワードを抜かれる、CORS が `Access-Control-Allow-Origin: *` でどこからでも API を叩ける、Cookie の `SameSite` 未設定で CSRF
- 道具: Vercel/Netlify/Cloudflare の HTTPS 強制 / HSTS / Helmet.js / SameSite Cookie / CSP

##### 3-6. デプロイ前チェックリスト（→ #8）
- 概要: 本番に出す前に「今すぐ」見るべき 10 項目
- 例え: 飛行機の離陸前チェック。一個一個 OK 確認するだけで事故は減る
- 典型的事故: デバッグログがプロダクションで個人情報を吐く、エラーメッセージにスタックトレースが出て内部構造が漏れる、開発用の `/admin` ページが本番に残る
- 道具: 環境変数の本番分離（dotenv-vault, Doppler）/ Helmet.js / ロガーのログレベル切替

> #6→#8 を続けて紹介。間に挟まる #7（レート制限）は **「公開後」フェーズ** で扱うため、ここでは「公開直後の話は次の章で」と接続する。

#### Phase 3: 「公開後」のセキュリティ
> 「公開した瞬間〜運用中」に起きること。

##### 3-7. レート制限と乱用対策（→ #7）
- 概要: 公開直後から始まる Bot の叩き。ログイン・送信フォーム・API を守る
- 例え: お店を開店した瞬間に、買う気のない冷やかしが 100 人並ぶ。本物のお客さんが入れない
- 典型的事故: ログイン API がレート制限なしでパスワードを総当たりされる、無料枠 API を叩かれて課金枠を食い潰す、お問い合わせフォームでスパム連投
- 道具: Cloudflare WAF / Rate Limit / express-rate-limit / hCaptcha / reCAPTCHA

##### 3-8. 漏らした時の最初の30分（→ #9）
- 概要: 事故が起きた直後にやるべき手順。「焦って何をすべきか分かる」状態を作る
- 例え: 火事の初期消火と同じ。最初の 30 分の動きで被害が大きく変わる
- 典型的事故対応の流れ: キーを即ローテーション → 公開リポからシークレットを除去（git history scrub）→ ログ確認 → 影響ユーザーに告知
- 道具: BFG Repo-Cleaner / git filter-repo / Stripe・AWS のキー再発行画面 / 各種ステータスページ

#### Phase 4: 通底するメタ的な注意

##### 3-9. AI 生成コードを信用しない（→ #10）
- 概要: 「AI が書いたから安全」ではない。ハルシネーション・古い API・過剰な権限要求などの罠
- 例え: AI アシスタントは賢いインターン。アウトプットは必ず先輩（自分）がチェックするもの。インターンに勝手に本番デプロイさせない
- 典型的事故: 存在しないパッケージ名でインストール → 攻撃者の偽パッケージを掴む（slop squatting）、Deprecated な認証方式を提案、`.env` を public リポに commit する提案
- 道具: 自分の目（コードを読む）/ `npm audit` / `pip-audit` / Socket.dev
- 軽い自虐: 「この授業も AI で作ってるから、私たちも油断できない」を 1 回だけ入れる

### Section 4: question — 概論クイズ
3 択問題例:
> Cursor で Web アプリを書いて、いまから公開します。最後に必ず確認しないとマズいのはどれ？
>
> A. アバターのアニメーションが滑らかか
> B. `.env` ファイルが Git に含まれていないか
> C. サイトの配色がモダンか

- 正解: **B**
- 解説: A/C はセキュリティと無関係。B は今日の最初のテーマ「シークレットを漏らさない」の話で、漏らした瞬間に金銭被害になり得る

### Section 5: summary — 持ち帰り 3 つ + 次回予告
1. 公開前に 5 分立ち止まる
2. 自作しない。既製品に乗る
3. 各テーマは次回以降で詳しく — 今日は「名前を覚える」が目標

予告: 「次回 #2 は『シークレットを守る』。`.env` を絶対に push しない方法、漏らした時の対処、を見ていく」

## display_text 候補（teacher が読み上げる短いコード/コマンド片、必要に応じて）
| 用途 | 内容 |
|------|------|
| .env の例（漏らしてはいけないファイル） | `.env`<br>`.env.local`<br>`*.pem`<br>`secrets.json` |
| 危険な input 表示 | `el.innerHTML = userInput;  // 危険`<br>`<div>{userInput}</div>  // Reactなら自動エスケープ` |
| 弱すぎる Firestore ルール | `allow read, write: if true;  // 全公開状態` |
| 弱すぎる CORS | `Access-Control-Allow-Origin: *  // 誰からでも叩ける` |

各サブトピックで 1 つだけ表示する想定。1 セクションに全部出さない。

## 言語タグ運用メモ
- 英単語に `[lang:en]xxx[/lang]` を必ず付ける対象:
  - 一般用語: XSS, SQL injection, RLS, JWT, bcrypt, OAuth, CORS, HTTPS, HSTS, CSRF, CSP, WAF
  - サービス名: Auth0, Clerk, Supabase, Firebase, Vercel, Netlify, Cloudflare, Stripe, GitHub
  - コマンド/パッケージ: npm, pip, dotenv, Helmet.js, DOMPurify, Prisma, Socket.dev
- 日本語のキャッチフレーズには付けない

## 触れる順序の根拠（生成時の参考）
- アプリの **ライフサイクル順** で並べる: 開発中 → 公開直前 → 公開後 → 通底メタ
- 視聴者が「自分が今いる段階」をイメージしやすい
- 「公開した瞬間に Bot が来る」という現実感を Phase 3 で出すと、本シリーズを最後まで見るモチベになる

## トーン指示
- 怖がらせない。「お得感」を出す
- teacher（Chobi）: 明るく分かりやすく、視聴者の味方
- student（Mafuyu）: 「えっ、それ知らなかった！」を代弁する
- 自虐: 「この授業も AI で作ってます」を 1 回だけ入れて軽くする（連発しない）
- **攻撃の具体的な手口は教えない**。「こういう穴がある」までで止める

## 制約（生成時の reminder）
- 6〜8 分（5 セクション）。Section 3 が 9 サブトピックを含むため、概論にしてはやや長め
- display_text は 5〜10 行
- dialogues は 1 セクションあたり 4〜10 ターン（Section 3 だけは長くなってよい）
- teacher 連投で student が空気にならないよう、各サブトピックで student に 1 ターンは反応させる
- サブトピックの読み上げテンポを揃える（30 秒前後 / topic）

## 参考リンク（執筆者向け、視聴者には出さない）
- OWASP Top 10: https://owasp.org/www-project-top-ten/
- OWASP Top 10 for LLM Applications: https://owasp.org/www-project-top-10-for-large-language-model-applications/
- MDN Web Security: https://developer.mozilla.org/en-US/docs/Web/Security
- GitHub Secret Scanning: https://docs.github.com/en/code-security/secret-scanning
- Supabase RLS: https://supabase.com/docs/guides/auth/row-level-security
- Firebase Security Rules: https://firebase.google.com/docs/rules
- BFG Repo-Cleaner: https://rtyley.github.io/bfg-repo-cleaner/
- git filter-repo: https://github.com/newren/git-filter-repo
