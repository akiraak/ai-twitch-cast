# TODO

## 実装
- [ ] 授業コンテンツのバージョニング機能 → [plans/lesson-versioning.md](plans/lesson-versioning.md)
  - [ ] Step 2: API実装（バージョンCRUD, カテゴリCRUD, 注釈API, 既存APIのversion対応, APIテスト）
  - [ ] Step 3: 検証&部分改善API（元教材整合性チェック, source_version指定の部分再生成, 学習結果注入, プロンプト作成）
  - [ ] Step 4: 授業横断の学習ループAPI（カテゴリ別パターン分析, 学習結果書き出し, プロンプト改善diff生成+承認）
  - [ ] Step 5: 授業再生エンジン対応（version_numberパラメータ, TTSキャッシュパス変更, 旧互換）
  - [ ] Step 6: UI実装（バージョン管理, 注釈◎/✕, 検証結果, 改善元選択+部分再生成, 差分比較, 学習ダッシュボード, プロンプト改善承認UI）
  - [ ] Step 7: テスト&動作確認（全テスト通過, カテゴリ→注釈→検証→改善→学習分析→プロンプト改善の手動テスト）

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