# TODO

## 機能追加

### 教師モード改善
- [ ] 生徒役のキャラを入れる → [plans/student-character/](plans/student-character/README.md)
  - [ ] Step 2: WebSocketアバター制御 — avatar_idでリップシンク・感情を振り分け → [02-websocket-routing.md](plans/student-character/02-websocket-routing.md)
  - [ ] Step 3: TTS styleパラメータ — 話者ごとに異なる声・スタイルで発話 → [03-tts-style.md](plans/student-character/03-tts-style.md)
  - [ ] Step 4: DBスキーマ + 設定 — dialoguesカラム・生徒キャラ設定 → [04-db-schema.md](plans/student-character/04-db-schema.md)
  - [ ] Step 5: スクリプト生成の対話化 — LLMで先生と生徒の掛け合い生成 → [05-script-generation.md](plans/student-character/05-script-generation.md)
  - [ ] Step 6: レッスンランナーの対話再生 — dialoguesを話者別に順次再生 → [06-lesson-runner.md](plans/student-character/06-lesson-runner.md)
  - [ ] Step 7: 管理画面UI — 生徒設定・VRM選択・プレビュー色分け → [07-admin-ui.md](plans/student-character/07-admin-ui.md)
  - [ ] Step 8: テスト — ユニットテスト + 手動動作確認 → [08-testing.md](plans/student-character/08-testing.md)
- [ ] 全体の構成が悪いところがある。どうしたら改善できるか検討する
- [ ] 授業パネルの内容が大きすぎて表示がおかしいときがある。内容を適切な量に。多ければ文字を小さくなどちゃんと見えるような対策をする
- [ ] 英語授業なのに英語の発音が悪すぎる。改善したい
- [ ] 授業パネルの英文を読み上げた方が自然
- [ ] 授業モードで最初の挨拶と終わりの挨拶を定型的なものにしたい。TV番組でよくあるように最初と終わりが分かりやすいようにしたい

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
