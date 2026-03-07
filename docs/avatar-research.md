# アバター表示・アニメーション調査レポート

AI全自動配信でアバターを表示・動作させる方法を調査した。プログラムから制御可能かどうかを重視している。

---

## 方式の比較

| 方式 | 表現力 | 導入コスト | プログラム制御 | 備考 |
|------|:------:|:----------:|:--------------:|------|
| **PNGtuber** | ★★☆ | ★☆☆ | ◎ | 画像切替のみ。最もシンプル |
| **Live2D + VTube Studio** | ★★★ | ★★☆ | ◎ | 2Dアバターの業界標準。API充実 |
| **Live2D + ブラウザソース** | ★★★ | ★★★ | ◎ | 自前実装。柔軟だが開発コスト高 |
| **VRM（3Dモデル）+ ブラウザ** | ★★★ | ★★★ | ○ | 3Dアバター。Web上で表示可能 |

---

## 1. PNGtuber（画像切替方式）

最もシンプルなアバター表示方法。口を開けた画像・閉じた画像など数枚のPNGを用意し、音声入力に応じて切り替える。

### 仕組み

- 静止画を数枚用意（通常時・発話時・表情差分など）
- 音声レベルに応じて画像を切り替えることで「しゃべっている感」を出す
- フェイストラッキング不要

### ツール

| ツール | 特徴 |
|--------|------|
| [obs-pngtuber](https://github.com/dungodoot/obs-pngtuber) | OBSブラウザソースで動作。React製。外部アプリ不要 |
| [Flood-Tuber](https://obsproject.com/forum/resources/flood-tuber-native-pngtuber-plugin.2336/) | OBSネイティブプラグイン。軽量 |
| [PNGtuber Enhanced](https://kylealamode.itch.io/pngtuber-enhanced) | レイヤーベースのアニメーション。音声反応あり |

### プログラム制御

- OBSのソース切替（`SetSceneItemEnabled`）で画像を表示/非表示にするだけで実装可能
- ブラウザソース方式なら、WebSocket等で外部からトリガーを送ることも可能
- **AI配信では、TTS再生タイミングに合わせて画像を切り替えるだけで十分機能する**

### 評価

- **メリット**: 実装が極めて簡単。リソース消費が少ない。画像さえあれば始められる
- **デメリット**: 表現が限定的。滑らかなアニメーションはできない

---

## 2. Live2D + VTube Studio（推奨）

2Dアバターの業界標準。Live2Dモデルを用意し、VTube Studioで表示・アニメーションする。VTube Studio APIにより**プログラムからの制御が充実**している。

### VTube Studio API

WebSocketベースのAPI。ポート8001でローカルサーバーが起動する。

#### できること

- **パラメータ制御**: 目の開閉、口の開閉、体の傾きなどのパラメータ値をプログラムから設定
- **表情の切替**: 事前に定義した表情（Expression）をトリガー
- **ホットキーの実行**: モーションやアニメーションの再生
- **モデルの位置・回転・拡大縮小**: 画面上のモデル配置を制御
- **カスタムパラメータの追加**: 独自のパラメータを作成してモデルに反映
- **フェイストラッキングとの混合**: API制御とトラッキングの値を任意の比率で混合可能

#### Pythonライブラリ: pyvts

```python
import pyvts
import asyncio

async def main():
    vts = pyvts.vts(plugin_info={
        "plugin_name": "AI Twitch Cast",
        "developer": "ai-twitch-cast",
    })
    await vts.connect()
    await vts.request_authenticate_token()
    await vts.request_authenticate()

    # 口の開閉パラメータを設定（リップシンク）
    await vts.request(
        vts.vts_request.requestSetParameterValue(
            parameter="MouthOpen",
            value=1.0,  # 0.0（閉じ）〜 1.0（開き）
        )
    )

    # 表情を切り替え
    await vts.request(
        vts.vts_request.requestTriggerHotKey(hotkeyID="expression_happy")
    )

    await vts.close()

asyncio.run(main())
```

### Live2Dモデルの入手方法

#### 1. マーケットプレイスで購入する

既製品のモデルを購入する方法。すぐに使い始められる。

| プラットフォーム | 特徴 | 価格帯 |
|----------------|------|--------|
| [nizima](https://nizima.com/) | Live2D公式マーケット。品質が高い。オーダーメイド依頼も可能 | 3,000〜50,000円程度 |
| [BOOTH](https://booth.pm/) | 国内最大級。無料配布モデルも多数。「Live2D」で検索 | 無料〜30,000円程度 |
| [VGen](https://vgen.co/category/vtuber-model-art) | 海外クリエイターへのコミッション（オーダーメイド） | $100〜$1,000+ |
| [Fiverr](https://www.fiverr.com/gigs/live2d) | 海外フリーランスへの制作依頼 | $50〜$500+ |
| [vtuber.gg](https://vtuber.gg/) | VTuberモデル専門マーケット | 様々 |

**モデルの種類**:

- **汎用モデル（安価）**: 誰でも購入・使用可能。同じモデルを他の人も使う可能性がある
- **買い切りモデル（高価）**: 購入者専用。他の人とかぶらない

#### 2. 無料モデルを使う

学習用・テスト用にはまず無料モデルがおすすめ。

| 配布元 | 内容 |
|--------|------|
| [Live2D公式サンプル](https://www.live2d.com/en/learn/sample/) | 公式の学習用サンプルモデル |
| [BOOTH（無料）](https://booth.pm/en/search/free%20live2d) | クリエイターが無料配布しているモデル（1,000件以上） |
| VTube Studio内蔵 | VTube Studioにデフォルトで数体のモデルが付属 |

!!! note "ライセンスに注意"
    無料モデルでも利用条件（商用利用可否、クレジット表記、改変の可否等）はモデルごとに異なる。配信で使用する前に必ず確認すること。

#### 3. 自作する

Live2D Cubism Editorでイラストからモデルを制作する。

**必要なもの**:

- イラスト（パーツごとにレイヤー分けしたPSD）
- [Live2D Cubism Editor](https://www.live2d.com/en/cubism/download/editor/)（FREE版あり）

**FREE版の制限**:

- ArtMesh（レイヤー）: 最大100個
- パーツ（フォルダ）: 最大30個
- デフォーマ数に制限あり
- テクスチャアトラスのサイズ制限

シンプルなバストアップモデルであればFREE版でも制作可能。細かい動きや全身モデルにはPRO版（月額/年額）が必要。

**制作期間の目安**:

- 基本的な上半身モデル: 1〜2週間（初心者）
- 全身＋細かい表情差分: 約1ヶ月

#### 本プロジェクトでの推奨

1. **まずはVTube Studio内蔵モデルやBOOTHの無料モデルでテスト**
2. 動作確認が取れたら、nizimaやBOOTHで本番用モデルを購入
3. 必要に応じてオーダーメイドや自作を検討

### OBSとの連携

VTube Studioの画面をOBSで取り込む方法:

1. **ゲームキャプチャ**: VTube Studioウィンドウをキャプチャ（背景透過可能）
2. **Spout2**: 高品質な映像共有（Windows。Spout2プラグインが必要）

### AI配信での活用

1. TTS音声の音量/タイミングを解析
2. pyvtsで口の開閉パラメータ（MouthOpen）をリアルタイムに制御 → リップシンク
3. LLMの出力内容に応じて表情をトリガー（嬉しい・悲しい・驚き等）
4. アイドル時は自動的にまばたき・呼吸アニメーション（VTube Studio内蔵）

### 評価

- **メリット**: 表現力が高い。API経由で細かく制御可能。エコシステムが充実
- **デメリット**: Live2Dモデルの準備が必要（制作 or 購入）。VTube Studioを別途起動する必要がある

---

## 3. Live2D + ブラウザソース（自前実装）

OBSのブラウザソース上でLive2D Cubism SDK for Webを使い、自前でアバターを描画・制御する方式。

### 技術スタック

- [Live2D Cubism SDK for Web](https://www.live2d.com/en/sdk/download/web/) - TypeScript/JavaScript
- [CubismWebFramework](https://github.com/Live2D/CubismWebFramework) - Live2D公式フレームワーク
- [pixi-live2d-display](https://github.com/guansss/pixi-live2d-display) - PixiJS上でLive2Dモデルを表示するライブラリ

### 仕組み

1. Webアプリとしてアバターを描画
2. WebSocketサーバーを内蔵し、Pythonプログラムからコマンドを受信
3. OBSのブラウザソースとしてURLを設定

### 評価

- **メリット**: 完全に自由な制御が可能。外部アプリ不要（OBSだけで完結）
- **デメリット**: 開発コストが高い。Live2D SDKのライセンス条件に注意が必要

---

## 4. VRM（3Dアバター）+ ブラウザ

3Dの人型アバター（VRMフォーマット）をWeb上で表示する方式。VRoidStudioで無料作成可能。

### 技術スタック

- [three-vrm](https://github.com/pixiv/three-vrm) - pixiv製。Three.js上でVRMを表示
- [VRoid Studio](https://vroid.com/studio) - 無料の3Dアバター作成ツール

### できること

- ボーン制御による体の動き
- ブレンドシェイプによる表情制御（喜怒哀楽、リップシンク）
- 物理シミュレーション（髪・服の揺れ）
- VRMAアニメーションの再生

### コード例（three-vrm）

```javascript
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader';
import { VRMLoaderPlugin } from '@pixiv/three-vrm';

const loader = new GLTFLoader();
loader.register((parser) => new VRMLoaderPlugin(parser));

loader.load('/avatar.vrm', (gltf) => {
  const vrm = gltf.userData.vrm;
  scene.add(vrm.scene);

  // 表情を設定
  vrm.expressionManager.setValue('happy', 1.0);

  // リップシンク
  vrm.expressionManager.setValue('aa', 0.8);  // 「あ」の口

  // ボーンを回転（手を振る等）
  const rightArm = vrm.humanoid.getBoneNode('rightUpperArm');
  rightArm.rotation.z = -Math.PI / 4;
});
```

### 評価

- **メリット**: 3Dならではの立体感。VRoid Studioで無料作成可能。ブラウザソースで完結
- **デメリット**: 3D描画の負荷がやや高い。2Dに比べて「VTuberらしさ」が異なる

---

## 5. 既存のAI VTuberシステム（参考）

フルスタックのAI VTuberシステムが複数オープンソースで公開されている。

| プロジェクト | 特徴 |
|-------------|------|
| [AI-VTuber-System](https://github.com/topics/ai-vtuber) | LLM + TTS + VTube Studio + OBS の統合システム |
| [Persona Engine](https://github.com/fagenorn/handcrafted-persona-engine) | Live2D + LLM + TTS + RVC。感情駆動アニメーション |

これらはパイプラインの参考になるが、本プロジェクトでは各コンポーネントを自前で組み立てる方針のため、直接採用はしない。

---

## 推奨アプローチ

本プロジェクト（AI全自動Twitch配信）では、以下の段階的なアプローチを推奨する。

### Phase 1: PNGtuber（まず動かす）

- 数枚のアバター画像を用意（通常・発話中・表情差分）
- TTS再生タイミングに合わせてOBSソースを切り替え
- 最小限の実装でアバター付き配信を実現

### Phase 2: Live2D + VTube Studio（本格化）

- Live2Dモデルを用意
- pyvtsでリップシンク・表情制御を実装
- LLMの感情分析と連動して表情を自動切替

### 選定理由

- VTube Studio + pyvtsの組み合わせが、**プログラム制御のしやすさ**と**表現力**のバランスが最も良い
- PNGtuberで素早くプロトタイプし、後からLive2Dに移行できる
- ブラウザソース自前実装は開発コストが高く、現時点では不要

---

## 参考資料

- [VTube Studio API - GitHub](https://github.com/DenchiSoft/VTubeStudio)
- [pyvts - Python VTube Studio API ライブラリ](https://github.com/Genteki/pyvts)
- [pyvts ドキュメント](https://genteki.github.io/pyvts/)
- [Live2D Cubism SDK for Web](https://docs.live2d.com/en/cubism-sdk-manual/cubism-sdk-for-web/)
- [pixi-live2d-display](https://guansss.github.io/pixi-live2d-display/)
- [three-vrm - pixiv](https://github.com/pixiv/three-vrm)
- [VRoid Studio](https://vroid.com/studio)
- [obs-pngtuber](https://github.com/dungodoot/obs-pngtuber)
- [Persona Engine](https://github.com/fagenorn/handcrafted-persona-engine)
