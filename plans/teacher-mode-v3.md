# 授業モード v3 — 高速イテレーション改善

## ステータス: 未着手

## 背景

v1〜v2で授業生成・再生の基盤は完成したが、**品質改善のイテレーションが遅い**のが最大のボトルネック。

現状のワークフロー:
1. ソース追加 → プラン生成（LLM×3、〜30秒）
2. スクリプト生成（LLM×1、〜15秒）+ TTS全件生成（〜2分）
3. 授業開始して最初から最後まで聞いて品質確認
4. 問題があればスクリプト全体を再生成 → またTTS全件生成 → 最初から再確認

**→ 1回の改善サイクルに3〜5分かかり、特定セクションだけ直したくても全体を作り直すしかない**

## v3のゴール

**「生成→確認→修正→再確認」のサイクルを最短にする仕組みを作る**

具体的には:
- 特定セクションだけをすぐ聞ける（全体再生不要）
- 特定セクションだけ再生成できる（全体再生成不要）
- テキストだけで素早くプレビューできる（TTS生成待ち不要）
- 既知の問題（表示崩れ、英語発音、定型挨拶）を同時に修正

## 既存TODOからの取り込み

| TODO項目 | v3での対応 | Phase |
|---------|-----------|-------|
| 全体の構成が悪いところがある | セクション個別再生成 + プロンプト改善 | 2 |
| 授業パネルの内容が大きすぎて表示がおかしい | パネル表示修正 | 1 |
| 英語授業なのに英語の発音が悪すぎる | プロンプト + TTSスタイル改善 | 1 |
| 授業パネルの英文を読み上げた方が自然 | display_text読み上げオプション | 3 |
| 最初の挨拶と終わりの挨拶を定型的に | テンプレート導入 | 3 |
| v2未着手: URLテキスト抽出改善 | BeautifulSoup前処理 | 4 |
| v2未着手: チャット割り込み改善 | スコープ外（v3後に別途） |

---

## Phase 0: 現状確認（既存の仕組みで短い授業を生成・再生）

改善の前にまず現状を把握する。短い教材で授業を1本通して生成・再生し、問題点を具体的に洗い出す。

### 手順

1. **サーバーが起動していることを確認**
   ```bash
   curl -s http://localhost:$WEB_PORT/api/status
   ```

2. **テスト用コンテンツを作成**
   - 管理画面（会話モード → 教師モード）で新規コンテンツ作成
   - 名前: 「v3テスト: 簡単な英語挨拶」（短いテーマにする）
   - またはAPI:
   ```bash
   curl -s -X POST http://localhost:$WEB_PORT/api/lessons \
     -H 'Content-Type: application/json' \
     -d '{"name": "v3テスト: 簡単な英語挨拶"}'
   ```

3. **教材テキストを直接設定**（画像/URL不要、最小構成で検証）
   - 抽出テキストを手動で設定（短い素材で十分）:
   ```bash
   LESSON_ID=<上で作成したID>
   curl -s -X PUT "http://localhost:$WEB_PORT/api/lessons/$LESSON_ID" \
     -H 'Content-Type: application/json' \
     -d '{"name": "v3テスト: 簡単な英語挨拶"}'
   ```
   - ※ `extracted_text` はDBに直接入れるか、短いURLを `add-url` で追加

4. **プラン生成**（3エキスパート、〜30秒）
   ```bash
   curl -N "http://localhost:$WEB_PORT/api/lessons/$LESSON_ID/generate-plan?lang=ja"
   ```
   - SSEで進捗確認。最終行のJSONに `ok: true` + `plan_sections` が返ること
   - セクション数が3〜5程度になるよう短い教材にする

5. **スクリプト+TTS生成**（〜1-2分）
   ```bash
   curl -N "http://localhost:$WEB_PORT/api/lessons/$LESSON_ID/generate-script?lang=ja"
   ```
   - SSEで進捗確認。スクリプト生成→TTS生成の順で進む
   - 最終行の `sections` と `tts_generated` / `tts_errors` を確認

6. **生成結果の確認**（テキストレベル）
   ```bash
   curl -s "http://localhost:$WEB_PORT/api/lessons/$LESSON_ID" | python3 -m json.tool
   ```
   - 各セクションの `content`, `tts_text`, `display_text` を目視確認
   - `[lang:en]` タグが英語部分に正しく付いているか
   - `display_text` の文字量は適切か
   - 導入と締めの挨拶の自然さ

7. **授業再生**
   ```bash
   curl -s -X POST "http://localhost:$WEB_PORT/api/lessons/$LESSON_ID/start?lang=ja"
   ```
   - broadcast.html で実際の表示を確認
   - 確認ポイント:
     - [ ] 授業テキストパネルの表示（はみ出し・重なりがないか）
     - [ ] 英語の発音（カタカナ発音になっていないか）
     - [ ] display_text の内容と読み上げ内容の関係
     - [ ] 導入・締めの挨拶の印象
     - [ ] セクション間の繋がり（唐突でないか）
     - [ ] 対話モード（生徒がいる場合）の掛け合い自然さ
     - [ ] 進捗パネルの表示

8. **問題の記録**
   - 発見した問題を具体的にメモ（どのセクション、何が悪いか）
   - Phase 1以降の優先度調整に使う

### 完了条件

- 短い授業を1本、生成→再生まで通せること
- 現状の問題点が具体的にリストアップされていること
- どのPhaseで何を直すか、優先度が確定していること

---

## Phase 1: クイックフィックス（既存バグ修正）

既存の目に見える問題をまず直す。検証基盤を作る前提条件。

### 1-1. 授業パネル表示修正

**問題**: `display_text` の内容が長いとパネルが画面を覆い尽くす。保存済みのCSS値が固定レイアウトを上書きしている。

**対策**:
- `lesson-text-panel` に `max-height` + `overflow-y: auto` を確実に適用
- `applyCommonStyle` で `lesson_text` / `lesson_progress` の `width/height` を除外
- DB上の不正な保存値（`positionX/Y`, `width/height`）をクリーンアップ
- テキスト量に応じた `font-size` 自動調整（文字数閾値で段階的に縮小）

**変更対象**:
- `static/js/broadcast/settings.js` — applyCommonStyle除外リスト追加
- `static/broadcast.html` — lesson-text-panel のCSS強化
- `scripts/routes/overlay.py` — `_OVERLAY_DEFAULTS` からlesson系の位置・サイズ削除

### 1-2. 英語発音改善

**問題**: 英語授業なのに英語がカタカナ発音になる。`[lang:en]` タグがLLMに正しく付与されない。

**対策** ([plans/teacher-mode-v2/06-english-pronunciation.md](teacher-mode-v2/06-english-pronunciation.md) の内容を実行):
- スクリプト生成プロンプトに `[lang:en]` タグの詳細説明を追加（※v2プラン作成後に実装済みのため、実際の動作を確認し不足があれば追加修正）
- `tts.py` の `synthesize()` に `style` オプション引数を追加
- 授業再生時に英語発音強調スタイルを適用

**変更対象**:
- `src/lesson_generator.py` — プロンプト確認・必要に応じて追加
- `src/tts.py` — `style` 引数追加
- `src/speech_pipeline.py` — `style` パラメータ伝搬
- `src/lesson_runner.py` — 授業用TTSスタイル指定

---

## Phase 2: 高速プレビュー（v3のコア機能）

**目標**: 生成されたスクリプトを**TTS生成を待たずに**素早く確認できる仕組み。

### 2-1. セクション単体再生

管理画面のセクション一覧から、特定のセクションだけを即座に再生できるボタンを追加。

**API**: `POST /api/lessons/{lesson_id}/sections/{section_id}/play`
- 指定セクションのみをLessonRunnerで再生
- TTSキャッシュがあれば即座に再生、なければその場で生成
- 全体の授業を開始せず、単一セクションのみ

**LessonRunner変更**:
- `play_single(section_id)` メソッド追加
- 既存の `_play_section()` を流用
- 状態は `RUNNING` にせず、一時的な再生として扱う

**UI変更** (`static/js/admin/teacher.js`):
- 各セクション行に ▶ 再生ボタン追加
- 再生中はボタンがスピナーに変化
- 再生完了で元に戻る

### 2-2. セクション個別TTS生成

スクリプト生成時のTTS一括生成とは別に、個別セクションのTTSを生成/再生成できる。

**API**: `POST /api/lessons/{lesson_id}/sections/{section_id}/generate-tts`
- 指定セクションのTTSのみ生成（既存キャッシュは削除して再生成）
- レスポンスで生成状況を返す

**用途**: セクションのテキストを編集した後、そのセクションだけTTSを再生成して確認。

### 2-3. テキストプレビューモード

TTS音声なしで、テキストだけを順次表示して構成を確認するモード。

**API**: `POST /api/lessons/{lesson_id}/preview`
- 各セクションの `content` と `display_text` を一定間隔で配信画面に表示
- 音声なし、アバター動作なし
- 1セクション2〜3秒で自動進行（実際の授業の1/3〜1/5の速度）
- スキップ/次へ/前へ の操作が可能

**LessonRunner変更**:
- `preview_mode` フラグ追加
- `start(lesson_id, lang, preview=False)` — preview時はTTSスキップ
- `_play_section()` のpreview分岐: display_text表示 + 字幕表示のみ

**UI変更**:
- 「プレビュー」ボタン追加（授業開始ボタンの横）
- プレビュー中は簡易進捗バー表示

---

## Phase 3: ターゲット再生成

**目標**: 問題のあるセクションだけをピンポイントで再生成。全体を作り直す必要をなくす。

### 3-1. セクション個別再生成

特定セクションの `content` / `tts_text` / `display_text` をLLMで再生成する。

**API**: `POST /api/lessons/{lesson_id}/sections/{section_id}/regenerate`
- リクエストボディにオプションで `instruction`（追加指示）を含められる
  - 例: 「もっと短く」「英語の例文を増やして」「もっと面白く」
- 現在のセクション内容 + 前後セクションのコンテキスト + 教材テキストをLLMに渡す
- 該当セクションのTTSキャッシュを自動削除

**lesson_generator.py に追加**:
```python
def regenerate_section(
    lesson_name: str,
    extracted_text: str,
    current_section: dict,
    prev_section: dict | None,
    next_section: dict | None,
    instruction: str = "",
    student_config: dict | None = None,
) -> dict:
```

**プロンプト設計**:
- システム: 「授業の1セクションを改善してください」
- コンテキスト: 教材テキスト + 前後セクション + 現在のセクション
- 追加指示があればそれも含める
- 出力: 同じJSON形式で1セクション分のみ

**UI変更**:
- 各セクション行に 🔄 再生成ボタン追加
- クリック → テキストボックスで追加指示（任意、空でもOK）→ 実行
- 再生成中はローディング表示
- 完了後、セクション内容が更新される

### 3-2. プラン↔スクリプトの部分同期

プランを編集した後、変更されたセクションだけスクリプトを再生成する。

**判定ロジック**:
- プランの `title` / `summary` / `section_type` / `emotion` が変わったセクションを検出
- 変更セクションだけ `regenerate_section()` で再生成

**UI変更**:
- プラン編集後に「変更セクションを再生成」ボタン表示
- どのセクションが変更されたかハイライト表示

---

## Phase 4: 品質改善

### 4-1. 定型挨拶テンプレート

TV番組のように、授業の開始と終了に決まった形式の挨拶を入れる。

**仕組み**:
- DB設定 (`settings` テーブル) に `lesson.intro_template` / `lesson.outro_template` を保存
- デフォルトテンプレート例:
  - 導入: 「みなさんこんにちは！ちょビです！今日の授業は「{lesson_name}」！一緒に楽しく学んでいこう！」
  - 締め: 「というわけで今日の授業はここまで！楽しかったかな？次の授業もお楽しみに！ちょビでした、バイバーイ！」
- スクリプト生成時に、`introduction` の最初と `summary` の最後にテンプレートを挿入
- テンプレートはプロンプトに含めてLLMに自然に馴染ませる（丸ごと挿入ではなくLLMが調整）
- 管理画面でテンプレート編集可能

**変更対象**:
- `src/lesson_generator.py` — プロンプトにテンプレート情報を追加
- `scripts/routes/teacher.py` — テンプレートCRUD API
- `static/js/admin/teacher.js` — テンプレート編集UI（設定領域）

### 4-2. display_text読み上げオプション

授業パネルに表示されている英文などを、先生が「画面の内容を読みますね」と読み上げるオプション。

**方針**: プロンプト改善で対応（コード変更最小限）
- スクリプト生成プロンプトに「display_textに英文や例文を表示する場合、contentでもその内容を自然に読み上げること」を追加
- 「画面を見てください」ではなく「画面にも出しますが、読みますね」という導入を促す

**変更対象**:
- `src/lesson_generator.py` — プロンプト追加のみ

### 4-3. 構成品質のプロンプト改善

**問題**: 「全体の構成が悪いところがある」

**対策**: スクリプト生成プロンプトに構成品質ガイドラインを追加
- セクション間の繋がり（前セクションの内容を自然に受けて話す）
- 同じ表現の繰り返しを避ける
- 各セクションの長さのバランス（長すぎ/短すぎを防ぐ）
- display_textの情報量コントロール（多すぎない、少なすぎない）

**変更対象**:
- `src/lesson_generator.py` — プロンプト改善

---

## Phase 5: コンテンツパイプライン改善

### 5-1. URLテキスト抽出の改善

**問題**: 生HTMLをGeminiに丸投げしており、ノイズが多くトークンを浪費。

**対策** ([plans/teacher-mode-v2/01-url-text-extraction.md](teacher-mode-v2/01-url-text-extraction.md)):
- BeautifulSoup（requirements.txtに既存）でHTML前処理
- `<script>`, `<style>`, `<nav>`, `<footer>`, `<iframe>`, `<aside>` 等を除去
- `<article>`, `<main>`, `.entry-content` 等のセマンティック要素を優先抽出
- フォールバック: BeautifulSoup失敗時は従来のGemini直接抽出

**変更対象**:
- `src/lesson_generator.py` の `extract_text_from_url()` のみ

---

## 実装優先順序

```
Phase 1（クイックフィックス）
  ├─ 1-1. パネル表示修正          → すぐ直せる、視覚的効果大
  └─ 1-2. 英語発音改善            → プロンプト中心、効果検証しやすい

Phase 2（高速プレビュー）⭐ v3の核心
  ├─ 2-1. セクション単体再生      → 最も重要、これだけで検証速度が大幅向上
  ├─ 2-2. セクション個別TTS生成   → 2-1と組み合わせて即効性あり
  └─ 2-3. テキストプレビューモード → TTS待ちを完全に排除

Phase 3（ターゲット再生成）
  ├─ 3-1. セクション個別再生成    → 全体再生成の無駄を排除
  └─ 3-2. プラン↔スクリプト部分同期 → プラン調整後の再生成を効率化

Phase 4（品質改善）
  ├─ 4-1. 定型挨拶テンプレート    → プロンプト追加
  ├─ 4-2. display_text読み上げ    → プロンプト追加
  └─ 4-3. 構成品質プロンプト改善  → プロンプト追加

Phase 5（パイプライン改善）
  └─ 5-1. URL抽出改善            → 独立、いつでも実装可能
```

## リスク

| リスク | 対策 |
|--------|------|
| セクション個別再生成で前後の文脈が崩れる | 前後セクションをコンテキストとしてLLMに渡す |
| プレビューモードと通常再生の状態管理が複雑化 | LessonRunnerに `preview` フラグで分岐、状態遷移は共通 |
| プロンプト改善の効果が不安定 | Phase 2の高速検証基盤で素早くA/B確認できる |
| テンプレート挨拶が不自然になる | LLMにテンプレートを「参考」として渡し、自然に馴染ませる |

## 検証方法

各Phaseの完了時:
1. `python3 -m pytest tests/ -q` — 全テスト通過
2. Phase 1: 授業パネルが正常表示、英語TTS音声が改善
3. Phase 2: セクション▶ボタンで即再生、プレビューモードで全体確認
4. Phase 3: セクション🔄再生成でそのセクションだけ更新
5. Phase 4: 授業の導入/締めが安定した形式になる
6. Phase 5: URL入力からの抽出品質が向上
