# TODO

## 教師モード
- [ ] AIによるキャラクタープロンプト編集 → [plans/character-prompt-editor.md](plans/character-prompt-editor.md)
- [ ] メインコンテンツ読み上げ方式改善: 手動テストで会話文コンテンツの先生・生徒役割分担を確認
- [ ] 授業の品質分析が入ったのでコンテンツ生成に反映させる
- [ ] セクションごとの会話のつながりが不自然なのを解決する
- [ ] 授業の品質分析をスクリプト生成の中に含める（2c） → [plans/quality-analysis-in-pipeline.md](plans/quality-analysis-in-pipeline.md)
  - [x] Step 1: Phase B-5追加（lesson_generator.py に analyze_content() 組み込み）
  - [ ] Step 2: 戻り値変更（list[dict] → dict with sections + analysis）
  - [ ] Step 3: teacher.py 呼び出し側更新（アンパック + 重複分析削除）
  - [ ] Step 4: テスト追加 + 全テスト通過確認
- [ ] スクリプト再生成時にLLM評価結果が上書きされる問題の対応

## 実装
- [ ] 管理画面からdocsファイルの内容を見れるようにする

## バグ
- [ ] 配信中の音声ドロップ調査（音声キューdepth=100飽和、10秒ごとに+13〜30ドロップ）→ [plans/stream-buffering-fix.md](plans/stream-buffering-fix.md)
- [ ] 授業モード: 手動テストで字幕サイズ・セリフ長を再確認（rulesが効いているか）

## 検討
- [ ] 遅延が大きく発生した場合にスキップしてでも最新の配信内容に追いつく機能の検証 → [plans/latency-skip-catchup.md](plans/latency-skip-catchup.md)
- [ ] キャプチャウィンドウの音を配信に自然に乗せれるかを検証 → [plans/capture-window-audio.md](plans/capture-window-audio.md)
- [ ] YouTube動画などFPSが高いウィンドウをキャプチャしてスムーズに配信できるかの検証 → [plans/high-fps-capture-verification.md](plans/high-fps-capture-verification.md)
- [ ] capture.pyのbroadcast_items全面移行（二重管理解消） → [plans/capture-broadcast-items-migration.md](plans/capture-broadcast-items-migration.md)
- [ ] SE（効果音）とコメント応答の連携検証（AIがSEカテゴリを正しく選択するか、再生タイミング・音量が適切か）
