# TODO

## 授業再生のクライアント主導型への移行 → [plans/client-driven-lesson.md](plans/client-driven-lesson.md)

サーバー再起動で授業が途切れる問題を根本解決。C#が再生を主導し、Pythonはコンテンツ生成に専念する。

- [>] Phase 1: C# 再生エンジン + WebSocket API（LessonPlayer新設、lesson_*アクション追加）— ビルド・動作確認待ち
- [>] Phase 2: broadcast.html 授業表示ハンドラ（lesson.js新設、C# JS interop経由で字幕・口パク・感情）— Phase 1と合わせて動作確認待ち
- [ ] Phase 3: Python LessonRunner 書き換え（バンドル生成・送信・完了イベント待ち、旧speak/sleep/polling削除）
- [ ] Phase 4: DB永続化・サーバー再起動復旧（進捗永続化、lesson_status問い合わせ、startup復旧）
- [ ] Phase 5: 旧コード整理（旧メソッド削除、ドキュメント更新）

## TTS完了待ちの過剰遅延改善（コメント応答用） → [plans/tts-wait-excess-delay.md](plans/tts-wait-excess-delay.md)

- [ ] C# PlaybackStoppedで`tts_complete` Push通知送信
- [ ] Python `_wait_tts_complete` をイベントベースに変更（sleep+polling廃止）
