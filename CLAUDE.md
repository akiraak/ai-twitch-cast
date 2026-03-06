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

- 言語: 未定（決定次第更新）
- コミットメッセージ: 日本語可
- コード内コメント: 日本語可
- ドキュメント: 日本語

## ディレクトリ構成

```
ai-twitch-cast/
├── .github/workflows/
│   └── deploy-pages.yml  # GitHub Pages自動デプロイ
├── docs/              # ドキュメント（GitHub Pagesで公開）
├── mkdocs.yml         # MkDocs設定
├── CLAUDE.md          # このファイル
├── DONE.md            # 完了タスク
├── TODO.md            # タスク一覧
├── LICENSE
└── README.md
```

※ プロジェクト進行に応じて更新する
