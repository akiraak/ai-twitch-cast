# Step 1: マルチアバター表示

## ステータス: 未着手

## ゴール

**配信画面に2体のVRMアバターを同時に表示する。** 両方ともidle animation（呼吸・体の揺れ・まばたき・耳ぴくぴく）が動いている状態。

```
┌─────────────────────────────────────────────┐
│  broadcast.html                              │
│                                              │
│  ┌──────────┐            ┌──────────┐       │
│  │          │            │          │       │
│  │  生徒    │            │  先生    │       │
│  │ (左側)   │            │ (右側)   │       │
│  │          │            │          │       │
│  └──────────┘            └──────────┘       │
│                                              │
└─────────────────────────────────────────────┘
```

## 変更対象

| ファイル | 変更内容 |
|---------|---------|
| `static/js/avatar-renderer.js` | グローバル状態→AvatarInstanceクラス化 |
| `static/broadcast.html` | canvas要素を2つに |
| `static/css/broadcast.css` | デュアルアバターレイアウト |

## 実装

### 1-1. broadcast.html — 2つのavatar-area

現在:
```html
<div id="avatar-area" data-editable="avatar">
  <canvas id="avatar-canvas"></canvas>
  <img id="avatar-stream" style="display:none;" alt="">
</div>
```

変更後:
```html
<!-- 先生アバター（右側、従来位置） -->
<div id="avatar-area-1" data-editable="avatar1">
  <canvas id="avatar-canvas-1"></canvas>
  <img id="avatar-stream" style="display:none;" alt="">
</div>

<!-- 生徒アバター（左側、授業モード時のみ表示） -->
<div id="avatar-area-2" data-editable="avatar2" style="display:none;">
  <canvas id="avatar-canvas-2"></canvas>
</div>
```

### 1-2. broadcast.css — レイアウト

```css
/* 先生アバター — 従来の #avatar-area と同じ位置 */
#avatar-area-1 {
  position: absolute;
  z-index: 5;
  left: 46.5%; top: 24.3%;
  width: 53.5%; height: 75.7%;
}
#avatar-area-1 canvas {
  width: 100%; height: 100%;
  pointer-events: none;
}

/* 生徒アバター — 左側、やや小さめ */
#avatar-area-2 {
  position: absolute;
  z-index: 4;
  left: 0%; top: 30%;
  width: 40%; height: 70%;
}
#avatar-area-2 canvas {
  width: 100%; height: 100%;
  pointer-events: none;
}
```

### 1-3. avatar-renderer.js — AvatarInstance クラス化

**方針**: 現在の519行のグローバルコードを、1アバター分の状態を全てカプセル化するクラスに変換する。

**クラスの外に残すもの**（共有ユーティリティ）:
- `quatFromAxisAngle()` — クォータニオン計算
- `setBoneRotation()` — ボーン回転設定
- `GESTURES` 定義 — ジェスチャーの時間・角度データ
- `buildGestureClip()` — AnimationClip生成

**クラスに入れるもの**（1アバター分の状態）:

```javascript
class AvatarInstance {
  constructor(canvasId, areaId) {
    // --- Three.js基盤 ---
    this.canvas = document.getElementById(canvasId);
    this.area = document.getElementById(areaId);
    if (!this.canvas || !this.area) return;

    this.renderer = new THREE.WebGLRenderer({
      canvas: this.canvas, alpha: true, antialias: true
    });
    this.renderer.setPixelRatio(Math.max(window.devicePixelRatio || 1, 2));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.NoToneMapping;

    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(20, 1, 0.1, 100);
    this.camera.position.set(0, 1.2, 3.0);
    this.camera.lookAt(0, 1.1, 0);

    // ライティング
    this.BASE_AMBIENT = 0.75;
    this.BASE_DIRECTIONAL = 1.0;
    this.ambientLight = new THREE.AmbientLight(0xffffff, this.BASE_AMBIENT);
    this.scene.add(this.ambientLight);
    this.dirLight = new THREE.DirectionalLight(0xffffff, this.BASE_DIRECTIONAL);
    this.dirLight.position.set(0.5, 1.5, 2.0);
    this.scene.add(this.dirLight);

    // レンダラーサイズ
    this._resizeRenderer();
    new ResizeObserver(() => this._resizeRenderer()).observe(this.area);

    // --- VRM状態 ---
    this.currentVRM = null;
    this.mixer = null;
    this.currentGestureAction = null;
    this.idleScale = 1.0;
    this.t0 = performance.now() / 1000;
    this.clock = new THREE.Clock();

    // --- まばたき ---
    this.nextBlink = this.t0 + 2 + Math.random() * 3;
    this.blinkEnd = 0;

    // --- 耳ぴくぴく ---
    this.nextEarTwitch = this.t0 + 3 + Math.random() * 5;
    this.earTwitchEnd = 0;
    this.earTwitchStart = 0;
    this.earTwitchDuration = 0.2;
    this.earTwitchShake = false;
    this.earTwitchShakeHz = 0;

    // --- 表情イージング ---
    this.exprTarget = {};
    this.exprCurrent = {};
    this.exprPrev = {};
    this.exprTransitionStart = 0;
    this.EXPR_TRANSITION_MS = 300;

    // --- リップシンク ---
    this.lipsyncFrames = null;
    this.lipsyncStart = 0;
    this.pendingLipsyncFrames = null;

    // --- ジェスチャー表情 ---
    this.gestureExprState = null;
    this.gestureShapes = {};
  }

  _resizeRenderer() { /* 現在の resizeRenderer() と同等 */ }
  async loadVRM(url) { /* 現在の loadVRM() と同等 */ }

  // 外部API
  setBlendShapes(shapes) { /* 現在の avatarVRM.setBlendShapes と同等 */ }
  setLipsync(frames) { this.pendingLipsyncFrames = frames; }
  startLipsync() { /* ... */ }
  stopLipsync() { this.lipsyncFrames = null; this.pendingLipsyncFrames = null; }
  setIdleScale(s) { this.idleScale = s; }
  playGesture(name) { /* 現在の playGesture() と同等 */ }
  debugExpressions() { /* ... */ }

  // 内部: 毎フレーム更新
  _updateExpressionEasing() { /* 現在の updateExpressionEasing() と同等 */ }
  animate() { /* 現在の animate() の本体と同等（requestAnimationFrameは呼ばない） */ }
}
```

### 1-4. インスタンス管理 + 後方互換

```javascript
// --- インスタンス管理 ---
window.avatarInstances = {};

// 先生アバター（常に存在）
const teacherAvatar = new AvatarInstance('avatar-canvas-1', 'avatar-area-1');
window.avatarInstances['teacher'] = teacherAvatar;

// 生徒アバター（canvas存在時のみ）
if (document.getElementById('avatar-canvas-2')) {
  const studentAvatar = new AvatarInstance('avatar-canvas-2', 'avatar-area-2');
  window.avatarInstances['student'] = studentAvatar;
}

// --- 後方互換: window.avatarVRM ---
window.avatarVRM = {
  setBlendShapes(shapes) { teacherAvatar.setBlendShapes(shapes); },
  setLipsync(frames)     { teacherAvatar.setLipsync(frames); },
  startLipsync()         { teacherAvatar.startLipsync(); },
  stopLipsync()          { teacherAvatar.stopLipsync(); },
  setIdleScale(s)        { teacherAvatar.idleScale = s; },
  playGesture(name)      { teacherAvatar.playGesture(name); },
  debugExpressions()     { teacherAvatar.debugExpressions(); },
};

// --- 後方互換: window.avatarLighting ---
window.avatarLighting = {
  BASE_AMBIENT: 0.75,
  BASE_DIRECTIONAL: 1.0,
  setAmbient(i)     { teacherAvatar.ambientLight.intensity = i; },
  setDirectional(i) { teacherAvatar.dirLight.intensity = i; },
  setExposure(val) {
    for (const a of Object.values(window.avatarInstances)) {
      a.ambientLight.intensity = a.BASE_AMBIENT * val;
      a.dirLight.intensity = a.BASE_DIRECTIONAL * val;
    }
  },
  setColor(r, g, b) {
    for (const a of Object.values(window.avatarInstances)) {
      a.ambientLight.color.setRGB(r, g, b);
      a.dirLight.color.setRGB(r, g, b);
    }
  },
  setPosition(x, y, z) { teacherAvatar.dirLight.position.set(x ?? teacherAvatar.dirLight.position.x, y ?? teacherAvatar.dirLight.position.y, z ?? teacherAvatar.dirLight.position.z); },
};

// --- 統合アニメーションループ ---
function animateAll() {
  requestAnimationFrame(animateAll);
  for (const avatar of Object.values(window.avatarInstances)) {
    avatar.animate();
  }
}
animateAll();

// --- 初期化: 先生アバター読み込み ---
(async () => {
  try {
    const res = await fetch('/api/files/avatar/list');
    const data = await res.json();
    if (data.active) {
      await teacherAvatar.loadVRM(`/resources/vrm/${data.active}`);
    }
  } catch (e) {
    console.error('アバター初期化失敗:', e);
  }
})();
```

### 1-5. ID変更の影響箇所

`#avatar-area` → `#avatar-area-1`、`#avatar-canvas` → `#avatar-canvas-1` への変更で影響を受ける箇所:

| ファイル | 参照 | 対応 |
|---------|------|------|
| `broadcast/settings.js` | `#avatar-area` のスタイル適用 | `#avatar-area-1` に変更 |
| `broadcast/edit-mode.js` | `data-editable="avatar"` | `data-editable="avatar1"` に変更 |
| `broadcast/init.js` | 初期化時のDOM参照 | 確認して修正 |
| `scenes.json` | `overlay.avatar` キー | `overlay.avatar1` に変更（マイグレーション） |

### 1-6. 動作確認方法

1. サーバー起動 → `/broadcast` を開く
2. 先生アバター（右側）が従来通り表示・idle animation動作
3. ブラウザのDevToolsで `document.getElementById('avatar-area-2').style.display = 'block'` を実行
4. 生徒アバターエリア（左側）が表示される（VRM未読み込みなので空のcanvas）
5. DevToolsで `window.avatarInstances['student'].loadVRM('/resources/vrm/Shinano.vrm')` を実行
6. 生徒エリアにもアバターが表示され、idle animationが動く
7. 先生と生徒が独立してまばたき・耳ぴくぴくしている

## 完了条件

- [ ] 先生アバターが従来通り動作する（idle, blink, ear twitch, lipsync, gesture, blendshape）
- [ ] `window.avatarVRM` 後方互換が維持される
- [ ] `window.avatarInstances['student']` に VRM をロードすると2体目が表示される
- [ ] 2体が独立してidle animationする
- [ ] 生徒アバターが `display:none` / `display:block` で表示/非表示できる
- [ ] 両アバターが `data-editable` でドラッグ＆リサイズ可能
- [ ] パフォーマンス: 2体同時でも60fps維持
