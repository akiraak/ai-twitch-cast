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

- テキストパネルWebUI
        - テキストパネルの背景を赤に設定してたのに設定は黒になっている。表示は赤で正しかった
        - TODOパネルで背景透明度を変更したら文字のサイズが変わった



- [ ] テキストパネルで使える変数{version}のヘルプをどこかに表示してほしい
- [ ] テキストパネルで上下も左右も文字を中央寄せにしたい
- [ ] テキストパネルで文字のフォントを変えたい
- [ ] テキストパネルに子のパネルを追加できるようにする
        パネルは入れ子構造にします。複数の子パネルを追加できます。
        子パネルは固有の情報として親パネルからの相対のXY座標をもちます。

### サーバ
- [ ] 各ウィンドウの表示のON/OFF
- [ ] 表示が煩雑なので整理する
- [ ] 開発の読み上げのON/OFFをWEBUIに入れる
- [ ] capture.pyのbroadcast_items全面移行（二重管理解消） → [plans/capture-broadcast-items-migration.md](plans/capture-broadcast-items-migration.md)
- [ ] WebUI 右上の「配信開始」「配信停止」を削除「再起動」は機能を調査してから不要なら削除
### その他
- [ ] ブラウザテスト（Playwright等）導入の検証
