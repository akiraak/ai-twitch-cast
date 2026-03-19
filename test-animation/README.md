# VRM Animation 動作検証ページ

本番コードとは完全に独立した検証環境。VRMモデルに対する表情・アニメーション・ライブラリの動作確認用。

## 起動方法

```bash
cd test-animation
python3 -m http.server 8888
```

ブラウザで `http://localhost:8888/` を開く。

## 使い方

### Idle Animation
- **Scale** スライダーで動きの大きさを調整（0〜3）
- 0でアイドル停止、1が通常、2以上で大げさに動く

### 表情（BlendShape）テスト
- プリセットボタン（neutral / joy / angry / sad / fun / surprise / thinking / excited）をクリックで切替
- VRMモデルが持つ各BlendShapeの個別スライダーでも調整可能

### 表情イージング
- **Duration** スライダーで表情遷移の補間時間を設定（0〜2000ms）
- 0ms = 瞬間切替、300ms = 自然な遷移

### VRMAアニメーション再生
- `.vrma` ファイルをページ上にドラッグ＆ドロップ
- `@pixiv/three-vrm-animation` で読み込み、AnimationMixerで再生される

#### .vrmaファイルの入手先
- VRoid公式（無料7種）: https://vroid.booth.pm/items/5512385
- BOOTH「3Dモーション」カテゴリで検索

### Mixamo FBXアニメーション
- https://www.mixamo.com/ からFBXをダウンロード（Adobe ID必要、無料）
  - キャラクターは何でもOK（ボーンリターゲットされる）
  - Format: **FBX Binary (.fbx)** を選択
  - **Without Skin** 推奨（ファイルサイズ小）
- `.fbx` ファイルをページにドラッグ＆ドロップ、またはファイル選択ボタンで読み込み
- Mixamoボーン名 → VRMヒューマノイドボーンへの自動リターゲットが行われる

#### おすすめMixamoモーション
| 検索ワード | 用途 |
|-----------|------|
| Talking | 会話中の身振り |
| Waving | 手を振る（挨拶） |
| Nod | うなずき |
| Thinking | 考え中 |
| Clapping | 拍手 |
| Dancing | ダンス |
| Idle | 待機バリエーション |
| Excited | 喜び・興奮 |

### アニメーション制御
- **Crossfade** スライダーで idle↔アニメーションの切替の滑らかさを調整（0〜2秒）
- **Stop Animation** ボタンでアニメーション停止、idleに戻る

### デバッグ
- **List Bones** — VRMモデルのボーン一覧をログに表示
- **List Expressions** — 利用可能なBlendShape一覧をログに表示
- 画面左下にログが表示される

## ファイル構成

```
test-animation/
├── index.html              # 検証ページ（HTML + JS 全部入り）
├── README.md               # このファイル
└── resources/
    ├── Shinano.vrm          # VRMモデル（本体からコピー）
    └── background.png       # 背景画像（本体からコピー）
```

## 使用ライブラリ（CDN読み込み）

| ライブラリ | バージョン | 用途 |
|-----------|----------|------|
| Three.js | 0.169.0 | 3Dレンダリング |
| @pixiv/three-vrm | 3.3.3 | VRMモデル読込・表示 |
| @pixiv/three-vrm-animation | 3.3.3 | .vrmaアニメーション再生 |
| Three.js FBXLoader | 0.169.0 | Mixamo FBX読込 |
