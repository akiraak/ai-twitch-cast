# 「間のスケール」（pace_scale）削除

## ステータス
- ステータス: 完了
- 起票: 2026-05-05
- 完了: 2026-05-05
- 起点: ユーザー指示「管理画面の『会話モード』->『授業モード』の『間のスケール』を削除。内部実装も削除」

## 実施結果
- UI / API / lesson_runner / C# / テスト / ドキュメントから `pace_scale` を完全に削除
- `python3 -m pytest tests/ -q -m "not slow"` 1278 passed (6:22)
- C# ビルドは WSL2 では検証不可。次回 `stream.sh` 経由で起動して実機確認すること
- DB の `lesson.pace_scale` 設定値は残置（読み取り側を消したため害はなし）

## 背景

授業モードのコンテンツ一覧上部に表示されている **「間のスケール」スライダー（0.5〜2.0x）** と、その値を `section.wait_seconds` / `question.wait_seconds` に乗算して再生間隔を伸縮させる実装一式を削除する。

現状の固定倍率による尺調整より、コンテンツ側の `wait_seconds` を直接調整する運用に寄せる方針。

## 削除対象

### UI（管理画面）
- `static/js/admin/teacher.js:98-99` — `_renderPaceScaleSlider(list)` の呼び出し
- `static/js/admin/teacher.js:112-128` — `_renderPaceScaleSlider` 関数本体
- `static/js/admin/teacher.js:130-132` — `updatePaceScale` 関数

### Python サーバ
- `scripts/routes/teacher.py:283-302`:
  - `PaceScaleUpdate` Pydantic モデル
  - `GET /api/lessons/pace-scale` ルート
  - `PUT /api/lessons/pace-scale` ルート

### Python ロジック（lesson_runner）
- `src/lesson_runner.py:594` — `pace_scale = self._get_pace_scale()`
- `src/lesson_runner.py:615` — `_calc_section_duration(bundle, pace_scale)` の第2引数
- `src/lesson_runner.py:633` — C#送信ペイロードの `pace_scale=pace_scale`
- `src/lesson_runner.py:703-711` — `_calc_section_duration` の `pace_scale` 引数とその乗算（`* pace_scale` を `* 1.0` 同等に）
- `src/lesson_runner.py:973-981` — `_get_pace_scale()` メソッド全体
- DB 設定キー: `lesson.pace_scale` — マイグレーション不要だが、削除コメントを残しておくか要検討

### C# (LessonPlayer.cs)
- `LessonPlayer.cs:41` — `SectionData.PaceScale` プロパティ
- `LessonPlayer.cs:75` — `_paceScale` フィールド
- `LessonPlayer.cs:108` — `pace_scale` JSON読み込み
- `LessonPlayer.cs:120` — `section.PaceScale = _paceScale` 代入
- `LessonPlayer.cs:132-133` — ログ出力の `paceScale={Pace}`
- `LessonPlayer.cs:358, 363, 436, 449` — `* sec.PaceScale` 乗算（`section.PaceScale` を削るので単純に `sec.WaitSeconds` のみ）
- `LessonPlayer.cs:564` — 別経路の `pace_scale` 読み取り

### ドキュメント
- `docs/speech-generation-flow.md:221` — 「ペース制御: lesson.pace_scale（DB設定、デフォルト1.0）でセクション間の間隔を調整」の記述
- `plans/client-driven-lesson.md` — `pace_scale` への言及（並行プラン。本タスクで完全削除する場合、整合性のため要確認）

### テスト
- `tests/test_lesson_runner.py:1155-1156` — `pace_scale in load_call.kwargs` のアサート
- `tests/test_lesson_runner.py:1494` — `pace_scale=1.0` の引数（_calc_section_duration の引数自体を削るなら不要）
- `tests/test_lesson_runner.py:1498-1506` — pace_scale テストケース全体
- `tests/test_api_teacher.py:591-616` — `TestPaceScale` クラス全体

## 実装ステップ案

1. UI を消す（`teacher.js`）→ 管理画面が空のスペースだけ残らないことを確認
2. APIルートを消す（`teacher.py`）→ 401 でなく 404 になる
3. lesson_runner から削除（`_get_pace_scale`, `_calc_section_duration` シグネチャ変更, C#送信ペイロード）
4. C# 側を削除（フィールド・JSONパース・乗算・ログ）→ ビルド通る確認
5. テストを更新／削除（`_calc_section_duration` のシグネチャ変更に伴い `test_calc_section_duration` / `test_calc_section_duration_with_pace` も同時に更新）
6. ドキュメント更新（`docs/speech-generation-flow.md:221` のペース制御記述を削除）
7. `python3 -m pytest tests/ -q -m "not slow"` で全緑確認
8. C# ビルドが通ることを確認（`dotnet build` または ユーザーに実機確認依頼）
9. DONE.md / TODO.md 更新

## リスク・注意

- C# 側の削除は WinNativeApp の再ビルドが必要。ユーザー側で `stream.sh` 経由のアプリ更新を依頼すること
- DB の `lesson.pace_scale` 設定値は残置されても害はない（読み取り側を消すので無視される）。気になるなら `db.delete_setting("lesson.pace_scale")` をワンショットで実行
- `lesson_runner._build_section_bundle` から C# に送る JSON の `pace_scale` キーを消した場合、古い WinNativeApp が起動していると `pace_scale` 不在で `1.0` フォールバックになる（後方互換あり）。逆に古い lesson_runner + 新 C# は `pace_scale` フィールドが消えてビルド失敗するので、Python と C# は同時に更新する想定
- `_calc_section_duration` の戻り値は C# の `lesson_complete` 待ちタイムアウト計算 (`_wait_lesson_complete`) に使われるので、削除後も合計尺が正しく出ることを必ず確認
