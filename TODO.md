# TODO

## 教師モード
- [ ] AIによるキャラクタープロンプト編集 → [plans/character-prompt-editor.md](plans/character-prompt-editor.md)
- [ ] スクリプト再生成時にLLM評価結果が上書きされる問題の対応
- [ ] 品質評価の数値が体感と違って高すぎる。80%が30%くらいにしか感じないので改善する
- [ ] 教材やセリフの生成をGeminiとClaude Codeで選択可能にする → [plans/claude-code-lesson-generator.md](plans/claude-code-lesson-generator.md)
  - [ ] Step 1: DBマイグレーション — `generator` カラム追加
  - [ ] Step 2: `prompts/lesson_generate.md` ワークフロー定義
  - [ ] Step 3: APIエンドポイント追加・修正（import-sections API + 既存API修正）
  - [ ] Step 4: LessonRunner修正（generator パラメータ + キャッシュパス）
  - [ ] Step 5: フロントエンド変更（ジェネレータタブ・インポートUI・再生時generator指定）

## 実装
- [ ] リファクタリング → [plans/refactoring-2026-03-30.md](plans/refactoring-2026-03-30.md)
  - Phase 1: ✅ lesson_generator.py の分割完了（→ 8ファイルのパッケージ）
  - Phase 2: ✅ db.py の分割完了（→ 4ファイルのパッケージ）
  - Phase 3: ✅ ai_responder.py のキャラクター管理分離完了（→ character_manager.py）
  - Phase 4: ✅ overlay.py の TODO 操作ロジック抽出完了（→ todo_service.py）
  - [ ] Phase 5: 未使用 import の削除
    - [ ] `scripts/routes/teacher.py` の `LESSON_AUDIO_DIR` 削除

## バグ
- [ ] 配信中の音声ドロップ調査（音声キューdepth=100飽和、10秒ごとに+13〜30ドロップ）→ [plans/stream-buffering-fix.md](plans/stream-buffering-fix.md)
- [ ] 授業モード: 手動テストで字幕サイズ・セリフ長を再確認（rulesが効いているか）

## 検討
- [ ] 遅延が大きく発生した場合にスキップしてでも最新の配信内容に追いつく機能の検証 → [plans/latency-skip-catchup.md](plans/latency-skip-catchup.md)
- [ ] キャプチャウィンドウの音を配信に自然に乗せれるかを検証 → [plans/capture-window-audio.md](plans/capture-window-audio.md)
- [ ] YouTube動画などFPSが高いウィンドウをキャプチャしてスムーズに配信できるかの検証 → [plans/high-fps-capture-verification.md](plans/high-fps-capture-verification.md)
- [ ] capture.pyのbroadcast_items全面移行（二重管理解消） → [plans/capture-broadcast-items-migration.md](plans/capture-broadcast-items-migration.md)
- [ ] SE（効果音）とコメント応答の連携検証（AIがSEカテゴリを正しく選択するか、再生タイミング・音量が適切か）
/