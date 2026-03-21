# TODO

## 機能追加

### その他
- [>] 画像/URLで授業モード（教材画像やURLから自動授業） → [plans/english-teacher-mode.md](plans/english-teacher-mode.md)
  - [ ] ベース1: コンテンツソース抽象化（analyze_images/analyze_url → コンテキストテキスト）
  - [ ] ベース2: トピックへのコンテキスト/画像紐付け（image_paths/context追加、コメント応答連携）
  - [ ] ベース3: 配信画面のトピック画像/情報表示（#topic-panel拡張、image_indexで切り替え）
  - [ ] ベース4: 教材ファイルアップロード（files.pyにteachingカテゴリ追加）
  - [ ] 拡張5: 授業スクリプト生成（コンテキスト→ステップ+image_index形式のスクリプト生成）
  - [ ] 拡張6: WebUI操作（画像/URL入力、授業開始/終了ボタン）
  - [ ] 共通7: テスト
- [ ] ブラウザテスト（Playwright等）導入の検証

## バグ
- [ ] 配信バッファリング改善の効果検証（Phase 4: ネットワーク耐性は効果を見て判断） → [plans/stream-buffering-fix.md](plans/stream-buffering-fix.md)

## 検討
- [ ] 遅延が大きく発生した場合にスキップしてでも最新の配信内容に追いつく機能の検証 → [plans/latency-skip-catchup.md](plans/latency-skip-catchup.md)
- [ ] キャプチャウィンドウの音を配信に自然に乗せれるかを検証 → [plans/capture-window-audio.md](plans/capture-window-audio.md)
- [ ] YouTube動画などFPSが高いウィンドウをキャプチャしてスムーズに配信できるかの検証 → [plans/high-fps-capture-verification.md](plans/high-fps-capture-verification.md)
- [ ] capture.pyのbroadcast_items全面移行（二重管理解消） → [plans/capture-broadcast-items-migration.md](plans/capture-broadcast-items-migration.md)
- [ ] SE（効果音）とコメント応答の連携検証（AIがSEカテゴリを正しく選択するか、再生タイミング・音量が適切か）
