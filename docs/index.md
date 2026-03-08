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

## ドキュメント

### OBS

- [OBS自動制御でできること](obs-automation-guide.md)
- [OBS Studio 機能調査](obs-research.md)

### アバター

- [アバター表示・アニメーション調査](avatar-research.md)
- [3Dモデル調査](3d-model-research.md)
- [アバター変更ガイド](avatar-change-guide.md)
- [VRM表示 実装プラン](vrm-implementation-plan.md)
- [VRM変換 作業ログ](vrm-conversion-log.md)

### 運用

- [コンソールコマンド](console-commands.md)
- [リソース管理](resource-management.md)
