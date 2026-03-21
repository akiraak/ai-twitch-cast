# 配信言語設定の再設計

## ステータス: 完了

## 背景

現在の「言語モード」は5つのプリセットから選ぶ方式だが、違いが分かりにくく実質2つしか使っていない。
ゼロから再設計し、直感的な3項目の設定に置き換える。

## 新設計: 3項目の配信言語設定

### 設定項目

| 項目 | 内容 | UI |
|------|------|-----|
| 基本言語 | メインで話す言語 | ドロップダウン |
| サブ言語 | 混ぜる言語（「なし」も可） | ドロップダウン |
| 混ぜ具合 | サブ言語をどれくらい混ぜるか | 3段階セレクト |

### 混ぜ具合の3段階

| レベル | DBキー | プロンプトへの指示イメージ |
|--------|--------|--------------------------|
| 少し | `low` | 挨拶・感嘆詞・一単語程度。「やったー! We did it!」 |
| ほどほど | `medium` | フレーズ単位で自然に混ぜる。「えー、I didn't know that!」 |
| たくさん | `high` | 文単位で両方使う。ほぼバイリンガル |

サブ言語が「なし」の場合、混ぜ具合は非表示。

### 他言語コメントへの対応（固定ルール）

- **相手の言語で返答する**
- 基本言語・サブ言語も自然に混ぜる
- 翻訳欄にはサブ言語で訳を出す（サブ言語なしなら基本言語で訳）

例: 基本=English, サブ=日本語, 混ぜ具合=ほどほど でスペイン語コメントが来たら
→ 「¡Hola! Bienvenido! えー、it's great to have you here! 楽しんでいってね!」

### 対応言語（初期）

日本語、English、한국어、Español、中文、Français、Português、Deutsch

### WebUI

```
配信言語
┌─────────────────────────────┐
│ 基本言語: [English     ▼]  │
│ サブ言語: [日本語      ▼]  │
│ 混ぜ具合: [少し] [ほどほど] [たくさん] │
└─────────────────────────────┘
```

### DB保存

`settings` テーブルに3つのキーで保存:
- `stream_lang_primary` — 基本言語コード（例: `en`）
- `stream_lang_sub` — サブ言語コード（例: `ja`、なしなら `none`）
- `stream_lang_mix` — 混ぜ具合（`low` / `medium` / `high`）

### AI出力フォーマット

```json
{
  "speech": "返答テキスト",
  "tts_text": "読み上げ用テキスト（言語タグ付き）",
  "emotion": "感情",
  "translation": "翻訳テキスト"
}
```

- `english` → `translation` にリネーム（中身が英語とは限らないため）

## プロンプト設計

### テキスト生成とTTSの分離

言語設定（primary, sub, mix_level）は共有し、プロンプトは別々に生成する。

```
共有: primary, sub, mix_level
         │
    ┌────┴────┐
    ▼         ▼
テキスト生成   TTS
プロンプト    プロンプト
```

### テキスト生成プロンプト: `build_language_rules(primary, sub, mix_level)`

3項目から「## 言語ルール」セクションのテキストを動的生成する。

**生成ロジック:**

1. 基本言語の指示: 「{primary}をメインで話す」
2. サブ言語の混ぜ方（mix_level に応じて）:
   - `low`: 「{sub}は挨拶・感嘆詞・一単語程度にとどめる」
   - `medium`: 「{sub}をフレーズ単位で自然に混ぜる。文のどの位置にも置ける」
   - `high`: 「{sub}を文単位で積極的に使う。両言語ほぼ均等」
3. 他言語対応（固定）: 「コメントの言語で返答する。基本言語・サブ言語も自然に混ぜる」
4. 翻訳欄の指示: 「translationには{sub}訳を入れる」（サブなしなら{primary}訳）

**適用先（発話系3関数）:**
- `generate_response()` — `build_system_prompt()` 経由
- `generate_topic_line()` — 直接注入
- `generate_event_response()` — 直接注入

**適用外（内部処理系5関数）:**
- `generate_user_notes()`, `generate_self_note()`, `generate_persona()`, `generate_persona_from_prompt()`, `generate_topic_title()` — 日本語固定のまま

### TTSプロンプト: `build_tts_style(primary, sub)`

TTS音声の読み方指示を動的生成する。

**生成ロジック:**

1. ベーストーン: 「Cheerful, warm tone」（固定 or 将来的にキャラ設定から）
2. 基本言語の発音: 「{primary}をネイティブ発音で読む」
3. サブ言語の発音: 「{sub}が出てきたらネイティブ発音に切り替える」
4. その他の言語: 「他言語もできるだけネイティブに近い発音で」

**適用先:**
- `src/tts.py` の `_get_tts_style()` — Gemini TTSに渡すスタイル指示

## 実装ステップ

### Step 1: prompt_builder.py 再設計
- `LANGUAGE_MODES` 辞書を廃止
- 新しい状態管理:
  ```python
  _stream_lang = {"primary": "ja", "sub": "en", "mix": "low"}
  def get_stream_language() -> dict
  def set_stream_language(primary, sub, mix)
  ```
- `build_language_rules(primary, sub, mix_level)` 関数を新設
- `build_tts_style(primary, sub)` 関数を新設
- `build_system_prompt()` 内の言語ルール注入を新関数に差し替え

### Step 2: ai_responder.py 更新
- `generate_topic_line()`, `generate_event_response()` の言語ルール注入を `build_language_rules()` に統一
- レスポンスパーサーの `english` → `translation` 対応

### Step 3: tts.py 更新
- `_get_tts_style()` を `build_tts_style()` に差し替え
- 旧 `LANGUAGE_MODES` への依存を削除

### Step 4: API更新（scripts/routes/character.py）
- `GET /api/language` → `{primary, sub, mix, languages: [選択肢一覧]}`
- `POST /api/language` → `{primary, sub, mix}` を受け取る

### Step 5: WebUI更新（static/js/index-app.js）
- 5ボタン → ドロップダウン2つ + 3段階セレクト
- サブ言語「なし」で混ぜ具合を非表示

### Step 6: broadcast.html 更新
- 字幕表示の `english` → `translation` 対応

### Step 7: DB・設定移行
- scenes.json の `language_mode` キー削除
- 旧DB値からの移行ロジック:
  - `ja` → primary=ja, sub=en, mix=low
  - `en_mixed` → primary=en, sub=ja, mix=medium
  - 不明値 → primary=ja, sub=en, mix=low（デフォルト）
- `scripts/web.py` の startup 復元を新形式に対応

### Step 8: テスト更新
- 旧 `LANGUAGE_MODES` テストを削除
- `build_language_rules()` のテスト新設（各組み合わせで異なるルールが生成されること）
- `build_tts_style()` のテスト新設
- API テストを新形式に更新

## リスク

- **`english` → `translation` リネーム**: 影響範囲が広い（broadcast.html, ai_responder.py, テスト等）。grep で全箇所確認してから実施
- **プロンプト品質**: 動的生成ルールが旧プリセットと同等の品質を出せるか → 実際に試して調整
- **DB移行**: 旧 `language_mode` 値が残っている場合のフォールバック処理が必要
