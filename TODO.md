# TODO

## 授業モード
- [ ] speech-generation-flow.md を最新実装に更新とフローチャートの追加 → [plans/speech-flow-doc-update.md](plans/speech-flow-doc-update.md)
- [ ] C#画面のセクション進捗パネルが動いていない
- [ ] 授業生成の授業内容とセリフのチェックと再生成を入れる
- [ ] 管理画面から授業を再生した後にクライアントのLessonタブで開始されたことやデータ転送の進捗を確認したい

## その他
- [>] 録画モードAV同期: B2 計測完了（cap=10 で B1 副作用は解消したが「ぶつぶつ音切れ」「0.5秒の遅延ばらつき」が出た）。次は **C+A 案**（`MaxAudioQueueChunks` 10→30、`AudioOffset` 0→-0.3）を実装してジッタ吸収＋中央値オフセット補正を入れる。実装後は授業再生 60〜90 秒録画で目視＋ログ確認。→ [plans/recording-av-sync-fix.md](plans/recording-av-sync-fix.md)
- [ ] 録画モードAV同期: 30分長尺でのドリフト累積確認（上記解消後）