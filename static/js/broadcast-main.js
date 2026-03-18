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
  const avatarArea = document.getElementById('avatar-area');
  if (s.avatar) {
    if (s.avatar.positionX != null) avatarArea.style.left = s.avatar.positionX + '%';
    if (s.avatar.positionY != null) avatarArea.style.top = s.avatar.positionY + '%';
    if (s.avatar.width != null) avatarArea.style.width = s.avatar.width + '%';
    if (s.avatar.height != null) avatarArea.style.height = s.avatar.height + '%';
    if (s.avatar.zIndex != null) avatarArea.style.zIndex = s.avatar.zIndex;
    if (window.dispatchEvent) window.dispatchEvent(new Event('resize'));
  }
  if (s.lighting) {
    if (window.avatarLighting) {
      _applyLighting(s.lighting);
    } else {
      // module script未ロード → pending保存（module側で適用）
      window._pendingLighting = s.lighting;
    }
  }
  if (s.subtitle) {
    if (s.subtitle.bottom != null) {
      subtitleEl.style.bottom = s.subtitle.bottom + '%';
      subtitleEl.style.top = '';  // ドラッグで設定されたtopをクリア（bottomと競合するため）
      subtitleEl.style.left = '50%';
      subtitleEl.style.transform = 'translateX(-50%)';
    }
    if (s.subtitle.fontSize != null) subtitleEl.querySelector('.response').style.fontSize = s.subtitle.fontSize + 'vw';
    if (s.subtitle.maxWidth != null) subtitleEl.style.maxWidth = s.subtitle.maxWidth + '%';
    if (s.subtitle.fadeDuration != null) subtitleEl.dataset.fadeDuration = s.subtitle.fadeDuration;
    if (s.subtitle.bgOpacity != null) setBgOpacity(subtitleEl, s.subtitle.bgOpacity);
    if (s.subtitle.zIndex != null) subtitleEl.style.zIndex = s.subtitle.zIndex;
  }
  if (s.todo) {
    todoSettings = s.todo;
    if (s.todo.width != null) todoPanelEl.style.width = s.todo.width + '%';
    if (s.todo.height != null) {
      todoPanelEl.style.height = s.todo.height + '%';
      todoPanelEl.style.maxHeight = 'none';
      todoPanelEl.style.overflow = 'hidden';
    }
    if (s.todo.positionX != null) {
      todoPanelEl.style.left = s.todo.positionX + '%';
      todoPanelEl.style.transform = 'none';
    }
    if (s.todo.positionY != null) {
      todoPanelEl.style.top = s.todo.positionY + '%';
    }
    if (s.todo.fontSize != null) {
      todoPanelEl.querySelectorAll('.todo-item').forEach(el => el.style.fontSize = s.todo.fontSize + 'vw');
    }
    if (s.todo.titleFontSize != null) todoPanelEl.querySelector('.todo-title').style.fontSize = s.todo.titleFontSize + 'vw';
    if (s.todo.bgOpacity != null) setBgOpacity(todoPanelEl, s.todo.bgOpacity);
    if (s.todo.zIndex != null) todoPanelEl.style.zIndex = s.todo.zIndex;
    loadTodo();
  }
  if (s.topic) {
    if (s.topic.positionX != null) topicPanelEl.style.left = s.topic.positionX + '%';
    if (s.topic.positionY != null) topicPanelEl.style.top = s.topic.positionY + '%';
    if (s.topic.maxWidth != null) topicPanelEl.style.maxWidth = s.topic.maxWidth + '%';
    if (s.topic.titleFontSize != null) {
      document.getElementById('topic-title-text').style.fontSize = s.topic.titleFontSize + 'vw';
    }
    if (s.topic.bgOpacity != null) setBgOpacity(topicPanelEl, s.topic.bgOpacity);
    if (s.topic.zIndex != null) topicPanelEl.style.zIndex = s.topic.zIndex;
  }
  if (s.version) {
    const vp = document.getElementById('version-panel');
    if (vp) {
      if (s.version.visible != null) vp.style.display = s.version.visible ? 'block' : 'none';
      if (s.version.positionX != null) vp.style.left = s.version.positionX + '%';
      if (s.version.positionY != null) vp.style.top = s.version.positionY + '%';
      if (s.version.fontSize != null) document.getElementById('version-text').style.fontSize = s.version.fontSize + 'vw';
      const vText = document.getElementById('version-text');
      if (s.version.strokeSize != null || s.version.strokeOpacity != null) {
        const size = s.version.strokeSize ?? parseFloat(vText.dataset.strokeSize || 3);
        const opacity = s.version.strokeOpacity ?? parseFloat(vText.dataset.strokeOpacity || 0.8);
        vText.dataset.strokeSize = size;
        vText.dataset.strokeOpacity = opacity;
        vText.style.textShadow = `0 0 ${size}px rgba(0,0,0,${opacity}), 0 0 ${size}px rgba(0,0,0,${opacity})`;
      }
      if (s.version.bgOpacity != null) setBgOpacity(vp, s.version.bgOpacity);
      if (s.version.zIndex != null) vp.style.zIndex = s.version.zIndex;
    }
  }
  if (s.sync) {
    if (s.sync.lipsyncDelay != null) {
      _lipsyncDelay = s.sync.lipsyncDelay;
      // C#パネルに同期通知
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
    for (const corner of ['se', 'sw', 'ne', 'nw']) {
      const handle = document.createElement('div');
      handle.className = 'resize-handle ' + corner;
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
      const isLeft = handle.classList.contains('sw') || handle.classList.contains('nw');
      const isTop = handle.classList.contains('ne') || handle.classList.contains('nw');
      const otherRects = getOtherEditableRects(el);

      function onMove(e) {
        const dx = e.clientX - startX, dy = e.clientY - startY;
        const ww = window.innerWidth, wh = window.innerHeight;
        let newLeft = origLeft, newTop = origTop;
        let newW = origW, newH = origH;

        if (isLeft) {
          newW = origW - dx; newLeft = origLeft + dx;
        } else {
          newW = origW + dx;
        }
        if (isTop) {
          newH = origH - dy; newTop = origTop + dy;
        } else {
          newH = origH + dy;
        }

        // リサイズ中の端をスナップ
        const { vLines, hLines } = calcSnapPoints(otherRects, ww, wh);
        // 動く辺をスナップ候補に
        const vEdges = isLeft ? [newLeft] : [newLeft + newW];
        // 中央もスナップ候補
        vEdges.push(newLeft + newW / 2);
        const hEdges = isTop ? [newTop] : [newTop + newH];
        hEdges.push(newTop + newH / 2);

        const snappedV = applySnap(vEdges, vLines, SNAP_THRESHOLD_PX);
        const snappedH = applySnap(hEdges, hLines, SNAP_THRESHOLD_PX);

        if (snappedV) {
          if (isLeft) { newLeft -= snappedV.delta; newW += snappedV.delta; }
          else { newW -= snappedV.delta; }
        }
        if (snappedH) {
          if (isTop) { newTop -= snappedH.delta; newH += snappedH.delta; }
          else { newH -= snappedH.delta; }
        }

        el.style.width = (newW / ww * 100) + '%';
        el.style.height = (newH / wh * 100) + '%';
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
  const avatarArea = document.getElementById('avatar-area');
  overlaySettings.avatar = {
    positionX: parseFloat(avatarArea.style.left) || 46.5,
    positionY: parseFloat(avatarArea.style.top) || 24.3,
    width: parseFloat(avatarArea.style.width) || 53.5,
    height: parseFloat(avatarArea.style.height) || 75.7,
    zIndex: getRealZIndex(avatarArea, 5),
  };
  overlaySettings.subtitle = {
    zIndex: getRealZIndex(subtitleEl, 20),
  };
  overlaySettings.todo = {
    positionX: parseFloat(todoPanelEl.style.left) || 36,
    positionY: parseFloat(todoPanelEl.style.top) || 2,
    width: parseFloat(todoPanelEl.style.width) || 28,
    zIndex: getRealZIndex(todoPanelEl, 20),
  };
  if (todoPanelEl.style.height && todoPanelEl.style.height !== 'auto') {
    overlaySettings.todo.height = parseFloat(todoPanelEl.style.height);
  }
  overlaySettings.topic = {
    positionX: parseFloat(topicPanelEl.style.left) || 1.04,
    positionY: parseFloat(topicPanelEl.style.top) || 1.85,
    zIndex: getRealZIndex(topicPanelEl, 20),
  };
  const vp = document.getElementById('version-panel');
  if (vp) {
    overlaySettings.version = {
      visible: vp.style.display !== 'none' ? 1 : 0,
      positionX: parseFloat(vp.style.left) || 1,
      positionY: parseFloat(vp.style.top) || 95,
      zIndex: getRealZIndex(vp, 10),
    };
  }

  try {
    await fetch('/api/overlay/settings', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(overlaySettings),
    });
  } catch (e) { console.log('レイアウト保存エラー:', e.message); }

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
  _saving = false;
}

function initEditMode() {
  document.querySelectorAll('[data-editable]').forEach(setupEditable);
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

  // バージョン情報取得
  try {
    const res = await fetch('/api/status');
    const st = await res.json();
    const vEl = document.getElementById('version-text');
    if (vEl && st.version) {
      let text = `v${st.version}`;
      if (st.updated_at) {
        const d = new Date(st.updated_at);
        text += ` (${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')})`;
      }
      vEl.textContent = text;
    }
  } catch (e) {}

  await loadTodo();
  await loadTopicPanel();
  // TODOはWebSocket pushで更新されるためポーリング不要
  setInterval(loadTopicPanel, 15000);
  connectWS();

  initEditMode();
}

init();
