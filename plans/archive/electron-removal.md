# Phase 8: Electron完全削除 ✅

## 背景

C#ネイティブ配信アプリ（win-native-app/）がPhase 1-7で完成・安定稼働しており、Electronアプリ（win-capture-app/）はフォールバックとしてのみ残存している。`USE_NATIVE_APP=1`（デフォルト）で常にネイティブアプリが使われる状態。Electronコードを完全に削除してコードベースを簡素化する。

## 影響範囲サマリ

| 対象 | 操作 | 行数影響 |
|------|------|---------|
| `win-capture-app/` | **ディレクトリ削除** | 全ファイル（main.js 1585行等） |
| `scripts/routes/capture.py` | **大幅削除** | 1362行 → ~500行（約860行削除） |
| `scripts/routes/stream_control.py` | **簡素化** | Electron分岐削除 |
| `static/index.html` | **UI要素削除** | Electronビルド/起動UI |
| `static/broadcast.html` | **死コード削除** | window.audioCapture/captureReceiver |
| `.env.example` | **設定削除** | USE_NATIVE_APP |
| `.gitignore` | **行削除** | win-capture-app関連3行 |
| `CLAUDE.md` | **更新** | ディレクトリ構成・説明 |
| `README.md` | **更新** | Electron説明・セットアップ |
| `plans/native-implementation.md` | **ステータス更新** | Phase 8完了 |

## 実装ステップ

### Step 1: win-capture-app/ ディレクトリ削除

```
rm -rf win-capture-app/
```

対象ファイル: main.js, preload.js, broadcast-preload.js, capture.html, capture-renderer.js, package.json, build.sh, scripts/download-ffmpeg.sh, ffmpeg/

### Step 2: capture.py 大幅リファクタ

**ファイル:** `scripts/routes/capture.py` (1362行 → ~500行)

**削除する要素:**
- docstring「Electronアプリの管理」→「Windows配信アプリ経由のウィンドウキャプチャ」
- `_APP_DIR`, `_EXE_PATH`, `_SOURCE_FILES`, `_ASAR_PATH` (行30-36)
- `_build_state`, `_build_lock`, `_BUILD_LOG_PATH` (行38-47)
- `_log_build()` (行50-63)
- `_needs_build()`, `_save_build_hash()` (行66-84)
- `_fix_dist_permissions()` (行86-123)
- `_needs_asar_update()`, `_update_asar()` (行126-204)
- `_run_build()` (行207-266)
- `_deploy_to_windows()` (行435-470)
- `_launch_electron()` (行473-490)
- `_wait_for_server()` (行493-503)
- `capture_launch()` endpoint (行506-551)
- `capture_shutdown()` endpoint (行554-564)
- ワンクリックプレビュー全体 (行567-843)
- プレビューウィンドウAPI (行846-882)
- `capture_build()`, `capture_build_log()` endpoints (行414-432)
- `_capture_proc` 変数

**削除する不要import:**
- `shutil` (Electronデプロイ専用)
- `threading` (ビルド/ワンクリックロック専用)
- `subprocess` (Electronビルド/起動専用)

**保持する要素:**
- `CAPTURE_PORT`, `_capture_base_url()`, `_capture_ws_url()`
- WebSocketクライアント: `_ensure_capture_ws()`, `_read_capture_ws()`, `_ws_request()`
- `_PATH_TO_ACTION`, `_proxy_request()`
- `capture_status()` (簡素化: ビルド状態なし)
- `capture_windows()`
- 全キャプチャ操作API (start/stop/sources/layout)
- DB管理 (capture sources, saved configs)
- スクリーンショットAPI
- ストリーム制御API (`/api/capture/stream/*`)

**`capture_status()`の簡素化:**
```python
# Before: ビルド状態 + Electron状態
result = {"build": dict(_build_state)}

# After: アプリ接続状態のみ
try:
    data = await _proxy_request("GET", "/status")
    return {"running": True, **data}
except Exception:
    return {"running": False}
```

### Step 3: stream_control.py 簡素化

**ファイル:** `scripts/routes/stream_control.py` (417行)

**削除:**
- `_use_native_app()` 関数 (行25-27)
- `_launch_electron_app()` 関数 (行96-126)
- `capture_preview_oneclick`, `capture_preview_oneclick_status` のimport (行36-37)

**変更:**
- docstring: 「C#ネイティブ or Electron」→「Windows配信アプリ経由でTwitch配信」
- `_ensure_capture_app()`: Electron分岐削除、常にネイティブ（`_launch_native_app()`直接呼び出し）
- `broadcast_go_live()` docstring: Electron言及削除
- `broadcast_diag()`: `_use_native_app()` 参照削除、app_type固定
- `broadcast_status()`: `native_app` フィールド削除

### Step 4: index.html UI削除

**ファイル:** `static/index.html`

**削除するUI要素:**
- 「サーバー起動」ボタン (`captureLaunch()`)
- 「サーバー停止」ボタン (`captureShutdown()`)
- ビルド進捗表示 (`#capture-build-status`)
- 「ワンクリックプレビュー」ボタン (`previewOneClick()`)

**削除するJS関数:**
- `captureLaunch()`
- `captureShutdown()`
- `captureRefreshStatus()` とビルドポーリング
- `previewOneClick()` と進捗ポーリング
- `_captureBuildPolling`, `_stageLabels` 変数

### Step 5: broadcast.html Electron IPC死コード削除

**ファイル:** `static/broadcast.html`

**削除:**
- `_electronAudioCtx` 変数
- `setupElectronAudioCapture()` 関数全体
- `window.audioCapture` 参照箇所（TTS/BGM再生通知IPC）
- `setupDirectCapture()` 関数全体
- `window.captureReceiver` 参照箇所（フレーム受信IPC）
- 初期化での `setupDirectCapture()` 呼び出し

**理由:** ネイティブアプリではWebView2 JS injectionでキャプチャ追加、WASAPIで音声キャプチャ。broadcast-preload.jsのIPC APIは使われない。

### Step 6: 設定ファイル更新

**.env.example:**
- `USE_NATIVE_APP=1` 行と関連コメント削除

**.gitignore:**
- `win-capture-app/node_modules/` 削除
- `win-capture-app/package-lock.json` 削除
- `win-capture-app/dist/` 削除

### Step 7: ドキュメント更新

**CLAUDE.md:**
- ディレクトリ構成から `win-capture-app/` 削除
- 「Electron配信パイプライン」→「C#ネイティブ配信アプリ」に統一
- WSL2環境の説明更新

**README.md:**
- Electron関連のセットアップ手順削除
- アーキテクチャ説明をネイティブアプリに更新

**plans/native-implementation.md:**
- Phase 8ステータスを「完了」に更新

### Step 8: エラーメッセージ修正

capture.py内の「Electronに接続できません」等のメッセージを「配信アプリに接続できません」に統一。

## 削除しないもの（注意）

- `websockets` パッケージ (requirements.txt) - `_ws_request()`で引き続き使用
- `/api/capture/stream/*` エンドポイント - stream_control.pyと重複するが、既存の呼び出し元がある可能性
- `_capture_base_url()`, `_capture_ws_url()` - ネイティブアプリとの通信で使用
- `src/wsl_path.py` の `get_windows_host_ip()` - ネイティブアプリのIPアドレス取得で使用

## 検証手順

1. **サーバー起動確認:**
   ```bash
   curl -s http://localhost:8080/api/status
   curl -s http://localhost:8080/api/todo
   ```

2. **API疎通確認:**
   ```bash
   curl -s http://localhost:8080/api/capture/status    # {"running": false}
   curl -s http://localhost:8080/api/broadcast/status   # native_appフィールドなし
   ```

3. **Web UI確認:**
   - index.htmlにElectronビルド/起動ボタンが表示されないこと
   - キャプチャタブのウィンドウ一覧・操作が正常であること

4. **broadcast.html確認:**
   - ブラウザコンソールにElectron関連エラーが出ないこと
   - WebSocket接続が正常であること

5. **Python import確認:**
   ```bash
   python -c "from scripts.routes.capture import router"
   python -c "from scripts.routes.stream_control import router"
   ```

6. **Go Live動線確認（ネイティブアプリ起動時）:**
   - POST /api/broadcast/go-live が正常に動作すること

## ステータス
- 作成日: 2026-03-15
- 状態: 完了
