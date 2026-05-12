# TODO

## 授業モード
- [ ] speech-generation-flow.md を最新実装に更新とフローチャートの追加 → [plans/speech-flow-doc-update.md](plans/speech-flow-doc-update.md)
- [ ] C#画面のセクション進捗パネルが動いていない
- [ ] 授業生成の授業内容とセリフのチェックと再生成を入れる
- [ ] 管理画面から授業を再生した後にクライアントのLessonタブで開始されたことやデータ転送の進捗を確認したい

## その他
- [ ] クライアント画面の文字をもっと綺麗に表示できないか
- [>] 録画の別アプローチ：画面キャプチャ＋WASAPI Loopback で AV 同期を OS 任せにする（Step 4 前半完了：subprocess 経路に着地） → [plans/recording-screen-capture-alternative.md](plans/recording-screen-capture-alternative.md)
  - [ ] 画質とファイルサイズの改善 → [plans/recording-quality-improvements.md](plans/recording-quality-improvements.md)
  - [ ] **Step 4-2/3/4**: 90秒・5分・30分長尺で AV ドリフトと CPU 負荷を計測（subprocess 経路で）
  - [ ] **Step 5**: 配信モード（RTMP）に劣化がないか確認
  - [ ] **Step 6**: ドキュメント整備（recording-av-sync-fix.md と役割分担明記、CLAUDE.md にラウドネス基準追記）