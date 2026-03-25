# 授業モード v3 — Phase 0: 現状確認

## ステータス: 未着手

## 目的

既存の授業モードで短い授業を1本通して生成・再生し、**具体的な問題点をリストアップ**する。
Phase 1以降の優先度を実データに基づいて確定させる。

---

## 前提条件

- サーバーが起動していること（`./server.sh`）
- 環境変数 `GEMINI_API_KEY` が設定されていること（プラン/スクリプト生成にGemini使用）
- broadcast.html が表示できる環境（C#配信アプリ or ブラウザ直接アクセス）

---

## 手順

### Step 1: サーバー状態確認

```bash
# サーバー起動確認
curl -s http://localhost:$WEB_PORT/api/status | jq .

# 授業モードのエンドポイントが応答するか
curl -s http://localhost:$WEB_PORT/api/lessons | jq .

# キャラクター設定確認（先生・生徒がDBにあるか）
curl -s http://localhost:$WEB_PORT/api/characters | jq '.characters[] | {id, name, role}'
```

**確認ポイント**:
- [ ] サーバーが `ok` を返す
- [ ] `/api/lessons` がリスト（空でもOK）を返す
- [ ] 先生キャラ（role: teacher or main相当）が存在する
- [ ] 生徒キャラ（role: student or sub相当）が存在する（対話モード検証用）

---

### Step 2: テスト用コンテンツ作成

短くて結果が確認しやすい教材を使う。英語授業で `[lang:en]` タグの挙動も同時に検証。

```bash
# コンテンツ作成
curl -s -X POST "http://localhost:$WEB_PORT/api/lessons" \
  -H 'Content-Type: application/json' \
  -d '{"name": "v3テスト: 簡単な英語挨拶"}' | jq .

# → レスポンスの lesson.id を控える → 以降 LESSON_ID として使用
LESSON_ID=<返ってきたID>
```

#### 教材テキストの設定

URL追加でテキスト抽出を検証する。短いページを使用:

```bash
# URL追加（短い英語学習ページなど）
curl -s -X POST "http://localhost:$WEB_PORT/api/lessons/$LESSON_ID/add-url" \
  -H 'Content-Type: application/json' \
  -d '{"url": "https://example.com"}' | jq .
```

URL抽出がうまくいかない場合、直接DBに教材テキストを設定:

```bash
# extracted_textを直接設定
curl -s -X PUT "http://localhost:$WEB_PORT/api/lessons/$LESSON_ID" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "v3テスト: 簡単な英語挨拶",
    "extracted_text": "英語の基本挨拶を学びましょう。\n\n1. Hello - こんにちは（一番基本的な挨拶）\n2. Good morning - おはようございます\n3. Good afternoon - こんにちは（午後）\n4. Good evening - こんばんは\n5. How are you? - お元気ですか？\n6. Nice to meet you - はじめまして\n\nこれらの挨拶は日常会話でよく使います。発音のポイント: Helloの「H」は息を吐くように、Good morningの「r」は舌を巻きすぎないように注意しましょう。"
  }' | jq .
```

**確認ポイント**:
- [ ] コンテンツが作成されIDが返る
- [ ] URL追加の場合: テキスト抽出が成功するか（`extracted_text` がセットされるか）
- [ ] PUT更新の場合: `extracted_text` が正しく保存されるか

---

### Step 3: プラン生成

```bash
# プラン生成（SSE — リアルタイム進捗表示）
curl -N -X POST "http://localhost:$WEB_PORT/api/lessons/$LESSON_ID/generate-plan?lang=ja"
```

SSE出力で以下のイベントが順に来ることを確認:
1. `expert: knowledge` — 知識エキスパートの分析
2. `expert: entertainment` — エンタメエキスパートの分析
3. `expert: director` — 監督による統合
4. 最終JSON — `plan_sections` 配列

```bash
# 生成されたプランを確認
curl -s "http://localhost:$WEB_PORT/api/lessons/$LESSON_ID" | jq '.plans'
```

**確認ポイント**:
- [ ] 3エキスパートが順に実行される
- [ ] `plan_sections` が3〜5セクション程度に収まるか
- [ ] セクションの `section_type` が適切か（introduction → explanation → example → summary等）
- [ ] 各セクションに `emotion` が設定されているか
- [ ] `has_question` が true のセクションがあるか（問いかけ検証用）
- [ ] SSE中にエラーが出ないか
- [ ] 生成にかかった時間を記録（目安: 〜30秒）

---

### Step 4: スクリプト + TTS生成

```bash
# スクリプト生成（SSE — TTS生成進捗も含む）
curl -N -X POST "http://localhost:$WEB_PORT/api/lessons/$LESSON_ID/generate-script?lang=ja"
```

SSE出力の確認:
1. スクリプト生成フェーズ — セクション構造のJSON
2. TTS生成フェーズ — 各セクションのTTS生成進捗

```bash
# 生成されたセクション一覧を確認
curl -s "http://localhost:$WEB_PORT/api/lessons/$LESSON_ID" | jq '.sections[] | {order_index, section_type, title, emotion, display_text, dialogues}'

# TTS キャッシュ確認
curl -s "http://localhost:$WEB_PORT/api/lessons/$LESSON_ID/tts-cache?lang=ja" | jq .
```

**確認ポイント**:

#### テキスト品質
- [ ] 各セクションの `content` が自然な日本語か
- [ ] `tts_text` に `[lang:en]` タグが英語部分に正しく付与されているか
- [ ] `display_text` が適切な文字量か（長すぎ→パネルはみ出し、短すぎ→情報不足）
- [ ] 導入（introduction）の挨拶が自然か
- [ ] 締め（summary）の挨拶が自然か
- [ ] セクション間の繋がりが自然か（唐突な話題転換がないか）

#### 対話モード
- [ ] `dialogues` フィールドにJSON配列が入っているセクションがあるか
- [ ] 対話内容で先生(teacher)と生徒(student)が交互に話しているか
- [ ] 生徒の発話が不自然でないか

#### TTS生成
- [ ] 全セクションのTTSが正常に生成されたか（`tts_generated` / `tts_errors`）
- [ ] TTSキャッシュファイルが `resources/audio/lessons/{id}/ja/` に存在するか
- [ ] 生成にかかった時間を記録（目安: 〜1-2分）

---

### Step 5: 授業再生

```bash
# broadcast.html をブラウザで開く（配信画面の確認用）
# URL: http://localhost:$WEB_PORT/broadcast

# 授業開始
curl -s -X POST "http://localhost:$WEB_PORT/api/lessons/$LESSON_ID/start?lang=ja" | jq .
```

再生中に broadcast.html を目視で確認:

**確認ポイント**:

#### パネル表示
- [ ] `lesson-text-panel` にセクションのテキストが表示される
- [ ] テキストがパネルからはみ出していないか
- [ ] テキストが重なっていないか
- [ ] フォントサイズが読みやすいか
- [ ] `lesson-progress-panel` に進捗が表示される
- [ ] セクション切替時にパネルが正しく更新される

#### 音声
- [ ] TTS音声が再生される
- [ ] 英語部分の発音がカタカナ発音になっていないか
- [ ] 音量が適切か（他の音声要素とのバランス）
- [ ] 対話モード時に先生・生徒の声が区別できるか

#### アバター
- [ ] 発話中にアバターのリップシンクが動作する
- [ ] 感情（emotion）に応じた表情変化があるか

#### タイミング
- [ ] セクション間の待機時間が自然か（長すぎ/短すぎ）
- [ ] 問いかけ（question）セクションで適切に待機するか

#### 制御
- [ ] 一時停止が効くか
  ```bash
  curl -s -X POST "http://localhost:$WEB_PORT/api/lessons/$LESSON_ID/pause" | jq .
  ```
- [ ] 再開が効くか
  ```bash
  curl -s -X POST "http://localhost:$WEB_PORT/api/lessons/$LESSON_ID/resume" | jq .
  ```
- [ ] 停止が効くか
  ```bash
  curl -s -X POST "http://localhost:$WEB_PORT/api/lessons/$LESSON_ID/stop" | jq .
  ```
- [ ] 停止後にパネルが非表示になるか

---

### Step 6: 問題の記録

発見した問題を以下のテンプレートで記録する:

```markdown
### 発見した問題

| # | セクション | カテゴリ | 問題の内容 | 重大度 | 対応Phase |
|---|-----------|---------|-----------|--------|----------|
| 1 | 全体 | パネル表示 | ... | 高/中/低 | Phase 1 |
| 2 | section 0 | 英語発音 | ... | 高/中/低 | Phase 1 |
| ... | | | | | |
```

カテゴリ:
- **パネル表示**: はみ出し、重なり、フォントサイズ
- **英語発音**: カタカナ発音、[lang:en]タグ欠落
- **テキスト品質**: 構成、繋がり、不自然さ
- **対話品質**: 掛け合い、生徒発話の自然さ
- **タイミング**: 待機時間、セクション間
- **TTS**: 生成エラー、音質
- **UI/UX**: 管理画面、操作性

---

## 完了条件

- [ ] 短い授業を1本、生成（プラン→スクリプト→TTS）→ 再生まで通すことができた
- [ ] broadcast.html での表示を目視確認した
- [ ] 英語発音の現状を確認した
- [ ] 対話モード（先生+生徒）の動作を確認した
- [ ] 発見した問題を具体的にリストアップした
- [ ] 各問題の対応Phaseを仮割り当てした
- [ ] Phase 1の作業内容が問題リストに基づいて確定した

---

## 所要時間の目安

| ステップ | 目安 |
|---------|------|
| Step 1: サーバー確認 | 1分 |
| Step 2: コンテンツ作成 | 2分 |
| Step 3: プラン生成 | 30秒〜1分 |
| Step 4: スクリプト+TTS生成 | 1〜2分 |
| Step 5: 授業再生・確認 | 3〜5分（授業の長さ次第） |
| Step 6: 問題記録 | 5分 |
| **合計** | **約15分** |

---

## 備考

- Phase 0は「問題を見つける」フェーズ。修正はPhase 1以降で行う
- 問題が想定より少なければPhase 1をスキップしてPhase 2に進むことも可能
- 問題が想定より多ければPhaseの構成を見直す
- 生成結果はランダム性があるため、同じ教材で2回試すと違う問題が出ることがある
