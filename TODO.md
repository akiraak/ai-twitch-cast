# TODO

## 授業再生のクライアント主導型への移行（旧プラン） → [plans/client-driven-lesson.md](plans/client-driven-lesson.md)

- [>] Phase 1-4: 実装済み（ビルド・動作確認待ち）
- [>] Phase 5: バグ修正
    - [ ] 最初のセリフしか読まれない問題 → 多層防御を実装済みだが実機検証未完了。次回再生時に PlaybackStopped 発火タイミングログとフォールバック警告ログを確認する [plans/lesson-playback-stopped-hang.md](plans/lesson-playback-stopped-hang.md)
    - [ ] 授業開始ボタン押下後、TTSキャッシュミスがあると `lesson_load` 送信前にユーザーが「始まらない」と感じる問題（今回 18:50:44 開始→18:51:54 停止で C# に何も届かず）。事前生成完了状態を開始ボタンに反映 or 進捗を配信画面に表示する

## TTS完了待ちの過剰遅延改善（コメント応答用） → [plans/tts-wait-excess-delay.md](plans/tts-wait-excess-delay.md)

- [ ] C# PlaybackStoppedで`tts_complete` Push通知送信
- [ ] Python `_wait_tts_complete` をイベントベースに変更（sleep+polling廃止）
