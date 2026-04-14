# TODO

## 授業モード改善: 自動検査・改善ループ → [plans/auto-verify-improve-loop.md](plans/auto-verify-improve-loop.md)
- [ ] 自動検査・改善ループ実装（verify→improve×3回、上記の3軸判定を活用）
- [ ] `lesson_generate.md` に「各セクションの最初のdialogueで、display_textの内容を先生が読み上げる（または紹介する）こと」ルールを追加 → [plans/display-text-readout-rule.md](plans/display-text-readout-rule.md)

## 管理画面
- [ ] カテゴリごとに付けている良い/悪いの情報を管理画面で見れるようにする。そのセクションの会話など内容も保存し何が悪いのか分かりやすく確認できるようにする

## バグ
- [ ] 配信中の音声ドロップ調査（音声キューdepth=100飽和、10秒ごとに+13〜30ドロップ）→ [plans/stream-buffering-fix.md](plans/stream-buffering-fix.md)
- [ ] 授業モード: 手動テストで字幕サイズ・セリフ長を再確認（rulesが効いているか）
- [ ] 授業モード: TTS事前生成が単話者モード（part）にフォールバックし、対話モード（dlg）で生成されない。dialoguesにテキストがあるのにsection.content（短い要約）だけが読み上げられ、display_textの全文読み上げが行われない

## 検討
- [ ] 遅延が大きく発生した場合にスキップしてでも最新の配信内容に追いつく機能の検証 → [plans/latency-skip-catchup.md](plans/latency-skip-catchup.md)
- [ ] キャプチャウィンドウの音を配信に自然に乗せれるかを検証 → [plans/capture-window-audio.md](plans/capture-window-audio.md)
- [ ] YouTube動画などFPSが高いウィンドウをキャプチャしてスムーズに配信できるかの検証 → [plans/high-fps-capture-verification.md](plans/high-fps-capture-verification.md)
- [ ] capture.pyのbroadcast_items全面移行（二重管理解消） → [plans/capture-broadcast-items-migration.md](plans/capture-broadcast-items-migration.md)
- [ ] SE（効果音）とコメント応答の連携検証（AIがSEカテゴリを正しく選択するか、再生タイミング・音量が適切か）
