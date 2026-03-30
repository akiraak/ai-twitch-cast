import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import * as VRM from '@pixiv/three-vrm';

// === 共有ユーティリティ（クラスの外に置く） ===

// クォータニオン生成（軸+角度）
function quatFromAxisAngle(ax, ay, az, deg) {
  const rad = (deg * Math.PI / 180) / 2;
  const s = Math.sin(rad);
  return new THREE.Quaternion(ax * s, ay * s, az * s, Math.cos(rad));
}

// ボーン回転設定
function setBoneRotation(vrm, boneName, quat) {
  const node = vrm.humanoid?.getNormalizedBoneNode(boneName);
  if (node) node.quaternion.copy(quat);
}

// --- ジェスチャー定義 ---
const GESTURES = {
  nod: {
    name: 'nod', duration: 1.0,
    tracks: {
      head: {
        times:  [0, 0.15, 0.35, 0.55, 0.75, 1.0],
        values: [[1,0,0,0], [1,0,0,-8], [1,0,0,3], [1,0,0,-6], [1,0,0,2], [1,0,0,0]],
      },
      chest: {
        times:  [0, 0.2, 0.5, 0.8, 1.0],
        values: [[1,0,0,0], [1,0,0,-2], [1,0,0,1], [1,0,0,-1], [1,0,0,0]],
      },
    },
  },
  nod_deep: {
    name: 'nod_deep', duration: 1.2,
    tracks: {
      head: {
        times:  [0, 0.2, 0.5, 0.8, 1.2],
        values: [[1,0,0,0], [1,0,0,-18], [1,0,0,5], [1,0,0,-12], [1,0,0,0]],
      },
      chest: {
        times:  [0, 0.25, 0.6, 1.0, 1.2],
        values: [[1,0,0,0], [1,0,0,-5], [1,0,0,2], [1,0,0,-2], [1,0,0,0]],
      },
      spine: {
        times:  [0, 0.3, 0.7, 1.2],
        values: [[1,0,0,0], [1,0,0,-3], [1,0,0,1], [1,0,0,0]],
      },
    },
  },
  head_tilt: {
    name: 'head_tilt', duration: 1.5,
    tracks: {
      head: {
        times:  [0, 0.3, 1.0, 1.5],
        values: [[0,0,1,0], [0,0,1,-15], [0,0,1,-12], [0,0,1,0]],
      },
      neck: {
        times:  [0, 0.35, 1.0, 1.5],
        values: [[0,0,1,0], [0,0,1,-5], [0,0,1,-3], [0,0,1,0]],
      },
    },
  },
  surprise: {
    name: 'surprise', duration: 1.2,
    tracks: {
      head: {
        times:  [0, 0.1, 0.3, 0.8, 1.2],
        values: [[1,0,0,0], [1,0,0,8], [1,0,0,5], [1,0,0,2], [1,0,0,0]],
      },
      chest: {
        times:  [0, 0.1, 0.4, 1.0, 1.2],
        values: [[1,0,0,0], [1,0,0,5], [1,0,0,3], [1,0,0,1], [1,0,0,0]],
      },
      spine: {
        times:  [0, 0.15, 0.5, 1.2],
        values: [[1,0,0,0], [1,0,0,3], [1,0,0,1], [1,0,0,0]],
      },
    },
  },
  happy_bounce: {
    name: 'happy_bounce', duration: 1.6,
    tracks: {
      spine: {
        times:  [0, 0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.6],
        values: [[1,0,0,0], [1,0,0,-3], [1,0,0,2], [1,0,0,-3], [1,0,0,2], [1,0,0,-2], [1,0,0,1], [1,0,0,0]],
      },
      head: {
        times:  [0, 0.2, 0.4, 0.6, 0.8, 1.0, 1.6],
        values: [[0,0,1,0], [0,0,1,5], [0,0,1,-5], [0,0,1,5], [0,0,1,-5], [0,0,1,3], [0,0,1,0]],
      },
      chest: {
        times:  [0, 0.15, 0.35, 0.55, 0.75, 0.95, 1.6],
        values: [[1,0,0,0], [1,0,0,-2], [1,0,0,2], [1,0,0,-2], [1,0,0,2], [1,0,0,-1], [1,0,0,0]],
      },
    },
  },
  sad_droop: {
    name: 'sad_droop', duration: 3.0,
    tracks: {
      head: {
        times:  [0, 0.8, 2.2, 3.0],
        values: [[1,0,0,0], [1,0,0,-15], [1,0,0,-12], [1,0,0,0]],
      },
      chest: {
        times:  [0, 1.0, 2.0, 3.0],
        values: [[1,0,0,0], [1,0,0,-5], [1,0,0,-4], [1,0,0,0]],
      },
      spine: {
        times:  [0, 1.0, 2.0, 3.0],
        values: [[1,0,0,0], [1,0,0,-3], [1,0,0,-2], [1,0,0,0]],
      },
    },
  },
  bow: {
    name: 'bow', duration: 2.5,
    tracks: {
      spine: {
        times:  [0, 0.5, 1.5, 2.5],
        values: [[1,0,0,0], [1,0,0,-20], [1,0,0,-18], [1,0,0,0]],
      },
      chest: {
        times:  [0, 0.5, 1.5, 2.5],
        values: [[1,0,0,0], [1,0,0,-10], [1,0,0,-8], [1,0,0,0]],
      },
      head: {
        times:  [0, 0.4, 1.5, 2.5],
        values: [[1,0,0,0], [1,0,0,-15], [1,0,0,-12], [1,0,0,0]],
      },
    },
  },
};

// ジェスチャー用AnimationClip生成
function buildGestureClip(gesture, vrm) {
  const tracks = [];
  for (const [boneName, data] of Object.entries(gesture.tracks)) {
    const node = vrm.humanoid?.getNormalizedBoneNode(boneName);
    if (!node) continue;
    const values = [];
    for (const aa of data.values) {
      const q = quatFromAxisAngle(aa[0], aa[1], aa[2], aa[3]);
      values.push(q.x, q.y, q.z, q.w);
    }
    const track = new THREE.QuaternionKeyframeTrack(
      node.name + '.quaternion', data.times, values
    );
    track.setInterpolation(THREE.InterpolateSmooth);
    tracks.push(track);
  }
  return new THREE.AnimationClip(gesture.name, gesture.duration, tracks);
}


// === AvatarInstance クラス ===
class AvatarInstance {
  constructor(canvasId, areaId) {
    this.canvas = document.getElementById(canvasId);
    this.area = document.getElementById(areaId);
    if (!this.canvas || !this.area) { this._disabled = true; return; }
    this._disabled = false;

    // --- Three.js基盤 ---
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
    window.addEventListener('resize', () => this._resizeRenderer());
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

    // --- 体の向き + 見回し ---
    this._bodyAngle = 0;
    this._gazeTargetY = 0;
    this._gazeCurrentY = 0;
    this._gazeTargetX = 0;
    this._gazeCurrentX = 0;
    this._gazeNextChange = performance.now() / 1000 + 3 + Math.random() * 5;
    this._gazeHoldUntil = 0;
  }

  _resizeRenderer() {
    const w = this.area.clientWidth;
    const h = this.area.clientHeight;
    if (w === 0 || h === 0) return;
    this.renderer.setSize(w, h);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  async loadVRM(url) {
    const loader = new GLTFLoader();
    loader.register((parser) => new VRM.VRMLoaderPlugin(parser));

    try {
      const gltf = await loader.loadAsync(url);
      const vrm = gltf.userData.vrm;
      if (!vrm) { console.error('VRMデータがありません'); return; }

      // 既存モデル削除
      if (this.currentVRM) {
        this.scene.remove(this.currentVRM.scene);
        VRM.VRMUtils.deepDispose(this.currentVRM.scene);
      }

      // VRM追加
      VRM.VRMUtils.rotateVRM0(vrm);
      this.scene.add(vrm.scene);
      this.currentVRM = vrm;

      // ジェスチャー用AnimationMixer作成
      this.mixer = new THREE.AnimationMixer(vrm.scene);
      this.currentGestureAction = null;

      // DEBUG: 利用可能な表情名を列挙
      const em = vrm.expressionManager;
      if (em) {
        const names = [];
        const map = em._expressionMap || em._expressions;
        if (map) {
          if (map instanceof Map) {
            for (const k of map.keys()) names.push(k);
          } else {
            names.push(...Object.keys(map));
          }
        }
        console.log('VRM expressions available:', names);
      }

      // bodyAngle再適用
      if (this._bodyAngle !== 0) {
        vrm.scene.rotation.y = this._bodyAngle * Math.PI / 180;
      }

      console.log('VRM読み込み完了:', url);
      this.t0 = performance.now() / 1000;
    } catch (e) {
      console.error('VRM読み込み失敗:', e);
    }
  }

  // --- 外部API ---
  setBlendShapes(shapes) {
    console.log('[avatar] setBlendShapes called:', JSON.stringify(shapes));
    this.exprPrev = { ...this.exprCurrent };
    this.exprTarget = { ...shapes };
    this.exprTransitionStart = performance.now();
  }

  setLipsync(frames) {
    this.pendingLipsyncFrames = frames;
  }

  startLipsync() {
    if (this.pendingLipsyncFrames) {
      this.lipsyncFrames = this.pendingLipsyncFrames;
      this.lipsyncStart = performance.now() / 1000;
      this.pendingLipsyncFrames = null;
    }
  }

  stopLipsync() { this.lipsyncFrames = null; this.pendingLipsyncFrames = null; }

  setIdleScale(s) { this.idleScale = s; }

  setBodyAngle(deg) {
    this._bodyAngle = deg;
    if (this.currentVRM) {
      this.currentVRM.scene.rotation.y = deg * Math.PI / 180;
    }
  }

  playGesture(name) {
    if (!this.currentVRM) return;
    const gesture = GESTURES[name];
    if (!gesture) return;

    if (!this.mixer) {
      this.mixer = new THREE.AnimationMixer(this.currentVRM.scene);
    }

    const clip = buildGestureClip(gesture, this.currentVRM);
    const action = this.mixer.clipAction(clip);
    action.clampWhenFinished = true;
    action.setLoop(THREE.LoopOnce);

    const crossfade = 0.3;
    if (this.currentGestureAction) {
      action.reset().play();
      this.currentGestureAction.crossFadeTo(action, crossfade, true);
    } else {
      action.reset().play();
    }
    this.currentGestureAction = action;
  }

  debugExpressions() {
    if (!this.currentVRM?.expressionManager) return;
    const em = this.currentVRM.expressionManager;
    const map = em._expressionMap || em._expressions;
    const names = map instanceof Map ? [...map.keys()] : (map ? Object.keys(map) : []);
    console.log('[avatar] expressions:', names);
  }

  // --- 内部: 表情イージング ---
  _updateExpressionEasing() {
    if (!this.exprTransitionStart) return;
    const elapsed = performance.now() - this.exprTransitionStart;
    const progress = Math.min(elapsed / this.EXPR_TRANSITION_MS, 1);
    const t = progress < 0.5
      ? 2 * progress * progress
      : 1 - Math.pow(-2 * progress + 2, 2) / 2;

    const allNames = new Set([...Object.keys(this.exprPrev), ...Object.keys(this.exprTarget)]);
    for (const name of allNames) {
      const from = this.exprPrev[name] || 0;
      const to = this.exprTarget[name] || 0;
      this.exprCurrent[name] = from + (to - from) * t;
    }
    if (progress >= 1) this.exprTransitionStart = 0;
  }

  // --- 内部: 毎フレーム更新 ---
  animate() {
    const delta = this.clock.getDelta();

    // ジェスチャーAnimationMixer更新
    if (this.mixer) this.mixer.update(delta);

    if (!this.currentVRM) { this.renderer.render(this.scene, this.camera); return; }

    const now = performance.now() / 1000;
    const t = now - this.t0;
    const s = this.idleScale;

    // ジェスチャー再生中はidleボーンをスキップ（mixerに任せる）
    const gestureActive = this.currentGestureAction && this.currentGestureAction.isRunning();

    if (!gestureActive) {
      // ジェスチャー終了後にactionをクリア
      if (this.currentGestureAction && !this.currentGestureAction.isRunning()) {
        this.currentGestureAction = null;
      }

      // --- 呼吸 (~4秒周期) ---
      const breath = Math.sin(t * 1.6) * 0.8 * s;
      setBoneRotation(this.currentVRM, 'chest', quatFromAxisAngle(1, 0, 0, breath));

      // --- 体の揺れ (~7秒周期) ---
      const sway = (Math.sin(t * 0.9) * 1.0 + Math.sin(t * 0.37) * 0.4) * s;
      setBoneRotation(this.currentVRM, 'spine', quatFromAxisAngle(0, 0, 1, sway));

      // --- 見回し (gaze) ---
      if (now >= this._gazeNextChange && now >= this._gazeHoldUntil) {
        this._gazeTargetY = (Math.random() - 0.5) * 12;  // ±6°
        this._gazeTargetX = (Math.random() - 0.5) * 6;   // ±3°
        this._gazeHoldUntil = now + 2 + Math.random() * 4;
        this._gazeNextChange = this._gazeHoldUntil + 3 + Math.random() * 10;
      }
      this._gazeCurrentY += (this._gazeTargetY - this._gazeCurrentY) * Math.min(1, delta * 2);
      this._gazeCurrentX += (this._gazeTargetX - this._gazeCurrentX) * Math.min(1, delta * 2);

      // --- 頭の動き ---
      const headX = (Math.sin(t * 0.7) * 1.2 + Math.sin(t * 1.3) * 0.6) * s + this._gazeCurrentX;
      const headZ = (Math.sin(t * 0.5) * 1.6 + Math.sin(t * 1.1) * 0.6) * s;
      const headY = Math.sin(t * 0.4) * 1.2 * s + this._gazeCurrentY;
      const qHead = quatFromAxisAngle(1, 0, 0, headX)
        .multiply(quatFromAxisAngle(0, 1, 0, headY))
        .multiply(quatFromAxisAngle(0, 0, 1, headZ));
      setBoneRotation(this.currentVRM, 'head', qHead);

      // --- 腕の揺れ ---
      const rArmSway = Math.sin(t * 0.6 + 1.0) * 0.8 * s;
      const lArmSway = Math.sin(t * 0.6 + 2.5) * 0.8 * s;
      setBoneRotation(this.currentVRM, 'rightUpperArm', quatFromAxisAngle(0, 0, 1, -70 + rArmSway));
      setBoneRotation(this.currentVRM, 'leftUpperArm', quatFromAxisAngle(0, 0, 1, 70 + lArmSway));

      // --- 前腕 ---
      const rFore = 20 + Math.sin(t * 0.8 + 0.5) * 0.6 * s;
      const lFore = -20 + Math.sin(t * 0.8 + 2.0) * 0.6 * s;
      setBoneRotation(this.currentVRM, 'rightLowerArm', quatFromAxisAngle(0, 1, 0, rFore));
      setBoneRotation(this.currentVRM, 'leftLowerArm', quatFromAxisAngle(0, 1, 0, lFore));
    }

    // --- BlendShape ---
    const em = this.currentVRM.expressionManager;
    if (em) {
      // まばたき
      if (now >= this.nextBlink && this.blinkEnd === 0) {
        this.blinkEnd = now + 0.08;
      }
      if (this.blinkEnd > 0) {
        if (now < this.blinkEnd) {
          em.setValue('blink', 1.0);
        } else {
          em.setValue('blink', 0.0);
          this.blinkEnd = 0;
          this.nextBlink = now + 2 + Math.random() * 4;
        }
      }

      // 耳ぴくぴく（カスタムBlendShape）
      if (now >= this.nextEarTwitch && now >= this.earTwitchEnd) {
        this.earTwitchShake = Math.random() < 0.15;
        if (this.earTwitchShake) {
          this.earTwitchDuration = 0.3 + Math.random() * 0.3;
          this.earTwitchShakeHz = 30 + Math.random() * 20;
          em.setValue('happy', 0.6);
        } else {
          this.earTwitchDuration = 0.15 + Math.random() * 0.15;
        }
        this.earTwitchEnd = now + this.earTwitchDuration;
        this.earTwitchStart = now;
        this.nextEarTwitch = now + 3 + Math.random() * 7;
      }
      try {
        if (now < this.earTwitchEnd) {
          const progress = (now - this.earTwitchStart) / this.earTwitchDuration;
          if (this.earTwitchShake) {
            const fade = 1 - progress;
            const wave = Math.sin(progress * this.earTwitchShakeHz * Math.PI) * fade;
            em.setValue('ear_stand', Math.max(0, wave));
            em.setValue('ear_droop', Math.max(0, -wave));
          } else {
            em.setValue('ear_stand', Math.sin(progress * Math.PI));
            em.setValue('ear_droop', 0.0);
          }
        } else {
          em.setValue('ear_stand', 0.0);
          em.setValue('ear_droop', 0.0);
          if (this.earTwitchShake) {
            em.setValue('happy', 0.0);
            this.earTwitchShake = false;
          }
        }
      } catch (e) { /* ear BlendShapeがない場合は無視 */ }

      // リップシンク
      if (this.lipsyncFrames) {
        const frameIdx = Math.floor((now - this.lipsyncStart) * 30);
        if (frameIdx >= 0 && frameIdx < this.lipsyncFrames.length) {
          em.setValue('aa', this.lipsyncFrames[frameIdx]);
        } else {
          this.lipsyncFrames = null;
          em.setValue('aa', 0.0);
        }
      }

      // 感情BlendShape（イージング遷移）
      this._updateExpressionEasing();
      for (const [name, value] of Object.entries(this.exprCurrent)) {
        const lname = name.toLowerCase();
        if (lname === 'aa' || lname === 'blink' || lname === 'ear_stand') continue;
        try { em.setValue(lname, value); } catch (e) {}
      }

      em.update();
    }

    this.currentVRM.update(delta);
    this.renderer.render(this.scene, this.camera);
  }
}


// === インスタンス管理 ===
window.avatarInstances = {};

// 先生アバター（常に存在）
const teacherAvatar = new AvatarInstance('avatar-canvas-1', 'avatar-area-1');
window.avatarInstances['teacher'] = teacherAvatar;

// 生徒アバター（canvas存在時のみ）
if (document.getElementById('avatar-canvas-2')) {
  const studentAvatar = new AvatarInstance('avatar-canvas-2', 'avatar-area-2');
  window.avatarInstances['student'] = studentAvatar;
}

// === 後方互換: window.avatarVRM ===
window.avatarVRM = {
  setBlendShapes(shapes) { teacherAvatar.setBlendShapes(shapes); },
  setLipsync(frames)     { teacherAvatar.setLipsync(frames); },
  startLipsync()         { teacherAvatar.startLipsync(); },
  stopLipsync()          { teacherAvatar.stopLipsync(); },
  setIdleScale(s)        { teacherAvatar.idleScale = s; },
  setBodyAngle(deg)      { teacherAvatar.setBodyAngle(deg); },
  playGesture(name)      { teacherAvatar.playGesture(name); },
  debugExpressions()     { teacherAvatar.debugExpressions(); },
};

// === 後方互換: window.avatarLighting ===
// デフォルトはteacherに適用（後方互換）。avatarId指定で個別適用可能。
function _getAvatarForLighting(avatarId) {
  if (avatarId && window.avatarInstances[avatarId]) return window.avatarInstances[avatarId];
  return teacherAvatar;
}
window.avatarLighting = {
  BASE_AMBIENT: 0.75,
  BASE_DIRECTIONAL: 1.0,
  setAmbient(i, avatarId)     { _getAvatarForLighting(avatarId).ambientLight.intensity = i; },
  setDirectional(i, avatarId) { _getAvatarForLighting(avatarId).dirLight.intensity = i; },
  setExposure(val, avatarId) {
    const a = _getAvatarForLighting(avatarId);
    if (a._disabled) return;
    a.ambientLight.intensity = a.BASE_AMBIENT * val;
    a.dirLight.intensity = a.BASE_DIRECTIONAL * val;
  },
  setColor(r, g, b, avatarId) {
    const a = _getAvatarForLighting(avatarId);
    if (a._disabled) return;
    a.ambientLight.color.setRGB(r, g, b);
    a.dirLight.color.setRGB(r, g, b);
  },
  setPosition(x, y, z, avatarId) {
    const a = _getAvatarForLighting(avatarId);
    if (x != null) a.dirLight.position.x = x;
    if (y != null) a.dirLight.position.y = y;
    if (z != null) a.dirLight.position.z = z;
  },
};

// init()がmodule scriptより先に実行された場合のpending適用
if (window._pendingLighting) {
  const pending = window._pendingLighting;
  delete window._pendingLighting;
  if (typeof _applyLighting === 'function') {
    _applyLighting(pending);
  }
}
// キャラ別pendingライティング適用
if (window._pendingLightingPerChar) {
  const pending = window._pendingLightingPerChar;
  delete window._pendingLightingPerChar;
  if (typeof _applyLighting === 'function') {
    if (pending.teacher) _applyLighting(pending.teacher, 'teacher');
    if (pending.student) _applyLighting(pending.student, 'student');
  }
}

// === 統合アニメーションループ ===
function animateAll() {
  requestAnimationFrame(animateAll);
  for (const avatar of Object.values(window.avatarInstances)) {
    if (!avatar._disabled) avatar.animate();
  }
}
animateAll();

// === 初期化: アバター読み込み ===
async function initAvatar() {
  // characters API からVRM情報を取得
  let teacherVrm = null;
  let studentVrm = null;
  try {
    const chars = await (await fetch('/api/characters')).json();
    for (const c of chars) {
      if (c.role === 'teacher' && c.vrm) teacherVrm = c.vrm;
      if (c.role === 'student' && c.vrm) studentVrm = c.vrm;
    }
  } catch (e) {}

  // フォールバック: files API
  if (!teacherVrm) {
    try {
      const filesRes = await fetch('/api/files/avatar/list');
      const filesData = await filesRes.json();
      if (filesData.ok && filesData.active) teacherVrm = filesData.active;
    } catch (e) {}
  }
  const vrmUrl = teacherVrm
    ? '/resources/vrm/' + teacherVrm
    : '/resources/vrm/Shinano.vrm';

  // 先生アバター読み込み
  await teacherAvatar.loadVRM(vrmUrl);

  // 生徒アバター読み込み
  const student = window.avatarInstances['student'];
  if (student && !student._disabled) {
    const studentVrmUrl = studentVrm
      ? '/resources/vrm/' + studentVrm
      : vrmUrl;
    await student.loadVRM(studentVrmUrl);
  }
}
initAvatar();

// グローバル公開（非module scriptからアクセス用）
window.loadVRM = (url) => teacherAvatar.loadVRM(url);
