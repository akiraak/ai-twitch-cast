# 録画モード 別アプローチ：スクリーンキャプチャ＋スピーカー録音

> 関連: [recording-av-sync-fix.md](recording-av-sync-fix.md)（既存方式の AV 同期対症療法・対症の限界を明示済み）
> 関連: [client-video-recording.md](client-video-recording.md)（録画機能本体）
> 関連: [capture-window-audio.md](capture-window-audio.md)（キャプチャ対象ウィンドウの音取り込み・別観点）

## ステータス: Step 0 PoC 完走 → Step 1 着手前（2026-05-10）

## 起点となる観察

**「アプリで再生しているだけ」のとき（録画も配信もしていない状態）は、画面とスピーカーの音はズレない。とても自然に見えるし聞こえる。録画・配信を始めた瞬間に音のズレや途切れが発生する。**

裏取り済み: TTS / BGM / Lesson は配信・録画の有無に関係なく `MainForm.cs` 内の `WaveOutEvent`（`PlayTtsLocally` / `_bgmWaveOut` / `_lessonWaveOut`）で既定スピーカーに常時再生されている。FFmpeg パイプラインへの送出は**それとは独立した別経路**で、AV 同期問題はその別経路に閉じている。

→ **「ユーザーが見聞きしているもの」をそのまま録れば、AV 同期は構造から消える。** 根本原因（FFmpeg の raw PCM 入力でのバイトベース PTS など）は後回しでよい。

## 背景

現行の録画モード（`OutputMode.File`）は、配信モードと **同一の FFmpeg パイプライン** を流用している。

```
[現行]
WGC フレーム  ─raw bgra─▶  FFmpeg stdin (映像)  ─┐
                                                  ├─▶  FFmpeg encoder  ─▶  MP4
TTS/BGM/SE   ─C# 合成─▶   FFmpeg stdin (音声)  ─┘
              （10ms tick generator）
```

[`recording-av-sync-fix.md`](recording-av-sync-fix.md) で対症療法（B1/B2/C+A/E ＝ cap・offset・pipe buffer の調整）と根本案 α/β/γ/δ（wallclock PTS、キュー撤廃、aresample=async）を順に検証した結果、**raw PCM 入力では音声 PTS が `byte_offset / sample_rate` のバイトベース計算で wall clock と乖離する**ことが構造的な根因と判明している。α 単独実装で改善する見込みはあるが、効果が無い／不十分なケースを想定して**「OS の単一 wall clock に同期を任せる」別ルート**を本案で平行検討する。

## 目的

1. **AV 同期問題を構造から消す**：raw PCM のバイトベース PTS / 自前 mixer / 自前 tick generator を録画経路から排除し、OS が打刻した wall clock タイムスタンプだけで音声・映像を揃える
2. **配信と録画を物理的に分離**：配信パイプライン（FFmpeg→RTMP）に手を入れずに済むので、AV 同期改修の影響範囲が録画側に閉じる
3. **既存の WGC キャプチャ・字幕オーバーレイ・broadcast.html レンダリング** の見た目をそのまま録る（broadcast.html を WebView2 でレンダリングしている領域＝最終的な「視聴者が見る絵」をキャプチャするので、配信と録画で見た目が完全一致する）
4. **「見聞きしているもの」と完全一致**：すでに `WaveOutEvent` でスピーカー再生されている TTS/BGM/SE をそのまま loopback で拾うことで、ユーザー体感と録画ファイルが一致する

## 提案アーキテクチャ（A0 採用）

```
[新方式 A0]
WaveOutEvent → 既定スピーカー ────┐
（既存の PlayTtsLocally / BGM       ├─ WASAPI Loopback ─▶ FFmpeg muxer ─▶ MP4
  /Lesson 再生はそのまま）         │
WGC（C# アプリのウィンドウ）─────────┘
                                   
※ FFmpeg の従来音声経路（generator → 10ms tick → audioQueue）は録画時は使わない
※ 配信モード（OutputMode.Rtmp）は従来どおり完全温存
```

- **映像ソース**: WinNativeApp 自身のウィンドウ全体を Windows.Graphics.Capture でキャプチャ → クロップで broadcast 領域 1280×720 を抜く（既存 `crop=1280:720:1:38` 手順と整合）
- **音声ソース**: 既定再生デバイスの WASAPI Loopback（NAudio `WasapiLoopbackCapture`）。スピーカーに到達した音 = ユーザーが聞いている音 = 配信用 broadcast 領域と同期している音
- **同期**: 両ストリームを wall clock PTS で FFmpeg muxer に渡すだけ。raw PCM の byte counter は使わない
- **既存 WaveOutEvent には一切手を入れない**（A2 のような WasapiOut 増設は不要）

### 期待されるメリット

| 観点 | 現行（FFmpeg 共有方式） | 新方式 A0（画面+Loopback） |
|------|------------------------|------------------------|
| AV 同期 | バイトベース PTS と wall clock の乖離が累積 → 蓄積遅延／ブツブツ | **OS の単一 wall clock** で video/audio 両方を打刻 → 構造的に同期 |
| TTS／BGM／SE の合成 | C# が 10ms tick で自前 mix（generator + cap=30 queue + 1MB pipe） | OS のオーディオエンジンがミックスした最終出力を録る（合成不要） |
| ブラウザ音（broadcast.html の WebAudio 等） | 拾えない | **拾える**（loopback に乗ってくる） |
| 配信モードへの影響 | 同じパイプライン → 改修の副作用が配信に波及するリスク | **完全分離** |
| 設計の単純さ | TtsDecoder / WaveProvider / mixer / queue / pipe が複雑に絡む | **WGC + Loopback + FFmpeg muxer** の 3 段で済む |
| 「見聞きしているもの」との一致 | C# の自前 mix なのでスピーカー出力とは別の音が録られる | **スピーカー出力そのもの**を録る |

## 設計の分岐点（決定済み）

### A. 音声出力先をどう構成するか → **A0 採用**

新方式では「スピーカーから出ている音」を録るが、**TTS／BGM／SE は既に `WaveOutEvent` 経由で物理スピーカーまで到達している**（`MainForm.cs:1856 PlayTtsLocally` / `MainForm.cs:2188 _bgmWaveOut`）。配信や録画の有無と関係なく常時再生されているため、追加の出力経路を作る必要はない。

```
[採用] A0: 既存 WaveOutEvent をそのまま loopback で録る
   - WaveOutEvent → 既定スピーカー → WASAPI Loopback → FFmpeg
   - C# 側の追加は WASAPI Loopback キャプチャ 1 つだけ
   - 既存の PlayTtsLocally / BGM 再生には手を入れない
   - 録画時は FFmpeg 側の従来音声パイプを使わず、loopback パイプ 1 本に置換
   - 配信モードは従来どおり完全温存

[却下] A2: C# 側に WasapiOut を増設
   - 既存 WaveOutEvent が既にスピーカー出力しているため、増設は冗長
   - WasapiOut→Loopback 往復遅延 10〜30ms が独立して乗る
   - 配信モードでも generator 経路を切り替える必要が生じ影響範囲が広がる

[将来検討] A3: broadcast.html に音源集約 + 配信も loopback 化
   - 配信と録画で同じ音源経路 → 整合性最高
   - ただし C# の音声生成パイプライン全体の刷新が必要 → 大改修
   - A0 で原理確認できてから検討する余地は残す
```

### B. 映像のキャプチャ対象 → **B1 採用**

```
[採用] B1: WinNativeApp ウィンドウ全体をキャプチャ → クロップ
   - 既存 WGC 経路（WindowCapture.cs / FrameCapture.cs）を流用しやすい
   - crop=1280:720:1:38（DONE.md の手順）と同じ運用

[後回し] B2: WebView2 が描画している HWND だけをキャプチャ
   - ピクセル等寸（1280×720）で撮れる利点はあるが、HWND 取得の安定性確認が必要
   - B1 で動いてから検討

[却下] B3: 既存の配信用 WGC フレームを録画にも流用
   - 映像側のバイトベース PTS 問題が残るので AV 同期改善は音声側のみ
   - A0 と矛盾するため不採用
```

### C. 音声デバイス分離ポリシー → **運用ルールで吸収**

WASAPI Loopback で取るスピーカー出力に「他アプリの音」が混ざる問題への対応:

```
[採用] 運用ルールで吸収
   - 「録画中は他アプリで音を鳴らさない」運用ルール
   - 既定再生デバイスをそのまま loopback で取る（実装最小）
   - Discord 通知音などは録画モード開始前にミュート / OFF
   - 授業など段取りどおりに録るユースケースなら現実的

[却下] VB-Cable 等の仮想デバイス必須
   - 追加ソフトのインストールと WaveOutEvent の出力先指定が必要
   - 「全自動配信」の理念から外れる

[将来検討] プロセス Loopback（capture-window-audio.md A 案）と統合
   - WGC 対象ウィンドウのプロセス音声 + C# アプリ自身の出力 を別ストリームで取る
   - COM interop で実装重い
   - capture-window-audio.md と二重投資せず一本化できる利点はある
   - A0 で原理確認できてから検討
```

### D. FFmpeg コマンドラインの構成

```
[新方式 A0 想定の FFmpeg コマンド]
ffmpeg \
  -f rawvideo -pix_fmt nv12 -s 1280x720 -framerate 30 \
    -use_wallclock_as_timestamps 1 -i \\.\pipe\winnative_video_xxx \
  -f f32le -ar 48000 -ac 2 \
    -use_wallclock_as_timestamps 1 -i \\.\pipe\winnative_loopback_xxx \
  -c:v <既存 encoder args> \
  -c:a aac -b:a 128k \
  -movflags +faststart+frag_keyframe \
  output.mp4
```

- 映像: 現行どおり名前付きパイプ（NV12）。`use_wallclock_as_timestamps` は付ける
- 音声: 別パイプから WASAPI Loopback の f32le PCM を流す。同じく `use_wallclock_as_timestamps`
- 既存の TtsDecoder / `_audioQueue` / `MixTtsInto` / `MixBgmInto` / `MixSeInto` / `AudioWriterLoop` / `StartAudioGenerator` は **録画モード（OutputMode.File）では使わない**（配信モード OutputMode.Rtmp は温存）

## 実装ステップ

### Step 0: PoC（最小コードで原理検証）→ **完了（2026-05-10）**

**目的**: 「見聞きしているものをそのまま録れば AV 同期は揃う」という仮説を最小コードで実証する。

**実装**: `win-native-app/PocLoopback/` (PocLoopback.csproj + Program.cs + ScreenCapture.cs + LoopbackCapture.cs + FfmpegRunner.cs)、起動スクリプト `poc-loopback.sh`。WinNativeApp と独立した C# Console + NAudio + ffmpeg subprocess。

**実装中に分かった設計上の修正**:
- **rawvideo BGRA で送る**: 当初プランは NV12 だったが PoC は BGRA 直送に簡素化。AV 同期検証には影響なし
- **wallclock は映像入力にだけ付ける**: プランでは映像/音声両方に `-use_wallclock_as_timestamps 1` を想定していたが、音声側に付けると silence プライムや読みバーストで PTS が歪んで `Non-monotonic DTS` / `Queue input is backward in time` が連発し AAC エンコーダのキューが破綻する。**音声は素のサンプル数ベース PTS** とし、AV 同期は「映像 wallclock + 連続的に流れる loopback 音声」で取る。これは WinNativeApp/Streaming/FfmpegProcess.cs と同じ設計
- **音声側の silence プライムは不要**: 上記の wallclock 撤去とセットで silence プライムも撤去（プライムを送ると PTS 歪みの原因になる）
- **映像のみ初期黒フレームを 1 枚送る**: FFmpeg は rawvideo の最初の 1 フレームを読まないと次の入力（audio pipe）を開かない仕様なので、video pipe 接続直後に 1 フレームだけ黒を送る（WinNativeApp と同パターン）
- **yuv420p のため偶数次元クロップ**: WGC が返すウィンドウサイズが奇数（1682×759）だと libx264 + yuv420p が失敗するので `-vf "crop=trunc(iw/2)*2:trunc(ih/2)*2"` を入れる
- **出力先は Windows 側ローカル**: WSL UNC 越し (\\\\wsl.localhost\\…) は書込が遅く FFmpeg がドロップしやすいので、`C:\\Users\\akira\\AppData\\Local\\win-native-app\\PocLoopback\\output\\` に書いて完走後 `debug-ss/` にコピーバック

**合格基準と結果（60 秒録画 / WinNativeApp 本体で TTS+BGM 再生中）**:

| 基準 | 結果 |
|------|------|
| VLC 目視で口パクと音声のズレがフレーム単位（≦33ms）で目立たない | ✅ 口パクと音が合っている |
| ブツブツ・音切れが 30 秒間で 0 回 | ✅ ブツブツなし |
| `ffprobe -show_packets` での音声 PTS と映像 PTS の差が ±100ms 以内 | ✅ 実フレーム同士の `pts_time` は両方 4.300s で **差 0ms** |
| 30 分長尺で AV ドリフトが累積しない | 後続 Step 4 で確認 |

**残課題（Step 1 で潰す）**:
- **スタートアップで 4.3 秒の無音黒フレーム前置きが入る**: 初期黒フレームを t=0 で書いたあと、x264 の rc-lookahead と静止ウィンドウで WGC が次フレームを発火しないため、実フレームの pts_time が 4.3s から始まる。Step 1 では「最初の実フレーム到着まで録画開始トリガーを遅らせる」か「アプリ側で毎フレーム invalidate して WGC を 30fps で確実に発火させる」で潰せる
- **`Queue input is backward in time` の warning が残存（fatal ではない）**: AAC エンコーダの内部キューが入力 PCM のバースト読みに反応して出している。PTS 歪みではなく PCM 入力の読み取りタイミングのジッタが原因。AV 同期には影響なし

**結論**: 仮説「アプリで再生しているだけのときは AV が揃う → ならば見聞きしているものをそのまま録れば AV 同期は構造から消える」が成立。本案を本実装に進める（Step 1 へ）。

### Step 1: WinNativeApp 本体への loopback キャプチャ追加

- `win-native-app/WinNativeApp/Streaming/` に `LoopbackAudioSource.cs`（仮）を新設
- NAudio `WasapiLoopbackCapture` で f32le 48kHz stereo PCM を取得、wall clock 付きで Named Pipe にバイト列を書く
- 既定デバイス変更時の reinit ロジック（`RecordingStopped` ハンドラ）を実装
- 既存の `MeteringWaveProvider` / `TtsDecoder` / `_audioQueue` / `StartAudioGenerator` には触らない

### Step 2: 録画モード時の FFmpeg パイプを 2 入力に変更

- `OutputMode.File` のとき、`FfmpegProcess` の音声入力を「既存 audio pipe（generator）」ではなく「loopback pipe」に切り替え
- `StartAudioGenerator` / `WriteTtsData` / `WriteAudioData` は録画モード時は呼ばない（または no-op に分岐）
- 配信モード（`OutputMode.Rtmp`）は従来どおり generator → FFmpeg 直結
- FFmpeg 引数: 映像入力に加えて音声入力 `-f f32le -ar 48000 -ac 2 -use_wallclock_as_timestamps 1 -i \\.\pipe\loopback_xxx` を追加
- 音声入力にも `-use_wallclock_as_timestamps 1` を付ける（α 案と同じ仕組みを音声側にも適用）

### Step 3: 計測スクリプト拡張

- `scripts/verify_av_sync.py` を音声 PTS まで読めるよう拡張（`recording-av-sync-fix.md` 既知の TODO）
- `ffprobe -show_packets -select_streams a` で音声 PTS を取得し、映像 PTS との差を時系列で出す
- これは α 検証（recording-av-sync-fix.md 側）でも必要なので、A0 PoC 着手と同時または先行で進めると両プランで再利用できる

### Step 4: 計測

- 60 秒・90 秒・5 分・30 分長尺で AV 同期と CPU 負荷を測る
- VLC 目視チェックリストは `recording-av-sync-fix.md` Step 1 の手順を流用
- ブツブツ／遅延／中央値ズレ／最大ズレ幅を記録

### Step 5: 副作用の確認

- 配信モード（RTMP）の挙動が変わっていないことを確認（同じ授業を録画→配信の順に流して、配信側に劣化がないか）
- アップロードフロー（[client-video-recording.md](client-video-recording.md)）は変更不要のはず（出力 MP4 のフォーマットは互換）

### Step 6: ドキュメント整備

- [recording-av-sync-fix.md](recording-av-sync-fix.md) と本プランの**役割分担**を明記
  - 旧方式（FFmpeg 共有パイプライン）: 配信専用にロールバック
  - 新方式（loopback 録画）: 録画専用
- DONE.md にステップごとの結果を残す
- CLAUDE.md の「配信動画のクロップ＆音量ノーマライズ（debug-ss/）」セクションに録画モードの音量基準値を追記（loopback 経由の基準音量が異なる可能性があるため）

## 既存方式との関係

- **本プランは [recording-av-sync-fix.md](recording-av-sync-fix.md) の代替案**ではなく **平行検討**。ただし起点観察（「再生だけなら同期している」）に基づき、**A0 経路の方が筋が良い可能性が高い**ため本案を優先する判断もありうる
- α 単独実装で十分な品質が出ればそれで良い。残差 / 別動機（ブラウザ音取り込み等）が生じた場合の本命候補として本案を持っておく
- 30 分長尺のドリフト累積問題（TODO.md「録画モードAV同期: 30 分長尺でのドリフト累積確認」）も、本案では OS 側 wall clock に責務が移るため**そもそも累積しない**見込み
- どちらを先に進めるかはユーザー判断。現時点では本案 PoC を先行する方針

## 想定される懸念点と対策

| 懸念 | 対策 |
|------|------|
| **マイクや他アプリの音まで録ってしまう** | C 案「運用ルールで吸収」採用。録画開始前に Discord・ブラウザ等を静音化。UI に「録画中は他アプリで音を鳴らさないでください」警告を出す |
| **ヘッドホン挿抜・既定デバイス変更で stream が止まる** | NAudio `WasapiLoopbackCapture` の `RecordingStopped` で reinit。録画中はデバイス変更を禁止する UI 制約も検討（`AudioEndpointVolume` の通知をフックして警告） |
| **画面解像度・スケーリング** | broadcast の WebView2 領域（1280×720）と等寸でキャプチャできるか。ウィンドウ全体ならクロップが必要（DONE.md 既存の crop 手順と整合） |
| **音量レベル** | スピーカー出力をそのまま録るので、PC のスピーカー音量に左右される。WASAPI Loopback はソフトウェア出力ミックスを取るのでハード音量とは独立だが、要実測。録画後のラウドネスノーマライズ（既存 debug-ss 手順）で吸収可能 |
| **CPU 負荷** | 1280×720@30fps の WGC＋WASAPI loopback＋h264 エンコードは現行配信と同じオーダー。h264_qsv/nvenc を継続利用可能 |
| **遅延** | WASAPI Loopback の固有遅延（10〜30ms 程度）は wall clock 基準なので PTS に正しく現れる。`-itsoffset` 等の補正が要るかは試聴で判断 |
| **既存の AudioOffset / cap=30 / pipe 1MB チューニングとの整合** | 録画モードでは音声経路を完全に置換するため、これらの既存対症療法（recording-av-sync-fix.md C+A / E）は録画モードでは無効化される。配信モードでは温存 |

## 完了条件（暫定）

- [x] Step 0 の PoC で AV 同期が体感ズレなし、ブツブツなしを確認（合格基準: §Step 0 の定量基準）→ 2026-05-10 達成
- [ ] Step 1〜2 を WinNativeApp 本体に組み込み、`OutputMode.File` で動作
- [ ] Step 3 計測スクリプト拡張完了
- [ ] Step 4 計測で 30 分長尺の AV ドリフトが ±100ms 以内
- [ ] Step 5 で配信モードに劣化がないことを確認
- [ ] DONE.md に結果を記録、本プランを「完了」に更新

## 参考

- [recording-av-sync-fix.md](recording-av-sync-fix.md) — 既存方式の対症療法と根本原因分析（必読）
- [client-video-recording.md](client-video-recording.md) — 録画機能の全体設計
- [capture-window-audio.md](capture-window-audio.md) — キャプチャ対象ウィンドウの音取り込み（プロセス Loopback / 将来統合候補）
- NAudio `WasapiLoopbackCapture`: <https://github.com/naudio/NAudio>
- Windows.Graphics.Capture（WGC）: 既存 `Capture/` 配下の実装
- FFmpeg `use_wallclock_as_timestamps`: <https://ffmpeg.org/ffmpeg-formats.html#Format-Options>
