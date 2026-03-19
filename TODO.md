# TODO

## 機能追加

### Windowsアプリ
- [ ] 右クリックメニューからWeb UIで設定できる上も編集可能に。
        サーバからjsonなどで項目の情報を受け取ってそれに合わせて設定画面を表示するようにする
- [ ] アプリを再起動しても配信が続いたままにしたい
- [ ] 字幕パネルの位置が中央にならない

### サーバ
- [ ] 表示が煩雑なので整理する
- [ ] 開発の読み上げのON/OFFをWEBUIに入れる
- [ ] capture.pyのbroadcast_items全面移行（二重管理解消） → [plans/capture-broadcast-items-migration.md](plans/capture-broadcast-items-migration.md)
- [ ] ちょびの発言をチャット欄に表示するかのスイッチをWebUIに入れたい

### その他
- [ ] トピックについて話すモードを運用してみる → [plans/topic-operation.md](plans/topic-operation.md)
- [ ] ブラウザテスト（Playwright等）導入の検証
- [ ] 夜になると配信が止まる（原因: PCスリープ → Windows電源設定で「スリープしない」に変更が必要）
