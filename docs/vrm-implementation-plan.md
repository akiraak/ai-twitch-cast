# VRM 3Dキャラ表示 実装プラン

VRM形式の3Dモデルをプログラムから制御し、OBS経由で配信に表示するための実装プラン。

---

## 現状

- Live2D + VTube Studio でアバターを表示・制御している
- `VTSController` が VTube Studio API (WebSocket) を通じて表情・リップシンクを制御
- `scene_config.py` でOBSのゲームキャプチャソースとしてVTube Studioウィンドウを取り込んでいる

## 目標

- VRM形式の3DモデルをVSeeFaceで表示し、VMC Protocol (OSC) でプログラムから制御する
- 既存のLive2D対応を残しつつ、VRM/VSeeFaceを**並行して使える**構成にする
- コンソールから統一的に操作できるようにする

---

## 構成図

```
Python (console.py)
├── OBSController         ... OBS WebSocket (既存)
├── VTSController         ... VTube Studio WebSocket (既存・Live2D用)
└── VSFController (新規)  ... VMC Protocol (OSC) → VSeeFace
                                ↓
                          VSeeFace (Windows)
                                ↓ ゲームキャプチャ
                          OBS Studio → Twitch配信
```

---

## 実装ステップ

### Step 1: VSFController の作成

`src/vsf_controller.py` を新規作成。VMC Protocol (OSC) でVSeeFaceを制御するクラス。

**依存ライブラリ**: `python-osc`（`requirements.txt` に追加）

```python
class VSFController:
    """VSeeFace を VMC Protocol (OSC) で制御するクラス"""

    def __init__(self, host=None, port=None):
        # OSC UDPクライアントを作成

    def connect(self):
        # UDPなので実際の接続は不要だが、初期化とテスト送信

    def disconnect(self):
        # クライアントのクリーンアップ

    def set_blendshape(self, name: str, value: float):
        # /VMC/Ext/Blend/Val → /VMC/Ext/Blend/Apply

    def set_blendshapes(self, shapes: dict[str, float]):
        # 複数のBlendShapeを一括送信

    def set_bone(self, bone: str, px, py, pz, qx, qy, qz, qw):
        # /VMC/Ext/Bone/Pos でボーンの位置・回転を送信

    def set_root(self, px, py, pz, qx, qy, qz, qw):
        # /VMC/Ext/Root/Pos でルート位置を送信
```

**主要なBlendShape名**:

| 用途 | BlendShape名 |
|------|-------------|
| リップシンク | `A`, `I`, `U`, `E`, `O` |
| 表情 | `Joy`, `Angry`, `Sorrow`, `Fun` |
| まばたき | `Blink`, `Blink_L`, `Blink_R` |

**主要なボーン名**:

| 用途 | ボーン名 |
|------|---------|
| 頭の向き | `Head` |
| 首 | `Neck` |
| 上半身 | `Spine`, `Chest`, `UpperChest` |
| 腕 | `LeftUpperArm`, `RightUpperArm` |

### Step 2: scene_config.py の拡張

VSeeFace用のゲームキャプチャソースを定義。既存のVTS用と切り替えられるようにする。

```python
# アバター表示ソフトの設定
AVATAR_APP = os.environ.get("AVATAR_APP", "vts")  # "vts" or "vsf"

AVATAR_SOURCES = {
    "vts": {
        "name": f"{PREFIX}アバター",
        "kind": "game_capture",
        "window": "VTube Studio:UnityWndClass:VTube Studio.exe",
        "allow_transparency": True,
        ...
    },
    "vsf": {
        "name": f"{PREFIX}アバター",
        "kind": "game_capture",
        "window": "VSeeFace:UnityWndClass:VSeeFace.exe",
        "allow_transparency": True,
        ...
    },
}
```

`AVATAR_APP` 環境変数で使用するアバターアプリを切り替える。

### Step 3: コンソールコマンドの追加

`scripts/console.py` に VSeeFace 操作コマンドを追加。

```
vsf connect               VSeeFace (VMC Protocol) に接続
vsf disconnect             切断
vsf status                 接続状態を表示
vsf blendshape <名前> <値> BlendShapeを設定（例: vsf blendshape Joy 1.0）
vsf bone <名前> <qx> <qy> <qz> <qw>  ボーン回転を設定
vsf demo                   デモアニメーション（リップシンク＋表情＋頷き）
```

### Step 4: 環境設定の追加

`.env.example` に VSeeFace 関連の設定を追加。

```env
# アバター表示アプリ: "vts"（VTube Studio）or "vsf"（VSeeFace）
AVATAR_APP=vsf

# VSeeFace (VMC Protocol) 設定
VSF_OSC_HOST=127.0.0.1
VSF_OSC_PORT=39539
```

### Step 5: VRMモデルのデプロイ対応

`scripts/deploy_model.py` を拡張し、VRMモデルのVSeeFaceへのデプロイに対応。

- VSeeFaceはモデルフォルダを指定して直接読み込むため、VTSのようなコピーは不要
- `resources/vrm/` にVRMファイルを配置するだけでよい
- コンソールから `vsf model <path>` でモデル読み込み（VSeeFace起動時の引数 or 手動選択）

### Step 6: ドキュメント更新

- `docs/console-commands.md` に vsf コマンドを追記
- `docs/resource-management.md` に VRM リソースの管理方法を追記
- `CLAUDE.md` のディレクトリ構成を更新

---

## ファイル変更一覧

| ファイル | 変更内容 |
|----------|----------|
| `src/vsf_controller.py` | **新規作成** VMC Protocol制御クラス |
| `src/scene_config.py` | VSeeFace用ゲームキャプチャ定義を追加 |
| `scripts/console.py` | vsf コマンド群を追加 |
| `requirements.txt` | `python-osc` を追加 |
| `.env.example` | `AVATAR_APP`, `VSF_OSC_HOST`, `VSF_OSC_PORT` を追加 |
| `docs/console-commands.md` | vsf コマンドのリファレンスを追記 |
| `docs/resource-management.md` | VRMリソース管理を追記 |

---

## VSeeFace側の事前設定

### 1. インストール

1. [VSeeFace公式サイト](https://www.vseeface.icu/) からダウンロード
2. zipを展開し、任意のフォルダに配置（インストーラなし）
3. `VSeeFace.exe` を起動

### 2. VRMモデルの読み込み

1. 起動時のモデル選択画面で「VRM file」からVRMファイルを選択
2. または画面上部のカメラアイコン横のモデル選択ボタンからロード

### 3. VMC Protocol Receiver の有効化

外部プログラム（本プロジェクトのPythonスクリプト）からアバターを制御するために必要。

1. 画面右端の **歯車アイコン** をクリック → 設定画面を開く
2. **「General settings」** タブを選択
3. 下にスクロールして **「VMC protocol」** セクションを見つける
4. **「Enable VMC protocol receiver」** にチェックを入れる
5. **ポート番号**: `39539`（デフォルトのまま）

!!! warning "ポートの注意"
    VMC protocol の **sender（送信）** と **receiver（受信）** のポートが同じにならないようにすること。同じポートに設定するとアバターが異常動作する。senderを使わない場合は無効のままでよい。

!!! note "BlendShapeの制限"
    VMC Protocol経由でBlendShapeを受信すると、VSeeFace内蔵の表情検出やホットキーによる表情切替は無効になる。本プロジェクトではプログラムから全制御するため問題ない。

### 4. 背景の透過設定

OBSのゲームキャプチャで透過表示するために必要。

1. 設定画面の **「General settings」** タブ
2. **「Background color」** セクションで **「transparent」** を選択（緑色の背景が消える）

### 5. OBSでの取り込み

1. OBSで **「ゲームキャプチャ」** ソースを追加
2. **「特定のウィンドウをキャプチャ」** → `[VSeeFace.exe]: VSeeFace` を選択
3. **「透過を許可」** にチェック
4. VSeeFaceのアバターが透過背景で表示される

本プロジェクトでは `obs setup` コマンドで自動作成される（`.env` に `AVATAR_APP=vsf` が必要）。

### 6. WSL環境での追加設定

WSLからWindows上のVSeeFaceにOSCを送信する場合:

1. `.env` に `VSF_OSC_HOST=wsl` を設定（WindowsホストIPを自動解決）
2. Windows Firewallで **UDPポート39539** の受信を許可する（OSCはUDP通信）

```powershell
# Windows PowerShell (管理者権限) で実行
New-NetFirewallRule -DisplayName "VSeeFace VMC Protocol" -Direction Inbound -Protocol UDP -LocalPort 39539 -Action Allow
```

---

## 将来の拡張

- **Warudo移行**: より高品質な3D表示が必要になった場合、WebSocket API経由で制御可能
- **three-vrm (ブラウザ)**: 外部アプリを排除したい場合、OBSブラウザソースで完結する構成に移行可能
- **モーション再生**: VRMAファイルの再生対応（ジェスチャー・リアクションの事前定義）
