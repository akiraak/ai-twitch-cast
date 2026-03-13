# リソース管理方針

すべてのリソース（画像、VRMモデル、音声等）はWSLのリポジトリで一元管理する。

---

## 基本方針

- リソースの実体は `ai-twitch-cast/resources/` 配下に配置する
- broadcast.htmlからはWebサーバー経由（`/resources/`）でアクセスする

## リソースディレクトリ構成

```
resources/
├── images/          # 背景画像、ロゴ、オーバーレイ等
├── vrm/             # VRMモデルデータ
├── audio/           # BGM、効果音
└── video/           # オープニング、ジングル等の動画素材
```
