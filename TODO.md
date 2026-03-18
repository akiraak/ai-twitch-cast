# TODO

## 機能追加

### Windowsアプリ
- [ ] 右クリックメニューからWeb UIで設定できる上も編集可能に。
        サーバからjsonなどで項目の情報を受け取ってそれに合わせて設定画面を表示するようにする
- [ ] 未配信中でも会話をアバターに送れるようにチャット欄を追加
- [ ] 表情や体の動きを入れる
- [ ] プレビューアプリの各アイテムの共通化と機能追加 → [plans/item-commonization.md](plans/item-commonization.md)
        - [x] Phase 1: 共通プロパティのDB保存基盤
        - [x] Phase 2: broadcast.html JS共通化
        - [x] Phase 5: 保存漏れバグ修正 + 全アイテムvisible対応 + プレビュー→WebUIリアルタイム反映
        - [x] Phase 4: Web UI設定パネル
        - [x] Phase 3: CSS統一
        - [x] Phase 6: broadcast_itemsテーブル作成 + 固定アイテム移行
        - [x] Phase 7: 動的アイテム移行（custom_texts → broadcast_items書き換え、capture_windowsデータ移行）
        共通プロパティ:
                表示: ON/OFF
                配置: XY座標、WHサイズ, Z値
                背景: 色、透明度, 角丸、ふち枠の有無と色とサイズと透明度
                文字: テキスト、色、サイズ、ふち枠の色とサイズと透明度, パディングサイズ

### サーバ
- [ ] 各ウィンドウの表示のON/OFF
- [ ] 表示が煩雑なので整理する
- [ ] 開発の読み上げのON/OFFをWEBUIに入れる
- [ ] capture_windowsテーブルとcapture.sources設定の二重管理を解消する（Phase 7で対応予定）
### その他
- [ ] ブラウザテスト（Playwright等）導入の検証
