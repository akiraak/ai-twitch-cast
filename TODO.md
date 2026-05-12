# TODO

## 授業モード
- [ ] speech-generation-flow.md を最新実装に更新とフローチャートの追加 → [plans/speech-flow-doc-update.md](plans/speech-flow-doc-update.md)
- [ ] C#画面のセクション進捗パネルが動いていない
- [ ] 授業生成の授業内容とセリフのチェックと再生成を入れる
- [ ] 管理画面から授業を再生した後にクライアントのLessonタブで開始されたことやデータ転送の進捗を確認したい

## その他
- [ ] クライアントアプリ再起動しても前に受信していた授業を再生できるようにする
- [ ] 管理画面から授業再生したあとに停止ボタンを削除。サーバからは送り付けるだけでクライアントの状態を確認する必要がないように
- [>] クライアント画面の文字をもっと綺麗に表示できないか（Step 2 完了 / 次は Step 3） → [plans/client-text-rendering-improvement.md](plans/client-text-rendering-improvement.md)
  - [ ] **Step 3**: 強すぎる text-shadow / 紫グローを軽減（subtitle の `0 0 1vw rgba(124,77,255,...)` と lesson-title の `0 0 8px` を弱める）
  - [ ] **Step 4**: 小サイズ要素（todo-section 0.83vw / lp-title-count 0.85vw / lesson-progress-item 0.95vw / child-panel 0.8vw）を底上げ、中サイズの太字を 700→600 / 600→500 に下げて滲み軽減
  - [ ] **Step 5**: 高解像度レンダリング→ダウンサンプリング (SSAA) を検討（WebView2 を 2560×1440 でレンダリング → FFmpeg で `scale=1280:720:lanczos`。本命策・要負荷実測）
  - [ ] **Step 6**: 効果確認とロールバック判断（before/after スクショ比較）
- [>] 録画の別アプローチ：画面キャプチャ＋WASAPI Loopback で AV 同期を OS 任せにする（Step 4 前半完了：subprocess 経路に着地） → [plans/recording-screen-capture-alternative.md](plans/recording-screen-capture-alternative.md)
  - [ ] 画質とファイルサイズの改善 → [plans/recording-quality-improvements.md](plans/recording-quality-improvements.md)
  - [ ] **Step 4-2/3/4**: 90秒・5分・30分長尺で AV ドリフトと CPU 負荷を計測（subprocess 経路で）
  - [ ] **Step 5**: 配信モード（RTMP）に劣化がないか確認
  - [ ] **Step 6**: ドキュメント整備（recording-av-sync-fix.md と役割分担明記、CLAUDE.md にラウドネス基準追記）