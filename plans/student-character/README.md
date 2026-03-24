# 教師モード — 生徒役キャラクター追加

## ステータス: 進行中

## 完了済み

- マルチアバター表示（2体のVRM、独立レンダリング）
- characters テーブル集約（VRM・ライティング・TTS設定をキャラ別管理）
- WebUIキャラクタータブ（キャラ切替・VRM選択・個別ライティング）

## 残ステップ

1. [WebSocket アバター制御](01-websocket-routing.md) — avatar_idでリップシンク・感情を振り分け
2. [TTS style パラメータ](02-tts-style.md) — 話者ごとに異なる声・スタイルで発話
3. [スクリプト生成の対話化](03-script-generation.md) — dialoguesカラム追加 + LLMで掛け合い生成
4. [レッスンランナーの対話再生](04-lesson-runner.md) — dialoguesを話者別に順次再生

## 方針

Step 1〜2 で「2体のアバターが別々の声で喋る」を実現 → Step 3〜4 で授業スクリプトの対話化。
