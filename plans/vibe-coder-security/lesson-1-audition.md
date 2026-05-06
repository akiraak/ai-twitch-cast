# Lesson #1（id=100）試聴チェックリスト

> 戻ってきたらここから再開。状況: セクション投入＋TTS事前生成は完了、**試聴のみ未実施**。
> プラン: [../vibe-coder-security-lesson.md](../vibe-coder-security-lesson.md) ／ 素材: [./lesson-1-source.md](./lesson-1-source.md)

## 現在の状態（コミット直前）

- `lesson_id=100` / `lang=ja` / `generator=claude` / `version=1`
- セクション 6 本（順番）:
  1. introduction（今日のテーマ）
  2. explanation（なぜ狙われる？）
  3. example（開発中の4テーマ／Phase 1）
  4. example（公開直前と公開後／Phase 2-4）
  5. question（概論クイズ：.env 漏れの3択）
  6. summary（今日のまとめ＋次回予告）
- dialogues 計 40 ターン（teacher=ちょビ / student=なるこ）
- TTS 事前生成: `resources/audio/lessons/100/ja/claude/v1/*.wav` 40 ファイル（gitignored）

## 試聴の手順

1. サーバー起動確認: `curl -s http://localhost:8080/api/status`
2. 管理画面 → Lesson タブ → lesson_id=100「#1 全体マップ：…」を選択
3. 各セクションを順に再生（または通し再生）

## チェック観点

- [ ] **誤読**: 専門用語・サービス名（Auth0 / Clerk / Supabase / Firebase / Cloudflare / Cursor 等）が日本語読みされていないか
- [ ] **言語タグ漏れ**: `[lang:en]` 漏れで `.env`, `XSS`, `SQLi`, `CORS`, `CSRF`, `HTTPS`, `API`, `Bot`, `Git`, `SNS`, `DB` が変な発音になっていないか
- [ ] **テンポ**: teacher が3連投以上で student が消えるセクションがないか（特に Section 3, 4 が長め）
- [ ] **display_text の読み上げ**: 各セクション最初の teacher ターンで画面の内容が省略なく読まれているか
- [ ] **クイズ間（Section 5）の wait_seconds=12** が長すぎ／短すぎないか
- [ ] **emotion**: 笑い／驚き／淡々の切り替えが内容に合っているか
- [ ] **トーン**: 怖がらせる方向に振れていないか（「お得感」基調を維持）
- [ ] **時間**: 全体で 6〜8 分に収まっているか

## 微修正のフロー

### A. テキストだけ直す（同 version=1 を上書き）

セクションを編集（管理画面の Section 編集 UI、または `PATCH /api/lessons/100/sections/{section_id}`）→ 該当セクションの TTS だけ再生成:

```bash
# 1セクションだけ TTS キャッシュを削除（order_index は 0〜5）
curl -X DELETE "http://localhost:8080/api/lessons/100/tts-cache/0?lang=ja&generator=claude&version=1"

# 全セクション再生成したいとき
curl -X DELETE "http://localhost:8080/api/lessons/100/tts-cache?lang=ja&generator=claude&version=1"

# TTS再生成キック
curl -X POST  "http://localhost:8080/api/lessons/100/tts-pregen?lang=ja&generator=claude&version=1"
curl -s       "http://localhost:8080/api/lessons/100/tts-pregen-status?lang=ja&generator=claude&version=1" | python3 -m json.tool
```

### B. 大幅に書き直す（v1 を破棄して再投入）

素材 md を編集 → セクションを再生成 → `import-sections?version=1` で **同バージョン上書き**（`teacher.py:946-956` で sections と tts キャッシュを掃除してから書き込む）。プランの「パターンC」に相当。

```bash
# import-sections に sections JSON を送る。version=1 を明示で同バージョン上書き
curl -X POST "http://localhost:8080/api/lessons/100/import-sections?lang=ja&generator=claude&version=1" \
  -H 'Content-Type: application/json' -d @sections.json
```

> **DB が正本**。ここで /tmp に置いた v1 importer スクリプトはコミットせず破棄した。再生成する場合は `prompts/lesson_generate.md` のワークフローに沿って素材mdから組み直す。

### C. 完全に作り直す

プランの「全削除・再生成の手順 パターンA」を参照（`plans/vibe-coder-security-lesson.md`）。lesson_id=100 を残してセクションだけ消し、Step 3 から再開。

## エンドポイント早見表（プラン記載との差分注意）

| 用途 | 実エンドポイント |
|------|------------------|
| TTS事前生成キック | `POST /api/lessons/{id}/tts-pregen?lang=ja&generator=claude&version=1`（プランの `pregenerate-tts` は誤り） |
| TTS進捗 | `GET /api/lessons/{id}/tts-pregen-status?...` |
| TTS中断 | `POST /api/lessons/{id}/tts-pregen-cancel?...` |
| セクション投入 | `POST /api/lessons/{id}/import-sections?lang=ja&generator=claude[&version=N]` |
| TTSキャッシュ削除 | `DELETE /api/lessons/{id}/tts-cache[/{order_index}]?...` |

## 試聴後にやること

- 修正不要 → TODO.md の Step 4 を `[x]` 化、Step 5（配信）に進む
- 軽微な修正 → A. のフローで直し、再試聴
- 大幅修正 → B. または C.

その後 **#2 シークレットを守る（id=101）** の素材md作成へ。
