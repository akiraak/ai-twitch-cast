# TODO

## 機能追加

### 教師モード改善
- [ ] 教師モード改善 v2 → [plans/teacher-mode-v2/](plans/teacher-mode-v2/README.md)
  - [ ] URLテキスト抽出改善 → [01-url-text-extraction.md](plans/teacher-mode-v2/01-url-text-extraction.md)
  - [ ] 授業テキストパネル書式対応 → [03-display-text-markdown.md](plans/teacher-mode-v2/03-display-text-markdown.md)
  - [ ] 授業中のチャット割り込み改善 → [04-chat-interruption.md](plans/teacher-mode-v2/04-chat-interruption.md)
  - [ ] 画面の左に授業中の全体の流れと現在どこをやってるかの表示を出してほしい
  - [ ] 説明文章の背景が真っ黒なので半透明に。でも文字は見やすいように
  - [ ] 全体の構成が悪いところがある。どうしたら改善できるか検討する

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
