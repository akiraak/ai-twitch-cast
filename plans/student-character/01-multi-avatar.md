# Step 1: マルチアバター表示

## ステータス: 完了

## 実装済み

- [x] `avatar-renderer.js` → `AvatarInstance` クラス化（2体独立レンダリング）
- [x] `broadcast.html` に先生（`avatar-area-1`）+ 生徒（`avatar-area-2`）追加
- [x] `window.avatarVRM` / `window.avatarLighting` 後方互換維持
- [x] DB マイグレーション（`avatar` → `avatar1`、`avatar2` デフォルト追加）
- [x] 生徒用VRMファイル管理（`avatar2` カテゴリ、独立active選択）
- [x] `avatar2_vrm_change` WebSocketイベントで生徒VRM即時反映
- [x] `server_restart` イベントで broadcast.html 自動リロード
- [x] WebUIタブ順変更（会話モード → キャラクター → 配信画面）
- [x] キャラクター切替セレクタ（先生/生徒）
- [x] VRM選択を配信画面タブ → キャラクタータブに移動
- [x] ライティングをアバター個別化（`lighting_teacher` / `lighting_student`）
- [x] `data-fixed-layout` 要素でもzIndex変更が反映されるよう修正

---

## 残タスク: characters テーブルへの設定集約

### 背景

キャラクター関連の設定が複数テーブルに散らばっている:

| 設定 | 現在の保存場所 | キャラ区別 |
|------|---------------|-----------|
| 名前・プロンプト・感情・BlendShape | `characters.config` JSON | 先生のみ（生徒レコードなし） |
| VRMファイル | `settings`: `files.active_avatar` / `files.active_avatar2` | キー名で区別 |
| ライティング | `settings`: `overlay.lighting_teacher.*` / `overlay.lighting_student.*` | キー名で区別 |
| ライティングプリセット | `settings`: `lighting.presets` | 共通（区別なし） |
| アバター配置（位置・サイズ） | `broadcast_items`: `avatar1` / `avatar2` | レコードで区別 |
| TTS声・スタイル | なし（先生はenv/コード固定、生徒は未実装） |

**問題**: キャラを追加するたびに settings キーが増えて管理不能。生徒はそもそも characters テーブルにレコードがない。

### 目標: characters.config に集約

```
characters テーブル（1行 = 1キャラ）
├── id: 1 (先生: ちょビ)
│   └── config JSON:
│       ├── name, system_prompt, rules, emotions, emotion_blendshapes（既存）
│       ├── role: "teacher"                  ← 新規: 役割
│       ├── vrm: "Shinano.vrm"              ← settings から移動
│       ├── tts_voice: "Despina"             ← 新規（現在はenv固定）
│       ├── tts_style: "にこにこ..."          ← 新規（現在はenv固定）
│       ├── lighting: {brightness, ...}      ← settings から移動
│       └── lighting_presets: [...]           ← settings から移動
│
├── id: 7 (生徒: まなび)                      ← 新規レコード
│   └── config JSON:
│       ├── name: "まなび"
│       ├── role: "student"
│       ├── system_prompt, rules, emotions, emotion_blendshapes
│       ├── vrm: "Mafuyu_VRM.vrm"
│       ├── tts_voice: "Kore"
│       ├── tts_style: "元気で明るい..."
│       ├── lighting: {brightness, ...}
│       └── lighting_presets: [...]
│
broadcast_items テーブル（レイアウトのみ、変更なし）
├── avatar1: {positionX, positionY, width, height, zIndex, ...}
└── avatar2: {positionX, positionY, width, height, zIndex, ...}
```

**broadcast_items との紐付け**: `characters.config.role` で対応
- `role: "teacher"` → `broadcast_items.id = "avatar1"`
- `role: "student"` → `broadcast_items.id = "avatar2"`

### 段階的移行プラン

#### Phase 1: 生徒を characters テーブルに追加

**目的**: 生徒キャラのレコードを作り、最低限の config を入れる。

- `characters` テーブルに生徒レコードを INSERT（`role: "student"` 付き）
- 先生レコードの config に `role: "teacher"` を追加
- `GET /api/characters` で全キャラ一覧を返すAPI追加
- `GET/PUT /api/character/{id}` でキャラ個別読み書き（既存 `/api/character` を拡張）
- WebUI のキャラクター切替セレクタが characters テーブルから動的に生成されるように
- セリフサブタブが選択キャラの config を読み書きするように

**この時点での状態**: 名前・プロンプト・感情は characters テーブル。VRM・ライティングはまだ settings テーブル。

#### Phase 2: VRM選択を characters.config に移行

**目的**: `files.active_avatar` / `files.active_avatar2` を characters.config.vrm に移す。

- `characters.config` に `vrm` フィールド追加
- マイグレーション: `settings` の `files.active_avatar` → 先生 config.vrm、`files.active_avatar2` → 生徒 config.vrm
- `/api/files/avatar/select` の保存先を characters.config に変更
- `avatar-renderer.js` の `initAvatar()` が characters API から VRM を取得するように
- `/api/files/avatar/list` と `/api/files/avatar2/list` は統合（VRMディレクトリは共通なので）
- 旧 settings キー (`files.active_avatar*`) を削除

#### Phase 3: ライティングを characters.config に移行

**目的**: `overlay.lighting_teacher.*` / `overlay.lighting_student.*` を characters.config.lighting に移す。

- `characters.config` に `lighting` フィールド追加（brightness, contrast, etc.）
- マイグレーション: settings の `overlay.lighting_teacher.*` → 先生 config.lighting、`overlay.lighting_student.*` → 生徒 config.lighting
- `/api/overlay/settings` のライティング読み込みを characters テーブルから取得に変更
- WebUI のライティングスライダーが characters API 経由で読み書きするように
- 旧 settings キー (`overlay.lighting_*`) を削除

#### Phase 4: ライティングプリセットをキャラ別に

**目的**: `lighting.presets` を characters.config.lighting_presets に移す。

- `characters.config` に `lighting_presets` フィールド追加
- マイグレーション: 旧 `lighting.presets` → 先生 config.lighting_presets にコピー
- `/api/lighting/presets` に `?character_id=` パラメータ追加
- WebUI のプリセット保存/適用/削除がキャラ別に
- 旧 settings キー (`lighting.presets`) を削除

#### Phase 5: TTS設定を characters.config に追加

**目的**: TTS声・スタイルをキャラごとに設定可能にする。

- `characters.config` に `tts_voice`, `tts_style` フィールド追加
- 先生: Despina / にこにこスタイル（現在のデフォルト）
- 生徒: Kore / 元気で明るいスタイル
- `src/tts.py` の `synthesize()` が characters config から voice/style を取得
- WebUI のセリフサブタブに TTS 設定セクション追加
- 環境変数 `TTS_VOICE` / `TTS_STYLE` はフォールバックとして残す

#### Phase 6: 旧設定キーの掃除 + テスト

**目的**: settings テーブルに残った旧キャラ関連キーを削除し、テストを整備。

- settings テーブルから旧キー削除（`files.active_avatar*`, `overlay.lighting_*`, `lighting.presets`, `overlay.avatar.*`）
- 全既存テストの更新（character API の変更に対応）
- characters テーブルのマルチキャラCRUDテスト追加
- 手動動作確認チェックリスト

### 懸念事項

1. **既存APIの破壊的変更**: Phase 1 で `/api/character` → `/api/character/{id}` に変わるため、既存のWebUI JS全面修正。旧APIを互換レイヤーとして残すか判断が必要
2. **マイグレーション失敗リスク**: 各Phase で settings → characters.config へデータ移動するため、移行前のDBバックアップ必須
3. **broadcast.html 側のID体系**: `avatar-area-1`/`avatar-area-2` のハードコードは当面維持。3人以上対応は将来課題
4. **channel_id**: 生徒は先生と同じ `channel_id` に所属する想定。1チャンネル = 複数キャラ
