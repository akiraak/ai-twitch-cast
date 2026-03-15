# TODO

## 機能追加

### Windowsアプリ
- [ ] 右クリックメニューからWeb UIで設定できる上も編集可能に。
        サーバからjsonなどで項目の情報を受け取ってそれに合わせて設定画面を表示するようにする
- [ ] 未配信中でも会話をアバターに送れるようにチャット欄を追加
- [ ] 表情や体の動きを入れる

### サーバ
- [ ] 表示が煩雑なので整理する
- [ ] 開発の読み上げのON/OFFをWEBUIに入れる
- [ ] あきらと他のユーザーに返すプロンプトを変える。あきらには英語多め。他の視聴者にはその人のコメントの言語をメインに。ちょっとだけ日本語入れる感じで
- [ ] 汎用的なGitリポジトリをベースにした開発配信機能を入れる。外部のリポジトリをcloneして、その操作を実況する
- [ ] 英語の読み上げが英語っぽくする 

### その他
- [ ] テストの充実
- [ ] リファクタリング
- [ ] 配信中に Electron で位置調整しても繁栄されない
- [ ] 画像保蔵機能と同様にElectron画面の動画撮影 → [plans/video-recording.md](plans/video-recording.md)
- [ ] Electronを別の実装に置き換えられるか検討（軽量化・柔軟な実装が行えるかの観点） → [plans/electron-alternative.md](plans/electron-alternative.md)
- [>] Electronをネイティブ実装に変更（C#+WebView2+WGC+WASAPI） → [plans/native-implementation.md](plans/native-implementation.md)
        - [>] Phase 7: UIパネル追加（配信領域+UIパネルの1ウィンドウ構成、WGCクロップ）
                - [ ] 音量スライダー: アプリで変更した音量がWeb UIに反映されない（サーバーAPIへのPOSTがタイムアウト）
                - [ ] トレイアイコン: 既存のトレイ機能（配信開始/停止/最小化）が引き続き動作する
                - [ ] Go Live API（WebSocket /ws/control経由）での配信開始が引き続き動作する
                - [ ] 配信後ウィンドウの×を押してもウィンドウが消えない
        - [ ] Phase 8: Electron完全削除（capture.pyのElectronコード・win-capture-app/・Web UI削除）
        - [ ] ネイティブアプリ起動時に旧Electronアプリ等のポート9090競合を検出・解決する仕組み
        - [ ] ネイティブアプリにffmpegが同梱されているか確認（現状はElectronダウンロード済みのものを流用）
        - [ ] broadcast.html, control-panel.htmlをサーバから受け取るメリットとデメリットの検討
        - [ ] ビュワーを×で閉じても一瞬間がある
