# Step 4: レッスンランナーの対話再生

## ステータス: 完了

## ゴール

`lesson_runner.py` に `_play_dialogues()` を追加し、先生/生徒の掛け合いを話者ごとに異なる声・アバターで再生する。授業開始時に生徒アバター表示、終了時に非表示。

## 変更対象

| ファイル | 変更内容 |
|---------|---------|
| `src/lesson_runner.py` | `_play_dialogues()` 追加・アバター表示制御 |

## 前提

- Step 1（WebSocket avatar_id ルーティング）完了済み
- Step 2（TTS style パラメータ）完了済み
- Step 3（スクリプト生成 — dialoguesカラム）完了済み

## 実装

### 4-1. _play_section() の分岐

既存の `_play_section()` 本体を `_play_single_speaker()` にリネームし、dialogues の有無で分岐。

### 4-2. _play_dialogues()

- characters テーブルから生徒設定（voice/style/name）を取得
- 全dialogueのTTSを事前生成（キャッシュ: `section_XX_dlg_YY.wav`）
- 順次再生: speaker に応じて voice/style/avatar_id を切り替え
- 発話間に0.3秒の間

### 4-3. アバター表示制御

授業開始時に生徒アバター表示（`student_avatar_show`）、終了時に非表示（`student_avatar_hide`）。生徒のVRMは characters テーブルの config.vrm から取得。

## 完了条件

- [x] dialogues ありで `_play_dialogues()` が呼ばれる
- [x] dialogues なしで従来の単話者再生（後方互換）
- [x] 話者ごとに voice/style/avatar_id が切り替わる
- [ ] 授業開始時に生徒アバター表示、終了時に非表示（アバター表示制御は別途）
