# TODO

## 機能追加

### Windowsアプリ
- [ ] 右クリックメニューからWeb UIで設定できる上も編集可能に。
        サーバからjsonなどで項目の情報を受け取ってそれに合わせて設定画面を表示するようにする
- [ ] 字幕の位置がおかしい。下端を決める。ウィンドウの中央は画面中央。高さは文章量によって可変。横幅も文章量によって可変だけど最大幅を指定して超えるなら複数行

### サーバ
- [ ] commentsテーブルのカラム名リネーム（message→trigger_text, response→speech等）。AI応答辞書・WS・API・テスト全体に波及するため要計画
- [ ] 開発の読み上げのON/OFFをWEBUIに入れる
- [ ] capture.pyのbroadcast_items全面移行（二重管理解消） → [plans/capture-broadcast-items-migration.md](plans/capture-broadcast-items-migration.md)

### その他
- [ ] ブラウザテスト（Playwright等）導入の検証
- [ ] キャラのコメント生成のセルフメモってなに？必要？
- [ ] Twitch配信情報の設定（タイトル）
- [ ] Twitch配信時に前のコメントを削除
