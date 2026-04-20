# TODO

## 授業モード
- [ ] speech-generation-flow.md を最新実装に更新とフローチャートの追加 → [plans/speech-flow-doc-update.md](plans/speech-flow-doc-update.md)
- [ ] C#画面のセクション進捗パネルが動いていない
- [ ] 授業生成の授業内容とセリフのチェックと再生成を入れる
- [ ] 管理画面から授業を再生した後にクライアントのLessonタブで開始されたことやデータ転送の進捗を確認したい

## その他
- [>] 録画モードAV同期: C→B1→B2 まで実施済み。B2（`MaxAudioQueueChunks` 100→10、`AudioOffset` デフォルト 0 に戻し）で音声 PTS 遅延の上限を 100ms に制限。実 TTS 発話ありで 60〜90 秒録画して目視確認と `[AVSync]` summary ログ計測が残っている。残差があれば A（`AudioOffset` 微調整）に進む。→ [plans/recording-av-sync-fix.md](plans/recording-av-sync-fix.md)
- [ ] 録画モードAV同期: 30分長尺でのドリフト累積確認（上記解消後）