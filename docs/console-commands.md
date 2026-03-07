# 対話式コンソール コマンドリファレンス

`python scripts/console.py` で起動する対話式コンソールのコマンド一覧。

## 接続管理

| コマンド | 説明 |
|---------|------|
| `obs connect` | OBS WebSocketに接続 |
| `obs disconnect` | OBSから切断 |
| `obs status` | OBS接続状態と配信状態を表示 |
| `vts connect` | VTube Studioに接続・認証 |
| `vts disconnect` | VTube Studioから切断 |
| `vts status` | VTS接続状態とモデル情報を表示 |

## 配信制御

| コマンド | 説明 |
|---------|------|
| `stream start` | 配信を開始 |
| `stream stop` | 配信を停止 |
| `stream status` | 配信状態を表示 |

## OBSシーン・ソース

| コマンド | 説明 |
|---------|------|
| `obs scenes` | シーン一覧を表示 |
| `obs scene <名前>` | シーンを切り替え |
| `obs sources` | 現在のシーンのソース一覧を表示 |
| `obs setup` | `scene_config.py` に基づきシーン・ソースを一括作成 |
| `obs teardown` | `scene_config.py` に基づきシーン・ソースを一括削除 |
| `obs add scene <名前>` | シーンを追加 |
| `obs add image <名前> <パス>` | 現在のシーンに画像ソースを追加（WSLパス） |
| `obs add text <名前> <テキスト>` | 現在のシーンにテキストソースを追加 |
| `obs add capture <名前>` | 現在のシーンにゲームキャプチャを追加 |
| `obs remove <名前>` | ソースを削除 |

## アバター制御

| コマンド | 説明 |
|---------|------|
| `vts model` | 現在のモデル情報を表示 |
| `vts params` | パラメータ一覧を表示 |
| `vts param <名前> <値>` | パラメータの値を設定 |
| `vts hotkeys` | ホットキー一覧を表示 |
| `vts hotkey <ID>` | ホットキーを実行 |
| `vts demo` | デモ動作（口パク・まばたき・体の動き） |

## 初期化

| コマンド | 説明 |
|---------|------|
| `init` | OBS・VTS接続 → シーン構築 → メインシーン切替を一括実行 |

## その他

| コマンド | 説明 |
|---------|------|
| `help` | コマンド一覧を表示 |
| `quit` / `exit` | コンソールを終了 |
