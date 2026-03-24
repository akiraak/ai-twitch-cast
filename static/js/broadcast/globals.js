// broadcast.html 共有グローバル変数・DOM参照

// console.logキャプチャ → サーバー送信（最初に実行）
(function() {
  const _buf = [];
  const _orig = console.log;
  const _origWarn = console.warn;
  const _origErr = console.error;
  function capture(level, args) {
    const line = '[' + level + '] ' + Array.from(args).map(a => {
      try { return typeof a === 'object' ? JSON.stringify(a) : String(a); } catch(e) { return String(a); }
    }).join(' ');
    _buf.push(new Date().toISOString().substr(11,12) + ' ' + line);
  }
  console.log = function() { capture('LOG', arguments); _orig.apply(console, arguments); };
  console.warn = function() { capture('WARN', arguments); _origWarn.apply(console, arguments); };
  console.error = function() { capture('ERR', arguments); _origErr.apply(console, arguments); };
  setInterval(function() {
    if (_buf.length === 0) return;
    const lines = _buf.splice(0, 100);
    fetch('/api/debug/jslog', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({lines}) }).catch(function(){});
  }, 2000);
})();

// === DOM参照 ===
const subtitleEl = document.getElementById('subtitle');
const todoPanelEl = document.getElementById('todo-panel');
const todoListEl = document.getElementById('todo-list');
let fadeTimer = null;
let todoSettings = {};

// === 音量管理（C#アプリに送信用、ブラウザでは音声再生しない） ===
let volumes = { master: 0.8, tts: 0.8, bgm: 1.0, se: 0.8 };

// === リップシンク同期（配信時は遅延、非配信時はリアルタイム） ===
let _isStreaming = false;
let _lipsyncDelay = 100; // 配信時の遅延(ms)、非配信時は0（音声先行送信により大幅削減）
let _syncTimer = null;   // 遅延タイマー（キャンセル用）
let _pendingSubtitle = null; // 遅延表示待ちの字幕データ

function applyVolume() {
  // WebView2パネルに音量+syncDelay同期通知
  try { window.chrome?.webview?.postMessage({_volumeSync: {...volumes, lipsyncDelay: _lipsyncDelay}}); } catch(e){}
}

// === アイテムレジストリ（editSaveで共通ループに使用） ===
const ITEM_REGISTRY = [
  { id: 'avatar-area-1', prefix: 'avatar1', hasSize: true, defaultZ: 5 },
  { id: 'avatar-area-2', prefix: 'avatar2', hasSize: true, defaultZ: 4 },
  { id: 'subtitle', prefix: 'subtitle', hasSize: false, defaultZ: 20 },
  { id: 'todo-panel', prefix: 'todo', hasSize: true, defaultZ: 20 },
];

// === アバターストリーム ===
const avatarImg = document.getElementById('avatar-stream');

// === ウィンドウキャプチャ ===
const captureContainer = document.getElementById('capture-container');
const captureLayers = {};
const captureImgMap = {};      // capture_id -> img element
let useDirectCapture = false;
const captureIndexToId = {};   // index -> capture_id
let snapshotHost = null;
let snapshotTimer = null;
const SNAPSHOT_INTERVAL = 200; // 5fps

// === カスタムテキスト ===
const customTextContainer = document.getElementById('custom-text-container');
const customTextLayers = {};

// === 子パネル ===
const childPanelEls = {};  // id → DOM要素

// === フローティング設定パネル状態 ===
const _spPanel = document.getElementById('settings-panel');
const _spTitle = document.getElementById('sp-title');
const _spBody = document.getElementById('sp-body');
const _schemaCache = {};  // item_type → schema
let _spItemId = null;     // 現在開いているアイテムID
let _spSaveTimer = null;

// === 編集モード状態 ===
const isEmbedded = new URLSearchParams(location.search).has('embedded') || window.parent !== window;
if (isEmbedded) document.body.classList.add('embedded');
let _saveTimer = null;
let _saving = false;  // editSave中はsettings_updateを無視
let _selectedEditable = null;
