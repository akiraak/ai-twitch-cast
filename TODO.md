# TODO

## 機能追加

### 教師モード改善
- [ ] 全体の構成が悪いところがある。どうしたら改善できるか検討する
- [ ] 授業パネルの内容が大きすぎて表示がおかしいときがある。内容を適切な量に。多ければ文字を小さくなどちゃんと見えるような対策をする
- [ ] 英語授業なのに英語の発音が悪すぎる。改善したい
- [ ] 授業パネルの英文を読み上げた方が自然
- [ ] 授業モードで最初の挨拶と終わりの挨拶を定型的なものにしたい。TV番組でよくあるように最初と終わりが分かりやすいようにしたい
- [ ] 管理画面の配信画面の項目名を変更
        アバター（ちょび）->アバター（メイン）
        アバター（まなび）->アバター（サブ）
        字幕（先生）->字幕（メイン）
        字幕（生徒）->字幕（サブ）
- [ ] キャラの位置を左に先生で右に生徒に変更

### その他
- [ ] ブラウザテスト（Playwright等）導入の検証
- [ ] 生徒キャラも先生キャラと同様のテキスト生成のフローを持つ。ペルソナやセルフメモや視聴者メモなど。他に必要なものがあればそれも含める

## バグ
- [ ] 配信中の音声ドロップ調査（音声キューdepth=100飽和、10秒ごとに+13〜30ドロップ）→ [plans/stream-buffering-fix.md](plans/stream-buffering-fix.md)

## 検討
- [ ] 遅延が大きく発生した場合にスキップしてでも最新の配信内容に追いつく機能の検証 → [plans/latency-skip-catchup.md](plans/latency-skip-catchup.md)
- [ ] キャプチャウィンドウの音を配信に自然に乗せれるかを検証 → [plans/capture-window-audio.md](plans/capture-window-audio.md)
- [ ] YouTube動画などFPSが高いウィンドウをキャプチャしてスムーズに配信できるかの検証 → [plans/high-fps-capture-verification.md](plans/high-fps-capture-verification.md)
- [ ] capture.pyのbroadcast_items全面移行（二重管理解消） → [plans/capture-broadcast-items-migration.md](plans/capture-broadcast-items-migration.md)
- [ ] SE（効果音）とコメント応答の連携検証（AIがSEカテゴリを正しく選択するか、再生タイミング・音量が適切か）
