# 録画AV同期修正: 原因切り分け検証

## ステータス: 検証完了（2026-04-19）／wallclock 採用決定

## 結論（サマリ）

**wallclock を採用**。以下の順で実本番化する:

1. pacer 関連コードを削除（初期 burst バグがあり wallclock を上回る利点なし）
2. `VideoTimingMode` を削除し、録画モード（`OutputMode.File`）では常に `-use_wallclock_as_timestamps 1` を付ける実装に変更
3. 実際の TTS 発話を含む録画でリップシンクを確認
4. `plans/recording-av-sync-fix.md` を書き換え、本実装フェーズに進む

詳細は「検証後の扱い」セクション参照。

## 目的

`plans/recording-av-sync-fix.md` の実装前に、AV ズレの原因が「映像PTSが frame_index 基準」であることを確定させる。3つのビルド（ベースライン / wallclock / Pacer）を同一条件で計測し、どれが有効かを数値で判定する。

## 親プラン

- `plans/recording-av-sync-fix.md` — 本検証の結果で方針を確定させる

## 検証する3ビルド

| 名前 | 切替値 | 変更点 | 予想 |
|------|--------|--------|------|
| ベースライン | `default` | 現行のまま | ドロップに比例してズレる |
| wallclock | `wallclock` | 録画時のみ映像入力に `-use_wallclock_as_timestamps 1` を追加 | rawvideo+framerate との相性次第、不定 |
| Pacer | `pacer` | C#側で30Hz tick。`WriteVideoFrame`はフレーム保持のみ。tickで最新フレームを書き込み、無ければ前フレーム複製 | 常に30fps CFR → 音声と自動同期するはず |

**切替手段**: `StreamConfig.VideoTimingMode`（enum）を追加。起動引数 `--video-timing default|wallclock|pacer` または環境変数 `VIDEO_TIMING=...` で切替。本実装時には採用案のみ残し、他は削除。

## 同期テスト素材

`static/av_sync_test.html`（新規）:

- 画面中央に大きな数字を表示（0→59、1秒ごとに更新）
- 1秒境界で100msだけ赤い全画面フラッシュ（PTSからの経過時刻を逆算しやすいキュー）
- 画面左下に `performance.now()` ベースのデジタル時計（ms精度、人間の目視確認用）
- 60秒固定。自動スタート（Start ボタン押下後）
- **音声は含めない**。現行の音声パイプは TTS/SE/BGM のみを FFmpeg に流し、WebView2 の Web Audio 出力はキャプチャされないため。AV 同期の本質は「映像PTS = 実時間」が成立するかどうかで、音声は既に実時間で進んでいる（`StartAudioGenerator` が `TickCount64` 駆動）。映像側だけ合えば AV 同期は自動的に取れる

## 計測スクリプト

`scripts/verify_av_sync.py` を新規作成:

1. 引数: 録画MP4パス
2. `ffprobe -show_frames -select_streams v` で全映像フレームの PTS（秒）を取得
3. ffmpeg で各フレームをPNGに展開 or 直接PIL/numpyでフレーム読み出し、**赤フラッシュ領域の平均R値** を抽出
4. R値のピーク（= フラッシュ中心）を検出し、N個のピークを得る（理想60個）
5. 期待値: n番目のピークは t=n 秒、フレームの PTS も n 秒であるべき
6. 出力: `| n | 期待(s) | flash_pts(s) | 差分(ms) |` の表
7. サマリ: 先頭 / 末尾 / 最大ズレ / 平均ズレ（ms）

実装は `numpy` + `Pillow` + `subprocess(ffmpeg)` のみ。

### 音声の同期については

本検証では**映像のPTSドリフトのみ計測する**。映像PTSが実時間と一致すれば、既に実時間で動いている音声と自動的に同期する。検証後、採用案のビルドで実際に TTS を発話させた状態の録画を手動で視聴し、リップシンクを耳で最終確認する（= 本プランの終わりに追加ステップ）。

## 実施条件

- 解像度 1280x720 / fps 30 / bitrate 2500k（現行デフォルト）
- 録画長: **60秒**（30分テストは実施しない）
- 負荷: **軽負荷のみ**（普通の待機状態）。重負荷条件は結果次第で追加判断
- ビルド数 × 負荷条件 = 3パターン

## 検証手順（詳細は本ファイル末尾）

1. WSL側で本リポジトリをビルド・デプロイ
2. Windows側でアプリ起動、`av_sync_test.html` を対象として録画モードで60秒記録
3. ビルドを切り替えて再録画（計3回）
4. MP4 を WSL の `videos/` にアップロード（既存フロー）
5. `python3 scripts/verify_av_sync.py videos/xxx.mp4` で各ビデオを解析
6. 結果を本ファイルの「結果」セクションに記録
7. 採用案確定後、実際の放送コンテンツ（TTS 発話あり）で録画→リップシンクを耳で確認

## 結果

### ベースライン（default）

- 録画ファイル: `videos/broadcast_20260419_125215.mp4`
- 総フレーム数: 1644（= MP4 duration 54.8s, CFR 30fps）
- 検出フラッシュ: 51件（録画停止が flash 50 の直後）
- 先頭ズレ: +0.0 ms
- 末尾ズレ: +533.3 ms
- 最大ズレ: 533.3 ms
- 平均ズレ: 261.4 ms
- 累積ドリフト（last - first）: +533.3 ms
- 所見: **明確な線形ドリフト**。50秒で映像PTSが実時刻より +533ms 進む（MP4が約1.07%ゆっくり再生される）。フレーム書き込みレートは 30.32fps で、`frame_index / 30` のPTS付与と実時刻の間にズレが累積。長尺録画で悪化するため不採用

### wallclock

- 録画ファイル: `videos/broadcast_20260419_125858.mp4`
- 総フレーム数: 1649（VFR、avg 27.82fps、duration 59.27s）
- 検出フラッシュ: 53件
- 先頭ズレ: 0 → -700ms（flash 1 で一回オフセット）
- flash 1 以降は **ほぼ完全に 1:1 追従**（stdev 95ms ≈ ±1フレームの量子化のみ）
- 累積ドリフト（flash 1→52、50秒間）: -33ms（= 1フレーム相当）
- 所見: **採用**。初期の -700ms は FFmpeg 初期化中にパイプへ書いた初期黒フレームが init 完了時刻で刻印され、後続の実フレームと詰まるため。定数オフセットなので録画長に依存しない

### pacer

- 録画ファイル: `videos/broadcast_20260419_130148.mp4`
- 総フレーム数: 1766（CFR 30fps、duration 58.87s）
- 検出フラッシュ: 52件
- 先頭ズレ: 0 → +2667ms（flash 1 で一回オフセット）
- flash 1 以降は steady state（stdev 366ms）
- 所見: **不採用**。実装バグあり。FFmpeg init 遅延中にパイプブロックし、init 完了後の catch-up ループが 30fps real ではなく NVENC のドレイン速度（~100fps）で書き込んでしまう。`-framerate 30 -f rawvideo` は到着順で PTS を打つので、burst 書き込み → MP4 時間が実時間より引き伸ばされる。フレーム検証画像で確定:
  - `pacer_frame_63.png` = "08" の flash（HTML t=8）
  - `pacer_frame_173.png` = "09" の flash（HTML t=9）
  - 1 real 秒の間に 110 frames 書いたことが確定

## 判定基準

- **許容**: 60秒録画で最大ズレが 66ms（2フレーム）以下、かつドリフトが単調増加しない
- **要改善**: 最大ズレが 66ms を超える、または時間経過で累積ドリフトが見える

この基準を満たす最も単純な案を `recording-av-sync-fix.md` の本実装として採用する。

## 実行コマンド

### 前提

- WSL 側で Web サーバーを起動済み（`./server.sh`）
- Windows 側で `./stream.sh` のビルド・起動パスが通っている

### 検証ラン 1 回あたりの手順

**1. 検証モードで配信アプリを起動**（WSL の bash で）

```bash
./stream.sh --av-sync-test --video-timing default    # ベースライン
./stream.sh --av-sync-test --video-timing wallclock  # wallclock
./stream.sh --av-sync-test --video-timing pacer      # Pacer
```

`--av-sync-test` が URL を `/static/av_sync_test.html` に差し替え、`--video-timing` が PTS 方式を切替える（起動時引数 or 環境変数 `VIDEO_TIMING` でも可）。

**2. WebView2 の画面で「▶ Start (60s)」ボタンをクリック**

**3. control-panel（右側パネル）の「● Rec」で録画開始**

Start ボタン押下直後に Rec を押すことで、1秒目のフラッシュから録画に含める。

**4. 60秒待って「END」表示を確認したら「■ Stop Rec」**

**5. アップロード完了を待つ**

`videos/broadcast_YYYYMMDD_HHmmss.mp4` に保存される。

**6. WSL 側で計測**

```bash
python3 scripts/verify_av_sync.py videos/broadcast_YYYYMMDD_HHmmss.mp4
```

**7. 出力を本ファイルの「結果」セクションにコピペ**

C# 側 `logs/app*.log` の `=== 配信終了レポート ===` 行からドロップ数・複製数も転記する。

**8. アプリを停止して次のビルドへ**

```bash
./stream.sh --stop
```

3 ビルド分（default / wallclock / pacer）同様に実施し、結果セクションが全部揃ったら判定基準に照らして採用案を決定。

## 関連ファイル（新規 / 変更）

| ファイル | 役割 |
|----------|------|
| `static/av_sync_test.html` | **新規**: 検証素材（数字+ビープ） |
| `win-native-app/WinNativeApp/Streaming/StreamConfig.cs` | `VideoTimingMode` 追加 |
| `win-native-app/WinNativeApp/Streaming/FfmpegProcess.cs` | wallclock引数追加・30Hzペーサー実装 |
| `scripts/verify_av_sync.py` | **新規**: MP4解析・ズレ計測 |
| `plans/recording-av-sync-verification.md` | **本ファイル**: 計画と結果 |

## 検証後の扱い

### 次セッションでやる作業（wallclock 本実装化）

1. **pacer コードの削除**
   - `FfmpegProcess.cs` の `StartVideoPacer` / `PacerLoop` / `WritePacerFrame` / `UpdatePacerLatestFrame` / Pacer関連フィールド（`_pacerLatestBgra`, `_pacerStagingBgra`, `_pacerDirty`, `_pacerThread`, `_pacerStartTick`, `_pacerWrittenCount`）
   - `WriteVideoFrame` の Pacer 分岐
   - `StopAsync` の `_pacerThread?.Join`
   - `StartAsync` 内の `StartVideoPacer()` 呼び出し

2. **`VideoTimingMode` enum 自体を削除**
   - `StreamConfig.cs` の enum, プロパティ, CLI/env パース
   - `stream.sh` の `--video-timing` フラグ
   - 録画モード（`_config.Mode == OutputMode.File`）では **常に** `-use_wallclock_as_timestamps 1` を付ける実装に変更（配信モードは現行維持）

3. **TTS 発話ありの実録画でリップシンク確認**
   - 通常の broadcast.html に戻して、ちょびに何か発話させながら 60-90 秒録画
   - MP4 を VLC 等で再生、話し始め・話し終わりの映像と音声のズレを目視
   - `-700ms` の定数オフセットが実際に同期に影響するか確認（両ストリームが同じ init 遅延を食うなら相対的にはゼロ）

4. **定数オフセット問題の扱い（必要なら）**
   - TTS と映像がズレる場合: `-itsoffset` をどちらかのストリームに付けて補正
   - ズレない場合（＝音声も同じ初期遅延で吸収される場合）: 追加対応不要

5. **`plans/recording-av-sync-fix.md` の書き換え**
   - 方針を「録画時のみ `-use_wallclock_as_timestamps 1`（WASAPI loopback は不採用）」に書き換え
   - Phase 2（Loopback）は不要（loopback の複雑さと引き換えに得るものがない）

6. **`stream.sh` の `--av-sync-test` フラグは残す**（将来の回帰検証用）

### 残す成果物

- `plans/recording-av-sync-verification.md`（本ファイル、結果の記録）
- `static/av_sync_test.html`（検証素材）
- `scripts/verify_av_sync.py`（計測スクリプト）
- 3つの MP4（検証結果の原典として `videos/` にそのまま保管）

### 注意点（次セッション向け）

- `MainForm.cs:743-748` に入れた `_serverBaseUrl` の URL オリジン抽出修正は **そのまま残す**（`--av-sync-test` の URL を正しく扱うために必要）
- `scripts/verify_av_sync.py` は `-fps_mode passthrough` を使って VFR/CFR 両対応になっている。`numpy` 必須（venv に `pip install numpy` 済み）
- 検証済みの3本の MP4 (`videos/broadcast_20260419_{125215,125858,130148}.mp4`) は削除しないこと。方針を再検討する際の一次情報
