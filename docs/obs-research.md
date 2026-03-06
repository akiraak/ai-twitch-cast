# OBS Studio 機能調査レポート

## 1. OBS WebSocket API

### 1.1 概要

obs-websocket は OBS Studio をWebSocket経由でリモート制御するためのプロトコル/プラグイン。**OBS Studio 28.0.0以降にはデフォルトで同梱**されており、別途インストールは不要。

- **デフォルトポート**: 4455（設定で変更可能）
- **プロトコル**: WebSocket（JSON または MsgPack エンコーディング対応）
- **サブプロトコル**: `obswebsocket.json`（テキストフレーム）/ `obswebsocket.msgpack`（バイナリフレーム）
- **プロトコルバージョン**: v5.x.x（v4系とは互換性なし）

### 1.2 OpCode（メッセージタイプ）

| OpCode | 名前 | 方向 | 説明 |
|--------|------|------|------|
| 0 | Hello | Server→Client | 接続時の初期メッセージ（RPCバージョン・認証情報含む） |
| 1 | Identify | Client→Server | Hello への応答（セッションパラメータ・認証情報） |
| 2 | Identified | Server→Client | 認証成功の確認 |
| 3 | Reidentify | Client→Server | 認証後のセッションパラメータ更新 |
| 5 | Event | Server→Client | OBSイベント通知 |
| 6 | Request | Client→Server | 個別リクエスト |
| 7 | RequestResponse | Server→Client | リクエストへの応答 |
| 8 | RequestBatch | Client→Server | バッチリクエスト（複数リクエストの一括送信） |
| 9 | RequestBatchResponse | Server→Client | バッチリクエストへの応答 |

全メッセージは `{"op": number, "d": object}` の形式。

### 1.3 接続・認証方法

**接続フロー**:

1. クライアントがWebSocket接続を確立
2. サーバーが `Hello`（OpCode 0）を送信
3. クライアントが `Identify`（OpCode 1）で応答（認証情報含む）
4. サーバーが `Identified`（OpCode 2）で認証成功を通知
5. 以降、リクエスト送信・イベント受信が可能

**認証アルゴリズム**（パスワード設定時）:

1. パスワード + サーバー提供のsaltを結合
2. SHA256ハッシュ → Base64エンコード（= base64 secret）
3. base64 secret + サーバー提供のchallengeを結合
4. SHA256ハッシュ → Base64エンコード（= 最終認証文字列）

### 1.4 リクエストカテゴリ一覧

#### General（一般）

`GetVersion`, `GetStats`, `BroadcastCustomEvent`, `CallVendorRequest`, `GetHotkeyList`, `TriggerHotkeyByName`, `TriggerHotkeyByKeySequence`, `Sleep`

#### Config（設定）

`GetPersistentData`, `SetPersistentData`, `GetSceneCollectionList`, `SetCurrentSceneCollection`, `CreateSceneCollection`, `GetProfileList`, `SetCurrentProfile`, `CreateProfile`, `RemoveProfile`, `GetProfileParameter`, `SetProfileParameter`, `GetVideoSettings`, `SetVideoSettings`, `GetStreamServiceSettings`, `SetStreamServiceSettings`, `GetRecordDirectory`, `SetRecordDirectory`

#### Sources（ソース）

`GetSourceActive`, `GetSourceScreenshot`, `SaveSourceScreenshot`

#### Scenes（シーン）

`GetSceneList`, `GetGroupList`, `GetCurrentProgramScene`, `SetCurrentProgramScene`, `GetCurrentPreviewScene`, `SetCurrentPreviewScene`, `CreateScene`, `RemoveScene`, `SetSceneName`, `GetSceneSceneTransitionOverride`, `SetSceneSceneTransitionOverride`

#### Inputs（入力）

`GetInputList`, `GetInputKindList`, `GetSpecialInputs`, `CreateInput`, `RemoveInput`, `SetInputName`, `GetInputDefaultSettings`, `GetInputSettings`, `SetInputSettings`, `GetInputMute`, `SetInputMute`, `ToggleInputMute`, `GetInputVolume`, `SetInputVolume`, `GetInputAudioBalance`, `SetInputAudioBalance`, `GetInputAudioSyncOffset`, `SetInputAudioSyncOffset`, `GetInputAudioMonitorType`, `SetInputAudioMonitorType`, `GetInputAudioTracks`, `SetInputAudioTracks`, `GetInputDeinterlaceMode`, `SetInputDeinterlaceMode`, `GetInputDeinterlaceFieldOrder`, `SetInputDeinterlaceFieldOrder`, `GetInputPropertiesListPropertyItems`, `PressInputPropertiesButton`

#### Transitions（トランジション）

`GetTransitionKindList`, `GetSceneTransitionList`, `GetCurrentSceneTransition`, `SetCurrentSceneTransition`, `SetCurrentSceneTransitionDuration`, `SetCurrentSceneTransitionSettings`, `GetCurrentSceneTransitionCursor`, `TriggerStudioModeTransition`, `SetTBarPosition`

#### Filters（フィルタ）

`GetSourceFilterKindList`, `GetSourceFilterList`, `GetSourceFilterDefaultSettings`, `CreateSourceFilter`, `RemoveSourceFilter`, `SetSourceFilterName`, `GetSourceFilter`, `SetSourceFilterIndex`, `SetSourceFilterSettings`, `SetSourceFilterEnabled`

#### Scene Items（シーンアイテム）

`GetSceneItemList`, `GetGroupSceneItemList`, `GetSceneItemId`, `GetSceneItemSource`, `CreateSceneItem`, `RemoveSceneItem`, `DuplicateSceneItem`, `GetSceneItemTransform`, `SetSceneItemTransform`, `GetSceneItemEnabled`, `SetSceneItemEnabled`, `GetSceneItemLocked`, `SetSceneItemLocked`, `GetSceneItemIndex`, `SetSceneItemIndex`, `GetSceneItemBlendMode`, `SetSceneItemBlendMode`

#### Outputs（出力）

`GetVirtualCamStatus`, `ToggleVirtualCam`, `StartVirtualCam`, `StopVirtualCam`, `GetReplayBufferStatus`, `ToggleReplayBuffer`, `StartReplayBuffer`, `StopReplayBuffer`, `SaveReplayBuffer`, `GetLastReplayBufferReplay`, `GetOutputList`, `GetOutputStatus`, `ToggleOutput`, `StartOutput`, `StopOutput`, `GetOutputSettings`, `SetOutputSettings`

#### Stream（配信）

`GetStreamStatus`, `ToggleStream`, `StartStream`, `StopStream`, `SendStreamCaption`

#### Record（録画）

`GetRecordStatus`, `ToggleRecord`, `StartRecord`, `StopRecord`, `ToggleRecordPause`, `PauseRecord`, `ResumeRecord`, `SplitRecordFile`, `CreateRecordChapter`

#### Media Inputs（メディア入力）

`GetMediaInputStatus`, `SetMediaInputCursor`, `OffsetMediaInputCursor`, `TriggerMediaInputAction`

#### UI（ユーザーインターフェース）

`GetStudioModeEnabled`, `SetStudioModeEnabled`, `OpenInputPropertiesDialog`, `OpenInputFiltersDialog`, `OpenInputInteractDialog`, `GetMonitorList`, `OpenVideoMixProjector`, `OpenSourceProjector`

### 1.5 イベントカテゴリ一覧

#### General Events

`ExitStarted`, `VendorEvent`, `CustomEvent`

#### Config Events

`CurrentSceneCollectionChanging`, `CurrentSceneCollectionChanged`, `SceneCollectionListChanged`, `CurrentProfileChanging`, `CurrentProfileChanged`, `ProfileListChanged`

#### Scenes Events

`SceneCreated`, `SceneRemoved`, `SceneNameChanged`, `CurrentProgramSceneChanged`, `CurrentPreviewSceneChanged`, `SceneListChanged`

#### Inputs Events

`InputCreated`, `InputRemoved`, `InputNameChanged`, `InputSettingsChanged`, `InputActiveStateChanged`, `InputShowStateChanged`, `InputMuteStateChanged`, `InputVolumeChanged`, `InputAudioBalanceChanged`, `InputAudioSyncOffsetChanged`, `InputAudioTracksChanged`, `InputAudioMonitorTypeChanged`, `InputVolumeMeters`

#### Transitions Events

`CurrentSceneTransitionChanged`, `CurrentSceneTransitionDurationChanged`, `SceneTransitionStarted`, `SceneTransitionEnded`, `SceneTransitionVideoEnded`

#### Filters Events

`SourceFilterListReindexed`, `SourceFilterCreated`, `SourceFilterRemoved`, `SourceFilterNameChanged`, `SourceFilterSettingsChanged`, `SourceFilterEnableStateChanged`

#### Scene Items Events

`SceneItemCreated`, `SceneItemRemoved`, `SceneItemListReindexed`, `SceneItemEnableStateChanged`, `SceneItemLockStateChanged`, `SceneItemSelected`, `SceneItemTransformChanged`

#### Outputs Events

`StreamStateChanged`, `RecordStateChanged`, `RecordFileChanged`, `ReplayBufferStateChanged`, `VirtualcamStateChanged`, `ReplayBufferSaved`

#### Media Inputs Events

`MediaInputPlaybackStarted`, `MediaInputPlaybackEnded`, `MediaInputActionTriggered`

#### UI Events

`StudioModeStateChanged`, `ScreenshotSaved`

### 1.6 対応クライアントライブラリ

| 言語 | ライブラリ名 | 備考 |
|------|------------|------|
| **Python 3.10+** | obsws-python | 同期型、pip install obsws-python |
| **Python 3.7+** | simpleobsws | 非同期（asyncio）対応 |
| **JavaScript/TypeScript** | obs-websocket-js | TypeScript型定義付き、Node.js/ブラウザ対応 |
| **Go** | goobs | |
| **Rust** | obws | |
| **Java** | obs-websocket-java | |
| **Dart/Flutter** | obs_websocket | |

#### Python（obsws-python）使用例

```python
import obsws_python as obs

# 接続
cl = obs.ReqClient(host='localhost', port=4455, password='mystrongpass', timeout=3)

# シーン切替
cl.set_current_program_scene("BRB")

# ミュートトグル
cl.toggle_input_mute('Mic/Aux')

# イベント監視
client = obs.EventClient()
def on_scene_created(data):
    print(data.attrs())
client.callback.register(on_scene_created)
```

#### JavaScript/TypeScript（obs-websocket-js）使用例

```typescript
import OBSWebSocket from 'obs-websocket-js';

const obs = new OBSWebSocket();
await obs.connect('ws://localhost:4455', 'password');

// シーン切替
await obs.call('SetCurrentProgramScene', { sceneName: 'Gameplay' });

// イベント監視
obs.on('CurrentProgramSceneChanged', (event) => {
  console.log('Scene changed to', event.sceneName);
});
```

---

## 2. シーン管理

### 2.1 シーンの作成・削除・切替

| 操作 | WebSocketリクエスト | 説明 |
|------|-------------------|------|
| シーン一覧取得 | `GetSceneList` | 全シーンのリストとインデックスを取得 |
| シーン作成 | `CreateScene` | 新しいシーンを作成 |
| シーン削除 | `RemoveScene` | 指定シーンを削除 |
| シーン名変更 | `SetSceneName` | シーン名を変更 |
| プログラムシーン取得 | `GetCurrentProgramScene` | 現在の出力シーンを取得 |
| プログラムシーン切替 | `SetCurrentProgramScene` | プログラムシーンを切替 |
| グループ一覧 | `GetGroupList` | シーン内のグループ一覧を取得 |

### 2.2 シーンコレクション

シーンコレクションは、シーン・ソース・その設定をまとめた設定セット。

| 操作 | WebSocketリクエスト |
|------|-------------------|
| コレクション一覧取得 | `GetSceneCollectionList` |
| コレクション切替 | `SetCurrentSceneCollection` |
| コレクション作成 | `CreateSceneCollection` |

- JSON形式で保存される
- アセットファイルのパスは絶対パスで保存されるため注意

### 2.3 スタジオモード（プログラム/プレビュー）

プレビュー画面とプログラム（配信出力）画面の2画面構成。トランジション実行前にプレビューで確認可能。

| 操作 | WebSocketリクエスト |
|------|-------------------|
| スタジオモード有効/無効取得 | `GetStudioModeEnabled` |
| スタジオモード有効/無効設定 | `SetStudioModeEnabled` |
| プレビューシーン取得 | `GetCurrentPreviewScene` |
| プレビューシーン設定 | `SetCurrentPreviewScene` |
| トランジション実行 | `TriggerStudioModeTransition` |
| Tバー位置設定 | `SetTBarPosition` |

---

## 3. ソース（Source）管理

### 3.1 利用可能なソースタイプ一覧

| ソースタイプ | 内部Kind名 | 説明 |
|------------|-----------|------|
| ブラウザソース | `browser_source` | Webページをレンダリング。アラート・チャットボックス等 |
| 画像 | `image_source` | 静止画像（BMP, TGA, PNG, JPEG, GIF対応） |
| 画像スライドショー | `slideshow` | 複数画像の自動切替表示 |
| メディアソース | `ffmpeg_source` | 動画・音声ファイル（MP4, MKV, WebM / MP3, AAC, WAV等） |
| VLCソース | `vlc_source` | VLCベースのメディア再生（プレイリスト対応） |
| テキスト（GDI+） | `text_gdiplus` | カスタマイズ可能なテキスト表示（Windows） |
| テキスト（FreeType2） | `text_ft2_source` | テキスト表示（Linux/Mac） |
| 映像キャプチャデバイス | `dshow_input` / `av_capture_input` | Webカメラ・キャプチャカード |
| ゲームキャプチャ | `game_capture` | GPU直接キャプチャ（Windows専用） |
| 画面キャプチャ | `monitor_capture` | ディスプレイ全体のキャプチャ |
| ウィンドウキャプチャ | `window_capture` | 特定ウィンドウのキャプチャ |
| 色ソース | `color_source_v3` | 単色の矩形表示 |
| 音声入力キャプチャ | `wasapi_input_capture` | マイク等の音声入力（Windows） |
| 音声出力キャプチャ | `wasapi_output_capture` | デスクトップ音声（Windows） |
| アプリ音声キャプチャ | `wasapi_process_output_capture` | 特定アプリの音声のみキャプチャ |

### 3.2 ソースの追加・削除・表示/非表示

| 操作 | WebSocketリクエスト | 説明 |
|------|-------------------|------|
| ソース作成 | `CreateInput` | 新しい入力をシーンに追加 |
| ソース削除 | `RemoveInput` | 入力を削除 |
| シーンアイテム追加 | `CreateSceneItem` | 既存ソースをシーンに配置 |
| シーンアイテム削除 | `RemoveSceneItem` | シーンからアイテムを除去 |
| アイテム複製 | `DuplicateSceneItem` | アイテムを複製 |
| 表示/非表示取得 | `GetSceneItemEnabled` | 表示状態を取得 |
| 表示/非表示設定 | `SetSceneItemEnabled` | 表示/非表示を切替 |
| ロック状態制御 | `GetSceneItemLocked` / `SetSceneItemLocked` | 位置ロック制御 |
| 描画順序設定 | `SetSceneItemIndex` | Zオーダーを変更 |

### 3.3 ソースプロパティの動的変更

`GetInputSettings` / `SetInputSettings` で各ソースの設定をJSON形式で動的に変更可能。

**変更可能なプロパティの例**:

- **ブラウザソース**: URL, 幅, 高さ, CSS, FPS
- **画像ソース**: ファイルパス
- **テキストソース**: テキスト内容, フォント, 色, サイズ
- **メディアソース**: ファイルパス, ループ設定, 再生速度
- **映像キャプチャ**: 解像度, FPS, デバイス選択

### 3.4 ソースの変換（位置・サイズ・回転）

`GetSceneItemTransform` / `SetSceneItemTransform` で制御可能。

| プロパティ | 説明 |
|-----------|------|
| positionX / positionY | シーン内の位置（ピクセル） |
| scaleX / scaleY | 拡大縮小率 |
| rotation | 回転角度（度数、時計回り） |
| cropTop / cropRight / cropBottom / cropLeft | 各辺のクロップ |
| boundsType | バウンディングボックスの種類 |
| boundsWidth / boundsHeight | バウンディングボックスのサイズ |
| alignment | アラインメント |

**バウンディングボックスタイプ**:

- `OBS_BOUNDS_NONE` - なし
- `OBS_BOUNDS_STRETCH` - 引き伸ばし
- `OBS_BOUNDS_SCALE_INNER` - 内側にフィット
- `OBS_BOUNDS_SCALE_OUTER` - 外側にフィット
- `OBS_BOUNDS_SCALE_TO_WIDTH` - 幅に合わせる
- `OBS_BOUNDS_SCALE_TO_HEIGHT` - 高さに合わせる
- `OBS_BOUNDS_MAX_ONLY` - 最大値のみ制限

**ブレンドモード**: `OBS_BLEND_NORMAL`, `OBS_BLEND_ADDITIVE`, `OBS_BLEND_SUBTRACT`, `OBS_BLEND_SCREEN`, `OBS_BLEND_MULTIPLY`, `OBS_BLEND_LIGHTEN`, `OBS_BLEND_DARKEN`

---

## 4. フィルタ（Filter）

### 4.1 映像フィルタ

| フィルタ名 | 説明 |
|-----------|------|
| Apply LUT | ルックアップテーブルによるカラーグレーディング |
| Chroma Key | グリーンスクリーン等の色除去（クロマキー合成） |
| Color Correction | 色補正（色相、コントラスト、彩度、ガンマ、不透明度等） |
| Color Key | グラフィックス用の色除去 |
| Crop/Pad | クロップまたはパディング |
| Image Mask/Blend | 画像マスク適用またはブレンド |
| Luma Key | 明度ベースのキー除去 |
| Render Delay | レンダリング遅延（音声/映像同期用） |
| Scaling/Aspect Ratio | サイズ・アスペクト比の変更 |
| Scroll | 無限スクロール（マーキーテキスト、繰り返し背景用） |
| Sharpen | シャープネス強調 |

### 4.2 音声フィルタ

| フィルタ名 | 説明 |
|-----------|------|
| Compressor | 音声ピーク制御・ダッキング |
| Expander | 背景音の低減 |
| Gain | 音量ブースト |
| Invert Polarity | 位相逆転 |
| Limiter | 音声歪み防止 |
| Noise Gate | バックグラウンドノイズ遮断 |
| Noise Suppression | ノイズ除去 |
| VST 2.x Plugin | VSTプラグインによる音声フィルタリング |

### 4.3 フィルタのプログラム制御

| 操作 | WebSocketリクエスト |
|------|-------------------|
| フィルタ種類一覧取得 | `GetSourceFilterKindList` |
| フィルタ一覧取得 | `GetSourceFilterList` |
| フィルタ作成 | `CreateSourceFilter` |
| フィルタ削除 | `RemoveSourceFilter` |
| フィルタ設定取得 | `GetSourceFilter` |
| フィルタ設定変更 | `SetSourceFilterSettings` |
| フィルタ有効/無効 | `SetSourceFilterEnabled` |
| フィルタ名変更 | `SetSourceFilterName` |
| フィルタ順序変更 | `SetSourceFilterIndex` |
| デフォルト設定取得 | `GetSourceFilterDefaultSettings` |

---

## 5. 音声制御

### 5.1 ミュート・音量制御

| 操作 | WebSocketリクエスト |
|------|-------------------|
| ミュート状態取得 | `GetInputMute` |
| ミュート設定 | `SetInputMute` |
| ミュートトグル | `ToggleInputMute` |
| 音量取得 | `GetInputVolume` |
| 音量設定 | `SetInputVolume` |
| 音声バランス | `GetInputAudioBalance` / `SetInputAudioBalance` |
| 音声同期オフセット | `GetInputAudioSyncOffset` / `SetInputAudioSyncOffset` |
| 音声トラック設定 | `GetInputAudioTracks` / `SetInputAudioTracks` |

### 5.2 音声モニタリング

| モニタリングタイプ | 説明 |
|------------------|------|
| Monitor Off | モニタリング無効（配信/録画出力のみ） |
| Monitor Only | モニターのみ（配信には含まれない） |
| Monitor and Output | モニターと配信の両方に出力 |

`InputVolumeMeters` イベントでリアルタイムの音声レベルメーターデータを受信可能。

---

## 6. 配信・録画制御

### 6.1 配信

| 操作 | WebSocketリクエスト |
|------|-------------------|
| 配信状態取得 | `GetStreamStatus` |
| 配信開始 | `StartStream` |
| 配信停止 | `StopStream` |
| 配信トグル | `ToggleStream` |
| 字幕送信 | `SendStreamCaption` |

### 6.2 録画

| 操作 | WebSocketリクエスト |
|------|-------------------|
| 録画状態取得 | `GetRecordStatus` |
| 録画開始 | `StartRecord` |
| 録画停止 | `StopRecord` |
| 録画トグル | `ToggleRecord` |
| 録画一時停止 | `PauseRecord` |
| 録画再開 | `ResumeRecord` |
| ファイル分割 | `SplitRecordFile` |
| チャプター作成 | `CreateRecordChapter` |
| 録画ディレクトリ設定 | `GetRecordDirectory` / `SetRecordDirectory` |

### 6.3 配信設定

`GetStreamServiceSettings` / `SetStreamServiceSettings` で配信サービス設定を制御可能。

**推奨エンコーダ設定**:

| 項目 | 推奨値 |
|------|-------|
| エンコーダ | NVENC（NVIDIA）/ AMF（AMD）/ x264（CPU） |
| コーデック | H.264 + AAC |
| レート制御 | CBR（固定ビットレート） |
| キーフレーム間隔 | 2秒 |
| 1080p 60fps | 6,000 - 9,000 kbps |
| 1080p 30fps | 4,500 - 6,000 kbps |
| 720p 30fps | 2,500 - 4,000 kbps |

### 6.4 RTMP/RTMPS

- **RTMP**: 標準ストリーミングプロトコル（ポート1935/TCP）
- **RTMPS**: TLS暗号化RTMP（ポート443/TCP）。Twitchを含む主要サービスが対応
- サーバーURLに `rtmps://` プレフィックスを使用で自動RTMPS接続
- `SetStreamServiceSettings` でサーバーURL・ストリームキーをプログラムから設定可能

---

## 7. トランジション

### 7.1 ビルトイントランジション

| トランジション | 説明 |
|--------------|------|
| Cut | 瞬時切替（アニメーションなし） |
| Fade | フェードイン/フェードアウト |
| Swipe | スワイプ（方向指定可能） |
| Slide | スライド（方向指定可能） |
| Fade to Color | 指定色にフェードしてから切替 |
| Luma Wipe | パターンを使ったワイプ切替 |
| Stinger | 透過動画（MOV/WebM）オーバーレイで切替 |

### 7.2 カスタムトランジション

- **Stinger Transition**: 透過動画を使用。Track Matte Stingerで高度なマスクベーストランジションも可能
- **Move Transition**（プラグイン）: ソースのアニメーション（位置・サイズ・不透明度の補間）
- **Scene as Transition**（プラグイン）: シーン自体をトランジションとして使用

### 7.3 プログラム制御

| 操作 | WebSocketリクエスト |
|------|-------------------|
| トランジション種類一覧 | `GetTransitionKindList` |
| 設定済みトランジション一覧 | `GetSceneTransitionList` |
| 現在のトランジション取得 | `GetCurrentSceneTransition` |
| トランジション設定 | `SetCurrentSceneTransition` |
| トランジション時間設定 | `SetCurrentSceneTransitionDuration` |
| トランジション詳細設定 | `SetCurrentSceneTransitionSettings` |
| 進行状況取得 | `GetCurrentSceneTransitionCursor` |
| スタジオモードトランジション実行 | `TriggerStudioModeTransition` |
| Tバー位置 | `SetTBarPosition`（0.0 - 1.0） |
| シーン別オーバーライド | `GetSceneSceneTransitionOverride` / `SetSceneSceneTransitionOverride` |

---

## 8. その他の重要機能

### 8.1 プロファイル管理

| 操作 | WebSocketリクエスト |
|------|-------------------|
| プロファイル一覧取得 | `GetProfileList` |
| プロファイル切替 | `SetCurrentProfile` |
| プロファイル作成 | `CreateProfile` |
| プロファイル削除 | `RemoveProfile` |
| パラメータ取得/設定 | `GetProfileParameter` / `SetProfileParameter` |

### 8.2 ホットキー

| 操作 | WebSocketリクエスト |
|------|-------------------|
| ホットキー一覧取得 | `GetHotkeyList` |
| ホットキー名で実行 | `TriggerHotkeyByName` |
| キーシーケンスで実行 | `TriggerHotkeyByKeySequence` |

### 8.3 仮想カメラ

OBSの出力をシステムレベルの仮想カメラデバイスとして公開する機能。

| 操作 | WebSocketリクエスト |
|------|-------------------|
| 状態取得 | `GetVirtualCamStatus` |
| 開始 | `StartVirtualCam` |
| 停止 | `StopVirtualCam` |
| トグル | `ToggleVirtualCam` |

### 8.4 リプレイバッファ

直近の指定秒数分の映像をメモリに保持し、任意のタイミングでファイルに保存する機能。

| 操作 | WebSocketリクエスト |
|------|-------------------|
| 状態取得 | `GetReplayBufferStatus` |
| 開始 | `StartReplayBuffer` |
| 停止 | `StopReplayBuffer` |
| トグル | `ToggleReplayBuffer` |
| リプレイ保存 | `SaveReplayBuffer` |
| 最後のリプレイ取得 | `GetLastReplayBufferReplay` |

### 8.5 メディア入力制御

| 操作 | WebSocketリクエスト |
|------|-------------------|
| メディア状態取得 | `GetMediaInputStatus` |
| 再生位置設定 | `SetMediaInputCursor` |
| 再生位置オフセット | `OffsetMediaInputCursor` |
| メディアアクション | `TriggerMediaInputAction` |

**メディアアクション**: PLAY, PAUSE, STOP, RESTART, NEXT, PREVIOUS

### 8.6 スクリーンショット

| 操作 | WebSocketリクエスト |
|------|-------------------|
| スクリーンショット取得 | `GetSourceScreenshot`（Base64画像データ） |
| スクリーンショット保存 | `SaveSourceScreenshot`（ファイル保存） |

### 8.7 主要プラグイン

| プラグイン | カテゴリ | 説明 |
|----------|---------|------|
| StreamFX | 映像効果 | 3Dトランスフォーム、ブラー、シェーダー等の高度な映像効果 |
| Move Transition | トランジション | ソースのアニメーション制御（位置・サイズ・不透明度の補間） |
| Advanced Scene Switcher | 自動化 | 音声レベル、メディア再生、時間等のトリガーで自動シーン切替 |
| NDI Plugin | ネットワーク | NDIによる複数PC間の映像伝送 |
| Scene Collection Manager | 管理 | シーンコレクションのバックアップ・復元 |
| OBS Lua/Python Scripts | 自動化 | スクリプトによるカスタム拡張 |

---

## 9. まとめ: プログラム自動制御の対応状況

| 機能カテゴリ | WebSocket対応 | 備考 |
|------------|:------------:|------|
| シーン管理 | 完全対応 | スタジオモード含む |
| ソース管理 | 完全対応 | 全プロパティの動的変更可能 |
| ソース変換 | 完全対応 | リアルタイムアニメーション可能 |
| フィルタ制御 | 完全対応 | 作成・削除・設定変更・有効/無効 |
| 音声制御 | 完全対応 | ミュート・音量・モニタリング・トラック |
| 配信制御 | 完全対応 | 開始・停止・設定変更 |
| 録画制御 | 完全対応 | 開始・停止・一時停止・ファイル分割 |
| トランジション | 完全対応 | 種類変更・Tバー・シーン別オーバーライド |
| プロファイル管理 | 完全対応 | 作成・削除・切替・パラメータ変更 |
| ホットキー | 完全対応 | 名前またはキーシーケンスで実行 |
| 仮想カメラ | 完全対応 | 開始・停止 |
| リプレイバッファ | 完全対応 | 開始・停止・保存 |
| メディア再生制御 | 完全対応 | 再生・停止・シーク・プレイリスト操作 |

**結論**: OBS Studio の obs-websocket v5 API は、OBS のほぼすべての機能をプログラムから完全に制御可能であり、AI駆動の全自動Twitch配信システムの構築に十分な機能を提供する。

---

## 参考資料

- [obs-websocket Protocol Documentation](https://github.com/obsproject/obs-websocket/blob/master/docs/generated/protocol.md)
- [obs-websocket GitHub Repository](https://github.com/obsproject/obs-websocket)
- [OBS Studio Sources Guide](https://obsproject.com/kb/sources-guide)
- [OBS Studio Filters Guide](https://obsproject.com/kb/filters-guide)
- [obsws-python (PyPI)](https://pypi.org/project/obsws-python/)
- [obs-websocket-js (npm)](https://www.npmjs.com/package/obs-websocket-js)
