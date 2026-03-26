# TODO

## テスト

- [ ] 授業モード v3 手動テスト → [plans/teacher-mode-v3-test.md](plans/teacher-mode-v3-test.md)
  - [ ] Phase 1: プラン生成の検証（director_sectionsの品質）
  - [ ] Phase 2: スクリプト生成 + TTS の検証
  - [ ] Phase 3: 管理画面 UI の検証（Step 7）
  - [ ] Phase 4: 授業再生の検証
  - [ ] Phase 5: 英語モード（オプション）

## 機能追加

### その他
- [ ] ブラウザテスト（Playwright）導入の検証 → [plans/playwright-browser-testing.md](plans/playwright-browser-testing.md)
  - [ ] Step 3: 授業モード ワークフローテスト（CRUD・プラン生成・管理画面UI）
  - [ ] Step 4: WebSocket / リアルタイムテスト（字幕・TODO更新・授業テキスト）

## バグ
- [ ] 配信中の音声ドロップ調査（音声キューdepth=100飽和、10秒ごとに+13〜30ドロップ）→ [plans/stream-buffering-fix.md](plans/stream-buffering-fix.md)

## 検討
- [ ] 遅延が大きく発生した場合にスキップしてでも最新の配信内容に追いつく機能の検証 → [plans/latency-skip-catchup.md](plans/latency-skip-catchup.md)
- [ ] キャプチャウィンドウの音を配信に自然に乗せれるかを検証 → [plans/capture-window-audio.md](plans/capture-window-audio.md)
- [ ] YouTube動画などFPSが高いウィンドウをキャプチャしてスムーズに配信できるかの検証 → [plans/high-fps-capture-verification.md](plans/high-fps-capture-verification.md)
- [ ] capture.pyのbroadcast_items全面移行（二重管理解消） → [plans/capture-broadcast-items-migration.md](plans/capture-broadcast-items-migration.md)
- [ ] SE（効果音）とコメント応答の連携検証（AIがSEカテゴリを正しく選択するか、再生タイミング・音量が適切か）
