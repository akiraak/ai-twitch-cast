# 録画モードのAV同期ずれ修正

## ステータス: 実装完了（2026-04-19）／実リップシンク目視確認は未実施

## 背景

`plans/client-video-recording.md` で実装した録画機能で、生成されるMP4の**音と映像がずれる**問題が報告されていた。
配信（Twitch RTMP）では Twitch 側の同期吸収があるため目立たないが、録画ファイルをローカル再生するとズレが顕在化していた。

原因の切り分けは `plans/recording-av-sync-verification.md` で 3 ビルド（default / wallclock / pacer）を比較して完了済み。
結論: **`-use_wallclock_as_timestamps 1`（wallclock）** を採用。

## 原因（検証済み）

現行の映像入力は `-framerate 30 -f rawvideo` で FFmpeg に渡すため、FFmpeg は**フレームに `frame_index × (1/30s)` の PTS** を付ける（到着時刻ではない）。
一方、音声は C# 側の 10ms タイマー + `Environment.TickCount64` で**実時刻レート**で書いている。

この 2 つが別時計のため、WGC キャプチャの実到着レート（平均 30.32fps など、微妙に 30 からズレる）と PTS（30fps 固定）の差が累積し、**50 秒で +533ms の線形ドリフト**が計測された。

映像入力に `-use_wallclock_as_timestamps 1` を付けると FFmpeg は**読み取り実時刻で PTS を打つ**ので、キャプチャレートが揺れてもドリフトが累積せず、ドロップ時も「時間圧縮」ではなく「直前フレームが停止」として表現される。

音声は既に実時間で動いているため、映像 PTS が実時刻に揃えば音声と自動的に同期する。

## 方針

録画モード（`OutputMode.File`）のとき**常に** `-use_wallclock_as_timestamps 1` を映像入力に付与する。配信モード（RTMP）は従来通り（検証対象外・運用実績あり）。

- **音声**: 従来通りの C# 側タイマーベースジェネレータ（TTS + BGM + SE を合成してパイプに書く）を維持。WASAPI Loopback 方式は採用しない（複雑さが増える割に wallclock 単独で AV 同期は成立する）
- **映像**: `OutputMode.File` のとき `-use_wallclock_as_timestamps 1` を付ける
- **切替フラグなし**: 検証用に導入した `VideoTimingMode` enum / `--video-timing` CLI / `VIDEO_TIMING` 環境変数、および Pacer モードの実装はすべて削除

## 実装内容

| ファイル | 変更 |
|----------|------|
| `win-native-app/WinNativeApp/Streaming/FfmpegProcess.cs` | `OutputMode.File` のときに常に `-use_wallclock_as_timestamps 1` を映像入力へ付与。Pacer 実装・`_pacer*` フィールド・`_dupCount` / `DupCount` をすべて削除 |
| `win-native-app/WinNativeApp/Streaming/StreamConfig.cs` | `VideoTimingMode` enum・`VideoTiming` プロパティ・`--video-timing` / `VIDEO_TIMING` パース処理を削除 |
| `stream.sh` | `--video-timing` フラグの Usage / オプション説明を削除。`--av-sync-test` は回帰検証用に残置 |
| `static/av_sync_test.html` | 検証素材として保持（将来の回帰検証に使う） |
| `scripts/verify_av_sync.py` | 計測スクリプトとして保持 |

## 既知のトレードオフ

検証で確認された、wallclock 単独方式に残る軽微な特性:

- **先頭 -700ms の定数オフセット**: FFmpeg 初期化中にパイプへ書いた初期黒フレームが init 完了時刻で刻印され、後続の実フレームと時間的に詰まるため、最初のフラッシュが理想より 700ms 早く見える。2秒目以降は ±1 フレームの量子化のみで追従するため、録画長に依存せず定数。
- 音声も同じ初期遅延を経由するため、**音声との相対位置はゼロで吸収される**見込み（要目視確認）。もしズレる場合は `-itsoffset` で補正する。

## 未実施の確認

次セッション以降で:

1. **TTS 発話ありの実リップシンク目視確認** — 通常の broadcast.html に戻してちょびに発話させながら 60〜90 秒録画し、話し始め・話し終わりの映像/音声のズレを VLC 等で目視。
2. **長尺（30分）録画でドリフトが累積しないこと** — 検証は 60 秒のみで完了しているため、長尺時の傾向を確認。
3. **AudioOffset（現デフォルト -0.5）の見直し** — wallclock 化で映像側の遅延特性が変わったため、最適値が変わる可能性あり。

いずれも結果次第で追加対応（`-itsoffset` やデフォルト値調整）を判断。

## リスクと対策

| リスク | 影響度 | 対策 |
|--------|--------|------|
| TTS と映像がズレる（初期オフセットが相殺されない） | 中 | `-itsoffset` でどちらかのストリームに補正を入れる |
| 配信モード（RTMP）の挙動が変わる | 低 | 配信側は `OutputMode.Rtmp` のため wallclock 条件分岐に入らない（変更なし） |
| フレーム停止が長時間続く見た目の違和感 | 低 | ドロップ時は直前フレームを表示し続けるが、通常運用では数フレーム程度。速度の揺らぎではなくヒッチとして自然に見える |

## 参考

- 検証記録: `plans/recording-av-sync-verification.md`
- FFmpeg [use_wallclock_as_timestamps](https://ffmpeg.org/ffmpeg-formats.html#Format-Options)（入力フォーマット共通オプション）
- 計測結果（60秒録画、flash カウント 50+）:
  - default: +10.7ms/秒で線形累積 → 長尺で悪化
  - **wallclock: flash 1 以降 ±1フレーム jitter のみ（stdev 95ms、累積 -33ms/50秒）→ 採用**
  - pacer: 実装バグで初期 +2667ms の定数オフセット → 不採用
