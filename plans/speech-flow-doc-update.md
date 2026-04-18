# `docs/speech-generation-flow.md` を最新実装に更新 + フローチャート追加

## ステータス: 未着手

## 背景

`docs/speech-generation-flow.md` は「キャラクター発話生成フロー」の正本として、コードを触る前に必ず参照すべきドキュメントと `CLAUDE.md` に明記されている。しかし実装が先行し、以下のドリフトが発生している:

- マルチキャラ掛け合いの **並列TTS事前生成**（commit `ab1c693` / `e2fc012`）が旧フロー（直列）のまま
- **授業モード**が「Claude Code手動生成」のみ前提だが、`src/lesson_generator/`（improver / extractor / utils）でLLM駆動の改善・評価パイプラインが実装済み
- **授業キャッシュパス**がバージョニング導入前（`{lesson_id}/{lang}/` のまま、実際は `{lesson_id}/{lang}/{generator}/v{version}/`）
- **`claude_watcher.py`**（Claude Code作業実況＝二人実況）がドキュメントで未言及
- **`character_manager.py`** への分離（キャラDB操作・キャッシュ・初期化の責務分割）が未反映
- **共通パイプライン**の `_wait_tts_complete()` ポーリング（`speech_pipeline.py:224,246-265`）が図に出ていない。push通知化の改善プラン（`plans/tts-wait-excess-delay.md`）は別管理なのでここでは現状のポーリング挙動をそのまま記述する
- **環境変数表**に `TTS_VOICE` / `TTS_STYLE` デフォルト（`tts.py:115,131`）が未記載
- 視覚的にフローを追えるチャートがなく、テキストだけで読みづらい
- **管理画面のDocsタブがMermaid非対応**。`static/js/admin/markdown.js` の `simpleMarkdownToHtml()` は独自実装で、コードブロック / テーブル / リスト / 見出し / admonition のみ対応。`` ```mermaid `` を書いても素のコードブロックとしてソースが表示されるだけで図にならない。`speech-generation-flow.md` はCLAUDE.mdで「コードを触る前に必ず参照」と指定された重要ドキュメントなので、管理画面でもフローチャートが見える必要がある

## 目的

1. ドキュメントの記述を現行コードと一致させる（呼び出し箇所・引数・キャッシュパス・パイプライン内部ステップ）
2. 追加されたサブシステム（`claude_watcher`、`character_manager`、`lesson_generator`）を適切な位置に組み込む
3. Mermaidフローチャートを追加して、テキスト記述では読み取りづらい分岐・並列化・時系列をビジュアルで示す
4. **管理画面のDocsタブでもMermaidをレンダリングできるようにする**（MkDocs側だけでなく `static/js/admin/markdown.js` でも図として描画）
5. フローチャートは**指示書の冒頭近く（目次直後の「全体像」セクション）**に配置し、読者がまず全体像を視覚で掴んでから各モードの詳細に進めるようにする

## 方針

- **書き直しではなく差分更新**。既存構成（モード別フロー + 共通パイプライン + 反映度表 + 環境変数表）を保持し、ずれている部分のみ修正する
- **コードを正とする**。doc とコードがぶつかった場合は必ず `rg` で実装を確認してから書く
- **Mermaidを採用**。MkDocs material はデフォルトで Mermaid をサポートしている（`mkdocs.yml` の `markdown_extensions` 確認必要、必要なら追加）
- **改善プランとの線引き**: `tts-wait-excess-delay.md`（ポーリング→push化）は未実装なので、現状フローをそのまま書き、末尾に「今後の改善: `plans/tts-wait-excess-delay.md`」の一文リンクで触れる

## 実装ステップ

### Step 1: 環境整備（Mermaid対応確認・追加）

**1-a. MkDocs側**
- `mkdocs.yml` の `markdown_extensions` に `pymdownx.superfences` + `mermaid2` またはカスタムフェンスが入っているか確認
- 未対応なら設定追加（`pymdownx.superfences` の `custom_fences` で `name: mermaid` → `class: mermaid` → `format: !!python/name:pymdownx.superfences.fence_code_format`）

**1-b. 管理画面側（Docsタブ）**
- `static/js/admin/markdown.js` の `simpleMarkdownToHtml()` を拡張して `` ```mermaid `` フェンスを `<div class="mermaid">...</div>` として出力する
- `static/index.html` で Mermaid CDN（`https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js`）を読み込む（またはローカルバンドル）
- ドキュメント読み込み後に `mermaid.run({ querySelector: '.doc-modal-body .mermaid, #docs-content .mermaid' })` を呼んで描画
- `showCharacterPromptDoc()` と `selectDocFile()` の両方で動作することを確認
- 他のドキュメントでも再利用できるよう、Mermaid描画は markdown.js 側で完結させる（docs.js から呼ぶだけで済むように）

### Step 2: モード別フローの更新

以下をコードと照合して書き直す:

1. **コメント応答**
   - `_respond()` の segment queue / `_speak_segment()` / キャンセル処理を明記
   - 並列TTS事前生成を図示（先頭 await → 再生中に後続生成完了）
   - `comment_reader.py:223-330` を参照点として示す

2. **授業モード**
   - 「Claude Code手動生成」だけでなく、`lesson_generator/` によるLLM駆動の改善・評価・プロンプトdiff適用フローを追加
   - `teacher.py` が import している関数群（`improve_sections`, `evaluate_lesson_quality`, `analyze_learnings`, `evaluate_category_fit`, `determine_targets`, `improve_prompt`, `apply_prompt_diff`）を整理して記述
   - キャッシュパスを `resources/audio/lessons/{lesson_id}/{lang}/{generator}/v{version}/` に修正（`lesson_runner.py:36-75` 参照）
   - `tts_pregenerate.py` の責務（授業再生前の一括事前生成）を明記し、「再生中の並行生成」との誤解を解く

3. **イベント応答**
   - `speak_event()` の新引数 `style`, `avatar_id`, `multi` を追記
   - SE解決の経路（`se_resolver.py` 経由、`comment_reader.py:310-316`）を追加

4. **直接発話 API**
   - シグネチャ変更なしを確認のうえ、呼び出し先が `speak_event(multi=True)` である旨を明記

5. **Claude Code作業実況（新セクション）**
   - `claude_watcher.py` の役割（transcript解析 → 二人実況会話生成 → 並列TTS → 再生）
   - コメント応答との割り込み関係（既存の segment queue と共有しているかを確認して書く）

### Step 3: 共通再生パイプラインの更新

- `_wait_tts_complete()` の現状ポーリング（`max_extra = duration * 0.5`）を図に追加
- `send_se_to_native_app` → SE長+0.3秒待機 → TTS送信の順序を正確に
- 並列TTS事前生成セクション（既存の 354-365 行周辺）はそのまま活用しつつ、`claude_watcher._play_conversation()` の位置づけを明示
- `character_manager.py` への分離は「キャラ情報の取得元」として共通パイプラインの前段に短く言及

### Step 4: フローチャート追加（Mermaid）

**配置方針**: メインのフローチャート（全体像）は**指示書の冒頭近く（目次直後の「全体像」セクション）**に置く。読者が詳細テキストを読む前に全体の流れを視覚で把握できるようにする。他のチャートは該当セクション内に配置。

挿入位置と内容:

1. **全体像（冒頭 "全体像" セクションの差し替え）— 最優先配置**
   - 4つの入力ソース → 4モード → テキスト生成 → TTS生成 → 共通パイプライン
   - ASCII art を Mermaid `flowchart TB` に置き換え
   - ドキュメント冒頭（タイトル＋目次の直後）に配置して、最初に目に入るようにする

2. **コメント応答: 並列TTSのタイムライン**
   - `sequenceDiagram` で LLM生成 → tts_task[0..N] 起動 → [0] await+speak 中に [1..N] 生成完了 → [1] speak → ... を可視化

3. **授業モード: 生成→インポート→事前TTS→再生の4ステージ**
   - `flowchart LR` で 教材抽出 → スクリプト生成（Claude Code / LLM improver）→ JSONインポート → TTS事前生成 → LessonRunner再生

4. **共通再生パイプライン: speak() 内部ステップ**
   - `flowchart TB` で SE → TTS生成（or cached）→ 素材準備（並行）→ C#送信 / 字幕 / リップシンク → ポーリング完了待ち → 停止イベント → クリーンアップ
   - 並行ブランチは `subgraph` で表現

### Step 5: 環境変数表の更新

- `TTS_VOICE`, `TTS_STYLE`（`tts.py` デフォルト値提供用）を追記
- `GEMINI_VISION_MODEL` 等が実在するかコードで再確認してから足す（いま grep では見つからない）

### Step 6: 反映度まとめ表の見直し

- 「授業スクリプト」行の注釈を「Claude Code生成 + lesson_generator改善」に更新
- Claude Code作業実況を追加行として入れるか検討

### Step 7: 校正・動作確認

- `rg` で doc 内の関数名・ファイル名が実在するかをチェック
- MkDocs ローカルビルドで Mermaid がレンダリングされることを確認（もしくはGitHub Actionsのプレビュー）
- **管理画面Docsタブで `speech-generation-flow.md` を開き、Mermaid図が描画されることを目視確認**（素のコードブロックとして出ていないこと）
- `showCharacterPromptDoc()` 経由のモーダルでもMermaidが描画されることを確認
- コミット前に `CLAUDE.md` のリグレッション防止チェック（テスト / サーバー起動）を実施

## リスク・留意点

- **管理画面のMermaid対応はコード改変を含む**。`markdown.js` の拡張とMermaid CDN読み込みが入るため、他のDocs表示（plans/ 配下全般、character-prompt モーダル）のレンダリングに影響しないことを確認する
- **Mermaid CDN読み込みのコスト**: 管理画面初回ロード時にCDNアクセスが発生する。オフライン環境では図が出ないが、素のコードブロックとしてはフォールバック表示される想定（要確認）
- **ドキュメント更新部分はコード改変なし**なので実装リグレッションのリスクは低い。ただし「コードの動きをdocに書く」際に誤読すると嘘が残るため、書く前に必ず当該ファイルを `Read` で確認する
- **MkDocsビルド失敗**は `mkdocs build` で事前検知する。未サポートなら設定追加が先
- **`tts-wait-excess-delay.md` との整合**: 現状ポーリング実装と改善プランの両方が doc に存在すると混乱する。現状だけ書き、末尾に改善プランへのリンクを置く
- **スコープ肥大化防止**: 「ついでに別機能のdocを直す」は別プラン。本プランは `speech-generation-flow.md` のみを扱う（ただしMermaid対応の `markdown.js` 拡張は全Docsに波及する共通基盤として許容）

## 完了条件

- [ ] `docs/speech-generation-flow.md` の全セクションが現行コードと一致している（引数・ファイルパス・ステップ）
- [ ] Mermaidフローチャートが4箇所に挿入され、MkDocsでレンダリングされる
- [ ] **全体像チャートがドキュメント冒頭（目次直後）に配置されている**
- [ ] **管理画面のDocsタブで `speech-generation-flow.md` を開くとMermaidが図として描画される**（素のコードブロックとして出ていない）
- [ ] `static/js/admin/markdown.js` のMermaid対応が他のDocs表示（character-prompt モーダル含む）を壊していない
- [ ] `claude_watcher` / `character_manager` / `lesson_generator` のそれぞれが適切な位置で言及されている
- [ ] 環境変数表が現行コードの参照と一致
- [ ] DONE.md に記録、本プランを「完了」に更新

## 参考

- 現行doc: `docs/speech-generation-flow.md`
- 関連改善プラン: `plans/tts-wait-excess-delay.md`（未着手）
- 関連コミット: `ab1c693` 並列TTS事前生成、`e2fc012` 診断ログ
