# TODO

## C#アプリ
- [ ] サイドバーのLessonにTTSの生成に使用されたテキストも表示する
- [ ] Lessonタブに再生ボタン、停止ボタン、一時停止ボタンを入れる
- [ ] C#画面のセクション進捗パネルが動いていない

## TTS完了待ちの過剰遅延改善（コメント応答用） → [plans/tts-wait-excess-delay.md](plans/tts-wait-excess-delay.md)

- [ ] C# PlaybackStoppedで`tts_complete` Push通知送信
- [ ] Python `_wait_tts_complete` をイベントベースに変更（sleep+polling廃止）

## 授業モード
- [ ] 授業生成の授業内容とセリフのチェックと再生成を入れる