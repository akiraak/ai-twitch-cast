# TODO

## 1. 教師モード
1.1. [ ] AIによるキャラクタープロンプト編集 → [plans/character-prompt-editor.md](plans/character-prompt-editor.md)
1.2. [ ] メインコンテンツ読み上げ方式改善: 手動テストで会話文コンテンツの先生・生徒役割分担を確認
1.5. [ ] スクリプト再生成時にLLM評価結果が上書きされる問題の対応
- [ ] 品質評価の数値が体感と違って高すぎる。80%が30%くらいにしか感じないので改善する
- [ ] メインコンテンツ読み上げ機能 Phase 2: 手動テストで読み上げ前に導入ターン（文脈説明・役割分担）が含まれることを確認
- [ ] アバターの体の向き設定＋自然な見回しモーション → [plans/avatar-body-angle-gaze.md](plans/avatar-body-angle-gaze.md)
  - [ ] Step 2: avatarスキーマに `bodyAngle` スライダー追加
  - [ ] Step 3: `_OVERLAY_DEFAULTS` に `bodyAngle` デフォルト値追加
  - [ ] Step 4: `AvatarInstance` にsetBodyAngle() + 見回しgaze system追加
  - [ ] Step 5: `applySettings()` でbodyAngle適用
  - [ ] Step 6: 設定パネルのスライダー即時反映

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
