# クライアント画面の文字表示改善

## ステータス
Step 1 完了 / Step 2 待ち

## 背景

C# ネイティブ配信アプリ（`win-native-app/`）の画面のうち、**左側の配信合成画面（`static/broadcast.html` + `static/css/broadcast.css`）** の文字が「綺麗じゃない」とユーザー指摘あり。
broadcast.html は配信映像にも乗るので、ここの品質改善は **配信視聴者にもそのまま見える** ことになる。

## Step 0 結果（スコープ確定）

ユーザーへの確認結果：

- **対象スコープ**: 左の配信合成画面 (broadcast.html) のみ
  - control-panel.html（右パネル）は対象外
  - WinForms 自体（タイトルバー / トレイ）も対象外
- **気になる要素**: 特定せず「全部同じくらい綺麗じゃない」
  - → 一部要素ピンポイントではなく、broadcast.html 全体のテキスト品質を底上げする方針

このため、当初プランの control-panel.html 向け Step 2〜4 は廃止し、broadcast.html 用に作り直す。

## 現状の確認結果（broadcast.css 読了）

- **フォントスタック**: `font-family: "Noto Sans JP", "Yu Gothic UI", "Meiryo", sans-serif;` — 日本語フォールバックは設定済み
- **`-webkit-font-smoothing` / `text-rendering` / `font-feature-settings` 指定なし**
- **vw 単位の相対サイズ**（1280×720 想定なので 1vw = 12.8px）:
  | 要素 | サイズ | 換算 px |
  |------|------|------|
  | `.subtitle-panel .speech` | 1.875vw | ~24px |
  | `.subtitle-panel .translation` | 1.04vw | ~13.3px |
  | `#todo-panel .todo-title` | 1.46vw | ~18.7px |
  | `#todo-panel .todo-item` | 1.25vw | ~16px |
  | `#todo-panel .todo-section` | 0.83vw | **~10.6px** 小 |
  | `#lesson-text-content` | 1.7vw | ~21.8px |
  | `#lesson-title-text` | 1.6vw | ~20.5px |
  | `#lesson-progress-title` | 1.1vw | ~14.1px |
  | `#lesson-progress-title .lp-title-count` | 0.85vw | **~10.9px** 小 |
  | `.lesson-progress-item` | 0.95vw | **~12.2px** やや小 |
  | `.child-panel` | 0.8vw | **~10.2px** 小 |
- **強めの text-shadow が多用されている**（滲みの一因の可能性）:
  - `.subtitle-panel .speech`: `text-shadow: 0 0.1vw 0.4vw rgba(0,0,0,0.7), 0 0 1vw rgba(124,77,255,0.2)` ← 紫グロー入り
  - `#lesson-title-text`: `text-shadow: 0 0 8px rgba(124,77,255,0.5)` ← グロー強め
  - 字幕は背景が見えるパネルだが、強グローで文字輪郭が広がっている可能性
- **太字多用**:
  - `.speech` / `.todo-title` / `.todo-item.in-progress` / `#lesson-title-text` / `#lesson-progress-title` などに `font-weight: bold` / `700` / `600`
  - 中サイズ（12〜20px）の太字 + シャドウ + ClearType (デフォルト) の組合せはダーク背景で滲んで見える

## 文字が綺麗に見えない原因候補

A. **font-smoothing 未指定**: WebView2/Chromium デフォルトの ClearType（サブピクセル）はダーク背景＋日本語太字だと滲みやすい。`-webkit-font-smoothing: antialiased`（グレースケール）の方が綺麗に見えるケースあり
B. **text-rendering 未指定**: `optimizeLegibility` でカーニング/リガチャが改善
C. **強い text-shadow**: 特に subtitle と lesson-title の紫グローが輪郭をぼかしている可能性
D. **太字の多用**: 中サイズの bold は線が太く滲みやすい
E. **小サイズ要素 (10〜12px)**: lesson-progress-item / todo-section / lp-title-count / child-panel など
F. **DPI awareness 未宣言**: `app.manifest` がなく WinForms が System DPI Aware 起動の可能性 → ハイDPIモニタで滲みやすい（Step 0 でスコープ外と判断したが、Step 2〜4 で改善しなければ再検討）
G. **レンダリング解像度が 1280×720 と低い**: WebView2 のレンダリング先がそのまま配信解像度なので、サブピクセル単位のアンチエイリアスの余地が少ない。高解像度（例: 2560×1440）でレンダリングして縮小（SSAA）すればエッジが滑らかになる → Step 5 で扱う

## 方針

低リスク・小変更（CSS-only）から段階適用する。各ステップ後にユーザーにスクショで before/after を見比べてもらい採否を判断。
配信に乗るテキストの見た目が変わるため、配信中は変更しないか、変更後に試聴で確認する。

## 実装ステップ

### Step 1: 現状のスクリーンショット取得（ユーザー作業）✅完了

- ユーザーが `debug-ss/font.png` に配信画面（lesson 中 + 字幕表示中）のスクショを保存
- 1 枚で lesson-title / lesson-text-content / subtitle / TODO パネルが同時に映る状況を押さえた
- 滲み主因の対応関係を plan 内表で確定:

| 画面要素 | CSS 該当 | 滲みの主因 |
|------|------|------|
| `#lesson-title-text` | 1.6vw / bold / `text-shadow: 0 0 8px rgba(124,77,255,0.5)` | C (text-shadow 過剰) |
| `#lesson-text-content` | 1.7vw | A (font-smoothing 未指定) |
| `.subtitle-panel .speech` | 1.875vw / bold / 紫グロー | A + C + D (太字) |
| `#todo-panel .todo-title/item` | 中サイズ太字 | D |

→ 主因は **A（font-smoothing 未指定）+ C（text-shadow 過剰）+ D（中サイズ太字多用）** の組合せで確定。Step 2〜4 でこの3点を順に潰す方針が裏付けられた。

### Step 2: broadcast.css にフォントレンダリングのベース指定を追加

```css
body {
  font-family: "Noto Sans JP", "Yu Gothic UI", "Meiryo", sans-serif;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
  font-feature-settings: "palt" 1;  /* 日本語プロポーショナル */
  background: #000;
}
```

- `antialiased`（グレースケール）はダーク背景で細く綺麗に見える事が多い
- `optimizeLegibility` でカーニング改善
- `palt` で日本語の詰め
- 最も低リスク・最も効果が期待できるので最初に試す

### Step 3: 強すぎる text-shadow / glow を軽減

- `.subtitle-panel .speech` の紫グロー (`0 0 1vw rgba(124,77,255,0.2)`) を弱める or 削る
  - 黒シャドウ (`0 0.1vw 0.4vw rgba(0,0,0,0.7)`) は読みやすさのため残す（背景透過時の保険）
- `#lesson-title-text` の `text-shadow: 0 0 8px rgba(124,77,255,0.5)` のぼかし半径を `4px`程度に絞る or 透明度を下げる
- 字幕がパネル背景に乗っているならグロー不要

### Step 4: 小さすぎる要素のサイズ底上げと太字の見直し

- `#todo-panel .todo-section` 0.83vw → **0.95vw**（10.6→12.2px）
- `#lesson-progress-title .lp-title-count` 0.85vw → **0.95vw**
- `.lesson-progress-item` 0.95vw → **1.05vw**（12.2→13.4px）
- `.child-panel` 0.8vw → **0.95vw**
- 中サイズの太字（13〜18px の `font-weight: bold/700`）を **600** に下げて滲み軽減
  - 対象例: `#lesson-progress-title` (font-weight: 600 → 500 検討)、`.lesson-progress-item.current` (600 → 500 検討)
  - `.subtitle .speech` の bold は字幕として強調が必要なので維持
- パネル幅（vw 指定）のはみ出しがないか目視確認

### Step 5: 高解像度レンダリング → ダウンサンプリング（スーパーサンプリング, SSAA）

CSS 改善（Step 2〜4）で改善が不十分な場合の**本命策**。
WebView2 のレンダリング先を 2x（例: 2560×1440）にして、WGC でキャプチャ → FFmpeg の `scale=1280:720:flags=lanczos` で縮小することで、ダウンサンプリング時に自然なアンチエイリアスがかかり文字エッジが滑らかになる。

broadcast.css は `vw` 単位中心なので、レンダリング解像度を上げれば DOM 内サイズ（px換算）も比例してスケール → 「中サイズ太字 + ダーク背景 + ClearType」の滲みに最も効くアプローチ。

#### 実装方針（要事前調査）

着手前に以下を確認:

- **WebView2 の論理サイズと物理サイズの分離**: WebView2 の `Bounds` を 2560×1440 にし、CSS の vw 計算もそれに追従するかを確認（vw は viewport の物理ピクセルではなく CSS ピクセルで計算されるので、ZoomFactor との組み合わせ次第）
- **WGC キャプチャ解像度の制御**: `win-native-app/WinNativeApp/Capture/` の WGC 初期化部で出力テクスチャ解像度がウィンドウサイズ依存か、独立指定可能か
- **FFmpeg 入力解像度の引き上げ**: `Streaming/FfmpegProcess.cs` 等の入力解像度・フィルタ・エンコード設定
- **CPU/GPU 負荷**: ピクセル数が 4 倍になる（WGC 取得 + スケールフィルタ + libx264 入力前処理）→ 配信が遅延しないか実測

#### 実装案（仮）

- **案 A（本命）**: WebView2 オフスクリーンを 2560×1440 でレンダリング → WGC でその解像度のままキャプチャ → FFmpeg で `scale=1280:720:flags=lanczos` → 配信
  - 配信先解像度（1280×720）と Twitch 推奨ビットレートは変えない
  - CSS の `vw` 計算は WebView2 のクライアント幅に追従するので、見た目の比率は維持される
- **案 B（保険）**: 配信は 1280×720 のまま、broadcast.html を表示しているコントロールパネル側 WebView2 のみ高解像度化（配信品質には影響しないが、ユーザーの「クライアント画面で見て綺麗じゃない」体験は改善）
  - 「クライアント画面」がユーザーの目で見える C# アプリのウィンドウ表示を指すなら、こっちで足りる可能性
  - ただし配信視聴者の体験は変わらない

#### 既存パイプラインとの干渉ポイント

- **録画クロップ座標 `crop=1280:720:1:38`**: これは C# アプリのウィンドウサイズ前提（タイトルバー+broadcast表示領域）。配信パイプライン（WebView2→WGC→FFmpeg）と録画（ウィンドウキャプチャ）は別経路のはずなので、案 A は配信側だけ高解像度化すれば録画クロップに影響しない想定 — ただし `Capture/` の構造を読んで二重キャプチャになっていないか確認
- **broadcast.css の px 直書き箇所**: `.edit-label { font-size: 11px }` / `.resize-handle { width: 12px }` などの px 指定はレンダリング解像度を上げると相対的に小さく見える → ただし編集モード UI なので配信に乗らない・無視可
- **アバター Canvas (VRM) のレンダリング解像度**: WebGL Canvas は `width/height` 属性で物理解像度が決まる。high-DPI 環境向けの devicePixelRatio 対応が入っていれば自動追従するが、入っていなければ別途引き上げが必要 → 要コード確認

#### 採用判断

Step 2〜4 完了後にスクショ比較し、満足度に応じて:
- 十分綺麗 → Step 5 不要
- 文字エッジの滲みが残る → 案 A を試す（4倍のレンダリング負荷を受け入れる価値があるか実測）
- 配信視聴側の品質はOKだがアプリ画面で見た時だけ気になる → 案 B（軽量）

### Step 6: 効果確認とロールバック判断

- 各ステップ実施後にスクショで before/after 比較
- 期待外の劣化（パネルはみ出し、可読性低下など）があれば該当ステップだけ revert

## 影響範囲 / リスク

- **配信視聴者に直接見える変更**: broadcast.html のテキストは配信に乗るので、変更は試聴時に確認する。配信中は変更しない
- **レイアウト崩れ**: フォントサイズを上げると vw 単位なので相対的にパネル内が窮屈になる可能性 → 個別調整で吸収
- **WSL から目視確認不可**: Claude は WSL なのでスクショ取得・ユーザー目視がボトルネック → 各ステップは「小さく1コミット」単位で進める
- **DPI 宣言 (Step 5)** はウィンドウサイズと録画クロップ座標の前提が変わるため、最終手段

## 関連ファイル

- `static/broadcast.html` — 配信合成ページ本体（最初の `<script>` で console-forwarder 読み込み済み）
- `static/css/broadcast.css` — メイン編集対象
- `win-native-app/WinNativeApp/MainForm.cs` — WebView2 初期化（Step 5 で必要なら ZoomFactor 設定追加）
- `win-native-app/WinNativeApp/WinNativeApp.csproj` — `app.manifest` 追加 (Step 5)

## 対象外（過去案からスコープ外に確定）

- `win-native-app/WinNativeApp/control-panel.html`（右パネル）
- WinForms のタイトルバー・システムトレイ
