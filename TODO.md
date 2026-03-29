# TODO

## 1. 教師モード
1.1. [ ] AIによるキャラクタープロンプト編集 → [plans/character-prompt-editor.md](plans/character-prompt-editor.md)
1.2. [ ] メインコンテンツ読み上げ方式改善: 手動テストで会話文コンテンツの先生・生徒役割分担を確認
1.5. [ ] スクリプト再生成時にLLM評価結果が上書きされる問題の対応
- [ ] 品質評価た体感と違って高すぎる。80%が30%くらいにしか感じないので改善する
- [ ] メインコンテンツ階層化の手動テスト: 既存レッスンで再抽出→UIで★主要コンテンツの区別確認
- [x] メインコンテンツ読み上げ機能 Phase 1 → [plans/main-content-read-aloud.md](plans/main-content-read-aloud.md)
- [ ] メインコンテンツ読み上げ機能 Phase 2: 読み上げ導入の自然化 → [plans/main-content-read-aloud.md](plans/main-content-read-aloud.md)
  - [ ] Step 6: `_build_structure_prompt()` の読み上げ指示に導入パターン追加
  - [ ] Step 7: `_director_review()` に導入チェック観点追加
  - [ ] Step 8: テスト追加

## 2. 実装
- [ ] リファクタリング

## 3. バグ
3.1. [ ] 配信中の音声ドロップ調査（音声キューdepth=100飽和、10秒ごとに+13〜30ドロップ）→ [plans/stream-buffering-fix.md](plans/stream-buffering-fix.md)
3.2. [ ] 授業モード: 手動テストで字幕サイズ・セリフ長を再確認（rulesが効いているか）

## 4. 検討
4.1. [ ] 遅延が大きく発生した場合にスキップしてでも最新の配信内容に追いつく機能の検証 → [plans/latency-skip-catchup.md](plans/latency-skip-catchup.md)
4.2. [ ] キャプチャウィンドウの音を配信に自然に乗せれるかを検証 → [plans/capture-window-audio.md](plans/capture-window-audio.md)
4.3. [ ] YouTube動画などFPSが高いウィンドウをキャプチャしてスムーズに配信できるかの検証 → [plans/high-fps-capture-verification.md](plans/high-fps-capture-verification.md)
4.4. [ ] capture.pyのbroadcast_items全面移行（二重管理解消） → [plans/capture-broadcast-items-migration.md](plans/capture-broadcast-items-migration.md)
4.5. [ ] SE（効果音）とコメント応答の連携検証（AIがSEカテゴリを正しく選択するか、再生タイミング・音量が適切か）
