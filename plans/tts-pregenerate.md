# 授業モード: TTS事前生成

## ステータス: 完了

## Context

現状、授業のTTS音声は再生時（`LessonRunner._play_single_speaker` / `_play_dialogues`）に初めて生成される。キャッシュ機構はあるが初回再生時はキャッシュがなく、各セクションでTTS生成に数秒待たされて授業テンポが悪い。コンテンツ生成/インポート完了時にTTSを事前生成し、再生時はキャッシュヒットのみにする。

## 方針

- 既存のキャッシュパス構造（`_cache_path` / `_dlg_cache_path`）をそのまま利用
- TTS生成ロジックを `src/tts_pregenerate.py` に切り出し、`tts.synthesize()` を直接呼ぶ（SpeechPipelineインスタンス不要）
- バックグラウンド `asyncio.Task` で非同期生成（APIレスポンスはブロックしない）
- LessonRunner側は変更不要（既にキャッシュチェック済み→キャッシュヒットするようになる）

## 実装ステップ

### Step 1: `src/tts_pregenerate.py` 新規作成

コアロジック。LessonRunnerから独立したTTS事前生成モジュール。

```python
# 主要関数
async def pregenerate_lesson_tts(
    lesson_id, lang, generator, version_number,
    cancel_event=None, on_progress=None,
) -> dict:
    """レッスン全セクションのTTSを事前生成
    
    Returns: {"total": int, "generated": int, "cached": int, "failed": int, "cancelled": bool}
    """

async def pregenerate_section_tts(
    lesson_id, section, order_index, lang, generator, version_number,
    teacher_cfg, student_cfg, cancel_event=None,
) -> dict:
    """1セクション分のTTSを事前生成
    
    Returns: {"generated": int, "cached": int, "failed": int}
    """
```

#### 実装詳細

**依存関係:**
- `from src.lesson_runner import _cache_path, _dlg_cache_path` — private関数だがプロジェクト内なのでOK
- `from src.speech_pipeline import SpeechPipeline` — `split_sentences()` staticmethodのみ使用
- `from src.tts import synthesize` — 直接呼び出し（SpeechPipelineインスタンス不要）
- `from src.lesson_generator.utils import get_lesson_characters` — キャラ設定取得
- `from src import db` — セクション取得

**voice/style の扱い（LessonRunnerと完全一致させる）:**

| モード | LessonRunnerの挙動 | 事前生成での再現 |
|--------|-------------------|----------------|
| 単話者 | `generate_tts(part, tts_text=...)` voice/style渡さない → `synthesize()` 内で `ai_responder.get_tts_config()` が決定 | `synthesize(text, path)` — voice/style渡さない（同じフォールバック） |
| 対話 | `cfg.get("tts_voice")`, `cfg.get("tts_style")` をspeaker別に明示渡し | `synthesize(text, path, voice=cfg["tts_voice"], style=cfg["tts_style"])` |

**TTS生成→キャッシュ保存パターン**（lesson_runner.py:527-536 の再現）:
```python
import tempfile, shutil
tmp_path = Path(tempfile.mkdtemp()) / "speech.wav"
await asyncio.to_thread(synthesize, tts_text, str(tmp_path), voice=voice, style=style)
cache.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(tmp_path, cache)
tmp_path.unlink(missing_ok=True)
try:
    tmp_path.parent.rmdir()
except OSError:
    pass
```

**dialogue解析**（lesson_runner.py:461-474 と同じ）:
```python
dialogues_raw = section.get("dialogues", "")
dialogues = None
if dialogues_raw and student_cfg:
    parsed = json.loads(dialogues_raw) if isinstance(dialogues_raw, str) else dialogues_raw
    if isinstance(parsed, dict) and "dialogues" in parsed:
        dialogues = parsed["dialogues"]  # v4形式
    else:
        dialogues = parsed
    if not isinstance(dialogues, list) or len(dialogues) == 0:
        dialogues = None
```

**各TTS生成間:**
- `cancel_event.is_set()` チェック → 即座にreturn
- `await asyncio.sleep(0.1)` — レート制限対策
- 失敗時: 1回リトライ、それでもダメなら failedカウントして次へ（部分成功OK）

### Step 2: `scripts/routes/teacher.py` にタスク管理追加

モジュールレベルのタスクレジストリ:
```python
_tts_pregen_tasks: dict[str, dict] = {}
# Key: "{lesson_id}_{lang}_{generator}_{version}"
# Value: {"task": asyncio.Task, "cancel_event": asyncio.Event, "status": dict}
```

進捗status構造:
```python
{
    "state": "running" | "completed" | "error",
    "total": int,         # 全セクション数
    "completed": int,     # 処理済みセクション数
    "generated": int,     # 新規生成数
    "cached": int,        # キャッシュヒット数
    "failed": int,        # 失敗数
    "error": str | None,  # エラーメッセージ
}
```

ヘルパー関数 `_start_tts_pregeneration(lesson_id, lang, generator, version_number)`:
- 既存タスクがあれば `cancel_event.set()` でキャンセル
- `pregenerate_lesson_tts()` をasyncioタスクで起動
- `on_progress` コールバックで `_tts_pregen_tasks[key]["status"]` を更新

### Step 3: import_sections / improve_content に統合

- `import_sections` (teacher.py:~845) の return 直前に `_start_tts_pregeneration()` 呼び出し
- `improve_content` (teacher.py:~1325) の return 直前に `_start_tts_pregeneration()` 呼び出し
- APIレスポンスに `"tts_pregeneration_started": True` を追加

### Step 4: 新APIエンドポイント追加 (teacher.py)

| エンドポイント | メソッド | 用途 |
|--------------|---------|------|
| `/api/lessons/{id}/tts-pregen-status` | GET | 進捗確認（status構造を返す） |
| `/api/lessons/{id}/tts-pregen` | POST | 手動トリガー |
| `/api/lessons/{id}/tts-pregen-cancel` | POST | キャンセル |

### Step 5: フロントエンド (static/js/admin/teacher.js)

- import/improve成功後、レスポンスに `tts_pregeneration_started` があれば進捗ポーリング開始（3秒間隔）
- 進捗表示: セクションカード上部に「TTS生成中: 3/8 セクション」バー
- 完了時にポーリング停止、TTSキャッシュ表示を自動更新（既存 `tts-cache` API再取得）
- 手動「TTS一括生成」ボタン追加（Step 3のカード、バージョンセレクタ横あたり）
- 生成中はキャンセルボタン表示

### Step 6: テスト

**`tests/test_tts_pregenerate.py`** (新規):
- `tts.synthesize` を `monkeypatch` でモック（conftest.pyの `mock_gemini` パターン参照）
- 単話者セクションの事前生成: contentが `split_sentences` で分割され、各パートのキャッシュファイルが作成される
- 対話セクションの事前生成: speaker別にvoice/styleが渡される
- キャンセル: `cancel_event.set()` 後に即座に停止
- キャッシュヒット: 既存ファイルがあればスキップ、generatedカウントが増えない
- `pregenerate_lesson_tts`: 全セクション一括、DBからセクション取得→全部生成

**`tests/test_api_teacher.py`** (追加):
- `tts-pregen-status`: idle/running/completed の各状態
- `tts-pregen`: 手動トリガーでタスク開始
- `tts-pregen-cancel`: キャンセルAPI

## 変更ファイル一覧

| ファイル | 変更種別 | 内容 |
|---------|---------|------|
| `src/tts_pregenerate.py` | 新規 | TTS事前生成コアロジック |
| `scripts/routes/teacher.py` | 修正 | タスク管理 + import/improve統合 + 3 API追加 |
| `static/js/admin/teacher.js` | 修正 | 進捗表示 + 手動トリガー/キャンセルUI |
| `tests/test_tts_pregenerate.py` | 新規 | ユニットテスト |
| `tests/test_api_teacher.py` | 修正 | API テスト追加 |

## 設計判断

- **`tts.synthesize()` 直接呼び出し**: `SpeechPipeline.generate_tts()` は tmpdir作成 + `synthesize()` + return の薄いラッパー (speech_pipeline.py:83-99)。SpeechPipelineはon_overlayコールバック等を必要とするため、事前生成にはインスタンス不要
- **voice/styleの扱い分け**: 単話者=渡さない（`synthesize()` 内の `get_tts_config()` に委ねる）、対話=speaker別に明示渡し。LessonRunnerの挙動と完全一致させてキャッシュ互換性を保証
- **`_cache_path` / `_dlg_cache_path` のインポート**: private関数（アンダースコア付き）だが、プロジェクト内の同一パッケージ間での利用。キャッシュパスのロジック重複を避けるため直接インポート
- **`asyncio.Event` によるキャンセル**: `task.cancel()` だとCancelledErrorで中間ファイルが残る。LessonRunnerの `_pause_event` と同じ協調パターン
- **メモリ内タスク管理**: エフェメラルなタスクにDB不要。サーバー再起動で消えるが、再トリガー可能なので問題なし
- **LessonRunner変更不要**: 既存のキャッシュチェック（lesson_runner.py:521-525, 565-567）が自動的にヒットする

## リスク

- Gemini TTS APIのレート制限 → 各TTS生成間に0.1秒スリープで対策
- 大量セクションの場合の生成時間 → 進捗表示+キャンセル機能で対応
- サーバー再起動時にタスクが消える → 手動再トリガーAPIで対応
- voice/style設定の変更後、古いキャッシュが使われる → 既存の問題（TTSキャッシュ削除APIで対応済み）

## 検証方法

1. `python3 -m pytest tests/ -q` — 全テスト通過
2. サーバー再起動後、教師モードでコンテンツをインポート → TTS生成の進捗バーが表示される
3. `GET /api/lessons/{id}/tts-pregen-status` でrunning→completed遷移を確認
4. 授業開始 → セクション間の待ち時間が大幅に短縮（ログで `cache hit` 確認）
5. キャンセルボタンで生成中断 → `tts-pregen-status` で `cancelled: true` 確認
6. `GET /api/lessons/{id}/tts-cache` でキャッシュファイルの存在確認
