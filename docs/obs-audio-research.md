# OBS Studio オーディオ機能調査レポート

OBS Studioのオーディオ機能と、obs-websocket v5によるプログラム制御の包括的な調査。

## 1. オーディオソースの種類

### Audio Input Capture（音声入力キャプチャ）
- マイク、ウェブカメラマイク、ライン入力、キャプチャーカードの音声入力をキャプチャ
- シーンごとにローカルなソースとして追加可能
- Settings → Audio でグローバル入力デバイスとしても設定可能（全シーンに適用）

### Audio Output Capture（音声出力キャプチャ）
- スピーカー、ヘッドセット、モニターなどの出力デバイスの音声をキャプチャ
- 「Desktop Audio」としてグローバルに設定するか、シーンローカルで追加可能

### Media Source Audio（メディアソース音声）
- メディアソース（動画・音声ファイル）に含まれる音声
- メディアソース自体がオーディオ出力を持つ

### Browser Source Audio（ブラウザソース音声）
- ブラウザソースで再生される音声（Web Audio API、HTML5 `<audio>`等）
- 「Control audio via OBS」チェックボックスで、ブラウザ音声をOBSミキサーにルーティング可能
- obs-websocket では `reroute_audio: true` で設定
- 有効にするとミキサーに表示され、音量・モニタリング・トラック割り当てが可能

### Application Audio Capture（アプリケーション音声キャプチャ）
- OBS Studio 28以降、Windows 10 (Version 2004+) / Windows 11で利用可能
- 特定のアプリケーションの音声のみを個別にキャプチャ
- アプリごとに独立したオーディオソースとして追加可能
- ウィンドウが不要（音を出していれば良い）
- OBS 30.1以降: Window Capture / Game Capture にも音声キャプチャオプション追加

## 2. オーディオミキサー

### チャンネル表示
- **モノラル**: 1本のメーター（自動的に左右両方にルーティング）
- **ステレオ**: 2本のメーター（左・右）
- **サラウンド**: Settings → Audio → Channels がステレオ（デフォルト）の場合、自動的にステレオにミックスダウン

### 音量制御
- **フェーダースライダー**: 音量をdB単位で調整
- **ミュートボタン**: 該当ソースの音声を完全にミュート
- 音量は乗数（mul: 0.0〜20.0）またはdB値（-100.0〜26.0）で指定可能

### オーディオモニタリングタイプ
| モニタリングタイプ | 配信/録画出力 | モニタリングデバイス | 用途 |
|---|---|---|---|
| **Monitor Off** | 聞こえる | 聞こえない | 通常のソース（デフォルト） |
| **Monitor Only (mute output)** | 聞こえない | 聞こえる | 自分だけ確認したい音声 |
| **Monitor and Output** | 聞こえる | 聞こえる | 自分も視聴者も聞く音声 |

obs-websocket でのmonitorType値:
- `OBS_MONITORING_TYPE_NONE`
- `OBS_MONITORING_TYPE_MONITOR_ONLY`
- `OBS_MONITORING_TYPE_MONITOR_AND_OUTPUT`

### オーディオトラック（1〜6）
- Track 1: Simple モードのストリーミング・録画で使用（デフォルト）
- Track 1〜6: Advanced モードで全トラック利用可能
- Edit → Advanced Audio Properties で各ソースのトラック割り当てを設定
- 各ソースを0個以上のトラックに割り当て可能
- 用途例: Track 1=配信用ミックス、Track 2=マイクのみ、Track 3=ゲーム音のみ

## 3. 高度なオーディオプロパティ（Advanced Audio Properties）

Audio Mixer の歯車アイコンまたは右クリックからアクセス。全ソースの一覧表で以下を設定:

| 設定項目 | 説明 | obs-websocket対応 |
|---|---|---|
| **Volume (%)** | 音量パーセンテージ | `SetInputVolume` |
| **Balance** | 左右バランス（0.0=左, 0.5=中央, 1.0=右） | `SetInputAudioBalance` |
| **Sync Offset (ms)** | 音声同期オフセット（ミリ秒） | `SetInputAudioSyncOffset` |
| **Audio Monitoring** | モニタリングタイプ（上記3種） | `SetInputAudioMonitorType` |
| **Tracks 1-6** | 各トラックへの出力On/Off | `SetInputAudioTracks` |

## 4. オーディオフィルター

### 内蔵フィルター一覧

| フィルター | filterKind（内部ID） | 機能 |
|---|---|---|
| **Gain** | `gain_filter` | 入力信号の音量を増減 |
| **Noise Suppression** | `noise_suppress_filter_v2` | 背景ノイズ除去（Speex / RNNoise） |
| **Noise Gate** | `noise_gate_filter` | 閾値以下の音声を自動ミュート |
| **Compressor** | `compressor_filter` | 大きい音を圧縮して均一化 |
| **Limiter** | `limiter_filter` | 0dB超えを防止するハードリミッター |
| **Expander** | `expander_filter` | ノイズゲートの高品質版（段階的に減衰） |
| **Upward Compressor** | `upward_compressor_filter` | 小さい音を持ち上げる |
| **Invert Polarity** | `invert_polarity_filter` | 位相を反転 |
| **3-Band EQ** | `eq_filter` | 3バンドイコライザー |
| **VST 2.x Plugin** | `vst_filter` | 外部VSTプラグイン（ReaPlugs等） |

### 推奨フィルター順序
1. Noise Gate / Expander
2. Noise Suppression
3. Compressor
4. Limiter

### Noise Suppressionの方式
- **Speex**: 低CPU使用率、低品質
- **RNNoise**: 高品質、CPU使用率高め（機械学習ベース）

## 5. オーディオルーティング（音声の流れ）

```
[音声ソース] → [ソースフィルター] → [音量/ミュート] → [トラック割り当て]
                                                           ↓
                                                    [Track 1-6]
                                                           ↓
                                              [Output (配信/録画)]
                                              [Monitor (モニタリングデバイス)]
```

- 各ソースは独立したフィルターチェーンを持つ
- フィルター後の音声がミキサーで音量調整される
- トラック割り当てにより配信・録画の出力先を制御
- モニタリング設定により自分への音声ルーティングを制御

## 6. ブラウザソース音声の詳細

### reroute_audio 設定
- ブラウザソースのプロパティ「Control audio via OBS」（`reroute_audio: true`）
- 有効にすると:
  - ブラウザ内の音声がOBSのオーディオパイプラインに入る
  - ミキサーに表示される
  - 音量・モニタリング・フィルター・トラック割り当てが可能
- 無効の場合: 音声はOBSを介さずシステムのデフォルト出力に直接流れる

### 重要な注意点
- `reroute_audio: true` のみでは配信に音声が乗らない場合がある
- Advanced Audio Properties でモニタリングを `Monitor and Output` に設定する必要がある場合あり
- obs-websocketでの設定:
  ```python
  # ブラウザソース作成時
  input_settings = {
      "url": "http://...",
      "reroute_audio": True
  }
  # モニタリング設定
  SetInputAudioMonitorType(inputName="...", monitorType="OBS_MONITORING_TYPE_MONITOR_AND_OUTPUT")
  ```

## 7. obs-websocket v5 オーディオ関連API

### Input Audio Requests（入力オーディオ操作）

| リクエスト | パラメータ | レスポンス | 説明 |
|---|---|---|---|
| `GetInputMute` | `inputName` or `inputUuid` | `inputMuted` (Boolean) | ミュート状態取得 |
| `SetInputMute` | `inputName`, `inputMuted` (Boolean) | - | ミュート状態設定 |
| `ToggleInputMute` | `inputName` | `inputMuted` (Boolean) | ミュートトグル |
| `GetInputVolume` | `inputName` | `inputVolumeMul` (Number), `inputVolumeDb` (Number) | 音量取得 |
| `SetInputVolume` | `inputName`, `inputVolumeMul` or `inputVolumeDb` | - | 音量設定 |
| `GetInputAudioBalance` | `inputName` | `inputAudioBalance` (Number) | バランス取得 |
| `SetInputAudioBalance` | `inputName`, `inputAudioBalance` (Number, 0.0-1.0) | - | バランス設定 |
| `GetInputAudioSyncOffset` | `inputName` | `inputAudioSyncOffset` (Number) | 同期オフセット取得 |
| `SetInputAudioSyncOffset` | `inputName`, `inputAudioSyncOffset` (Number, ms) | - | 同期オフセット設定 |
| `GetInputAudioMonitorType` | `inputName` | `monitorType` (String) | モニタリングタイプ取得 |
| `SetInputAudioMonitorType` | `inputName`, `monitorType` (String) | - | モニタリングタイプ設定 |
| `GetInputAudioTracks` | `inputName` | `inputAudioTracks` (Object) | トラック割り当て取得 |
| `SetInputAudioTracks` | `inputName`, `inputAudioTracks` (Object) | - | トラック割り当て設定 |

**注意**: すべてのリクエストで `inputName` (String) の代わりに `inputUuid` (String) も使用可能。

### Source Filter Requests（ソースフィルター操作）

| リクエスト | パラメータ | レスポンス | 説明 |
|---|---|---|---|
| `GetSourceFilterKindList` | - | `kinds` (Array\<String\>) | 利用可能なフィルター種類一覧 |
| `GetSourceFilterList` | `sourceName` | `filters` (Array\<Object\>) | ソースのフィルター一覧 |
| `GetSourceFilterDefaultSettings` | `filterKind` | `defaultFilterSettings` (Object) | フィルターのデフォルト設定 |
| `CreateSourceFilter` | `sourceName`, `filterName`, `filterKind`, `?filterSettings`, `?filterIndex` | - | フィルター作成 |
| `RemoveSourceFilter` | `sourceName`, `filterName` | - | フィルター削除 |
| `SetSourceFilterName` | `sourceName`, `oldFilterName`, `filterName` | - | フィルター名変更 |
| `GetSourceFilter` | `sourceName`, `filterName` | `filterEnabled`, `filterIndex`, `filterKind`, `filterSettings` | フィルター情報取得 |
| `SetSourceFilterIndex` | `sourceName`, `filterName`, `filterIndex` | - | フィルター順序変更 |
| `SetSourceFilterSettings` | `sourceName`, `filterName`, `filterSettings`, `?overlay` | - | フィルター設定変更 |
| `SetSourceFilterEnabled` | `sourceName`, `filterName`, `filterEnabled` (Boolean) | - | フィルター有効/無効 |

### Audio Events（オーディオイベント）

| イベント | データフィールド | 説明 |
|---|---|---|
| `InputMuteStateChanged` | `inputName`, `inputUuid`, `inputMuted` | ミュート状態変化 |
| `InputVolumeChanged` | `inputName`, `inputUuid`, `inputVolumeMul`, `inputVolumeDb` | 音量変化 |
| `InputAudioBalanceChanged` | `inputName`, `inputUuid`, `inputAudioBalance` | バランス変化 |
| `InputAudioSyncOffsetChanged` | `inputName`, `inputUuid`, `inputAudioSyncOffset` | 同期オフセット変化 |
| `InputAudioTracksChanged` | `inputName`, `inputUuid`, `inputAudioTracks` | トラック割り当て変化 |
| `InputAudioMonitorTypeChanged` | `inputName`, `inputUuid`, `monitorType` | モニタリングタイプ変化 |
| `InputVolumeMeters` | `inputs` (Array\<Object\>) | 全アクティブ入力の音量レベル（50ms間隔、高頻度） |

### inputAudioTracks オブジェクトの形式
```json
{
  "1": true,
  "2": true,
  "3": false,
  "4": false,
  "5": false,
  "6": false
}
```

## 8. プログラム制御の実用例

### ソースの音量をフェードイン/アウト
```python
import asyncio
import obsws_python as obs

# 音量を段階的に変更（フェードイン）
async def fade_in(client, input_name, duration=2.0, steps=20):
    for i in range(steps + 1):
        vol = i / steps  # 0.0 → 1.0
        client.set_input_volume(name=input_name, vol_mul=vol)
        await asyncio.sleep(duration / steps)
```

### BGMソースにコンプレッサーを追加
```python
client.create_source_filter(
    source_name="BGM",
    filter_name="Compressor",
    filter_kind="compressor_filter",
    filter_settings={
        "ratio": 4.0,
        "threshold": -18.0,
        "attack_time": 6,
        "release_time": 60,
        "output_gain": 0.0
    }
)
```

### ブラウザソースの音声を有効化
```python
# ソース作成時にreroute_audioを有効化
client.create_input(
    scene_name="Main",
    input_name="Overlay",
    input_kind="browser_source",
    input_settings={
        "url": "http://...",
        "reroute_audio": True
    }
)
# モニタリングタイプを設定
client.set_input_audio_monitor_type(
    name="Overlay",
    monitor_type="OBS_MONITORING_TYPE_MONITOR_AND_OUTPUT"
)
```

## 参考リンク

- [OBS Audio Sources](https://obsproject.com/kb/audio-sources)
- [OBS Audio Mixer Guide](https://obsproject.com/kb/audio-mixer-guide)
- [OBS Application Audio Capture Guide](https://obsproject.com/kb/application-audio-capture-guide)
- [OBS Noise Suppression Filter](https://obsproject.com/kb/noise-suppression-filter)
- [OBS Filters Guide](https://obsproject.com/kb/filters-guide)
- [obs-websocket v5 Protocol](https://github.com/obsproject/obs-websocket/blob/master/docs/generated/protocol.md)
- [OBS Advanced Recording Guide (Multi Track Audio)](https://obsproject.com/kb/advanced-recording-guide-and-multi-track-audio)
