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

## その他

| コマンド | 説明 |
|---------|------|
| `help` | コマンド一覧を表示 |
| `quit` / `exit` | コンソールを終了 |
