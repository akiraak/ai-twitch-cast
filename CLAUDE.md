# AI Twitch Cast

AIを活用し、プログラムで全自動Twitch配信を行うプロジェクト。

## プロジェクト概要

OBS制御、Twitch API連携、画像生成・収集、テキスト生成、音声合成など、配信に必要な要素をすべてプログラムで生成・制御する。

## 主要コンポーネント（予定）

- **OBS制御** - OBS WebSocket経由でシーン切替・ソース操作を自動化
- **Twitch API** - チャット読み取り・配信管理・視聴者インタラクション
- **画像生成/収集** - AI画像生成やWebからの素材収集
- **テキスト生成** - LLMによる台本・コメント・ナレーション生成
- **音声合成** - TTS（Text-to-Speech）によるナレーション音声生成

## 開発ルール

- 言語: Python
- コミットメッセージ: 日本語可
- コード内コメント: 日本語可
- ドキュメント: 日本語
- コミット前にTODO.mdとDONE.mdを更新する
- TODO.mdで完了したタスク（`[x]`）はDONE.mdに移動する

## リソース管理

- リソース（画像・Live2Dモデル・音声・動画）は `resources/` 配下で一元管理
- OBSからはWSLパス（`\\wsl.localhost\`）経由で参照
- VTube Studioにはデプロイスクリプトでコピー/クリーンアップ
- 詳細は [docs/resource-management.md](docs/resource-management.md) を参照

## 対話式コンソール

`python scripts/console.py` で起動。コマンド詳細は [docs/console-commands.md](docs/console-commands.md) を参照。

## ドキュメント

- `docs/` 配下のMarkdownがGitHub Pages（MkDocs + material）で自動公開される
- mainブランチへのpush時に `.github/workflows/deploy-pages.yml` で自動ビルド・デプロイ
- 公開URL: https://akiraak.github.io/ai-twitch-cast/

## ディレクトリ構成

```
ai-twitch-cast/
├── .github/workflows/
│   └── deploy-pages.yml     # GitHub Pages自動デプロイ
├── docs/                     # ドキュメント（GitHub Pagesで公開）
│   ├── assets/images/        # 画像素材（OGP等）
│   ├── overrides/            # MkDocsテーマオーバーライド（OGP設定等）
│   ├── index.md              # トップページ
│   ├── obs-automation-guide.md  # OBS自動制御ガイド
│   ├── obs-research.md       # OBS機能調査レポート
│   ├── avatar-research.md   # アバター表示・アニメーション調査
│   ├── 3d-model-research.md # 3Dモデル調査
│   └── vrm-conversion-log.md # VRM変換作業ログ
├── src/                      # ソースコード
│   ├── obs_controller.py     # OBS WebSocket制御
│   ├── vts_controller.py     # VTube Studio API制御（Live2D）
│   ├── vsf_controller.py     # VSeeFace VMC Protocol制御（VRM）
│   ├── scene_config.py       # シーン構成の定義（scenes.jsonから読み込み）
│   ├── tts.py                # TTS音声合成（Gemini 2.5 Flash TTS）
│   ├── twitch_chat.py        # Twitchチャット受信
│   ├── ai_responder.py       # AI応答生成（character.jsonベース）
│   ├── comment_reader.py     # コメント読み上げサービス
│   ├── git_watcher.py        # Gitコミット監視
│   ├── db.py                 # データベース管理（SQLite）
│   └── wsl_path.py           # WSL関連ユーティリティ
├── scripts/                  # 実行スクリプト
│   ├── start_stream.py       # 配信開始
│   ├── stop_stream.py        # 配信停止
│   ├── console.py            # 対話式コンソール
│   ├── web.py                # Webインターフェース
│   ├── deploy_model.py       # Live2Dモデルデプロイ
│   ├── convert_to_vrm.py     # FBX→VRM変換（Blenderスクリプト）
│   ├── fix_vrm_mtoon.py      # VRM MToonシェーダ修正
│   └── comment_reader.py     # Twitchコメント読み上げ
├── static/                   # Webインターフェース静的ファイル
│   └── index.html
├── resources/                # リソース（画像・モデル・音声・動画）
│   ├── images/
│   ├── live2d/
│   ├── vrm/                  # VRMモデル
│   ├── audio/
│   └── video/
├── scenes.json               # シーン構成設定（シーン・ソース・アバター配置）
├── character.json             # AIキャラクター設定（性格・ルール・表情マッピング）
├── mkdocs.yml                # MkDocs設定
├── requirements.txt          # Python依存パッケージ
├── .env.example              # 環境変数テンプレート
├── CLAUDE.md                 # このファイル
├── DONE.md                   # 完了タスク
├── TODO.md                   # タスク一覧
├── LICENSE
└── README.md
```

※ プロジェクト進行に応じて更新する

## Webサーバー運用注意

- Webサーバーは `uvicorn scripts.web:app --reload --host 0.0.0.0 --port 8000` で起動
- **Pydanticモデルやルートの変更後は `--reload` では反映されないことがある。その場合はuvicornプロセスを手動で再起動すること**
- OBSのブラウザソースはHTMLをキャッシュするため、overlay.html等を変更した場合はSetupボタン押下またはOBS側でブラウザソースの「キャッシュを無視してページをリフレッシュ」が必要
