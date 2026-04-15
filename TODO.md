# TODO

## 授業モード改善
- [ ] カテゴリ別学習の調査と修正
- [ ] 自動検査・改善ループ実装（verify→improve×3回、上記の3軸判定を活用）→ [plans/auto-verify-improve-loop.md](plans/auto-verify-improve-loop.md)
- [ ] セクション開始の長い読み上げなど、キャラのセリフ欄が大きすぎてdisplayコンテンツに被ってしまうのの対策 → [plans/subtitle-overflow-fix.md](plans/subtitle-overflow-fix.md)
  - [ ] 案A: 字幕パネルにCSS max-height制限を追加

## バグ
- [ ] 対話モード長文TTS切り詰め: `_play_dialogues` で長文を分割せず1回のTTSに投げるため末尾が無音になる → [plans/dialogue-tts-split.md](plans/dialogue-tts-split.md)
- [ ] 配信中の音声ドロップ調査（音声キューdepth=100飽和、10秒ごとに+13〜30ドロップ）→ [plans/stream-buffering-fix.md](plans/stream-buffering-fix.md)
- [ ] 授業モード: 手動テストで字幕サイズ・セリフ長を再確認（rulesが効いているか）

## 検討
- [ ] 遅延が大きく発生した場合にスキップしてでも最新の配信内容に追いつく機能の検証 → [plans/latency-skip-catchup.md](plans/latency-skip-catchup.md)
- [ ] キャプチャウィンドウの音を配信に自然に乗せれるかを検証 → [plans/capture-window-audio.md](plans/capture-window-audio.md)
- [ ] YouTube動画などFPSが高いウィンドウをキャプチャしてスムーズに配信できるかの検証 → [plans/high-fps-capture-verification.md](plans/high-fps-capture-verification.md)
- [ ] capture.pyのbroadcast_items全面移行（二重管理解消） → [plans/capture-broadcast-items-migration.md](plans/capture-broadcast-items-migration.md)
- [ ] SE（効果音）とコメント応答の連携検証（AIがSEカテゴリを正しく選択するか、再生タイミング・音量が適切か）
