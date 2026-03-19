# TODO

## 機能追加

### Windowsアプリ
- [ ] 右クリックメニューからWeb UIで設定できる上も編集可能に。
        サーバからjsonなどで項目の情報を受け取ってそれに合わせて設定画面を表示するようにする
- [ ] アプリを再起動しても配信が続いたままにしたい

### サーバ
- [ ] 表示が煩雑なので整理する
- [ ] 開発の読み上げのON/OFFをWEBUIに入れる
- [ ] capture.pyのbroadcast_items全面移行（二重管理解消） → [plans/capture-broadcast-items-migration.md](plans/capture-broadcast-items-migration.md)
- [ ] ちょびの発言をチャット欄に表示するかのスイッチをWebUIに入れたい

### その他
- [ ] ちょびの返信を改善する → [plans/improve-ai-responses.md](plans/improve-ai-responses.md)
  - [x] Phase 1: プロンプト改善（A:キャラ設定 / B:感情矯正 / C:応答ルール / F:GM対応）
  - [x] Phase 2: D:ペルソナ自動抽出 / G:temperature / E:履歴強化 / H:イベント応答バリエーション
  - [ ] Phase 3: I:ユーザーメモ品質 / J:感情種類追加
- [ ] トピックについて話すモードを運用してみる → [plans/topic-operation.md](plans/topic-operation.md)
- [ ] ブラウザテスト（Playwright等）導入の検証
- [ ] ちょびのバージョンを上げるルールを作る
- [ ] Claude Code へ話かけて返信することへちょびが反応をする
