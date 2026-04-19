# クライアント動画撮影機能

## ステータス: 承認済み（実装中）

## 背景

現在のC#ネイティブ配信アプリ（`win-native-app/`）は、配信出力をFFmpeg経由でRTMP（Twitch）に直接送るのみで、ローカルにファイル保存する手段がない。

以下のようなユースケースで、Twitchに流さずローカル録画したい:

- **切り抜き素材**: 配信予定のコンテンツをあとからX/YouTubeショート用に編集する
- **検証・デバッグ**: 字幕・音声・レイアウトの検証を、配信せずに再現・確認する
- **オフラインテスト**: broadcast.htmlの出力を録って見返す
- **アーカイブ**: Twitchに流す前にローカルで保存しておく

### 前提条件（重要）

- **配信と録画は排他**: 配信中は録画できない、録画中は配信できない
- → 既存のFFmpegパイプラインの**出力先を切り替える**だけで済む（並列エンコード不要）
- → 既存コードへの改変を最小化できる

## アーキテクチャ方針（アップロード方式）

FFmpegは**Windows側ローカル**にMP4を書き、録画停止後にC#が**Pythonサーバへアップロード**する。
リポジトリ内 `videos/` に最終保存することで Python が唯一のオーナーになる。

```
録画中:         C#(Windows) ──FFmpeg───▶ %LOCALAPPDATA%\AITwitchCast\recordings\xxx.mp4
                                               │
録画停止→      C# ──HTTP POST stream───▶ Python(WSL) ──▶ <repo>/videos/xxx.mp4
                                               │
アップロード成功後:                         7日経過で C# 側ローカル一時ファイルを gc
```

### この方式を選んだ理由

| | C#が提供(現行プラン) | WSL直書き(9P) | **アップロード方式** |
|---|---|---|---|
| 録画中のI/O | Windows native | 9P経由（遅い可能性） | **Windows native** |
| ファイルの最終所有者 | C#アプリ | WSL | **Pythonサーバ（唯一）** |
| 管理画面のDL/削除 | HTTPプロキシ必須 | ローカルFS | **ローカルFS（簡単）** |
| 管理画面のエラーケース | C#未起動で閲覧不可 | 常時OK | **常時OK** |

## 確定事項（決定済み）

| 項目 | 決定内容 |
|------|---------|
| 保存先（最終） | `<repo>/videos/broadcast_YYYYMMDD_HHmmss.mp4`（WSL側） |
| 録画一時領域（C#側） | `%LOCALAPPDATA%\AITwitchCast\recordings\` |
| ビットレート | 配信と同じ（2500k） |
| インライン再生（管理画面） | **なし**（DL/削除のみ） |
| 録画→配信ワンボタン切替 | **なし**（Stop Rec → Go Live の2ステップ） |
| アップロード中の挙動 | **次の録画はブロック**（Rec不可、アップロード完了までStandby復帰しない） |
| アップロード進捗UI | **表示する**（%とMB/MB） |
| アップロード失敗時 | ローカル一時ファイル保持＋UIに「再送」ボタン |
| ローカル一時ファイル保持 | **7日** (起動時/Stop Rec時にgc。失敗分は自動削除しない) |

## 要件

### 必須
1. **排他動作**: Standby状態から「配信モード」「録画モード」のいずれかを開始。両立しない
2. **録画出力**: MP4（H.264 + AAC）をローカルファイルに保存。ファイル名にタイムスタンプ
3. **録画内容**: 配信時と同じ合成結果（broadcast.html全体 + キャプチャウィンドウ + TTS + BGM）
4. **アップロード**: 録画停止→MP4 finalize→Pythonサーバに POST で転送→成功後はサーバ側が唯一のオーナー
5. **録画操作UI（クライアント側）**: control-panel.html の Stream タブに「● Rec / ■ Stop Rec」追加。録画中は赤点滅＋経過時間＋ファイルサイズ表示。アップロード中は `アップロード中…(50%)`。配信中はRec無効、録画/アップロード中はGo Live無効
6. **整合性**: UI側でボタン非活性 + サーバー側でも409 Conflictで検証
7. **録画ファイル管理UI（管理画面側）**: `static/index.html` に「録画」タブ新設。録画済みファイル一覧表示・ダウンロード・削除ができる。管理画面には録画中ステータスや操作ボタンは置かない

## 実装ステップ

### Phase 1: 出力モードの切り替え

**目的**: `FfmpegProcess` が RTMP とファイル両方を出せるようにする。

1. `StreamConfig` に出力モードを追加
   - `enum OutputMode { Rtmp, File }`
   - `OutputMode Mode { get; set; } = OutputMode.Rtmp`
   - `string? OutputPath { get; set; }` — ファイルモード時の保存先（絶対パス）
2. `FfmpegProcess.StartAsync()` の最終出力引数を分岐
   - RTMPモード: 現状維持（`-f flv -flvflags no_duration_filesize "{rtmp}"`）
   - Fileモード: `-f mp4 -movflags +faststart+frag_keyframe "{path}"`
3. ファイルモードでは低遅延系フラグを外す（録画画質優先）
   - `-flags +low_delay`、`-fflags +nobuffer`、`-flush_packets 1` を除去
   - `-g`（GOP）は配信と同じでOK（seekabilityのため短め推奨）

### Phase 2: 録画制御の MainForm 側実装

**目的**: `StartStreamingWithKeyAsync()` と対になる `StartRecordingAsync()` を追加。

1. `MainForm` に `StartRecordingAsync(RecordConfig cfg)` 追加
   - キャプチャ未開始時はエラー（配信と同じガード）
   - `StreamConfig` を作り `Mode = File, OutputPath = <生成パス>` で `FfmpegProcess` を起動
   - 音声ジェネレータ開始・フレーム結線・BGMデコードは `StartStreamingWithKeyAsync` と共通化（`StartPipelineAsync(config)` に抽出）
2. `StopRecordingAsync()` 追加 — FFmpeg停止 → 音声ジェネレータ停止 → フレーム結線解除 → **アップロード開始**
3. **状態の一元管理**: `enum PipelineState { Standby, Streaming, Recording, Uploading }` を導入
   - `Uploading` 中は Standby でも Recording でもない独立した状態（次の録画・配信を両方ブロック）
   - 違反時は `InvalidOperationException`（API は 409 Conflict）
4. ファイル名生成: `broadcast_yyyyMMdd_HHmmss.mp4`（ローカルタイム）
5. ローカル一時ディレクトリが存在しなければ作成（`%LOCALAPPDATA%\AITwitchCast\recordings\`）

### Phase 3a: C#側 HTTPエンドポイント（録画操作）

- `POST /record/start` — body: `{}` （省略時はデフォルト、将来拡張のためJSONで受ける）
- `POST /record/stop` — 返値は即時（アップロードは非同期）
- `GET /record/status` — `{ state, elapsed_sec?, file_path?, size_mb?, upload: { progress?, bytes_sent?, bytes_total?, error? } }`
  - `state`: `standby` | `recording` | `uploading` | `upload_failed`
- `POST /record/retry-upload` — 前回失敗したアップロードを再送
- 配信中に `/record/start` を叩いたら 409 Conflict、録画/アップロード中に `/stream/start` を叩いたら 409 Conflict

### Phase 3b: Python側 アップロード受信API

`scripts/routes/recordings.py`（新規）:

- `POST /api/recordings/upload` — C#からのストリーミング受信
  - ヘッダ: `X-Filename: broadcast_YYYYMMDD_HHmmss.mp4`、`Content-Length`, `Content-Type: application/octet-stream`
  - ファイル名検証（`..`/`/`/`\` を拒否、拡張子 `.mp4` のみ）
  - `<repo>/videos/.<filename>.part` にチャンク書き込み→成功時にrename
  - レスポンス: `{ filename, size, saved_path }`
- `GET /api/recordings` — ファイル一覧 `[{ filename, size_bytes, created_at, duration_sec? }, ...]`
  - `videos/` をスキャン、mtime降順
- `GET /videos/{filename}` — StaticFiles で配信（ダウンロード用）
  - `Content-Disposition: attachment` を付けるため routes 側で `FileResponse` を返す形で実装
- `DELETE /api/recordings/{filename}` — ファイル削除
  - ファイル名検証同上
- `scripts/web.py` にルーター登録、`videos/` の存在確認と自動作成

### Phase 3c: C#側アップロード処理

1. `Uploader.cs` 新規 — `HttpClient.PostAsync(url, StreamContent(fileStream))`
2. `Content-Length` を明示、`ProgressStreamContent`（自作）でバイト単位の進捗を内部変数に書き出し
3. `GET /record/status` で進捗参照可能
4. 成功時: ローカル一時ファイルに `.uploaded` マーカーファイル or 内部 DB に記録（7日gc のため）
5. 失敗時: マーカーは書かない（残存＝未アップロード扱い）、`state=upload_failed` に遷移、エラー文字列を保持
6. 再送API: 失敗扱いのファイルを再度アップロード

### Phase 3d: ローカル一時ファイルの7日gc

1. 起動時と Stop Rec 完了後に `%LOCALAPPDATA%\AITwitchCast\recordings\` を走査
2. `.uploaded` マーカーがあり、かつファイルの mtime が **7日以上前** のものを削除（MP4本体＋マーカー）
3. マーカーがないもの（未アップロード扱い）は削除しない

### Phase 4: クライアントUI（control-panel.html）

1. Stream タブに Rec ボタン追加
   ```html
   <div class="btn-row">
     <button class="btn btn-go" id="goLiveBtn" onclick="goLive()">● Go Live</button>
     <button class="btn btn-stop" id="stopBtn" onclick="stopStream()" disabled>■ Stop</button>
     <button class="btn btn-rec" id="recBtn" onclick="toggleRecord()">● Rec</button>
   </div>
   <div class="status" id="recStatus"></div>
   ```
2. 状態表示
   - 録画中: 赤丸点滅＋経過時間 `mm:ss`＋ファイルサイズ `xxx MB`
   - アップロード中: `アップロード中… 45% (230 / 512 MB)` + Rec無効
   - 失敗時: トースト「アップロード失敗: {error}」+「再送」ボタン表示
   - 成功時: トースト「録画保存: {filename} ({size}MB)」
3. **ボタンの排他制御**
   - `streaming`: Rec disabled、Go Liveは「■ Stop」
   - `recording`: Go Live disabled、Recは「■ Stop Rec」
   - `uploading`: Rec & Go Live 両方 disabled
   - `upload_failed`: Rec有効（新規録画可）、「再送」ボタンも表示
   - `standby`: 両方有効
4. 定期ポーリング（`GET /record/status`）で状態更新。録画中は1秒、アップロード中は500ms、待機中は2秒

### Phase 5: 管理画面UI（static/index.html — 録画タブ追加）

1. **タブ追加**: 既存タブ列に「録画」を追加
2. **ファイル一覧テーブル**（並び順: 作成日時降順）
   - カラム: ファイル名 / 作成日時 / 長さ（mm:ss or hh:mm:ss）/ サイズ（MB/GB）/ 操作
   - 操作: ⬇️ ダウンロード（`<a href="/videos/..." download>`）、🗑 削除（`showConfirm()` → DELETE）
   - インライン再生は**なし**
3. **Python API**（前述 Phase 3b でまとめて実装）
4. **クライアント未接続時**: 問題なし（録画済みファイルは Pythonサーバの `videos/` から独立して読める）
5. **共通UI使用**: `showConfirm()` / `showToast()` を使う（CLAUDE.md準拠）

## リスクと対策

| リスク | 影響度 | 対策 |
|--------|--------|------|
| MP4は途中中断に弱い | 中 | `-movflags +faststart+frag_keyframe` を必ず付与 |
| アップロード中のサーバクラッシュで部分ファイル残留 | 中 | `.part` サフィックスで書き込み、成功時にrename。起動時に `.part` を削除 |
| Windows側のディスク逼迫（7日分溜まる） | 低 | UIに「ローカル容量」表示（オプション） + 7日gc |
| 長尺録画で巨大ファイル（数GB）→アップロード時間 | 中 | 進捗表示＋ブロック方式で許容。失敗時再送。将来は `-f segment` 検討 |
| ディレクトリトラバーサル（`../../etc/passwd`） | 高 | 全API で filename を厳格検証（`/`・`\`・`..` 拒否、`.mp4`のみ） |
| アップロード中にC#終了 | 中 | 終了時に失敗扱い、次回起動時 `state=upload_failed` として復元（`.uploaded` マーカー未作成なら未完） |
| 録画中のファイル誤上書き | 低 | タイムスタンプ（秒単位）で十分。同秒多重起動は PipelineState でブロック |

## 段階的リリース案

- **v1**: Phase 1-5 の最小実装。ビットレートは配信と同じ、管理画面に録画タブ（一覧・DL・削除、再生なし）
- **v2**: ディスク監視・長尺分割・インライン再生・録画プリセットなど（別プラン化）

## 関連ファイル

| ファイル | 役割 |
|----------|------|
| `win-native-app/WinNativeApp/Streaming/StreamConfig.cs` | `OutputMode` / `OutputPath` 追加 |
| `win-native-app/WinNativeApp/Streaming/FfmpegProcess.cs` | 最終出力引数を出力モードで分岐 |
| `win-native-app/WinNativeApp/MainForm.cs` | `StartRecordingAsync` / `StopRecordingAsync`、`PipelineState` 管理、パイプライン起動共通化 |
| `win-native-app/WinNativeApp/Streaming/Uploader.cs` | **新規**: アップロード処理＋進捗計測 |
| `win-native-app/WinNativeApp/Server/HttpServer.cs` | `/record/*`、`/record/retry-upload` 追加、排他409応答 |
| `win-native-app/WinNativeApp/control-panel.html` | Rec ボタン・排他UI・状態表示＋進捗 |
| `scripts/routes/recordings.py` | **新規**: アップロード受信・一覧・DL・削除API |
| `scripts/web.py` | `recordings` ルーター登録、`videos/` 作成、`/videos` StaticFiles |
| `static/index.html` | 「録画」タブ追加 |
| `static/js/admin/recordings.js` | **新規**: 一覧表示・ダウンロード・削除処理 |
| `static/js/admin/init.js` | 録画タブ初期化フック |
| `tests/test_api_recordings.py` | **新規**: pytest（一覧・アップロード・削除） |
| `.gitignore` | `videos/` を追記 |

## 参考リソース

- [mp4 faststart+frag_keyframe](https://trac.ffmpeg.org/wiki/Encode/H.264#faststart) — 途中終了耐性
