# TODO

## 授業再生のクライアント主導型への移行（旧プラン） → [plans/client-driven-lesson.md](plans/client-driven-lesson.md)

- [>] Phase 1-4: 実装済み（ビルド・動作確認待ち）
- [>] Phase 5: バグ修正（PlaybackStopped未発火問題は実装済み・動作確認待ち）

## TTS完了待ちの過剰遅延改善（コメント応答用） → [plans/tts-wait-excess-delay.md](plans/tts-wait-excess-delay.md)

- [ ] C# PlaybackStoppedで`tts_complete` Push通知送信
- [ ] Python `_wait_tts_complete` をイベントベースに変更（sleep+polling廃止）
