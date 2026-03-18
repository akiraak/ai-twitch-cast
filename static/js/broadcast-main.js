// === 要素参照 ===
const subtitleEl = document.getElementById('subtitle');
const todoPanelEl = document.getElementById('todo-panel');
const todoListEl = document.getElementById('todo-list');
const topicPanelEl = document.getElementById('topic-panel');
let fadeTimer = null;
let todoSettings = {};

// === 音量管理（C#アプリに送信用、ブラウザでは音声再生しない） ===
let volumes = { master: 0.8, tts: 0.8, bgm: 1.0 };

// === リップシンク同期（配信時は遅延、非配信時はリアルタイム） ===
let _isStreaming = false;
let _lipsyncDelay = 100; // 配信時の遅延(ms)、非配信時は0（音声先行送信により大幅削減）
let _syncTimer = null;   // 遅延タイマー（キャンセル用）
let _pendingSubtitle = null; // 遅延表示待ちの字幕データ

function applyVolume() {
  // WebView2パネルに音量+syncDelay同期通知
  try { window.chrome?.webview?.postMessage({_volumeSync: {...volumes, lipsyncDelay: _lipsyncDelay}}); } catch(e){}
}


// === 背景透明度の適用（CSS変数で制御） ===
function setBgOpacity(el, opacity) {
  el.style.setProperty('--bg-opacity', opacity);
}

// === アイテムレジストリ（editSaveで共通ループに使用） ===
const ITEM_REGISTRY = [
  { id: 'avatar-area', prefix: 'avatar', hasSize: true, defaultZ: 5 },
  { id: 'subtitle', prefix: 'subtitle', hasSize: false, defaultZ: 20 },
  { id: 'todo-panel', prefix: 'todo', hasSize: true, defaultZ: 20 },
  { id: 'topic-panel', prefix: 'topic', hasSize: false, defaultZ: 20 },
  { id: 'version-panel', prefix: 'version', hasSize: false, defaultZ: 10, saveVisible: true },
  { id: 'dev-activity-panel', prefix: 'dev_activity', hasSize: false, defaultZ: 15 },
];

// === 共通スタイル適用 ===
function applyCommonStyle(el, props) {
  if (!el || !props) return;
  // 表示
  if (props.visible != null) {
    if (!Number(props.visible)) el.style.display = 'none';
    else if (el.style.display === 'none') el.style.display = '';
  }
  // 配置
  if (props.positionX != null) el.style.left = props.positionX + '%';
  if (props.positionY != null) el.style.top = props.positionY + '%';
  if (props.zIndex != null) el.style.zIndex = props.zIndex;
  // 背景透明度（既存のCSS変数パターン）
  if (props.bgOpacity != null) setBgOpacity(el, props.bgOpacity);
  // 新規共通プロパティ → CSS変数として設定（Phase 3でCSSから参照）
  if (props.bgColor != null) el.style.setProperty('--item-bg-color', props.bgColor);
  if (props.borderRadius != null) el.style.setProperty('--item-border-radius', props.borderRadius + 'px');
  if (props.borderEnabled != null) el.style.setProperty('--item-border-enabled', String(props.borderEnabled));
  if (props.borderColor != null) el.style.setProperty('--item-border-color', props.borderColor);
  if (props.borderSize != null) el.style.setProperty('--item-border-size', props.borderSize + 'px');
  if (props.borderOpacity != null) el.style.setProperty('--item-border-opacity', String(props.borderOpacity));
  if (props.textColor != null) el.style.setProperty('--item-text-color', props.textColor);
  if (props.fontSize != null) el.style.setProperty('--item-font-size', props.fontSize + 'vw');
  if (props.textStrokeColor != null) el.style.setProperty('--item-text-stroke-color', props.textStrokeColor);
  if (props.textStrokeSize != null) el.style.setProperty('--item-text-stroke-size', props.textStrokeSize + 'px');
  if (props.textStrokeOpacity != null) el.style.setProperty('--item-text-stroke-opacity', String(props.textStrokeOpacity));
  if (props.padding != null) el.style.setProperty('--item-padding', props.padding + 'px');
}

// === ライティング適用（applySettings・pending両方から呼ばれる） ===
function _applyLighting(lighting) {
  const L = window.avatarLighting;
  if (!L) return;
  const b = lighting.brightness ?? 1.0;
  const c = lighting.contrast ?? 1.0;
  const temp = lighting.temperature ?? 0;  // -1(寒色)〜+1(暖色)
  const sat = lighting.saturation ?? 1.0;
  // 詳細ライト設定（直接指定がある場合はそちらを優先）
  if (lighting.ambient != null) L.setAmbient(lighting.ambient);
  if (lighting.directional != null) L.setDirectional(lighting.directional);
  if (lighting.ambient == null && lighting.directional == null) {
    // 明るさ・コントラストからの自動計算（詳細設定がない場合のみ）
    L.setExposure(b);
    L.setAmbient(Math.max(0.1, Math.min(2.0, L.BASE_AMBIENT * b / c)));
    L.setDirectional(Math.max(0.2, Math.min(3.0, L.BASE_DIRECTIONAL * b * c)));
  }
  // ライト方向
  if (lighting.lightX != null || lighting.lightY != null || lighting.lightZ != null) {
    L.setPosition(lighting.lightX, lighting.lightY, lighting.lightZ);
  }
  // 色温度 → ライトの色（暖色=黄、寒色=青）
  const r = 1.0 + temp * 0.15;
  const g = 1.0;
  const bl = 1.0 - temp * 0.15;
  L.setColor(r, g, bl);
  // 彩度 → CSSフィルター
  document.getElementById('avatar-canvas').style.filter = sat !== 1.0 ? `saturate(${sat})` : '';
}

// === 設定適用（%/vw単位） ===
function applySettings(s) {
  // === avatar ===
  const avatarArea = document.getElementById('avatar-area');
  if (s.avatar) {
    applyCommonStyle(avatarArea, s.avatar);
    // avatar固有: サイズ + キャンバスリサイズ
    if (s.avatar.width != null) avatarArea.style.width = s.avatar.width + '%';
    if (s.avatar.height != null) avatarArea.style.height = s.avatar.height + '%';
    if (window.dispatchEvent) window.dispatchEvent(new Event('resize'));
  }
  // === lighting ===
  if (s.lighting) {
    if (window.avatarLighting) {
      _applyLighting(s.lighting);
    } else {
      window._pendingLighting = s.lighting;
    }
  }
  // === subtitle ===
  if (s.subtitle) {
    applyCommonStyle(subtitleEl, s.subtitle);
    // 字幕固有: bottom配置（commonのtop/leftをオーバーライド）
    if (s.subtitle.bottom != null) {
      subtitleEl.style.bottom = s.subtitle.bottom + '%';
      subtitleEl.style.top = '';
      subtitleEl.style.left = '50%';
      subtitleEl.style.transform = 'translateX(-50%)';
    }
    if (s.subtitle.fontSize != null) subtitleEl.querySelector('.response').style.fontSize = s.subtitle.fontSize + 'vw';
    if (s.subtitle.maxWidth != null) subtitleEl.style.maxWidth = s.subtitle.maxWidth + '%';
    if (s.subtitle.fadeDuration != null) subtitleEl.dataset.fadeDuration = s.subtitle.fadeDuration;
  }
  // === todo ===
  if (s.todo) {
    applyCommonStyle(todoPanelEl, s.todo);
    todoSettings = s.todo;
    // todo固有: サイズ + maxHeight + transform
    if (s.todo.width != null) todoPanelEl.style.width = s.todo.width + '%';
    if (s.todo.height != null) {
      todoPanelEl.style.height = s.todo.height + '%';
      todoPanelEl.style.maxHeight = 'none';
      todoPanelEl.style.overflow = 'hidden';
    }
    if (s.todo.positionX != null) todoPanelEl.style.transform = 'none';
    if (s.todo.fontSize != null) {
      todoPanelEl.querySelectorAll('.todo-item').forEach(el => el.style.fontSize = s.todo.fontSize + 'vw');
    }
    if (s.todo.titleFontSize != null) todoPanelEl.querySelector('.todo-title').style.fontSize = s.todo.titleFontSize + 'vw';
    loadTodo();
  }
  // === topic ===
  if (s.topic) {
    applyCommonStyle(topicPanelEl, s.topic);
    if (s.topic.maxWidth != null) topicPanelEl.style.maxWidth = s.topic.maxWidth + '%';
    if (s.topic.titleFontSize != null) {
      document.getElementById('topic-title-text').style.fontSize = s.topic.titleFontSize + 'vw';
    }
  }
  // === version ===
  if (s.version) {
    const vp = document.getElementById('version-panel');
    if (vp) {
      applyCommonStyle(vp, s.version);
      // version固有: format, fontSize(子要素), stroke
      if (s.version.format != null) { window._versionFormat = s.version.format; _applyVersionFormat(); }
      if (s.version.fontSize != null) document.getElementById('version-text').style.fontSize = s.version.fontSize + 'vw';
      const vText = document.getElementById('version-text');
      if (s.version.strokeSize != null || s.version.strokeOpacity != null) {
        const size = s.version.strokeSize ?? parseFloat(vText.dataset.strokeSize || 2);
        const opacity = s.version.strokeOpacity ?? parseFloat(vText.dataset.strokeOpacity || 0.8);
        vText.dataset.strokeSize = size;
        vText.dataset.strokeOpacity = opacity;
        vText.style.webkitTextStroke = `${size}px rgba(0,0,0,${opacity})`;
        vText.style.paintOrder = 'stroke fill';
      }
    }
  }
  // === dev_activity ===
  if (s.dev_activity) {
    const dap = document.getElementById('dev-activity-panel');
    if (dap) applyCommonStyle(dap, s.dev_activity);
  }
  // === sync ===
  if (s.sync) {
    if (s.sync.lipsyncDelay != null) {
      _lipsyncDelay = s.sync.lipsyncDelay;
      try { window.chrome?.webview?.postMessage({_syncDelay: _lipsyncDelay}); } catch(e){}
    }
  }
}

// === 字幕 ===
function showSubtitle(data) {
  clearTimeout(fadeTimer);
  subtitleEl.classList.remove('fading');
  subtitleEl.querySelector('.author').textContent = '';
  subtitleEl.querySelector('.message').textContent = data.message;
  subtitleEl.querySelector('.response').textContent = data.response;
  subtitleEl.querySelector('.english').textContent = data.english || '';
  subtitleEl.classList.add('visible');
}

function fadeSubtitle() {
  const duration = parseFloat(subtitleEl.dataset.fadeDuration || 3) * 1000;
  fadeTimer = setTimeout(() => {
    subtitleEl.classList.add('fading');
    subtitleEl.classList.remove('visible');
  }, duration);
}

// === トピックパネル ===
function updateTopicPanel(data) {
  const titleEl = document.getElementById('topic-title-text');
  const descEl = document.getElementById('topic-desc-text');
  const statsEl = document.getElementById('topic-stats');
  const dotEl = document.getElementById('topic-dot');
  const isIdle = !data || !data.active || data.paused;

  if (isIdle) {
    topicPanelEl.classList.add('idle');
    titleEl.textContent = '----';
    descEl.textContent = '';
    descEl.style.display = 'none';
    statsEl.textContent = '';
    dotEl.classList.add('paused');
    return;
  }
  topicPanelEl.classList.remove('idle');
  titleEl.textContent = data.topic.title;
  descEl.textContent = data.topic.description || '';
  descEl.style.display = data.topic.description ? '' : 'none';
  const parts = [];
  if (data.remaining_scripts != null) parts.push(`残り ${data.remaining_scripts}件`);
  if (data.spoken_count != null) parts.push(`発話済み ${data.spoken_count}件`);
  statsEl.textContent = parts.join(' / ');
  dotEl.classList.toggle('paused', false);
}

async function loadTopicPanel() {
  try {
    const res = await fetch('/api/topic');
    const data = await res.json();
    updateTopicPanel(data);
  } catch (e) {}
}

// === バージョンフォーマット ===
function _applyVersionFormat() {
  const vEl = document.getElementById('version-text');
  const info = window._versionInfo;
  if (!vEl || !info || !info.version) return;
  const fmt = window._versionFormat || 'Chobi v{version} ({date})';
  const d = info.updated_at ? new Date(info.updated_at) : null;
  const year = d ? String(d.getFullYear()) : '';
  const month = d ? String(d.getMonth() + 1).padStart(2, '0') : '';
  const day = d ? String(d.getDate()).padStart(2, '0') : '';
  const date = d ? `${year}-${month}-${day}` : '';
  vEl.textContent = fmt
    .replace(/\{version}/g, info.version)
    .replace(/\{date}/g, date)
    .replace(/\{year}/g, year)
    .replace(/\{month}/g, month)
    .replace(/\{day}/g, day);
}

// === 開発アクティビティ ===
let _devActivityTimer = null;
function showDevActivity(data) {
  const panel = document.getElementById('dev-activity-panel');
  const content = document.getElementById('dev-activity-content');
  if (!panel || !content) return;
  const commits = data.commits || [];
  const repo = data.repo || '';
  let html = '';
  if (repo) html += `<div style="color:#81d4fa; font-weight:600; margin-bottom:2px;">${repo}</div>`;
  for (const c of commits.slice(0, 5)) {
    const hash = (c.hash || '').substring(0, 8);
    const msg = c.message || '';
    const author = c.author || '';
    html += `<div style="margin-bottom:2px;"><span style="color:#ffb74d;">${hash}</span> ${msg}`;
    if (author) html += ` <span style="color:#888; font-size:0.55vw;">— ${author}</span>`;
    html += `</div>`;
  }
  content.innerHTML = html;
  panel.style.display = 'block';
  panel.style.opacity = '1';
  if (_devActivityTimer) clearTimeout(_devActivityTimer);
  _devActivityTimer = setTimeout(() => {
    panel.style.transition = 'opacity 2s';
    panel.style.opacity = '0';
    setTimeout(() => { panel.style.display = 'none'; panel.style.transition = ''; }, 2000);
  }, 15000);
}

// === TODO読み込み ===
function renderTodoItems(items) {
  todoListEl.innerHTML = '';
  const fs = todoSettings.fontSize;
  let lastSection = null;
  for (const item of items) {
    const text_val = typeof item === 'string' ? item : item.text;
    const status = typeof item === 'string' ? 'todo' : item.status;
    const section = item.section || '';
    if (section && section !== lastSection) {
      const sectionEl = document.createElement('div');
      sectionEl.className = 'todo-section';
      sectionEl.textContent = section;
      todoListEl.appendChild(sectionEl);
      lastSection = section;
    }
    const div = document.createElement('div');
    div.className = 'todo-item' + (status === 'in_progress' ? ' in-progress' : '');
    if (status === 'in_progress') {
      const arrow = document.createElement('span');
      arrow.className = 'todo-arrow';
      arrow.textContent = '\u25B6';
      div.appendChild(arrow);
    }
    const cb = document.createElement('span');
    cb.className = 'todo-checkbox';
    const text = document.createElement('span');
    text.textContent = text_val;
    if (fs) text.style.fontSize = fs + 'vw';
    div.appendChild(cb);
    div.appendChild(text);
    todoListEl.appendChild(div);
  }
}

async function loadTodo() {
  try {
    const res = await fetch('/api/todo');
    const data = await res.json();
    renderTodoItems(data.items);
  } catch (e) {
    console.log('TODO読み込みエラー:', e.message);
  }
}

// === WebSocket（統合: overlay + tts + bgm） ===
function connectWS() {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(`${protocol}//${location.host}/ws/broadcast`);
  window._ws = ws;  // グローバル参照（C# JS注入からの音量保存用）

  ws.onmessage = (e) => {
    const data = JSON.parse(e.data);

    switch (data.type) {
      // オーバーレイイベント
      case 'comment':
        _pendingSubtitle = data;
        if (!_isStreaming) { showSubtitle(data); }
        // 配信時は lipsync と同時に遅延表示（下の lipsync case で処理）
        break;
      case 'speaking_end':
        fadeSubtitle();
        break;
      case 'topic_update':
        updateTopicPanel(data);
        break;
      case 'settings_update':
        if (!_saving) applySettings(data);
        break;

      // 配信状態（リップシンク遅延切替用）
      case 'stream_status':
        _isStreaming = !!data.streaming;
        console.log('[Sync] streaming:', _isStreaming);
        break;

      // 音声はすべてC#アプリが再生（play_audio / bgm_play / bgm_stop はブラウザ不使用）

      // 音量制御（C#アプリに転送）
      case 'volume':
        if (data.source && data.volume != null) {
          volumes[data.source] = data.volume;
          applyVolume();
        }
        break;


      // VRMアバター制御
      case 'blendshape':
        if (window.avatarVRM && data.shapes) {
          window.avatarVRM.setBlendShapes(data.shapes);
        }
        break;
      case 'lipsync':
        if (window.avatarVRM && data.frames) {
          const delay = _isStreaming ? _lipsyncDelay : 0;
          window.avatarVRM.setLipsync(data.frames);
          clearTimeout(_syncTimer);
          if (delay > 0) {
            _syncTimer = setTimeout(() => {
              if (_pendingSubtitle) { showSubtitle(_pendingSubtitle); _pendingSubtitle = null; }
              window.avatarVRM.startLipsync();
            }, delay);
          } else {
            window.avatarVRM.startLipsync();
          }
          console.log(`[Sync] lipsync: ${data.frames.length} frames, delay=${delay}ms`);
        }
        break;
      case 'lipsync_stop':
        if (window.avatarVRM) {
          window.avatarVRM.stopLipsync();
        }
        break;

      // アバターストリーム（MJPEG fallback）
      case 'avatar_stream':
        setAvatarStream(data.url);
        break;
      case 'avatar_stop':
        stopAvatarStream();
        break;

      // TODO更新（WebSocket push）
      case 'todo_update':
        renderTodoItems(data.items || []);
        break;

      // 開発アクティビティ
      case 'dev_commit':
        showDevActivity(data);
        break;

      // ウィンドウキャプチャ
      case 'capture_add':
        addCaptureLayer(data.id, data.stream_url, data.label, data.layout);
        break;
      case 'capture_remove':
        removeCaptureLayer(data.id);
        break;
      case 'capture_layout':
        updateCaptureLayout(data.id, data.layout);
        break;

      // カスタムテキスト
      case 'custom_text_add':
        addCustomTextLayer(data.id, data.label, data.content, data.layout);
        break;
      case 'custom_text_update':
        updateCustomTextLayer(data.id, data);
        break;
      case 'custom_text_remove':
        removeCustomTextLayer(data.id);
        break;

      // 素材変更
      case 'avatar_vrm_change':
        if (data.url) loadVRM(data.url);
        break;
      case 'background_change':
        if (data.url) document.getElementById('background').src = data.url;
        break;
    }
  };

  ws.onclose = () => { window._ws = null; setTimeout(connectWS, 3000); };
  ws.onerror = () => ws.close();
}

// === アバターストリーム ===
const avatarImg = document.getElementById('avatar-stream');

function setAvatarStream(url) {
  avatarImg.src = url;
  avatarImg.style.display = '';
  avatarImg.onerror = () => {
    // ストリーム切断時は非表示
    avatarImg.style.display = 'none';
  };
}

function stopAvatarStream() {
  avatarImg.src = '';
  avatarImg.style.display = 'none';
}

// === ウィンドウキャプチャ ===
const captureContainer = document.getElementById('capture-container');
const captureLayers = {};
const captureImgMap = {};      // capture_id -> img element

// IPC直接受信モード（未使用）
let useDirectCapture = false;

// キャプチャインデックスマッピング
const captureIndexToId = {};   // index -> capture_id

// snapshotポーリング（プレビュー用フォールバック）
let snapshotHost = null;
let snapshotTimer = null;
const SNAPSHOT_INTERVAL = 200; // 5fps

function startSnapshotPolling(host) {
  if (snapshotHost === host && snapshotTimer) return;
  snapshotHost = host;
  if (snapshotTimer) clearInterval(snapshotTimer);
  console.log(`[Capture] snapshotポーリング開始: ${host}`);
  snapshotTimer = setInterval(() => {
    for (const [id, img] of Object.entries(captureImgMap)) {
      const url = `http://${snapshotHost}/snapshot/${id}?t=${Date.now()}`;
      img.src = url;
    }
  }, SNAPSHOT_INTERVAL);
}

function stopSnapshotPolling() {
  if (snapshotTimer) { clearInterval(snapshotTimer); snapshotTimer = null; }
}

function addCaptureLayer(id, streamUrl, label, layout) {
  console.log(`[Capture] addCaptureLayer: id=${id}, streamUrl=${streamUrl}, useDirectCapture=${useDirectCapture}`, layout);
  if (captureLayers[id]) removeCaptureLayer(id);
  const div = document.createElement('div');
  div.className = 'capture-layer';
  div.dataset.editable = `capture:${id}`;
  div.dataset.captureId = id;
  applyLayoutToEl(div, layout);

  const labelEl = document.createElement('div');
  labelEl.className = 'edit-label';
  labelEl.textContent = label || id;
  div.appendChild(labelEl);

  const img = document.createElement('img');
  img.alt = label || id;
  div.appendChild(img);

  captureContainer.appendChild(div);
  captureLayers[id] = div;
  captureImgMap[id] = img;

  if (!useDirectCapture && streamUrl) {
    // snapshotポーリングでフレーム受信
    try {
      const httpUrl = new URL(streamUrl);
      startSnapshotPolling(httpUrl.host);
    } catch (e) {}
  }

  setupEditable(div);
}

function removeCaptureLayer(id) {
  const el = captureLayers[id];
  if (el) {
    const img = captureImgMap[id];
    el.remove();
    delete captureLayers[id];
    delete captureImgMap[id];
  }
}

function updateCaptureLayout(id, layout) {
  const el = captureLayers[id];
  if (el) applyLayoutToEl(el, layout);
}

function applyLayoutToEl(el, layout) {
  if (layout.x != null) el.style.left = layout.x + '%';
  if (layout.y != null) el.style.top = layout.y + '%';
  if (layout.width != null) el.style.width = layout.width + '%';
  if (layout.height != null) el.style.height = layout.height + '%';
  if (layout.zIndex != null) el.style.zIndex = layout.zIndex;
  if (layout.visible === false) el.style.display = 'none';
  else el.style.display = '';
}

// === カスタムテキスト ===
const customTextContainer = document.getElementById('custom-text-container');
const customTextLayers = {};

function addCustomTextLayer(id, label, content, layout) {
  if (customTextLayers[id]) removeCustomTextLayer(id);
  const div = document.createElement('div');
  div.className = 'custom-text-layer';
  div.dataset.editable = `customtext:${id}`;
  div.dataset.customTextId = id;
  if (layout) {
    applyLayoutToEl(div, layout);
    if (layout.fontSize != null) div.style.fontSize = layout.fontSize + 'vw';
    if (layout.bgOpacity != null) setBgOpacity(div, layout.bgOpacity);
  }

  const labelEl = document.createElement('div');
  labelEl.className = 'edit-label';
  labelEl.textContent = label || `Text ${id}`;
  div.appendChild(labelEl);

  const textEl = document.createElement('div');
  textEl.className = 'custom-text-content';
  textEl.textContent = content || '';
  div.appendChild(textEl);

  customTextContainer.appendChild(div);
  customTextLayers[id] = div;
  setupEditable(div);
}

function updateCustomTextLayer(id, data) {
  const el = customTextLayers[id];
  if (!el) return;
  if (data.content != null) el.querySelector('.custom-text-content').textContent = data.content;
  if (data.label != null) el.querySelector('.edit-label').textContent = data.label;
  if (data.layout) {
    applyLayoutToEl(el, data.layout);
    if (data.layout.fontSize != null) el.style.fontSize = data.layout.fontSize + 'vw';
    if (data.layout.bgOpacity != null) setBgOpacity(el, data.layout.bgOpacity);
  }
  if (data.fontSize != null) el.style.fontSize = data.fontSize + 'vw';
  if (data.bgOpacity != null) setBgOpacity(el, data.bgOpacity);
}

function removeCustomTextLayer(id) {
  const el = customTextLayers[id];
  if (el) { el.remove(); delete customTextLayers[id]; }
}

// === 編集モード（常時有効） ===
const isEmbedded = new URLSearchParams(location.search).has('embedded') || window.parent !== window;
if (isEmbedded) document.body.classList.add('embedded');
let _saveTimer = null;
let _saving = false;  // editSave中はsettings_updateを無視
let _selectedEditable = null;
const _ctxMenu = document.getElementById('edit-context-menu');
const _zDialog = document.getElementById('zindex-dialog');
const _zdInput = document.getElementById('zd-input');

function getElZIndex(el) {
  return parseInt(el.style.zIndex) || parseInt(getComputedStyle(el).zIndex) || 0;
}

function showContextMenu(el, x, y) {
  hideAll();
  selectEditable(el);
  _selectedEditable = el;
  el.classList.add('selected');
  _ctxMenu.style.left = x + 'px';
  _ctxMenu.style.top = y + 'px';
  _ctxMenu.style.display = 'block';
}

function openZIndexDialog() {
  _ctxMenu.style.display = 'none';
  if (!_selectedEditable) return;
  _zdInput.value = getElZIndex(_selectedEditable);
  // メニューがあった位置に表示
  _zDialog.style.left = _ctxMenu.style.left;
  _zDialog.style.top = _ctxMenu.style.top;
  _zDialog.style.display = 'block';
}

let _editingEl = null;

function selectEditable(el) {
  if (_editingEl && _editingEl !== el) {
    _editingEl.classList.remove('editing');
    if (_editingEl._savedZIndex != null) {
      _editingEl.style.zIndex = _editingEl._savedZIndex;
      delete _editingEl._savedZIndex;
    }
  }
  _editingEl = el;
  el.classList.add('editing');
  el._savedZIndex = el.style.zIndex || getComputedStyle(el).zIndex || '0';
  el.style.zIndex = 9000;
  // 他パーツをイベント透過にして、重なっていても操作可能にする
  document.querySelectorAll('[data-editable]').forEach(other => {
    if (other !== el) other.classList.add('edit-inactive');
    else other.classList.remove('edit-inactive');
  });
}

function deselectEditable() {
  if (_editingEl) {
    _editingEl.classList.remove('editing');
    if (_editingEl._savedZIndex != null) {
      _editingEl.style.zIndex = _editingEl._savedZIndex;
      delete _editingEl._savedZIndex;
    }
    _editingEl = null;
  }
  // 全パーツのedit-inactiveを解除
  document.querySelectorAll('[data-editable]').forEach(el => {
    el.classList.remove('edit-inactive');
  });
}

function hideAll() {
  _ctxMenu.style.display = 'none';
  _zDialog.style.display = 'none';
  if (_selectedEditable) {
    _selectedEditable.classList.remove('selected');
    _selectedEditable = null;
  }
}

function editZIndex(delta) {
  if (!_selectedEditable) return;
  const newZ = Math.max(0, Math.min(100, getElZIndex(_selectedEditable) + delta));
  _selectedEditable.style.zIndex = newZ;
  _zdInput.value = newZ;
  scheduleSave();
}

function setZIndexDirect(val) {
  if (!_selectedEditable) return;
  const newZ = Math.max(0, Math.min(100, parseInt(val) || 0));
  _selectedEditable.style.zIndex = newZ;
  _zdInput.value = newZ;
  scheduleSave();
}

// メニュー/ダイアログ外・パーツ外クリックで閉じる
document.addEventListener('mousedown', (e) => {
  if (!_ctxMenu.contains(e.target) && !_zDialog.contains(e.target)) {
    hideAll();
    const clickedEditable = e.target.closest('[data-editable]');
    // 編集中パーツ自身のクリックはsetupEditableに任せる
    if (clickedEditable && clickedEditable === _editingEl) return;
    // 編集中パーツの外をクリックした → 一旦解除してから下のパーツを探す
    deselectEditable();
    let target = clickedEditable;
    if (!target) {
      // 他のパーツがクリック位置にあるか探す（z-index順で最前面）
      const candidates = [];
      document.querySelectorAll('[data-editable]').forEach(el => {
        const r = el.getBoundingClientRect();
        if (e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom) {
          candidates.push(el);
        }
      });
      if (candidates.length > 0) {
        candidates.sort((a, b) => (parseInt(getComputedStyle(b).zIndex) || 0) - (parseInt(getComputedStyle(a).zIndex) || 0));
        target = candidates[0];
      }
    }
    if (target) {
      selectEditable(target);
      // 選択と同時にドラッグ開始できるようにする
      startDrag(target, e);
    }
  }
});

// === スナップガイドシステム ===
const SNAP_THRESHOLD_PX = 6; // スナップ距離（ピクセル）
const _snapGuides = []; // DOM要素のプール

function ensureSnapGuides(count) {
  while (_snapGuides.length < count) {
    const g = document.createElement('div');
    g.className = 'snap-guide';
    document.body.appendChild(g);
    _snapGuides.push(g);
  }
}
ensureSnapGuides(10);

function hideSnapGuides() {
  _snapGuides.forEach(g => g.style.display = 'none');
}

function getOtherEditableRects(el) {
  const rects = [];
  document.querySelectorAll('[data-editable]').forEach(other => {
    if (other === el || other.style.display === 'none') return;
    const r = other.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) return;
    rects.push({
      left: r.left, right: r.right, top: r.top, bottom: r.bottom,
      centerX: (r.left + r.right) / 2, centerY: (r.top + r.bottom) / 2,
      label: other.dataset.editable,
    });
  });
  return rects;
}

function calcSnapPoints(otherRects, ww, wh) {
  // 画面中央
  const vLines = [{ px: ww / 2, isCenter: true }];
  const hLines = [{ px: wh / 2, isCenter: true }];
  // 他パーツの端と中央
  for (const r of otherRects) {
    vLines.push({ px: r.left }, { px: r.right }, { px: r.centerX });
    hLines.push({ px: r.top }, { px: r.bottom }, { px: r.centerY });
  }
  return { vLines, hLines };
}

function applySnap(edges, lines, threshold) {
  // edges: パーツ側のスナップ候補（左端, 右端, 中央など）のpx配列
  // lines: スナップ先のpx配列（{px, isCenter?}）
  // 最も近い一致を探す
  let bestDelta = Infinity, bestLine = null;
  for (const edge of edges) {
    for (const line of lines) {
      const d = Math.abs(edge - line.px);
      if (d < threshold && d < Math.abs(bestDelta)) {
        bestDelta = edge - line.px;
        bestLine = line;
      }
    }
  }
  return bestLine ? { delta: bestDelta, line: bestLine } : null;
}

function showActiveGuides(snappedV, snappedH) {
  let idx = 0;
  if (snappedV) {
    ensureSnapGuides(idx + 1);
    const g = _snapGuides[idx++];
    g.className = 'snap-guide vertical' + (snappedV.line.isCenter ? ' center' : '');
    g.style.left = snappedV.line.px + 'px';
    g.style.display = 'block';
  }
  if (snappedH) {
    ensureSnapGuides(idx + 1);
    const g = _snapGuides[idx++];
    g.className = 'snap-guide horizontal' + (snappedH.line.isCenter ? ' center' : '');
    g.style.top = snappedH.line.px + 'px';
    g.style.display = 'block';
  }
  for (let i = idx; i < _snapGuides.length; i++) {
    _snapGuides[i].style.display = 'none';
  }
}

function startDrag(el, e) {
  el.classList.add('dragging');
  const startX = e.clientX, startY = e.clientY;
  // getBoundingClientRect()はtransform適用後の実際の表示位置を返す
  const rect = el.getBoundingClientRect();
  const origVisualLeft = rect.left, origVisualTop = rect.top;
  const elW = rect.width, elH = rect.height;
  let didDrag = false;
  const otherRects = getOtherEditableRects(el);

  function onMove(e) {
    didDrag = true;
    const ww = window.innerWidth, wh = window.innerHeight;
    let newLeft = origVisualLeft + e.clientX - startX;
    let newTop = origVisualTop + e.clientY - startY;

    const { vLines, hLines } = calcSnapPoints(otherRects, ww, wh);
    // パーツの左端、右端、中央をスナップ候補に
    const vEdges = [newLeft, newLeft + elW, newLeft + elW / 2];
    const hEdges = [newTop, newTop + elH, newTop + elH / 2];

    const snappedV = applySnap(vEdges, vLines, SNAP_THRESHOLD_PX);
    const snappedH = applySnap(hEdges, hLines, SNAP_THRESHOLD_PX);

    if (snappedV) newLeft -= snappedV.delta;
    if (snappedH) newTop -= snappedH.delta;

    el.style.left = (newLeft / ww * 100) + '%';
    el.style.top = (newTop / wh * 100) + '%';
    el.style.transform = 'none';

    showActiveGuides(snappedV, snappedH);
  }
  function onUp() {
    el.classList.remove('dragging');
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup', onUp);
    hideSnapGuides();
    if (didDrag) editSave();
  }
  document.addEventListener('mousemove', onMove);
  document.addEventListener('mouseup', onUp);
}

function setupEditable(el) {
  if (!el.querySelector('.edit-label')) {
    const label = document.createElement('div');
    label.className = 'edit-label';
    label.textContent = el.dataset.editable;
    el.appendChild(label);
  }
  if (!el.querySelector('.resize-handle')) {
    for (const dir of ['se', 'sw', 'ne', 'nw', 'n', 's', 'e', 'w']) {
      const handle = document.createElement('div');
      handle.className = 'resize-handle ' + dir;
      el.appendChild(handle);
    }
  }

  el.addEventListener('contextmenu', (e) => {
    e.preventDefault();
    showContextMenu(el, e.clientX, e.clientY);
  });

  el.addEventListener('mousedown', (e) => {
    if (e.target.classList.contains('resize-handle')) return;
    if (e.button !== 0) return;
    e.preventDefault();
    e.stopPropagation();

    if (!el.classList.contains('editing')) {
      selectEditable(el);
    }
    startDrag(el, e);
  });

  el.querySelectorAll('.resize-handle').forEach(handle => {
    handle.addEventListener('mousedown', (e) => {
      e.preventDefault(); e.stopPropagation();
      const startX = e.clientX, startY = e.clientY;
      const origW = el.offsetWidth, origH = el.offsetHeight;
      const origLeft = el.offsetLeft, origTop = el.offsetTop;
      // どの方向にリサイズするか判定
      const hc = handle.classList;
      const isLeft = hc.contains('sw') || hc.contains('nw') || hc.contains('w');
      const isRight = hc.contains('se') || hc.contains('ne') || hc.contains('e');
      const isTop = hc.contains('ne') || hc.contains('nw') || hc.contains('n');
      const isBottom = hc.contains('se') || hc.contains('sw') || hc.contains('s');
      const resizeH = isLeft || isRight;
      const resizeV = isTop || isBottom;
      const otherRects = getOtherEditableRects(el);

      function onMove(e) {
        const dx = e.clientX - startX, dy = e.clientY - startY;
        const ww = window.innerWidth, wh = window.innerHeight;
        let newLeft = origLeft, newTop = origTop;
        let newW = origW, newH = origH;

        if (resizeH) {
          if (isLeft) { newW = origW - dx; newLeft = origLeft + dx; }
          else { newW = origW + dx; }
        }
        if (resizeV) {
          if (isTop) { newH = origH - dy; newTop = origTop + dy; }
          else { newH = origH + dy; }
        }

        // リサイズ中の端をスナップ
        const { vLines, hLines } = calcSnapPoints(otherRects, ww, wh);
        const vEdges = resizeH ? (isLeft ? [newLeft] : [newLeft + newW]) : [];
        if (resizeH) vEdges.push(newLeft + newW / 2);
        const hEdges = resizeV ? (isTop ? [newTop] : [newTop + newH]) : [];
        if (resizeV) hEdges.push(newTop + newH / 2);

        const snappedV = resizeH ? applySnap(vEdges, vLines, SNAP_THRESHOLD_PX) : null;
        const snappedH = resizeV ? applySnap(hEdges, hLines, SNAP_THRESHOLD_PX) : null;

        if (snappedV) {
          if (isLeft) { newLeft -= snappedV.delta; newW += snappedV.delta; }
          else { newW -= snappedV.delta; }
        }
        if (snappedH) {
          if (isTop) { newTop -= snappedH.delta; newH += snappedH.delta; }
          else { newH -= snappedH.delta; }
        }

        if (resizeH) el.style.width = (newW / ww * 100) + '%';
        if (resizeV) el.style.height = (newH / wh * 100) + '%';
        if (isLeft) { el.style.left = (newLeft / ww * 100) + '%'; el.style.transform = 'none'; }
        if (isTop) { el.style.top = (newTop / wh * 100) + '%'; el.style.transform = 'none'; }

        showActiveGuides(snappedV, snappedH);
      }
      function onUp() {
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
        hideSnapGuides();
        editSave();
      }
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    });
  });
}

function scheduleSave() {
  clearTimeout(_saveTimer);
  _saveTimer = setTimeout(editSave, 500);
}

function getRealZIndex(el, fallback) {
  // 編集中はz-index=9000なので、保存した元の値を返す
  if (el._savedZIndex != null) return parseInt(el._savedZIndex) || fallback;
  const z = parseInt(el.style.zIndex) || fallback;
  // 編集用の一時z-index(9000)は保存しない
  return z >= 9000 ? fallback : z;
}

async function editSave() {
  _saving = true;
  const overlaySettings = {};

  // ITEM_REGISTRYベースの共通レイアウト保存
  for (const item of ITEM_REGISTRY) {
    const el = document.getElementById(item.id);
    if (!el) continue;
    const data = {
      positionX: parseFloat(el.style.left) || 0,
      positionY: parseFloat(el.style.top) || 0,
      zIndex: getRealZIndex(el, item.defaultZ),
    };
    if (item.saveVisible) {
      data.visible = el.style.display !== 'none' ? 1 : 0;
    }
    if (item.hasSize) {
      const w = parseFloat(el.style.width);
      if (!isNaN(w)) data.width = w;
      const h = parseFloat(el.style.height);
      if (!isNaN(h) && el.style.height !== 'auto') data.height = h;
    }
    overlaySettings[item.prefix] = data;
  }

  try {
    await fetch('/api/overlay/settings', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(overlaySettings),
    });
  } catch (e) { console.log('レイアウト保存エラー:', e.message); }

  // capture/custom-text は個別APIに保存（既存ロジック維持）
  for (const [id, el] of Object.entries(captureLayers)) {
    const layout = {
      x: parseFloat(el.style.left) || 0,
      y: parseFloat(el.style.top) || 0,
      width: parseFloat(el.style.width) || 40,
      height: parseFloat(el.style.height) || 50,
      zIndex: getRealZIndex(el, 10),
    };
    try {
      await fetch(`/api/capture/${id}/layout`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(layout),
      });
    } catch (e) {}
  }

  for (const [id, el] of Object.entries(customTextLayers)) {
    const layout = {
      x: parseFloat(el.style.left) || 0,
      y: parseFloat(el.style.top) || 0,
      width: parseFloat(el.style.width) || 20,
      height: parseFloat(el.style.height) || 15,
      zIndex: getRealZIndex(el, 15),
    };
    try {
      await fetch(`/api/overlay/custom-texts/${id}/layout`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(layout),
      });
    } catch (e) {}
  }
  _saving = false;
}

function initEditMode() {
  document.querySelectorAll('[data-editable]').forEach(setupEditable);

  // カーソルキーで選択中の要素を微調整移動
  document.addEventListener('keydown', (e) => {
    if (!_editingEl) return;
    const moves = { ArrowLeft: [-1,0], ArrowRight: [1,0], ArrowUp: [0,-1], ArrowDown: [0,1] };
    const dir = moves[e.key];
    if (!dir) return;
    e.preventDefault();
    const step = e.shiftKey ? 1.0 : 0.1; // %単位
    const curLeft = parseFloat(_editingEl.style.left) || 0;
    const curTop = parseFloat(_editingEl.style.top) || 0;
    _editingEl.style.left = (curLeft + dir[0] * step) + '%';
    _editingEl.style.top = (curTop + dir[1] * step) + '%';
    _editingEl.style.transform = 'none';
    scheduleSave();
  });
}

// === 初期化 ===
async function init() {
  // オーバーレイ設定読み込み
  try {
    const res = await fetch('/api/overlay/settings');
    const s = await res.json();
    applySettings(s);
  } catch (e) {
    console.log('設定読み込みスキップ:', e.message);
  }

  // 音量設定読み込み
  try {
    const res = await fetch('/api/broadcast/volumes');
    const v = await res.json();
    if (v.master != null) volumes.master = v.master;
    if (v.tts != null) volumes.tts = v.tts;
    if (v.bgm != null) volumes.bgm = v.bgm;
    applyVolume();
  } catch (e) {
    console.log('音量設定読み込みスキップ:', e.message);
  }

  // 配信状態を取得（リップシンク遅延切替用）
  try {
    const res = await fetch('/api/broadcast/status');
    const st = await res.json();
    _isStreaming = !!st.streaming;
    console.log('[Sync] init streaming:', _isStreaming);
  } catch (e) {}

  // アバターストリーム復元
  try {
    const res = await fetch('/api/broadcast/avatar');
    const av = await res.json();
    if (av.url) setAvatarStream(av.url);
  } catch (e) {}

  // キャプチャソース読み込み
  try {
    const res = await fetch('/api/capture/sources');
    const sources = await res.json();
    for (const s of sources) {
      addCaptureLayer(s.id, s.stream_url, s.label || s.name || s.id, s.layout);
    }
  } catch (e) { console.log('キャプチャ読み込みスキップ:', e.message); }

  // カスタムテキスト読み込み
  try {
    const res = await fetch('/api/overlay/custom-texts');
    const items = await res.json();
    for (const item of items) {
      addCustomTextLayer(item.id, item.label, item.content, item.layout);
    }
  } catch (e) { console.log('カスタムテキスト読み込みスキップ:', e.message); }

  // バージョン情報取得
  try {
    const res = await fetch('/api/status');
    const st = await res.json();
    window._versionInfo = st;
    _applyVersionFormat();
  } catch (e) {}

  await loadTodo();
  await loadTopicPanel();
  // TODOはWebSocket pushで更新されるためポーリング不要
  setInterval(loadTopicPanel, 15000);
  connectWS();

  initEditMode();
}

init();
