# リソース管理方針

すべてのリソース（画像、Live2Dモデル、音声等）はWSLのリポジトリで一元管理する。OBSやVTube Studioには設定のみ行い、リソースファイルを残さない。

---

## 基本方針

- リソースの実体は `ai-twitch-cast/resources/` 配下に配置する
- OBS・VTube StudioからはWSLファイルシステム経由（`\\wsl.localhost\`）でアクセスする
- シーン・ソースはスクリプトから動的に作成し、OBSに事前設定しない

## OBS

### 仕組み

OBS WebSocket APIでソースを作成する際、ファイルパスにWSLのWindowsパスを指定する。

```
\\wsl.localhost\<ディストリビューション名>\home\ubuntu\ai-twitch-cast\resources\images\background.png
```

これにより画像・動画・音声などのリソースをWSL側に置いたまま、OBSから参照できる。

### 実現方法

| 操作 | 方法 |
|------|------|
| シーン作成 | `CreateScene` APIで動的に作成 |
| 画像ソース追加 | `CreateInput` APIでWSLパスを指定 |
| テキスト追加 | `CreateInput` APIでテキスト内容を直接設定 |
| ブラウザソース追加 | `CreateInput` APIでURLを指定 |
| ソース削除 | `RemoveInput` APIで終了時にクリーンアップ |

### 注意点

- WSLのパスは `\\wsl.localhost\<ディストリビューション名>\...` 形式を使う
- WSLディストリビューション名は環境によって異なる（`Ubuntu`、`Sandbox24`等）
- OBSのシーンコレクション設定はWindows側に残るが、リソースファイル自体はWSLにのみ存在する

## VTube Studio

### 制約

VTube StudioはLive2Dモデルを特定のフォルダから読み込む:

```
<VTube Studioインストール先>/VTube Studio_Data/StreamingAssets/Live2DModels/<モデル名>/
```

WSLファイルシステムから直接モデルをロードすることはできない。

### 解決策: スクリプトでモデルをデプロイ

リポジトリ内のモデルデータをVTube Studioのモデルフォルダにコピーするスクリプトで対応する。

```bash
# デプロイ: WSL → VTube Studio
python scripts/deploy_model.py

# クリーンアップ: VTube Studioからモデルを削除
python scripts/deploy_model.py --clean
```

これにより:

- **リソースの実体**はWSLリポジトリで管理
- VTube Studioには**デプロイ時にのみコピー**が作られる
- 不要になったら `--clean` で削除できる

### モデルフォルダ構成

```
resources/
└── live2d/
    └── <モデル名>/
        ├── <モデル名>.model3.json
        ├── <モデル名>.moc3
        ├── textures/
        └── ...
```

## リソースディレクトリ構成

```
resources/
├── images/          # 背景画像、ロゴ、オーバーレイ等
├── live2d/          # Live2Dモデルデータ
├── audio/           # BGM、効果音
└── video/           # オープニング、ジングル等の動画素材
```

## 環境変数

`.env` にVTube Studioのモデルフォルダパスを設定する:

```
VTS_MODELS_DIR=C:\Program Files (x86)\Steam\steamapps\common\VTube Studio\VTube Studio_Data\StreamingAssets\Live2DModels
```
