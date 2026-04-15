# TODO

## 授業データ一括送信方式 → [plans/lesson-full-bundle.md](plans/lesson-full-bundle.md)

全セクションを最初にC#に渡し、サーバーはその後一切関与しない方式に変更。セクション単位の往復通信（load→play→complete待ち）を廃止し、C#が全セクションを自律再生する。

- [ ] Phase A: C# LessonPlayer 全セクション対応（StartLesson/AddSection/PlayAsync全セクション版、lesson_complete通知）
- [ ] Phase B: Python LessonRunner 書き換え（全セクション一括バンドル生成→送信→lesson_play→lesson_complete待ち）
- [ ] Phase C: 旧コード整理（lesson_section_load/play/complete廃止）

## 授業再生のクライアント主導型への移行（旧プラン） → [plans/client-driven-lesson.md](plans/client-driven-lesson.md)

- [>] Phase 1-4: 実装済み（ビルド・動作確認待ち）
- [>] Phase 5: バグ修正
    - [ ] 最初のセリフしか読まれない問題が未解決 → 上記の一括送信方式で根本対策 lesson-full-bundle.md

## TTS完了待ちの過剰遅延改善（コメント応答用） → [plans/tts-wait-excess-delay.md](plans/tts-wait-excess-delay.md)

- [ ] C# PlaybackStoppedで`tts_complete` Push通知送信
- [ ] Python `_wait_tts_complete` をイベントベースに変更（sleep+polling廃止）
