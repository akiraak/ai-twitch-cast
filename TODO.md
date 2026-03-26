# TODO

## 機能追加

### 授業モード v3 → [plans/teacher-mode-v3.md](plans/teacher-mode-v3.md)
- [ ] Phase 0: 現状確認（既存の仕組みで短い授業を生成・再生して問題を洗い出す）
- [ ] Phase 1: クイックフィックス（パネル表示修正、英語発音改善）
- [ ] Phase 2: 高速プレビュー（セクション単体再生、個別TTS生成、テキストプレビュー）
- [ ] Phase 3: ターゲット再生成（セクション個別再生成、プラン↔スクリプト部分同期）
- [ ] Phase 4: 品質改善（定型挨拶テンプレート、display_text読み上げ、構成プロンプト改善）
- [ ] Phase 5: コンテンツパイプライン改善（URL抽出改善）

### キャラクター発話生成フロー設計ドキュメント
- [ ] 全モード（授業・雑談・イベント等）を横断したキャラクター発話生成フローの定義ドキュメントを作成 → [docs/speech-generation-flow.md](docs/speech-generation-flow.md)

### その他
- [ ] ブラウザテスト（Playwright等）導入の検証

## バグ
- [ ] 配信中の音声ドロップ調査（音声キューdepth=100飽和、10秒ごとに+13〜30ドロップ）→ [plans/stream-buffering-fix.md](plans/stream-buffering-fix.md)

## 検討
- [ ] 遅延が大きく発生した場合にスキップしてでも最新の配信内容に追いつく機能の検証 → [plans/latency-skip-catchup.md](plans/latency-skip-catchup.md)
- [ ] キャプチャウィンドウの音を配信に自然に乗せれるかを検証 → [plans/capture-window-audio.md](plans/capture-window-audio.md)
- [ ] YouTube動画などFPSが高いウィンドウをキャプチャしてスムーズに配信できるかの検証 → [plans/high-fps-capture-verification.md](plans/high-fps-capture-verification.md)
- [ ] capture.pyのbroadcast_items全面移行（二重管理解消） → [plans/capture-broadcast-items-migration.md](plans/capture-broadcast-items-migration.md)
- [ ] SE（効果音）とコメント応答の連携検証（AIがSEカテゴリを正しく選択するか、再生タイミング・音量が適切か）
