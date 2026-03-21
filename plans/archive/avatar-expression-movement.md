# 表情・体の動きの強化プラン

**ステータス: アイデア検討中**
**対象TODO**: 「表情や体の動きを入れる」

## 現状

### 表情（BlendShape）
- 4種類の感情: joy, surprise, thinking, neutral
- 感情は発話時に適用→発話後にneutralリセット（瞬間切替、遷移なし）
- idle中はblink（まばたき）とear_stand（耳ぴくぴく）のみ

### 体の動き（ボーンアニメーション）
- idle animation: 呼吸（chest）、体の揺れ（spine）、頭の動き（head）、腕の揺れ（upperArm）
- すべてsin波ベースの固定パターン
- 発話中も待機中も同じ動き

---

## アイデア一覧

### A. 表情の充実

#### A1. 感情バリエーション追加
現在4種 → 拡張案:
| 感情 | BlendShape構成 | 使用シーン |
|------|---------------|-----------|
| angry | Angry: 0.7 | 怒りツッコミ |
| sad | Sorrow: 0.8 | 悲しい話題 |
| excited | Joy: 1.0, A: 0.4 | 盛り上がり |
| smug | Joy: 0.3, Blink: 0.3 | ドヤ顔 |
| confused | Sorrow: 0.2, A: 0.2 | 困惑 |
| embarrassed | Joy: 0.4, Sorrow: 0.2 | 照れ |

**実装難易度**: 低（character configのemotion_blendshapesに追加するだけ）
**効果**: 中（表現の幅が広がる）

#### A2. 感情の滑らかな遷移（イージング）
- 現状: 瞬間的に切替（0→1）
- 改善: 200-500msかけて線形/イージング補間で遷移
- neutral→joy→neutralが自然に見える
- avatar-renderer.js内でlerpで実装可能

**実装難易度**: 低〜中（フロントエンドのみ）
**効果**: 高（最も違和感が減る改善）

#### A3. 微表情（Micro-expressions）
- idle中にランダムで微妙な表情変化を入れる
  - 口角がわずかに上がる（Joy: 0.1を2秒間）
  - 眉が少し動く
  - 考えているような表情が一瞬出る
- blinkと同様にランダム間隔で発火

**実装難易度**: 低（blink/ear_twitch と同じパターン）
**効果**: 中（生きている感が増す）

#### A4. リアクション表情
- チャットコメント受信時: 一瞬驚く表情（surprise 0.3を0.5秒）
- フォロー/サブスク時: 喜び表情
- 長時間コメントなし: 寂しそうな表情

**実装難易度**: 中（イベントハンドリング追加）
**効果**: 中（インタラクティブ感）

---

### B. 体の動きの強化

#### B1. 発話中の動きの変化
- 発話中はidle animationのスケールを上げる（1.0→1.5）
  - 頭の動きが大きくなる → 喋っている感
  - 体の揺れが増す → エネルギッシュに見える
- 発話終了後は徐々に元のスケールに戻す

**実装難易度**: 低（setIdleScale()にイージング追加）
**効果**: 高（発話中と待機中の差が出て自然）

#### B2. 感情連動ボディランゲージ
- 感情ごとに体の動きのパラメータを変える:
  | 感情 | 頭の動き | 体の揺れ | 腕 |
  |------|---------|---------|-----|
  | joy | 大きく頷く | 弾むように | 軽く広がる |
  | sad | うつむき気味 | 小さく | だらん |
  | excited | 激しく | 前のめり | 大きく動く |
  | thinking | 傾げる | ゆっくり | 顎に手（難） |
- WebSocketイベントで感情パラメータセットを送る

**実装難易度**: 中（ボーンのベースポーズ＋動きパラメータの調整）
**効果**: 高（感情が全身で伝わる）

#### B3. ジェスチャーアニメーション
- プリセットジェスチャー（ボーンキーフレーム）:
  - うなずき: 頭を上下に2回振る
  - 首かしげ: 頭をZ軸回転で傾ける
  - 手を振る: greeting（難易度高、腕のIK必要かも）
- WebSocketで `{"type": "gesture", "name": "nod"}` を送って再生

**実装難易度**: 中〜高（キーフレームアニメーション再生基盤が必要）
**効果**: 高（キャラクター性が出る）

#### B4. 相づちモーション
- AI応答生成中（思考中）: 頭を小さく傾げる + thinking表情
- チャット読み上げ中: 軽くうなずく（相手の話を聞いている感）
- テンプレートではなくランダムにバリエーション

**実装難易度**: 中
**効果**: 中（配信者らしさ）

---

### C. コンテキスト対応の動き

#### C1. 時間帯に応じた振る舞い
- 深夜: idle animationが眠そう（スケール小、まばたき頻度増）
- 配信開始直後: 元気（スケール大）
- 長時間経過: 少し疲れた動き

**実装難易度**: 低（時刻判定 + パラメータ変更）
**効果**: 低〜中（気づく人は少ないが没入感に寄与）

#### C2. チャット盛り上がり連動
- 短時間にコメントが多い → アバターも活発に動く（idle scale増加）
- コメントがない → 退屈そうにする（頬杖的なポーズ、キョロキョロ）
- チャットの感情分析と連動

**実装難易度**: 中（コメント頻度の統計 + パラメータ連動）
**効果**: 中（ライブ感が増す）

#### C3. BGM連動
- BGMのテンポ/ジャンルに合わせて体の揺れを変える
  - アップテンポ: リズムに乗るように体を振る
  - スロー: ゆったりとした動き
- BGM変更時にテンポ情報を送る or JavaScript側でAudio APIで解析

**実装難易度**: 高（音楽分析が必要）
**効果**: 中（面白いが優先度は低い）

---

### D. 高度な機能

#### D1. リップシンク強化
- 現状: 振幅ベースの単純な口パク（aa BlendShapeのみ）
- 改善案:
  - 母音推定で口の形を変える（あ/い/う/え/お → aa/ih/ou/ee/oh）
  - VRM標準の5母音BlendShapeを活用
  - TTS音声データから母音を推定、またはテキストから推定

**実装難易度**: 高（音素解析 or テキスト→母音マッピング）
**効果**: 高（口パクの質が大幅に上がる）

#### D2. 視線制御（Eye Tracking的）
- カメラ目線（デフォルト）とランダム目線の切替
- 考えている時: 視線が上に向く
- コメント読み上げ時: 画面端（チャット欄方向）を見る
- VRMのlookAt機能で実装可能

**実装難易度**: 中（VRM lookAtの活用）
**効果**: 高（目が動くと生きている感が格段に増す）

#### D3. 物理ベースの揺れ強化
- 髪/服/アクセサリーの揺れをThree.js側で有効化
- VRM SpringBone が使えるなら自動で髪が揺れる
- three-vrm の SpringBoneManager をupdate()するだけで動く可能性

**実装難易度**: 低（three-vrmの機能を有効化するだけかも）
**効果**: 中（自然さが増す）

#### D4. ポーズプリセット
- 通常立ち / 腕組み / ピース / 手を振る etc.
- WebSocket経由で切替可能
- ポーズ間はlerp遷移

**実装難易度**: 高（各ポーズのボーン角度を手動設定 or VRMポーズデータ）
**効果**: 中（配信シーン切替時などに使える）

---

## 優先度の提案（実装効果/難易度のバランス）

### Phase 1: 低コスト高効果（すぐできる）
1. **A2. 感情の滑らかな遷移** — 一番違和感が減る改善
2. **A1. 感情バリエーション追加** — config追加だけ
3. **B1. 発話中の動きの変化** — idle scale変更だけ
4. **D3. 物理ベースの揺れ** — three-vrm機能の有効化確認

### Phase 2: 中程度の工数で大きな効果
5. **A3. 微表情** — blinkパターンの応用
6. **D2. 視線制御** — VRM lookAt活用
7. **B2. 感情連動ボディランゲージ** — 感情ごとのパラメータセット
8. **A4. リアクション表情** — イベント駆動

### Phase 3: 本格的な拡張
9. **B3. ジェスチャーアニメーション** — キーフレーム基盤
10. **B4. 相づちモーション**
11. **D1. リップシンク強化** — 母音推定
12. **C2. チャット盛り上がり連動**

### 保留（面白いが優先度低）
- C1. 時間帯振る舞い
- C3. BGM連動
- D4. ポーズプリセット

---

## 技術的な実装方針

### フロントエンド（avatar-renderer.js）での実装が中心
- ほとんどの機能はフロントエンドのアニメーションループ内で完結
- バックエンドからはWebSocketで「感情名」「ジェスチャー名」などの指示を送るだけ
- アニメーションの詳細（イージング・ボーン角度）はフロントエンドで管理

### WebSocketイベント拡張案
```javascript
// 感情（既存を拡張）
{"type": "blendshape", "shapes": {...}, "duration": 500, "easing": "easeInOut"}

// ジェスチャー（新規）
{"type": "gesture", "name": "nod", "speed": 1.0}

// 動きパラメータ（新規）
{"type": "motion_params", "idle_scale": 1.5, "head_bias": [0, -0.1, 0.05]}

// 視線（新規）
{"type": "look_at", "target": [0, 0, 0], "duration": 1000}
```

### 状態管理
- 現在の感情状態
- 現在のジェスチャー再生状態
- ベースのidle parameterセット
- 各状態がブレンドされて最終的なボーン角度/BlendShape値を決定

---

## 利用可能なライブラリ・モーションデータ調査結果

### ライブラリ

#### @pixiv/three-vrm-animation（公式）
- pixiv公式パッケージ。既存 `@pixiv/three-vrm` と同じエコシステム
- `.vrma` (VRM Animation) ファイルを読み込み → Three.js AnimationClip に変換
- `VRMAnimationLoaderPlugin` + `createVRMAnimationClip()` で簡単に使える
- AnimationMixer でクロスフェード再生可能
- ライセンス: MIT
- npm: `@pixiv/three-vrm-animation`
- **統合難易度: 低（最有力候補）**

#### vrm-mixamo-retargeter
- Mixamo FBX をブラウザ内でVRMにリターゲット
- `retargetAnimation(fbxAsset, vrm, options)` → AnimationClip 一行
- 52本のMixamoボーン→VRMヒューマノイドボーンの自動マッピング
- Repo: github.com/saori-eth/vrm-mixamo-retargeter
- **統合難易度: 低**

#### fbx2vrma-converter
- Mixamo FBX → .vrma 変換（オフラインNode.js CLI）
- バッチ変換対応
- Repo: github.com/tk256ailab/fbx2vrma-converter
- **用途: モーションデータの事前変換**

#### Three.js AnimationMixer（内蔵）
- AnimationClipの再生・ブレンド・クロスフェード（`crossFadeTo()`）
- 追加依存なし、既にThree.jsに含まれている
- idle → gesture → idle の滑らかな遷移に必要

#### IKライブラリ（参考）
| ライブラリ | 特徴 |
|-----------|------|
| THREE.IK | FABRIK solver |
| IK-threejs | CCD + FABRIK + hybrid |
| CCDIKSolver | Three.js addons内蔵 |

### モーションデータ集

| ソース | モーション数 | 形式 | ライセンス | 備考 |
|--------|------------|------|-----------|------|
| **Mixamo** (Adobe) | 2,400+ | FBX | 無料(Adobe ID) | ジェスチャー・ダンス・歩行・会話等 |
| **VRoid公式 BOOTH** | 7 | .vrma | 無料 | greeting/peace/spin/squat等 |
| **SillyTavern VRM Assets Pack** | 112 | FBX/BVH/VRMA | 無料 | AI VTuber用途向け、感情マッピング済 |
| **CMU Mocap Database** | 2,500+ | BVH | 完全フリー | 最大の無料モーキャプDB |
| **Bandai Namco Research** | 3,077 | BVH | CC BY-NC-ND | 感情付きモーション |
| **MMDコミュニティ** | 数千+ | VMD | 作者次第 | ダンス中心 |

### 参考プロジェクト

| プロジェクト | 内容 | ライセンス |
|-------------|------|-----------|
| **ChatVRM** (pixiv) | AI+VRM+感情+VRMA再生 | MIT |
| **LocalChatVRM** (pixiv) | ChatVRM後継、ローカルAI | MIT |
| **Amica** | 3Dキャラチャット+VRM+音声 | MIT |
| **AIRI** (moeru-ai) | AIコンパニオン、VRM+Live2D | OSS |
| **Lobe Vidol** | VRM+MMDダンス+Mixamoジェスチャー | OSS |
| **SillyTavern Extension-VRM** | 感情→アニメーション自動マッピング | OSS |
| **Synthetic Heart** | 状態マシン(idle/talking/thinking)+Mixamo | OSS |

### 推奨アプローチ

**最小コストで最大効果の組み合わせ:**

1. `@pixiv/three-vrm-animation` を追加（公式、同じエコシステム）
2. Mixamo から配信向けモーション（うなずき・手振り・喜び等）をFBXダウンロード
3. `fbx2vrma-converter` で .vrma に事前変換、または `vrm-mixamo-retargeter` でランタイム変換
4. AnimationMixer でidle↔ジェスチャーのクロスフェード再生
5. WebSocketイベントでモーション指定 → フロントエンドで再生

---

## 動作検証

### 検証ページ
`static/test-avatar-animation.html` — 本番コードとは独立した検証用ページ

### 検証項目
1. **@pixiv/three-vrm-animation** で .vrma ファイルをロード・再生できるか
2. **AnimationMixer** でidle↔アニメーションのクロスフェードが動くか
3. **vrm-mixamo-retargeter** でMixamo FBXをVRMにリターゲットできるか
4. 複数アニメーションの切替がスムーズか
