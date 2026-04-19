# TODO

## 授業モード
- [ ] speech-generation-flow.md を最新実装に更新とフローチャートの追加 → [plans/speech-flow-doc-update.md](plans/speech-flow-doc-update.md)
- [ ] C#画面のセクション進捗パネルが動いていない
- [ ] 授業生成の授業内容とセリフのチェックと再生成を入れる
- [ ] 管理画面から授業を再生した後にクライアントのLessonタブで開始されたことやデータ転送の進捗を確認したい

## その他
- [>] 録画モードAV同期修正（wallclock採用決定、本実装フェーズ）→ [plans/recording-av-sync-verification.md](plans/recording-av-sync-verification.md) の「検証後の扱い」節を参照。次回: pacer コード削除 → `VideoTimingMode` enum 削除 → 録画時常時 `-use_wallclock_as_timestamps 1` → TTS発話ありで実リップシンク確認 → [plans/recording-av-sync-fix.md](plans/recording-av-sync-fix.md) を書き換え