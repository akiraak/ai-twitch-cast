# Step 6: レッスンランナーの対話再生

## ステータス: 未着手

## ゴール

`lesson_runner.py` に `_play_dialogues()` を追加し、セクション内の先生/生徒の掛け合いを話者ごとに異なる声・アバターで再生する。授業開始時に生徒アバターを表示し、終了時に非表示にする。

## 変更対象

| ファイル | 変更内容 |
|---------|---------|
| `src/lesson_runner.py` | `_play_dialogues()` 追加・アバター表示制御 |

## 前提

- Step 2（WebSocket avatar_id ルーティング）完了済み
- Step 3（TTS style パラメータ）完了済み
- Step 4（DBスキーマ — dialoguesカラム + 設定）完了済み

## 実装

### 6-1. _play_section() の分岐

既存の `_play_section()` 本体を `_play_single_speaker()` にリネームし、dialogues の有無で分岐。

### 6-2. _play_dialogues()

- DB から生徒設定（voice/style/name）を読み込む
- 全dialogueのTTSを事前生成（キャッシュ: `section_XX_dlg_YY.wav`）
- 順次再生: speaker に応じて voice/style/avatar_id を切り替え
- 発話間に0.3秒の間

### 6-3. アバター表示制御

```python
# start() 内
student_enabled = db.get_setting("student.enabled") != "false"
student_vrm = db.get_setting("student.vrm") or ""
if student_enabled and student_vrm:
    await self._on_overlay({"type": "student_avatar_show", "vrm": student_vrm})

# stop() 内 / 授業完了時
await self._on_overlay({"type": "student_avatar_hide"})
```

## 完了条件

- [ ] dialogues ありで `_play_dialogues()` が呼ばれる
- [ ] dialogues なしで `_play_single_speaker()` が呼ばれる（後方互換）
- [ ] 話者ごとに voice/style/avatar_id が切り替わる
- [ ] 授業開始時に生徒アバター表示、終了時に非表示
- [ ] TTSキャッシュが `dlg_` 形式で保存される
