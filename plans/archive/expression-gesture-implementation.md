# 表情の滑らかな遷移 + ちょっとしたジェスチャー 実装プラン

**ステータス: 未着手**
**対象TODO**: 「表情や体の動きを入れる」
**前提**: test-animation/ での動作検証済み

## 目的

1. 表情の瞬間切替をなくし、滑らかにイージング遷移させる
2. 発話時にうなずき・首かしげなどの小さなジェスチャーを自動で入れる

## 現状の問題

### 表情
- `setBlendShapes({happy: 1.0})` で瞬間的に切り替わる（0→1が1フレーム）
- 発話終了時の `neutral` リセットも瞬間（不自然）

### 体の動き
- idle animation（sin波）は常時動いている
- 発話中も待機中も完全に同じ動き
- うなずきや反応の動きが一切ない

## 実装方針

### フロントエンドのみで完結
- バックエンドの変更は最小限（WebSocketイベントに `gesture` フィールド追加のみ）
- アニメーションのロジックは全て `avatar-renderer.js` に集約

## 変更対象ファイル

| ファイル | 変更内容 |
|---------|---------|
| `static/js/avatar-renderer.js` | 表情イージング + ジェスチャーシステム追加 |
| `static/js/broadcast-main.js` | `gesture` WebSocketイベントのハンドリング追加 |
| `src/speech_pipeline.py` | `apply_emotion` に gesture 指定を追加 |
| `src/ai_responder.py` | （任意）AI応答に gesture フィールド追加 |

## 実装ステップ

### Step 1: 表情のイージング遷移 (avatar-renderer.js)

**現状:**
```javascript
window.avatarVRM = {
  setBlendShapes(shapes) { externalShapes = shapes; },
};
```

**変更後:**
```javascript
// 状態追加
let targetShapes = {};
let currentShapes = {};
let prevShapes = {};
let exprTransitionStart = 0;
const EXPR_TRANSITION_MS = 300;

window.avatarVRM = {
  setBlendShapes(shapes) {
    prevShapes = { ...currentShapes };
    targetShapes = { ...shapes };
    exprTransitionStart = performance.now();
  },
};
```

animateループ内で毎フレーム補間:
```javascript
// イーズインアウト補間
if (exprTransitionStart) {
  const elapsed = performance.now() - exprTransitionStart;
  const progress = Math.min(elapsed / EXPR_TRANSITION_MS, 1);
  const t = progress < 0.5
    ? 2 * progress * progress
    : 1 - Math.pow(-2 * progress + 2, 2) / 2;

  const allNames = new Set([...Object.keys(prevShapes), ...Object.keys(targetShapes)]);
  for (const name of allNames) {
    const from = prevShapes[name] || 0;
    const to = targetShapes[name] || 0;
    currentShapes[name] = from + (to - from) * t;
  }
  if (progress >= 1) exprTransitionStart = 0;
}

for (const [name, value] of Object.entries(currentShapes)) {
  try { em.setValue(name, value); } catch (e) {}
}
```

- 検証で効果確認済み
- 300msのイーズインアウトで自然に見える
- blink / ear_stand / lipsync は個別制御なので干渉しない

### Step 2: ジェスチャーシステム (avatar-renderer.js)

AnimationMixer + QuaternionKeyframeTrack（InterpolateSmooth）でジェスチャー再生。
idle animationはジェスチャー再生中は停止し、crossFadeで滑らかに戻る。

```javascript
let mixer = null;
let currentGestureAction = null;

// ジェスチャー定義（test-animationから移植、配信向けに控えめに調整）
const GESTURES = {
  nod: { ... },           // うなずき（相づち）
  nod_deep: { ... },      // 深いうなずき
  head_tilt: { ... },     // 首かしげ（考え中）
  surprise: { ... },      // 驚き（のけぞり）
  happy_bounce: { ... },  // 嬉しい
  sad_droop: { ... },     // 悲しい
  bow: { ... },           // お辞儀
};

window.avatarVRM = {
  ...
  playGesture(name, speed = 1.0) {
    const gesture = GESTURES[name];
    if (!gesture || !currentVRM) return;
    const clip = buildGestureClip(gesture, currentVRM);
    // AnimationMixer で再生、0.3s crossfade
    ...
  },
};
```

- 検証でInterpolateSmooth（スプライン補間）の効果確認済み
- ジェスチャーに表情キーフレームも連動（検証済み）

### Step 3: WebSocketイベント拡張 (broadcast-main.js)

```javascript
case 'blendshape':
  if (window.avatarVRM && data.shapes) {
    window.avatarVRM.setBlendShapes(data.shapes);
  }
  // ジェスチャーも同時指定可能
  if (window.avatarVRM && data.gesture) {
    window.avatarVRM.playGesture(data.gesture);
  }
  break;
```

既存の `blendshape` イベントにオプションで `gesture` フィールドを追加。
後方互換性あり（gestureがなければ今まで通り）。

### Step 4: バックエンド - 感情→ジェスチャーマッピング (speech_pipeline.py)

```python
EMOTION_GESTURES = {
    "joy": "nod",
    "surprise": "surprise",
    "thinking": "head_tilt",
    "neutral": None,
}

def apply_emotion(self, emotion):
    ...
    gesture = EMOTION_GESTURES.get(emotion)
    if self._on_overlay and blendshapes:
        asyncio.create_task(self._on_overlay({
            "type": "blendshape",
            "shapes": blendshapes,
            "gesture": gesture,  # 追加
        }))
```

- 感情ごとにデフォルトジェスチャーを自動選択
- neutralの場合はジェスチャーなし（idleに戻る）

### Step 5（任意）: AI応答でジェスチャー指定

ai_responder.pyのプロンプトに `gesture` フィールドを追加し、AIが文脈に応じてジェスチャーを選択。
優先度低。Step 4の固定マッピングで十分効果がある。

## 変更しないもの

- idle animation のsin波ロジック（そのまま）
- lipsync の仕組み（そのまま）
- blink / ear_twitch（そのまま）
- バックエンドのcomment_reader.pyの呼び出しパターン（apply_emotion → speak → apply_emotion("neutral") の流れはそのまま）

## テスト

- `tests/test_speech_pipeline.py`: blendshapeイベントに `gesture` フィールドが含まれることを確認
- ブラウザでの目視確認:
  - 表情が300msかけて滑らかに変わること
  - neutral復帰時も滑らかなこと
  - 発話時にジェスチャーが再生されること
  - ジェスチャー終了後にidleに戻ること
  - ジェスチャー途中に別ジェスチャーが来ても自然に遷移すること（crossFade）

## リスク

- **idle animation とジェスチャーの競合**: ジェスチャー再生中はidle animationのボーン設定をスキップする必要がある（`currentGestureAction?.isRunning()` で判定、検証済み）
- **lipsync との表情競合**: ジェスチャーの表情キーフレームが `aa` を含む場合、lipsyncの `aa` 設定と衝突する可能性がある → ジェスチャーの表情では `aa` を使わず、lipsyncに任せる

## 工数見積もり

| ステップ | 内容 | 規模 |
|---------|------|------|
| Step 1 | 表情イージング | 小（avatar-renderer.js 20行追加） |
| Step 2 | ジェスチャーシステム | 中（avatar-renderer.js 100行追加） |
| Step 3 | WS イベント拡張 | 小（broadcast-main.js 3行追加） |
| Step 4 | 感情→ジェスチャーマッピング | 小（speech_pipeline.py 10行追加） |
