# 3Dモデル調査レポート

AI全自動配信で3Dアバターを使用する方法を調査した。モデルの入手しやすさ、配信での使いやすさ、プログラムからの動き制御のしやすさを重視している。

---

## 3Dアバターのフォーマット: VRM

[VRM](https://vrm.dev/)は、3D人型アバター向けのファイルフォーマット。glTF 2.0をベースに、表情・視線・ライセンス情報などを1ファイルにまとめている。

### VRMの特徴

- **統一規格**: ヒューマノイドボーン構造が標準化されており、異なるアプリ間でモデルを使い回せる
- **表情制御**: BlendShape（ブレンドシェイプ）で喜怒哀楽・リップシンクを表現
- **物理演算**: 髪・服・アクセサリの揺れをシミュレーション
- **ライセンス情報内蔵**: 利用許諾条件がファイルに埋め込まれる
- **幅広い対応**: VSeeFace、VMagicMirror、Warudo、3tene、VRChat など多数のアプリが対応

BOOTHで流通する3Dアバターの大半はVRM形式（またはVRM変換可能な形式）であり、モデルの入手性が非常に高い。

---

## 表示ソフトの比較

| ソフト | 価格 | プログラム制御 | 制御方式 | OBS連携 | 特徴 |
|--------|:----:|:--------------:|----------|---------|------|
| **VSeeFace** | 無料 | ◎ | VMC Protocol (OSC) | ゲームキャプチャ | 軽量・高機能。Python連携が最も容易 |
| **VMagicMirror** | 無料 | ○ | MIDI / VMC Protocol | ゲームキャプチャ | Webカメラ不要で動く。Windows専用 |
| **Warudo** | 有料（Steam） | ◎ | WebSocket / C# SDK | ゲームキャプチャ | Blueprint + C# で高度な自動化。Twitch連携内蔵 |
| **3tene** | 無料版あり | △ | ファイル入力 | ゲームキャプチャ/NDI | 音声ファイルでリップシンク可能。API制御は限定的 |
| **three-vrm（ブラウザ）** | 無料（OSS） | ◎ | JavaScript / WebSocket | ブラウザソース | 完全自前制御。開発コスト高 |

---

## 1. VSeeFace + VMC Protocol（推奨）

[VSeeFace](https://www.vseeface.icu/)はWindows向けの無料VRMビューア。VMC Protocolによるプログラム制御が最も充実しており、Pythonからの操作が容易。

### VMC Protocolとは

[VMC Protocol](https://protocol.vmc.info/)はOSC（Open Sound Control）ベースのアバターモーション通信プロトコル。ボーンの回転・位置、表情（BlendShape）をネットワーク越しに送受信できる。

#### 送信可能なデータ

| OSCアドレス | 内容 |
|-------------|------|
| `/VMC/Ext/Bone/Pos` | ボーンの位置・回転（クォータニオン） |
| `/VMC/Ext/Blend/Val` | BlendShapeの値（表情・リップシンク） |
| `/VMC/Ext/Blend/Apply` | BlendShape値の適用トリガー |
| `/VMC/Ext/Root/Pos` | ルートの位置・回転 |

#### Pythonライブラリ: python-vmcp

[python-vmcp](https://codeberg.org/low-cost-body-tracking/python-vmcp)はVMC Protocolのpython実装。

```python
# python-vmcpによるBlendShape送信例
from vmcp import VMCPSender
from vmcp.events import BlendShapeEvent

sender = VMCPSender("127.0.0.1", 39539)

# リップシンク（口を開ける）
sender.send(BlendShapeEvent("A", 0.8))  # 「あ」の口
sender.send(BlendShapeEvent("Blink_L", 1.0))  # 左目を閉じる
```

#### python-oscを使う場合

```python
from pythonosc import udp_client

client = udp_client.SimpleUDPClient("127.0.0.1", 39539)

# BlendShape送信
client.send_message("/VMC/Ext/Blend/Val", ["Joy", 1.0])
client.send_message("/VMC/Ext/Blend/Apply", [])

# ボーン回転送信（ボーン名, px, py, pz, qx, qy, qz, qw）
client.send_message("/VMC/Ext/Bone/Pos", [
    "Head", 0.0, 0.0, 0.0, 0.0, 0.1, 0.0, 1.0
])
```

### VSeeFace側の設定

1. VSeeFaceの設定 → VMC Protocol receiverを有効化
2. ポート番号を指定（デフォルト: 39539）
3. Pythonプログラムから同じポートにOSCメッセージを送信

### OBSとの連携

- **ゲームキャプチャ**: VSeeFaceウィンドウをキャプチャ（背景透過対応）
- VSeeFaceで「背景を透明にする」設定を有効にし、OBSのゲームキャプチャで「透過を許可」にチェック

### AI配信での活用

1. TTS音声の音量を解析し、VMC ProtocolでBlendShape（A, I, U, E, O）を送信 → リップシンク
2. LLMの出力に応じて表情BlendShape（Joy, Angry, Sorrow, Fun）を送信
3. ボーン制御で頷き・手振りなどのジェスチャーを再現
4. アイドル時は自動的にまばたき・呼吸アニメーション

### 評価

- **メリット**: 無料。Python連携が最も簡単。軽量で安定。VMC Protocolはオープン仕様
- **デメリット**: Windows専用。UI/見た目のカスタマイズはWarudoに劣る

---

## 2. VMagicMirror

[VMagicMirror](https://malaybaku.github.io/VMagicMirror/)はWebカメラやVR機器なしで3Dアバターを動かせるWindows向け無料アプリ。キーボード・マウス操作をアバターの動きに反映できる。

### プログラム制御

- **MIDI制御**: PythonからMIDIメッセージを送信して表情切替が可能
- **VMC Protocol**: 受信側としてVMC Protocolに対応
- フェイストラッキングなしでもアイドルモーションが動く

```python
# MIDIで表情を制御する例
import mido

port = mido.open_output('VMagicMirror')  # 仮想MIDIポート
# ノート番号に表情をマッピング
port.send(mido.Message('note_on', note=60))  # 笑顔
```

### 評価

- **メリット**: カメラ不要で動く。無料。配信画面に馴染むデスクトップマスコットモード
- **デメリット**: プログラム制御はMIDI経由が主で、VSeeFaceほど柔軟ではない

---

## 3. Warudo

[Warudo](https://store.steampowered.com/app/2079120/Warudo/)は高機能な3D VTuber配信ソフト。Blueprint（ビジュアルスクリプティング）とC# SDK、WebSocketによる外部制御を提供。

### プログラム制御

- **WebSocket**: 外部プログラムからWebSocketメッセージでBlueprintをトリガー可能
- **C# SDK**: カスタムノード・プラグインの開発が可能。ホットリロード対応
- **MIDI / Stream Deck**: 物理デバイスからの制御もサポート
- **VMC Protocol受信**: 他アプリからのモーションデータを受信可能

### Twitch連携

Twitch連携が内蔵されており、チャットイベントやサブスクリプションに応じてアニメーションをトリガーする仕組みがBlueprintで構築可能。

### 評価

- **メリット**: 最も高機能。ビジュアルが美麗。Twitch連携内蔵。WebSocket制御が強力
- **デメリット**: 有料（Steam）。C# SDKの学習コストがある。リソース消費が大きい

---

## 4. 3tene

[3tene](https://3tene.com/)はVRM対応の3Dアバター操作アプリ。FREE版（無料）とPRO版（有料）がある。

### プログラム制御

- WAVファイルからのリップシンク自動生成
- MP4ファイルからのフェイストラッキング
- 自動実行機能（AutoRun）でプリセット動作を再生可能
- **APIによる外部制御は限定的**

### 評価

- **メリット**: 無料版あり。音声ファイルベースのリップシンクが簡単
- **デメリット**: リアルタイムのプログラム制御APIが乏しい。自動配信には不向き

---

## 5. three-vrm（ブラウザ自前実装）

[three-vrm](https://github.com/pixiv/three-vrm)はpixiv製のThree.jsライブラリ。ブラウザ上でVRMモデルを表示・制御できる。

### 仕組み

1. Three.js + three-vrmでWebアプリを構築
2. WebSocketサーバーを内蔵し、Pythonプログラムからコマンドを受信
3. OBSのブラウザソースとして表示

```javascript
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader';
import { VRMLoaderPlugin } from '@pixiv/three-vrm';

const loader = new GLTFLoader();
loader.register((parser) => new VRMLoaderPlugin(parser));

loader.load('/avatar.vrm', (gltf) => {
  const vrm = gltf.userData.vrm;
  scene.add(vrm.scene);

  // 表情制御
  vrm.expressionManager.setValue('happy', 1.0);

  // リップシンク
  vrm.expressionManager.setValue('aa', 0.8);

  // ボーン制御（手を振るなど）
  const rightArm = vrm.humanoid.getBoneNode('rightUpperArm');
  rightArm.rotation.z = -Math.PI / 4;
});
```

### VRMAアニメーション

VRM Animation（.vrma）ファイルにより、事前定義されたアニメーションを再生可能。BOOTHなどでVRMAファイルも流通している。

### 評価

- **メリット**: 完全に自由な制御。外部アプリ不要（OBSだけで完結）。クロスプラットフォーム
- **デメリット**: Web開発（TypeScript/JavaScript）が必要。開発コストが高い

---

## モデルの入手方法

### 1. BOOTHで購入・入手

[BOOTH](https://booth.pm/)はVRM 3Dモデルの最大級マーケットプレイス。20,000件以上のVRMモデルが流通。

| 検索キーワード | 件数（目安） | 備考 |
|----------------|:------------:|------|
| [VRMモデル](https://booth.pm/ja/search/VRM%E3%83%A2%E3%83%87%E3%83%AB) | 12,000+ | VRM対応モデル全般 |
| [商用利用可 3Dモデル](https://booth.pm/ja/browse/3D%E3%83%A2%E3%83%87%E3%83%AB?q=%E5%95%86%E7%94%A8%E5%88%A9%E7%94%A8%E5%8F%AF) | 16,000+ | 商用利用OK |
| [無料配布 3Dモデル](https://booth.pm/ja/browse/3D%E3%83%A2%E3%83%87%E3%83%AB?q=%E7%84%A1%E6%96%99%E9%85%8D%E5%B8%83) | 17,000+ | 無料モデル |

#### 選定時の注意点

- **ライセンス確認**: 配信での使用可否、商用利用可否を必ず確認する
- **VN3ライセンス**: BOOTHの人気3Dモデルの約70%が採用。条件が明確で分かりやすい
- **VRM形式の確認**: VRChat専用（.unitypackage）のみの場合はVRM変換が必要になることがある
- **ボーン・BlendShape**: 表情差分やリップシンク用BlendShapeの充実度を確認する

### 2. VRoid Studioで自作

[VRoid Studio](https://vroid.com/studio)はpixiv提供の無料3Dアバター作成ツール。

- **完全無料**: 全機能が無料で利用可能
- **直感的操作**: パーツ選択・カスタマイズで3Dモデルを作成。絵が描けなくてもOK
- **VRM出力**: 作成したモデルをVRM形式で直接エクスポート可能
- **BlendShape充実**: 標準でリップシンク・表情用BlendShapeが含まれる
- **VRoid Hub**: 作成したモデルを[VRoid Hub](https://hub.vroid.com/)にアップロード・共有可能

### 3. その他の入手先

| 入手先 | 特徴 |
|--------|------|
| [VRoid Hub](https://hub.vroid.com/) | VRoid Studioで作られたモデルが多数。一部ダウンロード可能 |
| [ニコニ立体](https://3d.nicovideo.jp/) | ニコニコ発の3Dモデル共有サイト |
| [THE SEED ONLINE](https://seed.online/) | VRM対応の3Dモデルマーケット |

---

## Live2D（2D）との比較

| 観点 | Live2D（2D） | VRM（3D） |
|------|:------------:|:---------:|
| **モデル入手性** | BOOTHやnizimaで入手可 | BOOTHに大量。VRoid Studioで無料自作も容易 |
| **表現の自由度** | 正面メインの表現 | 360度回転・全身の動きが可能 |
| **リップシンク** | VTube Studio APIで制御 | VMC ProtocolのBlendShapeで制御 |
| **表情制御** | VTube Studio APIで制御 | VMC ProtocolのBlendShapeで制御 |
| **身体の動き** | 限定的（上半身の傾き程度） | ボーン制御で手振り・頷き・全身ポーズが可能 |
| **プログラム制御** | pyvts（VTube Studio API） | python-vmcp / python-osc（VMC Protocol） |
| **表示ソフト** | VTube Studio | VSeeFace / VMagicMirror / Warudo |
| **見た目の印象** | アニメ調で親しみやすい | 立体感がある。VTuber配信では3Dも一般的 |
| **リソース消費** | 軽量 | やや重い（3D描画） |

---

## 本プロジェクトでの推奨

### 推奨構成: VSeeFace + VMC Protocol

| 項目 | 選定 |
|------|------|
| **フォーマット** | VRM |
| **表示ソフト** | VSeeFace |
| **制御プロトコル** | VMC Protocol（OSC） |
| **Pythonライブラリ** | python-osc または python-vmcp |
| **モデル入手** | VRoid Studio自作 or BOOTH購入 |

### 選定理由

1. **プログラム制御が最も容易**: VMC ProtocolはOSCベースで、PythonからBlendShape・ボーン制御が直接できる
2. **モデル入手が容易**: BOOTHに大量のVRMモデルがある。VRoid Studioで無料自作も可能
3. **動きの自由度が高い**: Live2Dと違い、全身のボーン制御で頷き・手振り・ポーズなど多彩なジェスチャーが可能
4. **無料で構築可能**: VSeeFace、python-osc、VRoid Studioすべて無料
5. **既存のLive2D環境との共存**: VSeeFaceとVTube Studioは併用でき、段階的に移行できる

### 実装ステップ

1. **VSeeFaceの導入**: VRMモデルを読み込み、OBSゲームキャプチャで透過表示
2. **VMC Protocol受信の設定**: VSeeFaceでVMC Protocol receiverを有効化
3. **Pythonコントローラの実装**: python-oscでBlendShape/ボーン制御
4. **リップシンク連携**: TTS音声の振幅解析 → 口のBlendShape送信
5. **表情・ジェスチャー連携**: LLMの感情分析 → 表情BlendShape + ボーン制御

### 将来的な選択肢

- **Warudo**: 見た目の品質を上げたい場合。WebSocket制御でPythonから操作可能。Twitch連携内蔵
- **three-vrm（ブラウザ）**: 外部アプリを排除したい場合。完全自前制御が可能

---

## 参考資料

- [VRM公式サイト](https://vrm.dev/)
- [VRMコンソーシアム](https://vrm-consortium.org/)
- [VSeeFace](https://www.vseeface.icu/)
- [VMC Protocol仕様](https://protocol.vmc.info/english.html)
- [python-vmcp（Codeberg）](https://codeberg.org/low-cost-body-tracking/python-vmcp)
- [VroidPoser（VMC送信ツール）](https://github.com/NeilioClown/VroidPoser)
- [VMagicMirror](https://malaybaku.github.io/VMagicMirror/)
- [Warudo（Steam）](https://store.steampowered.com/app/2079120/Warudo/)
- [Warudo Handbook](https://docs.warudo.app/)
- [3tene](https://3tene.com/)
- [three-vrm（GitHub）](https://github.com/pixiv/three-vrm)
- [VRoid Studio](https://vroid.com/studio)
- [BOOTH - VRMモデル](https://booth.pm/ja/search/VRM%E3%83%A2%E3%83%87%E3%83%AB)
- [VN3ライセンス](https://www.vn3.org/)
