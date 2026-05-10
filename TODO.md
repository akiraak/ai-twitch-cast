# TODO

## バイブコーダー向けセキュリティ講座（全10回・授業モード） → [plans/vibe-coder-security-lesson.md](plans/vibe-coder-security-lesson.md)

全10回構成確定（lesson_id 100〜109）。素材メモは `plans/vibe-coder-security/lesson-{N}-source.md`。
- [>] **Step 4 (#1)**: TTS 事前生成は完了（v1, 40/40 wav, failed=0）→ **管理画面 Lesson タブで試聴 → 必要なら微修正**。再開用チェックリスト＋手順は [plans/vibe-coder-security/lesson-1-audition.md](plans/vibe-coder-security/lesson-1-audition.md)
- [ ] **Step 5 (#1)**: 配信して反応を見る（フィードバック収集）
- [ ] **#2〜#10**: 各回の素材md → セクション生成 → 投入（概論への反応を見ながら順次着手）

## 授業モード
- [ ] speech-generation-flow.md を最新実装に更新とフローチャートの追加 → [plans/speech-flow-doc-update.md](plans/speech-flow-doc-update.md)
- [ ] C#画面のセクション進捗パネルが動いていない
- [ ] 授業生成の授業内容とセリフのチェックと再生成を入れる
- [ ] 管理画面から授業を再生した後にクライアントのLessonタブで開始されたことやデータ転送の進捗を確認したい

## その他
- [>] 録画モードAV同期: 多角検証完了→**α 単独実装**へ。音声入力に `-use_wallclock_as_timestamps 1` を 1 行追加し、FFmpeg read 時刻で音声 PTS を打刻することで映像 wallclock と自動同期させる。cap/offset/pipe 1MB は維持して α 単独効果を切り分け、効果ありなら段階的に対症療法をロールバックして本質を確定。残差あれば α+δ、最終手段 γ（β 単独には進まない）。→ [plans/recording-av-sync-fix.md](plans/recording-av-sync-fix.md)
- [ ] 録画モードAV同期: 30分長尺でのドリフト累積確認（上記解消後）
- [>] 録画の別アプローチ：画面キャプチャ＋WASAPI Loopback で AV 同期を OS 任せにする（Step 1 完了） → [plans/recording-screen-capture-alternative.md](plans/recording-screen-capture-alternative.md)
  - [ ] **Step 2**: 録画モード時の FFmpeg を 2 入力化（音声を loopback pipe に切替、generator は配信モードのみで使用）
  - [ ] **Step 3**: `scripts/verify_av_sync.py` を音声 PTS 計測まで拡張（α 検証とも共有）
  - [ ] **Step 4**: 60秒〜30分長尺で AV 同期と CPU 負荷を計測
  - [ ] **Step 5**: 配信モード（RTMP）に劣化がないか確認
  - [ ] **Step 6**: ドキュメント整備（recording-av-sync-fix.md と役割分担明記、CLAUDE.md にラウドネス基準追記、DONE.md 記録）