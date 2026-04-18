# TODO

## 授業モード
- [ ] speech-generation-flow.md を最新実装に更新とフローチャートの追加 → [plans/speech-flow-doc-update.md](plans/speech-flow-doc-update.md)
- [ ] C#画面のセクション進捗パネルが動いていない
- [ ] 授業生成の授業内容とセリフのチェックと再生成を入れる
- [ ] 管理画面から授業を再生した後にクライアントのLessonタブで開始されたことやデータ転送の進捗を確認したい

## その他
- [ ] テストの検証。不要なものを削除。必要なものがあれば追加 → [plans/test-suite-audit.md](plans/test-suite-audit.md)
  - [ ] Step 1-c: `ai_responder`→`character_manager` 等のモジュール分離に伴う重複テストを洗い出し
  - [ ] Step 1-d: `CLAUDE.md` の「テスト構成」表と実在ファイルの差分をプランに転記
  - [ ] Step 2: 不要テストをケース単位で削除（カテゴリ別にコミット分割）
  - [ ] Step 3-1: `lesson_generator/improver.py` のテスト追加（最優先・授業品質の中核）
  - [ ] Step 3-2: `scripts/routes/avatar.py` のテスト追加（発話API入口）
  - [ ] Step 3-3: `scripts/routes/capture.py` のテスト追加（配信アプリ連携）
  - [ ] Step 3-4: `character_manager.py` のテスト追加
  - [ ] Step 3-5: `lesson_generator/extractor.py` / `utils.py` のテスト追加
  - [ ] Step 3-6: `routes/bgm.py` / `files.py` / `prompts.py` のテスト追加
  - [ ] Step 3-7: `twitch_api.py` / `twitch_chat.py` のテスト追加
  - [ ] Step 4-a: 遅いテストに `@pytest.mark.slow` 付与 + `pytest.ini` にマーカー登録（目標: `-m "not slow"` で 60秒以内）
  - [ ] Step 4-b: `time.sleep` / 実I/O を使うテストを `freezegun` / モック化で置換
  - [ ] Step 5: `scripts/web.py` の `@app.on_event` を FastAPI lifespan ハンドラに移行（DeprecationWarning解消）
  - [ ] Step 6: `CLAUDE.md` のテスト構成表を実体と一致させ、`-m "not slow"` 運用を追記
- [ ] クライアントに動画撮影機能を入れる

- [ ] Claude Code が Yes/No を表示したタイミングでキャラがしゃべる（ただし連発しないように１分間は反応しないようにする） → [plans/claude-permission-prompt-tts.md](plans/claude-permission-prompt-tts.md)