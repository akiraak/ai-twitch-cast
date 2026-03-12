# 対話式コンソール コマンドリファレンス

`python scripts/console.py` で起動する対話式コンソールのコマンド一覧。

## アバター制御（VTube Studio / Live2D）

| コマンド | 説明 |
|---------|------|
| `vts connect` | VTube Studioに接続・認証 |
| `vts disconnect` | VTube Studioから切断 |
| `vts status` | VTS接続状態とモデル情報を表示 |
| `vts model` | 現在のモデル情報を表示 |
| `vts params` | パラメータ一覧を表示 |
| `vts param <名前> <値>` | パラメータの値を設定 |
| `vts hotkeys` | ホットキー一覧を表示 |
| `vts hotkey <ID>` | ホットキーを実行 |
| `vts demo` | デモ動作（口パク・まばたき・体の動き） |

## アバター制御（VSeeFace / VRM）

| コマンド | 説明 |
|---------|------|
| `vsf connect` | VSeeFace (VMC Protocol) に接続 |
| `vsf disconnect` | VSeeFaceから切断 |
| `vsf status` | VSF接続状態を表示 |
| `vsf blend <名前> <値>` | BlendShapeを設定（例: `vsf blend Joy 1.0`） |
| `vsf bone <名前> <qx> <qy> <qz> <qw>` | ボーン回転を設定（クォータニオン） |
| `vsf demo` | デモ動作（リップシンク・表情・まばたき・頷き） |

BlendShape名の例: `A`, `I`, `U`, `E`, `O`（リップシンク）、`Joy`, `Angry`, `Sorrow`, `Fun`（表情）、`Blink`（まばたき）

ボーン名の例: `Head`, `Neck`, `Spine`, `LeftUpperArm`, `RightUpperArm`

## その他

| コマンド | 説明 |
|---------|------|
| `help` | コマンド一覧を表示 |
| `quit` / `exit` | コンソールを終了 |
