# TODO

## 機能追加

### 授業モード v3 — 監督主導アーキテクチャ → [plans/teacher-mode-v3.md](plans/teacher-mode-v3.md)
- [x] Step 1: 監督プロンプト拡張（display_text + dialogue_directions + key_content を出力）
- [ ] Step 2: 全LLM呼び出しにgenerationメタデータ付与（JSハードコード廃止の前提）
- [ ] Step 3: generate_lesson_script_v2() のPhase B-1除去（監督の設計を直接使用）
- [ ] Step 4: セリフ個別生成のkey_content対応
- [ ] Step 5: teacher.pyルート対応（API戻り値にgenerations/director_sections追加）
- [ ] Step 6: DBスキーマ調整（lesson_plans.director_json/plan_generations、lesson_sections.dialogue_directions）
- [ ] Step 7: 管理画面 — 全LLM入出力の可視化（プロンプトをAPIから取得、データフロー表示）

### キャラクター発話生成フロー設計ドキュメント
- [x] 全モード（授業・雑談・イベント等）を横断したキャラクター発話生成フローの定義ドキュメントを作成 → [docs/speech-generation-flow.md](docs/speech-generation-flow.md)

### その他
- [ ] ブラウザテスト（Playwright等）導入の検証

## バグ
- [ ] 配信中の音声ドロップ調査（音声キューdepth=100飽和、10秒ごとに+13〜30ドロップ）→ [plans/stream-buffering-fix.md](plans/stream-buffering-fix.md)

## 検討
- [ ] 遅延が大きく発生した場合にスキップしてでも最新の配信内容に追いつく機能の検証 → [plans/latency-skip-catchup.md](plans/latency-skip-catchup.md)
- [ ] キャプチャウィンドウの音を配信に自然に乗せれるかを検証 → [plans/capture-window-audio.md](plans/capture-window-audio.md)
- [ ] YouTube動画などFPSが高いウィンドウをキャプチャしてスムーズに配信できるかの検証 → [plans/high-fps-capture-verification.md](plans/high-fps-capture-verification.md)
- [ ] capture.pyのbroadcast_items全面移行（二重管理解消） → [plans/capture-broadcast-items-migration.md](plans/capture-broadcast-items-migration.md)
- [ ] SE（効果音）とコメント応答の連携検証（AIがSEカテゴリを正しく選択するか、再生タイミング・音量が適切か）
