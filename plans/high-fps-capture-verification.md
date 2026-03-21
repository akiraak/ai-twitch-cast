# YouTube動画など高FPSウィンドウキャプチャのスムーズ配信検証

## ステータス: 未着手

## 背景

YouTube動画のような高FPS動画コンテンツをキャプチャして配信に載せた際、スムーズに視聴できるかを検証する。

## 現状のフレームパイプライン

```
YouTube (60fps)
  → WGC API (フレーム到着は不定期)
  → WindowCapture FPSスロットル (デフォルト15fps)
  → JPEG encode (品質70)
  → HTTP GET /snapshot/{id} ← broadcast.html がポーリング
  → <img> タグに表示 (ポーリング間隔 200ms = 5fps)  ← ★実際のボトルネック
  → broadcast.html 全体を FrameCapture が WGC キャプチャ (30fps)
  → BGRA → NV12 変換
  → FFmpeg H.264 encode (30fps / 2500kbps CBR)
  → Twitch RTMP
```

### 各段階のFPSと制約

| 段階 | FPS | 制約の性質 |
|------|-----|-----------|
| WGC → WindowCapture | 15 fps (設定可能) | C#側スロットル |
| JPEG encode | キャプチャと同期 | CPU依存 |
| **broadcast.html ポーリング** | **5 fps (SNAPSHOT_INTERVAL=200ms)** | **JS側ハードコード** |
| FrameCapture (配信全体) | 30 fps | C#側スロットル |
| FFmpeg出力 | 30 fps | 配信設定 |

### 構造的問題

**3回のエンコードステージ**を経由している:
1. WindowCapture: BGRA → **JPEG encode**
2. ブラウザ: JPEG decode → DOM render → WGC: BGRA → **NV12 encode**
3. FFmpeg: NV12 → **H.264 encode**

JPEG品質70で非可逆圧縮され、それをブラウザが再描画し、さらにWGCで再キャプチャするため、画質が2重に劣化する。

## ボトルネック分析（影響度順）

### 1. broadcast.html ポーリング間隔 = 5fps（最大のボトルネック）

`static/js/broadcast-main.js` L565:
```javascript
const SNAPSHOT_INTERVAL = 200; // 5fps
```

WindowCaptureが何fpsでキャプチャしても、ブラウザ側が200msごとにしかフレームを取得しない。**WindowCapture FPSを上げても効果なし**。

### 2. JPEG中間フォーマットによる画質劣化

動画コンテンツはJPEG圧縮との相性が悪い（動きの激しいシーンでブロックノイズ）。さらにブラウザでデコード→WGCで再キャプチャという経路で2重劣化。

### 3. FrameCapture 30fps の天井

配信全体のキャプチャが30fpsなので、ウィンドウキャプチャをそれ以上にしても意味がない。理論上限は30fps。

### 4. FFmpeg 2500kbps

動画コンテンツを含む配信には低め。ただしTwitchの推奨は720p30fpsで2500-4000kbps。

## 検証ステップ

### Phase 1: 現状の定量計測（コード変更なし）

目的: 「どこがどの程度のボトルネックか」を数値で把握する

- [ ] YouTube 60fps動画をキャプチャし、配信画面を録画
- [ ] 録画から実効FPSを計測（フレーム差分で動きのあるフレーム数をカウント）
- [ ] 体感評価: PiP小窓（画面の30%程度）で許容できるか
- [ ] 体感評価: 大きめのウィンドウ（画面の60%以上）で許容できるか
- [ ] CPU/GPU使用率をタスクマネージャーで確認

**判定**: 現状で「問題ない」なら以降のPhaseは不要。

### Phase 2: ポーリング間隔の短縮（最小変更）

最大のボトルネック（5fps）を解消する最もシンプルな変更。

- [ ] `SNAPSHOT_INTERVAL` を 200ms → 67ms (15fps) に変更
- [ ] WindowCapture FPS もデフォルト15のままで同期を確認
- [ ] 体感評価: Phase 1 からの改善度合い
- [ ] CPU使用率の変化を確認（HTTPリクエスト頻度3倍）
- [ ] ネットワーク帯域の変化を確認

**さらに改善が必要な場合:**
- [ ] `SNAPSHOT_INTERVAL` を 34ms (30fps) に変更
- [ ] WindowCapture FPS も 30 に引き上げ
- [ ] 体感評価 + CPU使用率確認

### Phase 3: JPEG品質の調整

Phase 2で FPS は改善したが画質が悪い場合に実施。

- [ ] JPEG品質 70 → 85 に変更してテスト
- [ ] フレームサイズ（バイト数）の変化を確認
- [ ] 1080p@30fps でJPEG変換が間に合うか（1フレーム < 33ms）を確認
- [ ] 体感画質の改善度を評価

### Phase 4: 配信ビットレートの調整

動画コンテンツを含む場合のFFmpeg設定。

- [ ] 2500kbps → 4000kbps に変更
- [ ] Twitch側の画質を確認（VODまたはプレビュー）
- [ ] 配信の安定性（ドロップフレーム）を確認

### Phase 5: アーキテクチャ改善の検討（Phase 2-4で不十分な場合のみ）

Phase 2-4のパラメータ調整で不十分な場合に、より根本的な改善を検討する。

#### 選択肢A: WebSocket Binary フレーム配信
- `/ws/broadcast` 経由でJPEGバイナリをpush
- ポーリング廃止 → サーバー主導のフレーム配信
- `<img>.src = URL.createObjectURL(blob)` で表示
- 実装コスト: 中（C#側WebSocket送信 + JS側受信）

#### 選択肢B: ネイティブD3D11合成（JPEG経由を完全排除）
- WindowCaptureのフレームをJPEGに変換せず、FrameCapture段階で直接合成
- broadcast.htmlのWGCフレーム + WindowCaptureのWGCフレームをGPU上で合成
- JPEG encode/decode を完全にバイパス
- 実装コスト: 大（D3D11テクスチャ合成の実装が必要）

#### 選択肢C: FFmpeg filtergraph による合成
- FFmpegに複数入力パイプを渡し、`-filter_complex overlay` で合成
- broadcast.htmlは overlay/字幕/アバターのみ描画、ウィンドウキャプチャは別パイプ
- 実装コスト: 大（FFmpegパイプライン全面改修）

**判断基準**: Phase 2-4でPiP小窓（30%サイズ）が十分な品質になれば、Phase 5は不要。

## 音声との関連

別TODO「ウィンドウの音を配信に自然に乗せれるかを検証」と密接に関連する。

- YouTube視聴体験では**映像と音声の同期**が必須
- 現在の音声パイプライン（TTS/BGM）はC#内で生成 → FFmpegへ直接入力
- ウィンドウ音声を載せるにはWASAPIループバックまたはアプリ別音声キャプチャが必要
- 映像のJPEG経由による遅延と、音声の直接入力の遅延差が同期問題を生む可能性
- **この検証では音声は対象外**とし、映像のみ評価する。音声は別タスクで検証。

## 成功基準

| ユースケース | 基準 |
|-------------|------|
| PiP小窓（画面の30%以下） | 15fps以上で表示、目立つカクつきなし |
| 大きめ表示（画面の50%以上） | 24fps以上で表示、動画として視聴に耐える |

定量基準:
- ウィンドウキャプチャ部分の実効FPS ≥ 15（録画フレーム差分で計測）
- CPU使用率がキャプチャ追加前の +30% 以内
- 配信全体のフレームドロップが発生しない

## リスク

| リスク | 影響 | 対策 |
|--------|------|------|
| ポーリング高頻度化でCPU負荷増大 | 配信全体のカクつき | Phase 2で段階的に変更、計測してから次へ |
| JPEG品質引き上げでフレームサイズ肥大 | HTTP転送遅延 | localhost通信なので影響軽微。計測で確認 |
| FrameCapture 30fps が天井 | 30fps以上は不可能 | 配信が30fpsなので30fpsで十分 |
| DRM保護コンテンツはキャプチャ不可 | Netflix等で黒画面 | YouTubeは問題なし。DRMコンテンツは対象外 |

## 備考: `useDirectCapture` フラグ

broadcast-main.js L557 に `let useDirectCapture = false;`（IPC直接受信モード・未使用）が存在する。将来的にWebView2のIPC経由で直接フレームを受け渡すための布石と思われるが、現在は未実装。Phase 5の選択肢として検討可能。

## 関連ファイル

- `static/js/broadcast-main.js` L565 — `SNAPSHOT_INTERVAL = 200`（**最大のボトルネック**）
- `win-native-app/WinNativeApp/Capture/WindowCapture.cs` — WGCキャプチャ + FPSスロットル
- `win-native-app/WinNativeApp/Capture/FrameCapture.cs` — 配信全体キャプチャ（30fps天井）
- `win-native-app/WinNativeApp/Server/HttpServer.cs` — `/snapshot/{id}` エンドポイント
- `win-native-app/WinNativeApp/Streaming/FfmpegProcess.cs` — FFmpegパイプライン
- `win-native-app/WinNativeApp/Streaming/StreamConfig.cs` — 配信設定デフォルト値
- `win-native-app/WinNativeApp/MainForm.cs` — 統合・オーケストレーション
