import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import * as VRM from '@pixiv/three-vrm';

// === VRMアバターレンダラー ===
const canvas = document.getElementById('avatar-canvas');
const avatarArea = document.getElementById('avatar-area');
const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
renderer.setPixelRatio(Math.max(window.devicePixelRatio || 1, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.NoToneMapping;

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(20, 1, 0.1, 100);
camera.position.set(0, 1.2, 3.0);
camera.lookAt(0, 1.1, 0);

// レンダラーサイズをアバター領域に合わせる
function resizeRenderer() {
  const w = avatarArea.clientWidth;
  const h = avatarArea.clientHeight;
  renderer.setSize(w, h);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
resizeRenderer();
window.addEventListener('resize', resizeRenderer);
new ResizeObserver(resizeRenderer).observe(avatarArea);

// ライティング
const BASE_AMBIENT = 0.75;
const BASE_DIRECTIONAL = 1.0;
const ambientLight = new THREE.AmbientLight(0xffffff, BASE_AMBIENT);
scene.add(ambientLight);
const dirLight = new THREE.DirectionalLight(0xffffff, BASE_DIRECTIONAL);
dirLight.position.set(0.5, 1.5, 2.0);  // 前方やや右上から照らす
scene.add(dirLight);

// ライティング設定を外部から制御
window.avatarLighting = {
  BASE_AMBIENT,
  BASE_DIRECTIONAL,
  setAmbient(intensity) { ambientLight.intensity = intensity; },
  setDirectional(intensity) { dirLight.intensity = intensity; },
  setExposure(val) {
    // NoToneMapping: ライト強度の倍率で代替
    ambientLight.intensity = BASE_AMBIENT * val;
    dirLight.intensity = BASE_DIRECTIONAL * val;
  },
  setColor(r, g, b) {
    ambientLight.color.setRGB(r, g, b);
    dirLight.color.setRGB(r, g, b);
  },
  setPosition(x, y, z) {
    if (x != null) dirLight.position.x = x;
    if (y != null) dirLight.position.y = y;
    if (z != null) dirLight.position.z = z;
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

let currentVRM = null;
let idleScale = 1.0;
let t0 = performance.now() / 1000;

// まばたき状態
let nextBlink = t0 + 2 + Math.random() * 3;
let blinkEnd = 0;

// 耳ぴくぴく状態
let nextEarTwitch = t0 + 3 + Math.random() * 5;
let earTwitchEnd = 0;
let earTwitchStart = 0;
let earTwitchDuration = 0.2;

// リップシンク状態
let lipsyncFrames = null;
let lipsyncStart = 0;
let pendingLipsyncFrames = null;  // 音声再生開始まで保持
// リップシンクはlipsyncイベント受信時に即座開始（遅延補正不要）。
// TTS音声はC#アプリが直接FFmpegパイプに書き込む。ブラウザでは再生しない。

// 外部BlendShape（感情等）
let externalShapes = {};

// グローバル公開
window.avatarVRM = {
  setBlendShapes(shapes) { externalShapes = shapes; },
  setLipsync(frames) {
    // フレームデータを保存のみ。アニメーションはplay_audio再生開始時に開始
    pendingLipsyncFrames = frames;
  },
  startLipsync() {
    // 音声再生開始時に呼ばれる
    if (pendingLipsyncFrames) {
      lipsyncFrames = pendingLipsyncFrames;
      lipsyncStart = performance.now() / 1000;
      pendingLipsyncFrames = null;
    }
  },
  stopLipsync() { lipsyncFrames = null; pendingLipsyncFrames = null; },
  setIdleScale(s) { idleScale = s; },
};

// VRMモデル読み込み
async function loadVRM(url) {
  const loader = new GLTFLoader();
  loader.register((parser) => new VRM.VRMLoaderPlugin(parser));

  try {
    const gltf = await loader.loadAsync(url);
    const vrm = gltf.userData.vrm;
    if (!vrm) { console.error('VRMデータがありません'); return; }

    // 既存モデル削除
    if (currentVRM) {
      scene.remove(currentVRM.scene);
      VRM.VRMUtils.deepDispose(currentVRM.scene);
    }

    // VRM追加
    VRM.VRMUtils.rotateVRM0(vrm);
    scene.add(vrm.scene);
    currentVRM = vrm;

    console.log('VRM読み込み完了:', url);
    t0 = performance.now() / 1000;
  } catch (e) {
    console.error('VRM読み込み失敗:', e);
  }
}

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

// アイドルアニメーション + レンダリングループ
function animate() {
  requestAnimationFrame(animate);
  if (!currentVRM) { renderer.render(scene, camera); return; }

  const now = performance.now() / 1000;
  const t = now - t0;
  const s = idleScale;

  // --- 呼吸 (~4秒周期) ---
  const breath = Math.sin(t * 1.6) * 0.8 * s;
  setBoneRotation(currentVRM, 'chest', quatFromAxisAngle(1, 0, 0, breath));

  // --- 体の揺れ (~7秒周期) ---
  const sway = (Math.sin(t * 0.9) * 1.0 + Math.sin(t * 0.37) * 0.4) * s;
  setBoneRotation(currentVRM, 'spine', quatFromAxisAngle(0, 0, 1, sway));

  // --- 頭の動き ---
  const headX = (Math.sin(t * 0.7) * 1.2 + Math.sin(t * 1.3) * 0.6) * s;
  const headZ = (Math.sin(t * 0.5) * 1.6 + Math.sin(t * 1.1) * 0.6) * s;
  const headY = Math.sin(t * 0.4) * 1.2 * s;
  const qHead = quatFromAxisAngle(1, 0, 0, headX)
    .multiply(quatFromAxisAngle(0, 1, 0, headY))
    .multiply(quatFromAxisAngle(0, 0, 1, headZ));
  setBoneRotation(currentVRM, 'head', qHead);

  // --- 腕の揺れ ---
  const rArmSway = Math.sin(t * 0.6 + 1.0) * 0.8 * s;
  const lArmSway = Math.sin(t * 0.6 + 2.5) * 0.8 * s;
  setBoneRotation(currentVRM, 'rightUpperArm', quatFromAxisAngle(0, 0, 1, -70 + rArmSway));
  setBoneRotation(currentVRM, 'leftUpperArm', quatFromAxisAngle(0, 0, 1, 70 + lArmSway));

  // --- 前腕 ---
  const rFore = 20 + Math.sin(t * 0.8 + 0.5) * 0.6 * s;
  const lFore = -20 + Math.sin(t * 0.8 + 2.0) * 0.6 * s;
  setBoneRotation(currentVRM, 'rightLowerArm', quatFromAxisAngle(0, 1, 0, rFore));
  setBoneRotation(currentVRM, 'leftLowerArm', quatFromAxisAngle(0, 1, 0, lFore));

  // --- BlendShape ---
  const em = currentVRM.expressionManager;
  if (em) {
    // まばたき
    if (now >= nextBlink && blinkEnd === 0) {
      blinkEnd = now + 0.08;
    }
    if (blinkEnd > 0) {
      if (now < blinkEnd) {
        em.setValue('blink', 1.0);
      } else {
        em.setValue('blink', 0.0);
        blinkEnd = 0;
        nextBlink = now + 2 + Math.random() * 4;
      }
    }

    // 耳ぴくぴく（カスタムBlendShape）
    if (now >= nextEarTwitch && now >= earTwitchEnd) {
      earTwitchDuration = 0.15 + Math.random() * 0.15;
      earTwitchEnd = now + earTwitchDuration;
      earTwitchStart = now;
      nextEarTwitch = now + 3 + Math.random() * 7;
    }
    // ear_standがある場合のみ
    try {
      if (now < earTwitchEnd) {
        const progress = (now - earTwitchStart) / earTwitchDuration;
        em.setValue('ear_stand', Math.sin(progress * Math.PI));
      } else {
        em.setValue('ear_stand', 0.0);
      }
    } catch (e) { /* ear_stand BlendShapeがない場合は無視 */ }

    // リップシンク
    if (lipsyncFrames) {
      const frameIdx = Math.floor((now - lipsyncStart) * 30);
      if (frameIdx >= 0 && frameIdx < lipsyncFrames.length) {
        em.setValue('aa', lipsyncFrames[frameIdx]);
      } else {
        lipsyncFrames = null;
        em.setValue('aa', 0.0);
      }
    }

    // 外部BlendShape（感情等）
    for (const [name, value] of Object.entries(externalShapes)) {
      try { em.setValue(name.toLowerCase(), value); } catch (e) {}
    }

    em.update();
  }

  currentVRM.update(1 / 30);
  renderer.render(scene, camera);
}

animate();

// デフォルトでVRMモデルを読み込み（素材管理で選択されたVRMを優先）
async function initAvatar() {
  try {
    // 素材管理で選択されたアバターを確認
    const filesRes = await fetch('/api/files/avatar/list');
    const filesData = await filesRes.json();
    if (filesData.ok && filesData.active) {
      await loadVRM('/resources/vrm/' + filesData.active);
      return;
    }
  } catch (e) {}
  try {
    const res = await fetch('/api/broadcast/avatar');
    const data = await res.json();
    const vrmUrl = data.vrm_url || '/resources/vrm/Shinano.vrm';
    await loadVRM(vrmUrl);
  } catch (e) {
    await loadVRM('/resources/vrm/Shinano.vrm');
  }
}

initAvatar();

// グローバル公開（非module scriptからアクセス用）
window.loadVRM = loadVRM;
