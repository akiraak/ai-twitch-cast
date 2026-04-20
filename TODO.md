# TODO

## 授業モード
- [ ] speech-generation-flow.md を最新実装に更新とフローチャートの追加 → [plans/speech-flow-doc-update.md](plans/speech-flow-doc-update.md)
- [ ] C#画面のセクション進捗パネルが動いていない
- [ ] 授業生成の授業内容とセリフのチェックと再生成を入れる
- [ ] 管理画面から授業を再生した後にクライアントのLessonタブで開始されたことやデータ転送の進捗を確認したい

## その他
- [>] 録画モードAV同期: 音声が映像より約1〜2秒遅れる問題を解消中。C（診断）で `_audioQueue` が恒常飽和し約1秒のバッファ遅延が溜まることを特定。B1（`-itsoffset` 配線）は副作用（映像fps 28→25、ドロップ 2.8%→12.4%）あり。B2（`MaxAudioQueueChunks` 100→10 で根治）に進む予定。→ [plans/recording-av-sync-fix.md](plans/recording-av-sync-fix.md)
- [ ] 録画モードAV同期: 30分長尺でのドリフト累積確認（上記解消後）