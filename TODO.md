# TODO

## 教師モード
- [ ] AIによるキャラクタープロンプト編集 → [plans/character-prompt-editor.md](plans/character-prompt-editor.md)
- [ ] 品質評価の数値が体感と違って高すぎる。80%が30%くらいにしか感じないので改善する
- [ ] 授業生成にGeminiとClaude CodeとあるけどClaude CodeのみにしてGemini生成の機能を削除する → [plans/remove-gemini-lesson-generation.md](plans/remove-gemini-lesson-generation.md)
  - [ ] Step 3: content_analyzer.py整理 — `analyze_content_full` + LLM関連削除
  - [ ] Step 4: teacher.py API整理 — generate-plan/generate-script削除、generatorデフォルト変更
  - [ ] Step 5: teacher.js整理 — Gemini UI削除、Claude Code固定、QAをgenerator非依存に
  - [ ] Step 6: テスト整理 — 不要テスト削除・修正
  - [ ] Step 7: クリーンアップ — 環境変数・conftest・CLAUDE.md更新
- [ ] Claude Codeでの生成の手順をまとめる。管理画面の授業生成のところで見えるようにする

## 実装

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