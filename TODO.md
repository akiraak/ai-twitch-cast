# TODO

## 授業再生のクライアント主導型への移行（旧プラン） → [plans/client-driven-lesson.md](plans/client-driven-lesson.md)

- [>] Phase 1-4: 実装済み（ビルド・動作確認待ち）
- [>] Phase 5: バグ修正
    - [ ] 最初のセリフしか読まれない問題が未解決 → 上記の一括送信方式で根本対策 lesson-full-bundle.md

## TTS完了待ちの過剰遅延改善（コメント応答用） → [plans/tts-wait-excess-delay.md](plans/tts-wait-excess-delay.md)

- [ ] C# PlaybackStoppedで`tts_complete` Push通知送信
- [ ] Python `_wait_tts_complete` をイベントベースに変更（sleep+polling廃止）
