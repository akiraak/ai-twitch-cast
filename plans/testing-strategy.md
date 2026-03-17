# テスト充実プラン

## ステータス: フェーズ1完了

## 背景

テスト基盤は構築済み（pytest + pre-commitフック）で、現在 **39テスト** が動作中。ただし対象モジュールが限定的で、DB操作・非同期サービス・APIエンドポイントのテストが欠けている。カバレッジを広げてリグレッション防止を強化する。

## 現状の棚卸し

### 既存テスト（39テスト）

| ファイル | テスト数 | 対象 | カバー範囲 |
|---------|---------|------|-----------|
| test_ai_responder.py | 10 | 言語モード、プロンプト構築 | `set/get_language_mode`, `_build_system_prompt` |
| test_capture_proxy.py | 10 | URL生成、パスマッピング | `_capture_base_url`, `_capture_ws_url`, `_PATH_TO_ACTION` |
| test_lipsync.py | 5 | 振幅解析 | `analyze_amplitude` |
| test_native_app_patterns.py | 5 | C#コードパターン検証 | MainForm.cs, FrameCapture.cs, Program.cs |
| test_overlay.py | 7 | TODOパース、ブロードキャスト | `get_todo`, `broadcast_todo` |
| test_wsl_path.py | 2 | ホスト解決 | `resolve_host` |

### 既存基盤
- `conftest.py`: twitchio/aiohttpのスタブ（import chain対策のみ）
- `pytest.ini`: testpaths=tests, asyncio_mode=auto
- `requirements.txt`: pytest, pytest-asyncio, pytest-mock, pytest-cov 定義済み
- `.git/hooks/pre-commit`: 毎コミットで `pytest tests/ -q --tb=short` を実行

### テストされていないモジュール

| モジュール | 重要度 | テスト困難度 | 備考 |
|-----------|--------|------------|------|
| **src/db.py** | 高 | 低 | 30+関数、DBスキーマ・CRUD。インメモリSQLiteで容易 |
| **src/scene_config.py** | 中 | 低 | DB/JSONからの設定読み書き |
| **src/tts.py** | 中 | 中 | Gemini TTS API呼び出し。言語タグ変換は純粋ロジック |
| **src/ai_responder.py** (残り) | 中 | 中 | `generate_response`, `load_character`, `generate_user_notes` 等 |
| **src/git_watcher.py** | 中 | 低 | subprocessモック、バッチ・クールダウンロジック |
| **src/topic_talker.py** | 中 | 中 | トピック管理・ローテーション |
| **src/twitch_api.py** | 中 | 中 | Helix API呼び出し（aiohttpモック） |
| **src/twitch_chat.py** | 低 | 高 | twitchioライブラリ依存、複雑な非同期 |
| **src/comment_reader.py** | 低 | 高 | 多数の依存、状態機械 |
| **scripts/routes/stream_control.py** | 中 | 中 | 配信制御エンドポイント |
| **scripts/routes/character.py** | 中 | 低 | キャラクタCRUD |
| **scripts/routes/topic.py** | 中 | 低 | トピック管理API |
| **scripts/routes/bgm.py** | 低 | 低 | BGM管理API |

## 方針

- **既存テストを壊さない**: conftest.pyは拡張のみ
- **DB操作を最優先**: 最もテスト効果が高く、実装も容易
- **外部APIはすべてモック**: Gemini, Twitch, C#アプリ
- **テスト用DBはtmp_path + SQLite**: テスト間を完全隔離
- **CIは後回し**: まずローカルでカバレッジ向上

## 実装ステップ

### フェーズ1: conftest拡張 + DB テスト（最優先）

#### Step 1-1: conftest.py にフィクスチャ追加
現在はスタブのみ。以下を追加：
```python
@pytest.fixture
def test_db(tmp_path, monkeypatch):
    """隔離されたテスト用SQLite DB"""
    # db.pyのDB_PATHをtmp_pathに差し替え
    # init_db()でスキーマ作成
    # yield後に自動クリーンアップ

@pytest.fixture
def mock_gemini(mocker):
    """Gemini APIモッククライアント"""

@pytest.fixture
def mock_env(monkeypatch):
    """テスト用環境変数（APIキー等のダミー値）"""

@pytest.fixture
def test_wav(tmp_path):
    """テスト用WAVファイル"""
```

#### Step 1-2: test_db.py — DBモジュールのテスト
- **スキーマ作成**: `init_db()` で11テーブルが正しく作られるか
- **ユーザーCRUD**: `get_or_create_user()` の冪等性、`update_user_notes()`
- **コメント**: `save_comment()`, `get_recent_comments()` の件数制限・時間フィルタ
- **エピソード**: `start_episode()`, `end_episode()` のライフサイクル
- **設定**: `set_setting()` / `get_setting()` の型変換（文字列・JSON）
- **トピック**: `create_topic()`, `add_topic_scripts()`, `get_next_script()`
- **BGM**: `get_bgm_tracks()`, BGM音量の保存
- **目標**: 20+ テスト、カバレッジ80%

#### Step 1-3: test_scene_config.py — 設定読み書きテスト
- DB → scenes.json → デフォルト値の優先順位
- JSON値の保存・読み出し
- 存在しないキーのデフォルト値
- **目標**: 6-8テスト

### フェーズ2: コアロジックの未テスト部分

#### Step 2-1: test_ai_responder.py 拡張
既存10テスト（言語モード・プロンプト構築）に追加：
- `load_character()`: DBからの読み込み + デフォルト値フォールバック
- `invalidate_character_cache()`: キャッシュクリア動作
- `generate_response()`: Geminiモック → JSONパース → emotion/response抽出
- JSON不正時のフォールバック（`"response"` キーが無い場合等）
- `generate_event_response()`: イベント応答
- **目標**: 8-10テスト追加

#### Step 2-2: test_tts.py — TTS純粋ロジック
- `_convert_lang_tags()`: 言語タグ変換（`<en>text</en>` → TTS形式）
- `_get_tts_style()`: 言語モード連動のスタイル取得
- `synthesize()`: Geminiモック → WAV生成確認
- リトライロジック（3回失敗→例外）
- **目標**: 6-8テスト

#### Step 2-3: test_wsl_path.py 拡張
既存2テスト（resolve_host）に追加：
- `is_wsl()`: /proc/version読み込みモック
- `get_windows_host_ip()`: ip route出力のパース
- `get_wsl_ip()`: hostname -I出力のパース
- `to_windows_path()`: パス変換（スペース・日本語）
- **目標**: 6-8テスト追加

### フェーズ3: 非同期サービス

#### Step 3-1: test_git_watcher.py
- subprocessモックでコミット検出
- バッチ通知（複数コミット → 1回のコールバック）
- クールダウン60秒の遵守
- start/stopライフサイクル
- **目標**: 6-8テスト

#### Step 3-2: test_twitch_api.py
- aiohttpモック（またはhttpx.AsyncClient）でHTTPレスポンス偽装
- `get_broadcaster_id()` のキャッシュ動作
- `get_channel_info()` のレスポンスパース
- エラーハンドリング（401, 404, 500）
- **目標**: 6-8テスト

#### Step 3-3: test_topic_talker.py
- トピック設定・クリア
- アイドル判定（`should_speak()`）
- ローテーション条件
- **目標**: 5-7テスト

### フェーズ4: APIエンドポイント

#### Step 4-1: FastAPI TestClient フィクスチャ
- `conftest.py` に `client` フィクスチャ追加
- 全state依存をモック化

#### Step 4-2: 各ルートのテスト
- `test_api_character.py`: キャラクター設定 GET/POST
- `test_api_topic.py`: トピック管理 CRUD
- `test_api_stream_control.py`: volume, scene, status
- **目標**: ルートあたり4-6テスト

## 完了時の目標

| 指標 | 現在 | 目標 |
|------|------|------|
| テスト数 | 39 | 100+ |
| テスト対象モジュール | 5 | 12+ |
| DB操作のテスト | 0 | 20+ |
| APIエンドポイントテスト | 0 | 15+ |
| pre-commit実行時間 | 0.7秒 | 3秒以内 |

## リスク

- **グローバルstate干渉**: `scripts/state.py` のグローバル変数 → monkeypatchで隔離
- **非同期テストの不安定性**: asyncioタイマー依存テスト → `asyncio.sleep` をモック or freezegun
- **import副作用**: 一部モジュールがimport時にDBアクセス → conftest.pyのスタブで対応
- **pre-commit時間増加**: テスト100+でも3秒以内を目標（超えたら `-m "not slow"` で分離）

## 実行方法

```bash
# 全テスト
pytest

# カバレッジレポート
pytest --cov=src --cov=scripts --cov-report=html

# 特定テストのみ
pytest tests/test_db.py -v
pytest tests/test_ai_responder.py -v

# 遅いテスト除外
pytest -m "not slow"
```
