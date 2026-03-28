# TODO

## 機能追加

## 教師モード
- [ ] 監督レビュー（ダメ出し→再生成）+ display_text 読み上げ強化 → [plans/director-review-and-display-text-coverage.md](plans/director-review-and-display-text-coverage.md)

  - [ ] Step 2: display_text[:200] 切り詰め撤廃（全文をキャラクターAIに渡す）
  - [ ] Step 3: `_director_review()` 新設（Phase B-3: 監督レビュー）
  - [ ] Step 4: Phase B-4 再生成ロジック（不合格セクションのみ再生成）
  - [ ] Step 5: `generate_lesson_script_v2()` に Phase B-3/B-4 統合
  - [ ] Step 6: レビュー結果の保存・管理画面表示
  - [ ] Step 7: SSE 進捗表示更新
- [ ] バグ教師モードコンテンツを客観的に分析しイケてるコンテンツかAIで検証するモードの追加
- [ ] AIによるキャラクタープロンプト編集 → [plans/character-prompt-editor.md](plans/character-prompt-editor.md)
- [ ] セリフ生成時に display_text が200文字で切り詰められ、長いコンテンツの後半が欠落する問題（表示を分割する等の対策が必要）

## バグ
- [ ] 配信中の音声ドロップ調査（音声キューdepth=100飽和、10秒ごとに+13〜30ドロップ）→ [plans/stream-buffering-fix.md](plans/stream-buffering-fix.md)
- [ ] 授業モード: 手動テストで字幕サイズ・セリフ長を再確認（rulesが効いているか）

## 検討
- [ ] 遅延が大きく発生した場合にスキップしてでも最新の配信内容に追いつく機能の検証 → [plans/latency-skip-catchup.md](plans/latency-skip-catchup.md)
- [ ] キャプチャウィンドウの音を配信に自然に乗せれるかを検証 → [plans/capture-window-audio.md](plans/capture-window-audio.md)
- [ ] YouTube動画などFPSが高いウィンドウをキャプチャしてスムーズに配信できるかの検証 → [plans/high-fps-capture-verification.md](plans/high-fps-capture-verification.md)
- [ ] capture.pyのbroadcast_items全面移行（二重管理解消） → [plans/capture-broadcast-items-migration.md](plans/capture-broadcast-items-migration.md)
- [ ] SE（効果音）とコメント応答の連携検証（AIがSEカテゴリを正しく選択するか、再生タイミング・音量が適切か）
