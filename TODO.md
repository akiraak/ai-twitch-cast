# TODO

## 授業再生のクライアント主導型への移行（旧プラン） → [plans/client-driven-lesson.md](plans/client-driven-lesson.md)

- [>] Phase 1-4: 実装済み（ビルド・動作確認待ち）
- [>] Phase 5: バグ修正
    - [ ] 授業開始ボタン押下後、TTSキャッシュミスがあると `lesson_load` 送信前にユーザーが「始まらない」と感じる問題（今回 18:50:44 開始→18:51:54 停止で C# に何も届かず） → [plans/lesson-start-prepare-progress.md](plans/lesson-start-prepare-progress.md)

## TTS完了待ちの過剰遅延改善（コメント応答用） → [plans/tts-wait-excess-delay.md](plans/tts-wait-excess-delay.md)

- [ ] C# PlaybackStoppedで`tts_complete` Push通知送信
- [ ] Python `_wait_tts_complete` をイベントベースに変更（sleep+polling廃止）
