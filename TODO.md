# TODO

## 授業モード
- [ ] speech-generation-flow.md を最新実装に更新とフローチャートの追加 → [plans/speech-flow-doc-update.md](plans/speech-flow-doc-update.md)
- [ ] C#画面のセクション進捗パネルが動いていない
- [ ] 授業生成の授業内容とセリフのチェックと再生成を入れる
- [ ] 管理画面から授業を再生した後にクライアントのLessonタブで開始されたことやデータ転送の進捗を確認したい

## その他
- [>] 録画モードAV同期: 多角検証完了→**α 単独実装**へ。音声入力に `-use_wallclock_as_timestamps 1` を 1 行追加し、FFmpeg read 時刻で音声 PTS を打刻することで映像 wallclock と自動同期させる。cap/offset/pipe 1MB は維持して α 単独効果を切り分け、効果ありなら段階的に対症療法をロールバックして本質を確定。残差あれば α+δ、最終手段 γ（β 単独には進まない）。→ [plans/recording-av-sync-fix.md](plans/recording-av-sync-fix.md)
- [ ] 録画モードAV同期: 30分長尺でのドリフト累積確認（上記解消後）