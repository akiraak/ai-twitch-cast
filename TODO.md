# TODO

## 機能追加

### Windowsアプリ
- [ ] 右クリックメニューからWeb UIで設定できる上も編集可能に。
        サーバからjsonなどで項目の情報を受け取ってそれに合わせて設定画面を表示するようにする
- [ ] 未配信中でも会話をアバターに送れるようにチャット欄を追加
- [ ] 表情や体の動きを入れる
- [ ] アイテム共通化バグ修正 → [plans/item-commonization-bugfix.md](plans/item-commonization-bugfix.md)
        - [ ] Step 1: applyCommonStyleを直接適用に変更
        - [ ] Step 2: applySettings固有コードの重複削除
        - [ ] Step 3: WebUI構造全面刷新（details廃止、共通UI→固有UIの2段構成）
        - [ ] Step 4: バージョン表示トグルを共通化
        - [ ] Step 5: テスト更新 + 実機テスト
        - バグ
                - 背景の項目名の変更
                        - 色
                        - 透明度
                - 文字の項目名の変更
                        - サイズ
                        - 色
                        - 縁取りサイズ

### サーバ
- [ ] 各ウィンドウの表示のON/OFF
- [ ] 表示が煩雑なので整理する
- [ ] 開発の読み上げのON/OFFをWEBUIに入れる
- [ ] capture.pyのbroadcast_items全面移行（二重管理解消） → [plans/capture-broadcast-items-migration.md](plans/capture-broadcast-items-migration.md)
### その他
- [ ] ブラウザテスト（Playwright等）導入の検証
