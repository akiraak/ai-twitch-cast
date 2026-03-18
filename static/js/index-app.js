let _volTimer = null;
const TAB_NAMES = ['layout', 'character', 'sound', 'topic', 'devstream', 'db', 'files', 'debug', 'todo'];

function switchTab(name, el) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  if (!el) {
    const idx = TAB_NAMES.indexOf(name);
    el = document.querySelectorAll('.tab')[idx];
  }
  el.classList.add('active');
  location.hash = name;
  if (name === 'db') loadDbTables();
  if (name === 'character') loadLanguageModes();
  if (name === 'sound') loadBgmTracks();
  if (name === 'topic') { loadTopicStatus(); loadTopicScripts(); }
  if (name === 'files') loadFilesList();
  if (name === 'debug') { loadScreenshots(); }
  if (name === 'todo') loadTodoList();
  if (name === 'devstream') loadDevstream();
  if (name === 'layout') loadCustomTexts();
}


function log(msg) {
  console.log(msg);
}

function showToast(msg, type = 'success', duration = 5000) {
  const el = document.createElement('div');
  el.className = 'toast ' + type;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), duration);
}

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// 汎用確認ダイアログ（Promise を返す）
function showConfirm(message, { title = '確認', okLabel = 'OK', cancelLabel = 'キャンセル', danger = false } = {}) {
  return new Promise(resolve => {
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    const btnClass = danger ? 'danger' : 'primary';
    overlay.innerHTML = `<div class="modal-box">
      <h3>${esc(title)}</h3>
      <p>${esc(message)}</p>
      <div class="btn-group">
        <button class="${btnClass}" data-action="ok">${esc(okLabel)}</button>
        <button class="secondary" data-action="cancel">${esc(cancelLabel)}</button>
      </div>
    </div>`;
    overlay.addEventListener('click', e => {
      const action = e.target.dataset?.action;
      if (action === 'ok') { overlay.remove(); resolve(true); }
      else if (action === 'cancel') { overlay.remove(); resolve(false); }
    });
    document.body.appendChild(overlay);
  });
}

function setStatus(id, msg, type) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = msg;
  el.style.color = type === 'err' ? '#c62828' : type === 'ok' ? '#2e7d32' : '#6a5590';
}

// api() は /static/js/lib/api-client.js から読み込み済み
// index.html 用ラッパー: log + showToast 付き
const _apiBase = api;
api = (method, url, body) => _apiBase(method, url, body, {
  onError: msg => showToast(msg, 'error'),
  onLog: msg => log(msg),
});

// --- 配信制御 ---
async function doGoLive() {
  log('Go Live...');
  showToast('配信準備中...', 'success', 10000);
  const res = await api('POST', '/api/broadcast/go-live');
  if (res?.ok) showToast('配信開始', 'success');
  else showToast(res?.detail || '配信開始失敗', 'error');
  refreshStatus();
}

async function doStop() {
  log('配信停止...');
  const res = await api('POST', '/api/broadcast/stop');
  if (res?.ok) showToast('配信停止', 'success');
  refreshStatus();
}

// --- 音量 ---
function onVolume(source, slider) {
  const pct = slider.value;
  document.getElementById(`vol-${source}-pct`).textContent = pct + '%';
  clearTimeout(_volTimer);
  _volTimer = setTimeout(() => {
    api('POST', '/api/broadcast/volume', { source, volume: pct / 100 });
  }, 150);
}

function onSyncDelay(slider) {
  document.getElementById('sync-delay-pct').textContent = slider.value + 'ms';
  clearTimeout(_syncDelayTimer);
  _syncDelayTimer = setTimeout(() => {
    api('POST', '/api/overlay/settings', { sync: { lipsyncDelay: parseInt(slider.value) } });
  }, 150);
}
let _syncDelayTimer;

async function loadVolumes() {
  try {
    const data = await (await fetch('/api/broadcast/volume')).json();
    for (const key of ['master', 'tts', 'bgm']) {
      const slider = document.getElementById(`vol-${key}`);
      if (document.activeElement === slider) continue;
      const val = data[key] ?? 1.0;
      const pct = Math.round(val * 100);
      slider.value = pct;
      document.getElementById(`vol-${key}-pct`).textContent = pct + '%';
    }
  } catch (e) {}
  // syncDelay読み込み
  try {
    const s = await (await fetch('/api/overlay/settings')).json();
    const delay = s?.sync?.lipsyncDelay ?? 500;
    document.getElementById('sync-delay').value = delay;
    document.getElementById('sync-delay-pct').textContent = delay + 'ms';
  } catch (e) {}
}

// --- ステータス更新 ---
async function refreshStatus() {
  try {
    const data = await (await fetch('/api/broadcast/status')).json();

    const streaming = data.streaming;
    document.getElementById('sb-stream').className = 'status-dot ' + (streaming ? 'live' : 'off');
    document.getElementById('sb-stream-text').textContent = streaming ? '配信中' : '停止中';
    document.getElementById('status-bar').classList.toggle('streaming', streaming);
  } catch (e) {}
  // バージョン表示（初回のみ）
  const verEl = document.getElementById('app-version');
  if (verEl && !verEl.textContent) {
    try {
      const st = await (await fetch('/api/status')).json();
      let text = st.version ? `v${st.version}` : '';
      if (st.updated_at) {
        const d = new Date(st.updated_at);
        text += ` (${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')})`;
      }
      verEl.textContent = text;
    } catch (e) {}
  }
  loadVolumes();
}

// --- ウィンドウキャプチャ ---
async function captureRefreshSources() {
  try {
    const saved = await (await fetch('/api/capture/saved')).json();
    _renderCaptureList(saved, []);
    const active = await (await fetch('/api/capture/sources')).json().catch(() => []);
    _renderCaptureList(saved, active);
  } catch (e) {}
}

function _renderCaptureList(saved, active) {
  const el = document.getElementById('capture-list');
  if (!saved.length) {
    el.innerHTML = '<span style="color:#9a88b5;">保存済みウィンドウなし</span>';
    return;
  }
  const activeByName = {};
  for (const a of active) {
    if (a.name) activeByName[a.name] = a;
  }
  // インデックスベースでイベント管理（ウィンドウ名に特殊文字があってもOK）
  _capSavedList = saved;
  _capActiveByName = activeByName;
  el.innerHTML = saved.map((s, idx) => {
    const wname = s.window_name || '';
    const a = activeByName[wname];
    const isActive = !!a;
    const l = (isActive ? a.layout : s.layout) || {};
    const vis = l.visible !== false;
    const label = escHtml(s.label || wname);
    const capId = isActive ? a.id : '';
    let buttons = '';
    if (isActive) {
      buttons += vis
        ? `<button class="cap-btn-vis" data-action="toggle-vis" data-idx="${idx}">&#x1f441; 表示</button>`
        : `<button class="cap-btn-vis hidden" data-action="toggle-vis" data-idx="${idx}">&#x1f441;&#xfe0f; 非表示</button>`;
    }
    buttons += `<button class="danger" style="padding:2px 8px; font-size:0.7rem;" data-action="delete" data-idx="${idx}">削除</button>`;
    const lr = (prop, min, max, step, val) =>
      `<div class="layout-row"><span class="layout-label">${prop === 'zIndex' ? 'Z順序' : prop === 'x' ? 'X位置 (%)' : prop === 'y' ? 'Y位置 (%)' : prop === 'width' ? '幅 (%)' : '高さ (%)'}</span><input type="range" class="vol-slider cap-layout-input" min="${min}" max="${max}" step="${step}" value="${val}" data-idx="${idx}" data-prop="${prop}"><input type="number" class="layout-num cap-layout-input" min="${min}" max="${max}" step="${step}" value="${val}" data-idx="${idx}" data-prop="${prop}"></div>`;
    const layoutHtml = `<div class="cap-item-layout">
      ${lr('x', 0, 100, 0.5, l.x ?? 5)}
      ${lr('y', 0, 100, 0.5, l.y ?? 10)}
      ${lr('width', 5, 100, 0.5, l.width ?? 40)}
      ${lr('height', 5, 100, 0.5, l.height ?? 50)}
      ${lr('zIndex', 0, 100, 1, l.zIndex ?? 10)}
    </div>`;
    return `<div class="cap-item ${isActive ? 'active' : 'inactive'}">
      <div class="cap-item-header">
        <span class="cap-item-label">${label}</span>
        ${buttons}
      </div>
      ${layoutHtml}
    </div>`;
  }).join('');
  // イベント委譲
  el.onclick = _capListClick;
  el.oninput = _capListInput;
}

let _capSavedList = [];
let _capActiveByName = {};
let _capLayoutTimers = {};

async function _capListClick(e) {
  const btn = e.target.closest('[data-action]');
  if (!btn) return;
  const idx = parseInt(btn.dataset.idx);
  const s = _capSavedList[idx];
  if (!s) return;
  const wname = s.window_name;
  const a = _capActiveByName[wname];
  if (btn.dataset.action === 'toggle-vis' && a) {
    const vis = (a.layout || {}).visible !== false;
    await api('POST', `/api/capture/${a.id}/layout`, { visible: !vis });
    captureRefreshSources();
  } else if (btn.dataset.action === 'delete') {
    if (!await showConfirm(`「${wname}」を削除しますか？`, { title: '削除', okLabel: '削除', danger: true })) return;
    await fetch('/api/capture/saved', { method: 'DELETE', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ window_name: wname }) });
    captureRefreshSources();
  }
}

function _capListInput(e) {
  const input = e.target;
  if (!input.classList.contains('cap-layout-input')) return;
  const idx = parseInt(input.dataset.idx);
  const prop = input.dataset.prop;
  const val = parseFloat(input.value);
  const s = _capSavedList[idx];
  if (!s) return;
  const wname = s.window_name;
  const a = _capActiveByName[wname];
  // 同じ行のスライダー/数値入力を同期
  const row = input.closest('.layout-row');
  const other = row.querySelector(input.type === 'range' ? '.layout-num' : 'input[type=range]');
  if (other) other.value = val;
  const key = (a ? a.id : '') + wname;
  clearTimeout(_capLayoutTimers[key]);
  _capLayoutTimers[key] = setTimeout(() => {
    if (a) {
      api('POST', `/api/capture/${a.id}/layout`, { [prop]: val });
    } else {
      api('POST', '/api/capture/saved/layout', { window_name: wname, [prop]: val });
    }
  }, 200);
}



async function captureRemove(id) {
  await fetch(`/api/capture/${id}`, { method: 'DELETE' });
  captureRefreshSources();
}

// --- カスタムテキスト ---

async function loadCustomTexts() {
  try {
    const items = await (await fetch('/api/overlay/custom-texts')).json();
    _renderCustomTextList(items);
  } catch (e) {}
}

function _renderCustomTextList(items) {
  const el = document.getElementById('custom-text-list');
  if (!items.length) {
    el.innerHTML = '<span style="color:#9a88b5;">カスタムテキストなし</span>';
    return;
  }
  el.innerHTML = items.map(item => {
    const l = item.layout || {};
    return `<div style="border:1px solid #d0c0e8; border-radius:6px; padding:10px; margin-bottom:8px;">
      <div style="display:flex; align-items:center; gap:8px; margin-bottom:6px;">
        <input type="text" value="${escHtml(item.label)}" placeholder="ラベル"
          style="flex:1; padding:2px 6px; font-size:0.85rem; border:1px solid #ccc; border-radius:4px;"
          onchange="updateCustomText(${item.id}, {label: this.value})">
        <button onclick="deleteCustomText(${item.id})"
          style="padding:2px 8px; background:#c62828; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:0.75rem;">削除</button>
      </div>
      <textarea rows="2" style="width:100%; box-sizing:border-box; padding:4px 6px; font-size:0.8rem; border:1px solid #ccc; border-radius:4px; resize:vertical;"
        onchange="updateCustomText(${item.id}, {content: this.value})">${escHtml(item.content)}</textarea>
      <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:6px; margin-top:6px; font-size:0.75rem;">
        <label>文字サイズ <input type="number" value="${l.fontSize ?? 1.2}" min="0.3" max="5" step="0.1"
          style="width:50px;" onchange="updateCustomText(${item.id}, {fontSize: parseFloat(this.value)})"> vw</label>
        <label>背景透明度 <input type="number" value="${l.bgOpacity ?? 0.85}" min="0" max="1" step="0.05"
          style="width:50px;" onchange="updateCustomText(${item.id}, {bgOpacity: parseFloat(this.value)})"></label>
        <label>Z順序 <input type="number" value="${l.zIndex ?? 15}" min="0" max="100" step="1"
          style="width:50px;" onchange="updateCustomText(${item.id}, {zIndex: parseInt(this.value)})"></label>
      </div>
    </div>`;
  }).join('');
}

async function addCustomText() {
  await api('POST', '/api/overlay/custom-texts', { label: '新規テキスト', content: '' });
  showToast('テキスト追加', 'success');
  loadCustomTexts();
}

async function updateCustomText(id, changes) {
  await api('PUT', `/api/overlay/custom-texts/${id}`, changes);
}

async function deleteCustomText(id) {
  if (!await showConfirm('このテキストアイテムを削除しますか？', { title: '削除', okLabel: '削除', danger: true })) return;
  await api('DELETE', `/api/overlay/custom-texts/${id}`);
  showToast('テキスト削除', 'success');
  loadCustomTexts();
}

// --- キャラクター設定 ---
let _charEmotions = {};
let _charBlendshapes = {};

async function loadCharacter() {
  try {
    const data = await (await fetch('/api/character')).json();
    document.getElementById('char-name').value = data.name || '';
    document.getElementById('char-prompt').value = data.system_prompt || '';
    renderRules(data.rules || []);
    _charEmotions = data.emotions || {};
    _charBlendshapes = data.emotion_blendshapes || {};
    renderEmotions();
    renderBlendshapes();
    document.getElementById('char-status').textContent = '読み込みました';
  } catch (e) {
    document.getElementById('char-status').textContent = 'エラー: ' + e.message;
  }
}

function renderRules(rules) {
  const el = document.getElementById('char-rules');
  el.innerHTML = '';
  rules.forEach((rule) => {
    const row = document.createElement('div');
    row.style.cssText = 'display:flex; gap:4px; margin-bottom:3px;';
    row.innerHTML = `<input type="text" class="char-rule text-input" value="${escHtml(rule)}" style="flex:1; padding:2px 6px; font-size:0.8rem;">
      <button class="danger" style="font-size:0.7rem; padding:2px 6px;" onclick="this.parentElement.remove()">×</button>`;
    el.appendChild(row);
  });
}

function addRule() {
  const el = document.getElementById('char-rules');
  const row = document.createElement('div');
  row.style.cssText = 'display:flex; gap:4px; margin-bottom:3px;';
  row.innerHTML = `<input type="text" class="char-rule text-input" value="" style="flex:1; padding:2px 6px; font-size:0.8rem;">
    <button class="danger" style="font-size:0.7rem; padding:2px 6px;" onclick="this.parentElement.remove()">×</button>`;
  el.appendChild(row);
}

function collectRules() {
  return [...document.querySelectorAll('.char-rule')].map(el => el.value).filter(v => v.trim());
}

function renderEmotions() {
  const el = document.getElementById('char-emotions');
  el.innerHTML = '';
  for (const [key, desc] of Object.entries(_charEmotions)) {
    const row = document.createElement('div');
    row.style.cssText = 'display:flex; gap:4px; margin-bottom:3px;';
    row.innerHTML = `<input type="text" class="emo-key text-input" value="${escHtml(key)}" style="width:70px; padding:2px 6px; font-size:0.8rem;" placeholder="キー">
      <input type="text" class="emo-desc text-input" value="${escHtml(desc)}" style="flex:1; padding:2px 6px; font-size:0.8rem;" placeholder="説明">
      <button class="danger" style="font-size:0.7rem; padding:2px 6px;" onclick="this.parentElement.remove()">×</button>`;
    el.appendChild(row);
  }
}

function addEmotion() {
  const el = document.getElementById('char-emotions');
  const row = document.createElement('div');
  row.style.cssText = 'display:flex; gap:4px; margin-bottom:3px;';
  row.innerHTML = `<input type="text" class="emo-key text-input" value="" style="width:70px; padding:2px 6px; font-size:0.8rem;" placeholder="キー">
    <input type="text" class="emo-desc text-input" value="" style="flex:1; padding:2px 6px; font-size:0.8rem;" placeholder="説明">
    <button class="danger" style="font-size:0.7rem; padding:2px 6px;" onclick="this.parentElement.remove()">×</button>`;
  el.appendChild(row);
}

function collectEmotions() {
  const result = {};
  const keys = document.querySelectorAll('.emo-key');
  const descs = document.querySelectorAll('.emo-desc');
  keys.forEach((k, i) => {
    if (k.value.trim()) result[k.value.trim()] = descs[i].value;
  });
  return result;
}

function renderBlendshapes() {
  const el = document.getElementById('char-blendshapes');
  el.innerHTML = '';
  for (const [emotion, shapes] of Object.entries(_charBlendshapes)) {
    const section = document.createElement('div');
    section.style.cssText = 'margin-bottom:8px; padding:6px; background:#ece5fa; border-radius:6px;';
    const header = document.createElement('div');
    header.style.cssText = 'font-size:0.8rem; color:#7b1fa2; margin-bottom:4px; display:flex; justify-content:space-between; align-items:center;';
    header.innerHTML = `<span>${escHtml(emotion)}</span>
      <button class="secondary" style="font-size:0.7rem; padding:1px 6px;" onclick="addBlendshapeRow(this.parentElement.nextElementSibling)">+</button>`;
    section.appendChild(header);
    const rows = document.createElement('div');
    rows.className = 'bs-rows';
    rows.dataset.emotion = emotion;
    for (const [name, val] of Object.entries(shapes)) {
      rows.appendChild(makeBlendshapeRow(name, val));
    }
    section.appendChild(rows);
    el.appendChild(section);
  }
}

function makeBlendshapeRow(name, val) {
  const row = document.createElement('div');
  row.style.cssText = 'display:flex; gap:4px; margin-bottom:2px;';
  row.innerHTML = `<input type="text" class="bs-name text-input" value="${escHtml(name)}" style="width:80px; padding:2px 4px; font-size:0.75rem;">
    <input type="number" class="bs-val num-input" value="${val}" step="0.1" min="0" max="1" style="width:60px; font-size:0.75rem;">
    <button class="danger" style="font-size:0.65rem; padding:1px 4px;" onclick="this.parentElement.remove()">×</button>`;
  return row;
}

function addBlendshapeRow(container) {
  container.appendChild(makeBlendshapeRow('', 0));
}

function collectBlendshapes() {
  const result = {};
  document.querySelectorAll('.bs-rows').forEach(container => {
    const emotion = container.dataset.emotion;
    const shapes = {};
    container.querySelectorAll('div').forEach(row => {
      const name = row.querySelector('.bs-name')?.value?.trim();
      const val = parseFloat(row.querySelector('.bs-val')?.value || 0);
      if (name) shapes[name] = val;
    });
    result[emotion] = shapes;
  });
  const emotions = collectEmotions();
  for (const key of Object.keys(emotions)) {
    if (!(key in result)) result[key] = {};
  }
  return result;
}

async function saveCharacter() {
  const body = {
    name: document.getElementById('char-name').value,
    system_prompt: document.getElementById('char-prompt').value,
    rules: collectRules(),
    emotions: collectEmotions(),
    emotion_blendshapes: collectBlendshapes(),
  };
  const res = await api('PUT', '/api/character', body);
  if (res?.ok) {
    document.getElementById('char-status').textContent = '保存しました';
    await loadCharacter();
  }
}

// --- 言語モード ---
async function loadLanguageModes() {
  try {
    const d = await (await fetch('/api/language')).json();
    const el = document.getElementById('language-modes');
    el.innerHTML = d.modes.map(m =>
      `<button class="${m.active ? '' : 'secondary'}" onclick="setLanguageMode('${m.key}')" style="font-size:0.8rem; padding:6px 14px;">
        ${esc(m.name)}
      </button>`
    ).join('');
    const active = d.modes.find(m => m.active);
    const descEl = document.getElementById('lang-description');
    if (active) {
      descEl.innerHTML = `<strong>${esc(active.name)}</strong>: ${esc(active.description)}<ul style="margin:6px 0 0; padding-left:20px;">${active.rules.map(r => `<li>${esc(r)}</li>`).join('')}</ul>`;
      descEl.style.display = '';
    } else {
      descEl.style.display = 'none';
    }
  } catch(e) {}
}

async function setLanguageMode(mode) {
  try {
    const r = await fetch('/api/language', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({mode}) });
    const d = await r.json();
    if (d.ok) {
      showToast('言語モード変更: ' + mode, 'success');
      loadLanguageModes();
    } else {
      showToast(d.error || '変更失敗', 'error');
    }
  } catch(e) { showToast('言語モード変更失敗', 'error'); }
}

// --- サウンド ---
async function ttsTest() {
  const lang1 = document.getElementById('tts-lang1').value;
  const lang2 = document.getElementById('tts-lang2').value;
  await api('POST', '/api/tts/test', { primary_lang: lang1, secondary_lang: lang2 });
}

const bgmTracksEl = document.getElementById('bgm-tracks');

async function loadBgmTracks() {
  const res = await fetch('/api/bgm/list');
  const data = await res.json();
  const currentTrack = data.track || '';
  bgmTracksEl.innerHTML = '';
  for (const t of data.tracks) {
    const isPlaying = t.file === currentTrack;
    const volPct = Math.round((t.volume ?? 1) * 100);
    const row = document.createElement('div');
    row.dataset.file = t.file;
    row.style.cssText = 'padding:8px 6px; border-bottom:1px solid #d0c0e8;'
      + (isPlaying ? ' background:#ece5fa; border-radius:6px;' : '');
    row.innerHTML = `
      <div style="display:flex; gap:8px; align-items:center;">
        ${isPlaying ? '<span style="font-size:0.8rem; margin-right:2px;">▶</span>' : ''}
        <span style="flex:1; font-size:0.9rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;${isPlaying ? ' font-weight:600; color:#7b1fa2;' : ''}">${
          t.source_url
            ? `<a href="${escHtml(t.source_url)}" target="_blank" rel="noopener" style="color:inherit; text-decoration:underline dotted; text-underline-offset:3px;" title="${escHtml(t.source_url)}">${esc(t.name)}</a>`
            : esc(t.name)
        }</span>
        ${isPlaying
          ? `<button class="secondary" data-bgm-stop style="font-size:0.75rem;">停止</button>`
          : `<button data-bgm-play="${esc(t.file)}" style="font-size:0.75rem;">再生</button>`}
        <button class="danger" data-bgm-del="${esc(t.file)}" style="font-size:0.7rem; padding:2px 6px;" title="削除">×</button>
      </div>
      <div class="vol-row" style="margin-top:4px;">
        <span class="vol-label">曲音量</span>
        <input type="range" min="0" max="100" step="1" value="${volPct}" class="vol-slider"
          oninput="this.nextElementSibling.textContent=this.value+'%'"
          onchange="setTrackVolume('${esc(t.file)}', this.value)">
        <span class="vol-pct">${volPct}%</span>
      </div>
    `;
    bgmTracksEl.appendChild(row);
  }
  if (data.tracks.length === 0) {
    bgmTracksEl.innerHTML = '<div style="color:#9a88b5; font-size:0.85rem;">BGMファイルがありません</div>';
  }
  bgmTracksEl.querySelectorAll('[data-bgm-play]').forEach(btn =>
    btn.addEventListener('click', () => bgmPlay(btn.dataset.bgmPlay)));
  bgmTracksEl.querySelectorAll('[data-bgm-stop]').forEach(btn =>
    btn.addEventListener('click', () => bgmStop()));
  bgmTracksEl.querySelectorAll('[data-bgm-del]').forEach(btn =>
    btn.addEventListener('click', () => bgmDelete(btn.dataset.bgmDel)));
}

async function setTrackVolume(file, pct) {
  await api('POST', '/api/bgm/track-volume', { file, volume: parseInt(pct) / 100 });
}

// C#プレビューパネルからの曲音量変更をWebUIに反映（定期同期）
async function syncBgmVolumes() {
  try {
    const res = await fetch('/api/bgm/list');
    const data = await res.json();
    for (const t of data.tracks) {
      const row = bgmTracksEl.querySelector(`[data-file="${CSS.escape(t.file)}"]`);
      if (!row) continue;
      const slider = row.querySelector('.vol-slider');
      const label = row.querySelector('.vol-pct');
      const newVal = Math.round((t.volume ?? 1) * 100);
      if (slider && slider.value != newVal && !slider.matches(':active')) {
        slider.value = newVal;
        if (label) label.textContent = newVal + '%';
      }
    }
  } catch {}
}

async function bgmPlay(file) {
  const res = await api('POST', '/api/bgm', { action: 'play', track: file });
  if (res && res.ok) loadBgmTracks();
}

async function bgmStop() {
  await api('POST', '/api/bgm', { action: 'stop' });
  loadBgmTracks();
}

async function bgmDelete(file) {
  if (!await showConfirm('このトラックを削除しますか？', { title: '削除', okLabel: '削除', danger: true })) return;
  try {
    const r = await fetch('/api/bgm/track?file=' + encodeURIComponent(file), { method: 'DELETE' });
    const data = await r.json();
    showToast(data.ok ? '削除しました' : (data.error || '削除失敗'), data.ok ? 'success' : 'error');
  } catch (e) {
    showToast('削除失敗: ' + e.message, 'error');
  }
  loadBgmTracks();
}

async function ytDownload() {
  const url = document.getElementById('yt-url').value.trim();
  if (!url) return;
  setStatus('yt-status', 'ダウンロード中...', '');
  try {
    const res = await fetch('/api/bgm/youtube', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    const data = await res.json();
    if (data.ok) {
      setStatus('yt-status', '完了: ' + (data.title || data.file), 'ok');
      document.getElementById('yt-url').value = '';
      loadBgmTracks();
    } else {
      setStatus('yt-status', 'エラー: ' + data.error, 'err');
    }
  } catch (e) {
    setStatus('yt-status', 'エラー: ' + e.message, 'err');
  }
}

// --- トピック ---
let _topicPollTimer = null;

async function loadTopicStatus() {
  try {
    const r = await fetch('/api/topic');
    const d = await r.json();
    const el = document.getElementById('topic-current');
    if (d.active) {
      const desc = d.topic.description ? `<br><small style="color:#6a5590;">${esc(d.topic.description)}</small>` : '';
      el.innerHTML =
        `<div style="padding:8px 12px; background:#ede7f6; border-radius:6px; border-left:3px solid #7b1fa2;">` +
        `<strong>${esc(d.topic.title)}</strong>${desc}<br>` +
        `<small style="color:#9a88b5;">` +
        `待機: ${d.remaining_scripts}件 / 発話済み: ${d.spoken_count}件` +
        `${d.generating ? ' / 生成中...' : ''}` +
        ` / モデル: ${esc(d.model || '?')}</small></div>`;
      document.getElementById('topic-idle').value = d.idle_threshold;
      document.getElementById('topic-interval').value = d.min_interval;
    } else {
      el.innerHTML = '<span style="color:#9a88b5;">トピック未設定</span>';
    }
    const pauseBtn = document.getElementById('topic-pause-btn');
    if (d.paused) {
      pauseBtn.textContent = '再開';
      pauseBtn.style.background = '#2e7d32';
    } else {
      pauseBtn.textContent = '停止';
      pauseBtn.style.background = '#e65100';
    }
    if (d.active && d.paused) {
      el.querySelector('div').style.borderLeftColor = '#e65100';
    }
    if (d.generating && !_topicPollTimer) {
      _topicPollTimer = setInterval(() => { loadTopicStatus(); loadTopicScripts(); }, 3000);
    } else if (!d.generating && _topicPollTimer) {
      clearInterval(_topicPollTimer);
      _topicPollTimer = null;
      loadTopicScripts();
    }
  } catch(e) {}
}

async function setTopic() {
  const title = document.getElementById('topic-title').value.trim();
  if (!title) return;
  const desc = document.getElementById('topic-desc').value.trim();
  const st = document.getElementById('topic-status');
  st.textContent = '設定中...';
  try {
    const r = await fetch('/api/topic', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({title, description: desc}),
    });
    const d = await r.json();
    st.textContent = d.ok ? 'トピック設定完了' : d.error;
    document.getElementById('topic-title').value = '';
    document.getElementById('topic-desc').value = '';
    loadTopicStatus();
    if (!_topicPollTimer) {
      _topicPollTimer = setInterval(() => { loadTopicStatus(); loadTopicScripts(); }, 3000);
    }
  } catch(e) { st.textContent = 'エラー: ' + e; }
}

async function clearTopic() {
  await fetch('/api/topic', {method: 'DELETE'});
  document.getElementById('topic-status').textContent = 'トピック解除';
  loadTopicStatus();
  loadTopicScripts();
}

async function topicSpeakNow() {
  const st = document.getElementById('topic-status');
  st.textContent = '発話中...';
  try {
    const r = await fetch('/api/topic/speak', {method: 'POST'});
    const d = await r.json();
    st.textContent = d.ok ? '発話完了' : d.error;
    loadTopicStatus();
    loadTopicScripts();
  } catch(e) { st.textContent = 'エラー: ' + e; }
}

async function updateTopicSettings() {
  const idle = document.getElementById('topic-idle').value;
  const interval = document.getElementById('topic-interval').value;
  await fetch('/api/topic/settings', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({idle_threshold: Number(idle), min_interval: Number(interval)}),
  });
  loadTopicStatus();
}

async function toggleTopicPause() {
  const btn = document.getElementById('topic-pause-btn');
  const isPaused = btn.textContent === '再開';
  const endpoint = isPaused ? '/api/topic/resume' : '/api/topic/pause';
  await fetch(endpoint, {method: 'POST'});
  loadTopicStatus();
}

const _emotionColors = {joy:'#4caf50', surprise:'#ff9800', thinking:'#2196f3', neutral:'#9a88b5'};
async function loadTopicScripts() {
  try {
    const r = await fetch('/api/topic/scripts');
    const d = await r.json();
    const el = document.getElementById('topic-scripts');
    const genEl = document.getElementById('topic-generating');
    const badge = document.getElementById('topic-script-badge');
    genEl.style.display = d.generating ? 'block' : 'none';
    if (!d.scripts.length) {
      el.innerHTML = '<span style="color:#9a88b5;">スクリプトなし</span>';
      badge.textContent = '';
      return;
    }
    const spoken = d.scripts.filter(s => s.spoken_at).length;
    badge.textContent = `(${spoken}/${d.scripts.length})`;
    el.innerHTML = d.scripts.map((s, i) => {
      const done = !!s.spoken_at;
      const eColor = _emotionColors[s.emotion] || '#9a88b5';
      return `<div style="padding:8px 10px; margin-bottom:6px; border-radius:6px; background:${done ? '#f5f0ff' : '#fff'}; border:1px solid ${done ? '#e0d8f0' : '#d0c0e8'}; ${done ? 'opacity:0.55;' : ''}">` +
        `<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">` +
        `<span style="font-size:0.75rem; color:${eColor}; font-weight:600;">#${i+1} ${esc(s.emotion)}</span>` +
        `${done ? '<span style="font-size:0.7rem; color:#4caf50;">発話済</span>' : '<span style="font-size:0.7rem; color:#7b1fa2;">待機中</span>'}` +
        `</div>` +
        `<div style="font-size:0.9rem; line-height:1.5;">${esc(s.content)}</div>` +
        `</div>`;
    }).join('');
  } catch(e) {}
}

// --- DB閲覧 ---
let _dbCurrentTable = '';
let _dbOffset = 0;
const _dbLimit = 50;

async function loadDbTables() {
  try {
    const r = await fetch('/api/db/tables');
    const d = await r.json();
    const el = document.getElementById('db-tables');
    el.innerHTML = d.tables.map(t =>
      `<button class="db-tab${t.name === _dbCurrentTable ? ' active' : ''}" onclick="selectDbTable('${t.name}')">${esc(t.name)}<span class="db-tab-count">(${t.count})</span></button>`
    ).join('');
  } catch(e) {}
}

async function updateUserNotes() {
  const btn = document.getElementById('btn-update-notes');
  btn.disabled = true;
  btn.textContent = '更新中...';
  try {
    const r = await fetch('/api/db/update-notes', { method: 'POST' });
    const d = await r.json();
    showToast(`メモ更新完了: ${d.updated}人`, 'success');
    if (_dbCurrentTable === 'users') await loadDbData();
  } catch(e) {
    showToast('メモ更新失敗', 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'メモ更新';
  }
}

async function selectDbTable(name) {
  _dbCurrentTable = name;
  _dbOffset = 0;
  loadDbTables();
  await loadDbData();
}

async function loadDbData() {
  if (!_dbCurrentTable) return;
  try {
    const r = await fetch(`/api/db/${_dbCurrentTable}?limit=${_dbLimit}&offset=${_dbOffset}`);
    const d = await r.json();
    if (d.error) return;
    document.getElementById('db-table-name').textContent = d.table;
    document.getElementById('db-table-count').textContent = `${d.total}件`;
    const thead = document.getElementById('db-thead');
    const tbody = document.getElementById('db-tbody');
    thead.innerHTML = '<tr>' + d.columns.map(c => `<th>${esc(c)}</th>`).join('') + '</tr>';
    tbody.innerHTML = d.rows.map(row =>
      '<tr>' + d.columns.map(c => {
        let v = row[c];
        if (v === null) v = '';
        return `<td title="${escHtml(String(v))}">${esc(String(v))}</td>`;
      }).join('') + '</tr>'
    ).join('');
    const pager = document.getElementById('db-pager');
    const page = Math.floor(_dbOffset / _dbLimit) + 1;
    const totalPages = Math.ceil(d.total / _dbLimit);
    pager.innerHTML = '';
    if (totalPages > 1) {
      pager.innerHTML =
        `<button onclick="dbPage(-1)" ${_dbOffset === 0 ? 'disabled' : ''} style="font-size:0.75rem;">前</button>` +
        `<span style="font-size:0.8rem; color:#6a5590;">${page} / ${totalPages}</span>` +
        `<button onclick="dbPage(1)" ${page >= totalPages ? 'disabled' : ''} style="font-size:0.75rem;">次</button>`;
    }
  } catch(e) {}
}

function dbPage(dir) {
  _dbOffset = Math.max(0, _dbOffset + dir * _dbLimit);
  loadDbData();
}

// --- スクリーンショット ---
async function takeScreenshot() {
  const btn = document.getElementById('btn-screenshot');
  const st = document.getElementById('screenshot-status');
  btn.disabled = true;
  btn.textContent = '撮影中...';
  st.textContent = '';
  try {
    const res = await api('POST', '/api/capture/screenshot');
    if (res?.ok) {
      st.textContent = res.file + ' (' + Math.round(res.size / 1024) + 'KB)';
      st.style.color = '#2e7d32';
      loadScreenshots();
    } else {
      st.textContent = res?.detail || 'スクリーンショット失敗';
      st.style.color = '#c62828';
    }
  } catch (e) {
    st.textContent = 'エラー: ' + e.message;
    st.style.color = '#c62828';
  } finally {
    btn.disabled = false;
    btn.textContent = 'スクリーンショット撮影';
  }
}

async function loadScreenshots() {
  try {
    const data = await (await fetch('/api/capture/screenshots')).json();
    const el = document.getElementById('screenshot-list');
    const countEl = document.getElementById('screenshot-count');
    countEl.textContent = data.files.length ? `(${data.files.length}件)` : '';
    if (!data.files.length) {
      el.innerHTML = '<span style="color:#9a88b5;">スクリーンショットなし</span>';
      return;
    }
    el.innerHTML = data.files.map(f => {
      const sizeKB = Math.round(f.size / 1024);
      const dt = f.created.replace('T', ' ').substring(0, 19);
      return `<div style="display:flex; align-items:center; gap:10px; padding:8px 6px; border-bottom:1px solid #e8e0f0;">
        <img src="/api/capture/screenshots/${f.name}" style="width:160px; height:90px; object-fit:contain; background:#1a1a2e; border-radius:4px; cursor:pointer;" onclick="window.open('/api/capture/screenshots/${f.name}','_blank')">
        <div style="flex:1; min-width:0;">
          <div style="font-size:0.85rem; font-weight:500; word-break:break-all;">${esc(f.name)}</div>
          <div style="font-size:0.75rem; color:#9a88b5;">${dt} / ${sizeKB}KB</div>
          <div style="font-size:0.7rem; color:#6a5590; margin-top:2px;">パス: /tmp/screenshots/${esc(f.name)}</div>
        </div>
        <button class="danger" style="font-size:0.75rem; padding:4px 10px;" onclick="deleteScreenshot('${esc(f.name)}')">削除</button>
      </div>`;
    }).join('');
  } catch (e) {}
}

async function deleteScreenshot(name) {
  await fetch('/api/capture/screenshots/' + encodeURIComponent(name), { method: 'DELETE' });
  loadScreenshots();
}

// --- ライティングプリセット ---
const LIGHTING_PRESETS = {
  default: { brightness: 1.0, contrast: 1.0, temperature: 0.1, saturation: 1.0, ambient: 0.75, directional: 1.0, lightX: 0.5, lightY: 1.5, lightZ: 2.0 },
};

function applyLightingValues(p) {
  // スライダーと数値入力を更新
  for (const [key, val] of Object.entries(p)) {
    const dataKey = 'lighting.' + key;
    const numEl = document.getElementById('lv-lighting-' + key);
    if (numEl) numEl.value = val;
    const slider = document.querySelector(`input[type="range"][data-key="${dataKey}"]`);
    if (slider) slider.value = val;
  }
  api('POST', '/api/overlay/preview', { lighting: p });
  api('POST', '/api/overlay/settings', { lighting: p });
}

function applyLightingPreset(name) {
  const p = LIGHTING_PRESETS[name];
  if (p) applyLightingValues(p);
}

// 現在のスライダー値を読み取る
function getCurrentLightingValues() {
  const keys = ['brightness', 'contrast', 'temperature', 'saturation', 'ambient', 'directional', 'lightX', 'lightY', 'lightZ'];
  const values = {};
  for (const key of keys) {
    const el = document.getElementById('lv-lighting-' + key);
    if (el) values[key] = parseFloat(el.value);
  }
  return values;
}

// プリセット保存UI
function showPresetSaveUI() {
  document.getElementById('preset-save-ui').style.display = '';
  document.getElementById('preset-name-input').focus();
}
function hidePresetSaveUI() {
  document.getElementById('preset-save-ui').style.display = 'none';
  document.getElementById('preset-name-input').value = '';
}

async function saveCurrentAsPreset() {
  const name = document.getElementById('preset-name-input').value.trim();
  if (!name) return;
  const values = getCurrentLightingValues();
  await api('POST', '/api/lighting/presets', { name, values });
  hidePresetSaveUI();
  loadLightingPresets();
}

async function deleteLightingPreset(name) {
  if (!await showConfirm(`プリセット「${name}」を削除しますか？`, { title: '削除', okLabel: '削除', danger: true })) return;
  await fetch('/api/lighting/presets', { method: 'DELETE', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ name }) });
  loadLightingPresets();
}

async function loadLightingPresets() {
  try {
    const data = await (await fetch('/api/lighting/presets')).json();
    const container = document.getElementById('lighting-presets-list');
    if (!data.presets || data.presets.length === 0) {
      container.innerHTML = '<span style="font-size:0.75rem; color:#9a88b5;">保存済みプリセットなし</span>';
      return;
    }
    container.innerHTML = data.presets.map(p =>
      `<div style="display:inline-flex; align-items:center; gap:2px; background:#f3e5f5; border-radius:4px; padding:2px 4px;">
        <button class="secondary" style="font-size:0.75rem; padding:3px 8px;" onclick='applyLightingValues(${JSON.stringify(p.values)})'>${esc(p.name)}</button>
        <button style="font-size:0.65rem; padding:1px 4px; background:none; border:none; color:#999; cursor:pointer;" onclick="deleteLightingPreset('${esc(p.name)}')" title="削除">&times;</button>
      </div>`
    ).join('');
  } catch (e) {}
}

// --- TODO ---
async function loadTodoList() {
  try {
    const data = await (await fetch('/api/todo')).json();
    const el = document.getElementById('todo-list');
    if (!data.items || data.items.length === 0) {
      el.innerHTML = '<div style="color:#9a88b5;">TODOはありません</div>';
      return;
    }
    let currentSection = '';
    let html = '';
    for (const item of data.items) {
      if (item.section !== currentSection) {
        currentSection = item.section;
        html += `<div style="font-size:0.8rem; font-weight:600; color:#7b1fa2; margin:12px 0 6px; border-bottom:1px solid #e8ddf5; padding-bottom:4px;">${esc(currentSection)}</div>`;
      }
      const isActive = item.status === 'in_progress';
      const bg = isActive ? 'background:#f3e5f5; border-left:3px solid #7b1fa2;' : 'border-left:3px solid transparent;';
      const checkbox = isActive
        ? '<span style="display:inline-flex; align-items:center; justify-content:center; width:18px; height:18px; border-radius:4px; background:#7b1fa2; flex-shrink:0; font-size:0.7rem; color:#fff;">▶</span>'
        : '<span style="display:inline-flex; align-items:center; justify-content:center; width:18px; height:18px; border:2px solid #d0c0e8; border-radius:4px; flex-shrink:0;"></span>';
      html += `<div style="padding:8px 12px; margin:4px 0; border-radius:4px; cursor:pointer; ${bg} transition:background 0.15s; display:flex; align-items:center; gap:8px;" onmouseenter="this.style.background='#f0e8ff'" onmouseleave="this.style.background='${isActive ? '#f3e5f5' : ''}'"><span style="flex:1; display:flex; align-items:center; gap:8px;" onclick="startTodo(this.parentElement, '${esc(item.text).replace(/'/g, "\\'")}')">${checkbox}${esc(item.text)}</span><button class="todo-copy-btn" onclick="event.stopPropagation();copyTodo(this,'${esc(item.text).replace(/'/g, "\\'")}')" title="コピー"></button></div>`;
    }
    el.innerHTML = html;
  } catch (e) {
    document.getElementById('todo-list').innerHTML = '<div style="color:#c62828;">読み込みエラー</div>';
  }
}

const ICON_COPY = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='%237b1fa2' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Crect x='9' y='9' width='13' height='13' rx='2'/%3E%3Cpath d='M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1'/%3E%3C/svg%3E";
const ICON_CHECK = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='%234caf50' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='20 6 9 17 4 12'/%3E%3C/svg%3E";
async function copyTodo(btn, text) {
  await navigator.clipboard.writeText(text);
  btn.style.backgroundImage = `url("${ICON_CHECK}")`;
  setTimeout(() => { btn.style.backgroundImage = `url("${ICON_COPY}")`; }, 1000);
}

async function startTodo(el, text) {
  el.style.opacity = '0.5';
  el.style.pointerEvents = 'none';
  try {
    const res = await api('POST', '/api/todo/start', { text });
    if (res.ok) {
      showToast('作業開始: ' + text);
    } else {
      showToast(res.error || 'エラー', 'error');
    }
    loadTodoList();
  } catch (e) {
    showToast('エラー', 'error');
    el.style.opacity = '1';
    el.style.pointerEvents = '';
  }
}

// --- 配信画面 ---
let layoutSettings = {};
let _layoutTimer = null;

let _pendingLayoutChanges = {};

function _updateLayout(key, val) {
  const [section, prop] = key.split('.');
  if (!layoutSettings[section]) layoutSettings[section] = {};
  layoutSettings[section][prop] = val;
  // 変更されたプロパティだけ記録
  if (!_pendingLayoutChanges[section]) _pendingLayoutChanges[section] = {};
  _pendingLayoutChanges[section][prop] = val;
  clearTimeout(_layoutTimer);
  _layoutTimer = setTimeout(() => {
    const changes = _pendingLayoutChanges;
    _pendingLayoutChanges = {};
    api('POST', '/api/overlay/settings', changes);
  }, 200);
}

function onLayoutSlider(slider) {
  const val = parseFloat(slider.value);
  if (isNaN(val)) return;
  const numEl = document.getElementById('lv-' + slider.dataset.key.replace('.', '-'));
  if (numEl) numEl.value = val;
  _updateLayout(slider.dataset.key, val);
}

function onLayoutNum(input) {
  const val = parseFloat(input.value);
  if (isNaN(val)) return;
  const slider = input.closest('.layout-row').querySelector('.layout-slider');
  if (slider) slider.value = val;
  _updateLayout(input.dataset.key, val);
}

async function loadLayout() {
  try {
    const data = await (await fetch('/api/overlay/settings')).json();
    layoutSettings = data;
    document.querySelectorAll('.layout-num[data-key]').forEach(numEl => {
      const [section, prop] = numEl.dataset.key.split('.');
      const val = data[section]?.[prop];
      if (val != null) {
        numEl.value = val;
        const slider = numEl.closest('.layout-row').querySelector('.layout-slider');
        if (slider) slider.value = val;
      }
    });
    // バージョン表示トグル・フォーマット初期化
    if (data.version) {
      const vToggle = document.getElementById('lv-version-visible');
      if (vToggle) {
        vToggle.checked = !!data.version.visible;
        _updateVersionToggleStyle(vToggle);
      }
      const vFormat = document.getElementById('lv-version-format');
      if (vFormat && data.version.format) {
        vFormat.value = data.version.format;
      }
    }
  } catch (e) {}
}

function onVersionToggle(cb) {
  _updateVersionToggleStyle(cb);
  _updateLayout('version.visible', cb.checked ? 1 : 0);
}

let _versionFormatTimer = null;
function onVersionFormatChange(input) {
  clearTimeout(_versionFormatTimer);
  _versionFormatTimer = setTimeout(() => {
    _updateLayout('version.format', input.value);
  }, 500);
}

function _updateVersionToggleStyle(cb) {
  const track = cb.nextElementSibling;
  const knob = document.getElementById('lv-version-visible-knob');
  if (cb.checked) {
    track.style.background = '#7b1fa2';
    knob.style.left = '20px';
  } else {
    track.style.background = '#ccc';
    knob.style.left = '2px';
  }
}

// --- 再起動 ---
async function doRestart() {
  if (!await showConfirm('サーバーを再起動しますか？', { title: '再起動' })) return;
  log('再起動リクエスト送信...');
  try {
    await fetch('/api/restart', { method: 'POST' });
  } catch (e) {}
  showToast('再起動中...', 'success', 3000);
  setTimeout(() => waitForRestart(), 2000);
}

function waitForRestart() {
  const check = async () => {
    try {
      const r = await fetch('/api/status', { signal: AbortSignal.timeout(2000) });
      if (r.ok) {
        location.reload();
        return;
      }
    } catch (e) {}
    setTimeout(check, 1000);
  };
  check();
}

// --- サーバー更新検知 ---
let _knownStartedAt = null;

async function checkServerUpdate() {
  try {
    const r = await fetch('/api/status', { signal: AbortSignal.timeout(3000) });
    if (!r.ok) return;
    const data = await r.json();
    const startedAt = data.server_started_at;
    if (_knownStartedAt === null) {
      _knownStartedAt = startedAt;
      return;
    }
    if (startedAt !== _knownStartedAt) {
      _knownStartedAt = startedAt;
      showUpdateDialog();
    }
  } catch (e) {}
}

function showUpdateDialog() {
  if (document.getElementById('update-dialog')) return;
  const div = document.createElement('div');
  div.id = 'update-dialog';
  div.className = 'update-dialog';
  div.innerHTML = `
    <div class="update-dialog-inner">
      <h3>サーバーが更新されました</h3>
      <p>新しいバージョンが起動しています。ページをリロードしますか？</p>
      <div class="btn-group">
        <button onclick="location.reload()">リロード</button>
        <button class="secondary" onclick="this.closest('.update-dialog').remove()">あとで</button>
      </div>
    </div>
  `;
  document.body.appendChild(div);
}

// --- 素材ファイル管理 ---
function _formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

async function loadFilesList() {
  await Promise.all([loadCategoryFiles('avatar'), loadCategoryFiles('background')]);
}

async function loadCategoryFiles(category) {
  const listEl = document.getElementById(category + '-files-list');
  if (!listEl) return;
  try {
    const res = await fetch('/api/files/' + category + '/list');
    const data = await res.json();
    if (!data.ok) { listEl.innerHTML = '<div style="color:#c62828; font-size:0.85rem;">' + esc(data.error) + '</div>'; return; }

    if (data.files.length === 0) {
      listEl.innerHTML = '<div style="color:#9a88b5; font-size:0.85rem;">ファイルがありません</div>';
      return;
    }

    listEl.innerHTML = '';
    for (const f of data.files) {
      const row = document.createElement('div');
      row.style.cssText = 'padding:8px 6px; border-bottom:1px solid #d0c0e8;'
        + (f.active ? ' background:#ece5fa; border-radius:6px;' : '');
      const previewHtml = category === 'background'
        ? `<img src="/resources/images/backgrounds/${encodeURIComponent(f.file)}" style="width:48px; height:36px; object-fit:cover; border-radius:4px; border:1px solid #d0c0e8;">`
        : '';
      row.innerHTML = `
        <div style="display:flex; gap:8px; align-items:center;">
          ${previewHtml}
          ${f.active ? '<span style="font-size:0.8rem; color:#2e7d32; margin-right:2px;">●</span>' : ''}
          <span style="flex:1; font-size:0.9rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;${f.active ? ' font-weight:600; color:#7b1fa2;' : ''}">${esc(f.name)}</span>
          <span style="font-size:0.75rem; color:#9a88b5;">${_formatSize(f.size)}</span>
          ${f.active
            ? '<span style="font-size:0.75rem; color:#2e7d32; font-weight:600;">使用中</span>'
            : `<button data-select-file="${escHtml(f.file)}" data-category="${category}" style="font-size:0.75rem;">使用</button>`}
          <button class="danger" data-delete-file="${escHtml(f.file)}" data-category="${category}" style="font-size:0.7rem; padding:2px 6px;" title="削除">×</button>
        </div>
      `;
      listEl.appendChild(row);
    }

    listEl.querySelectorAll('[data-select-file]').forEach(btn =>
      btn.addEventListener('click', () => selectFile(btn.dataset.category, btn.dataset.selectFile)));
    listEl.querySelectorAll('[data-delete-file]').forEach(btn =>
      btn.addEventListener('click', () => deleteFile(btn.dataset.category, btn.dataset.deleteFile)));
  } catch (e) {
    listEl.innerHTML = '<div style="color:#c62828; font-size:0.85rem;">読み込み失敗: ' + esc(e.message) + '</div>';
  }
}

async function uploadFile(category, input) {
  const files = input.files;
  if (!files || files.length === 0) return;
  const statusEl = document.getElementById(category + '-upload-status');

  for (const file of files) {
    if (statusEl) { statusEl.textContent = 'アップロード中: ' + file.name + '...'; statusEl.style.color = '#6a5590'; }
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await fetch('/api/files/' + category + '/upload', { method: 'POST', body: formData });
      const data = await res.json();
      if (data.ok) {
        showToast('アップロード完了: ' + (data.file || file.name), 'success');
      } else {
        showToast('アップロード失敗: ' + (data.error || ''), 'error');
      }
    } catch (e) {
      showToast('アップロード失敗: ' + e.message, 'error');
    }
  }
  input.value = '';
  if (statusEl) statusEl.textContent = '';
  loadCategoryFiles(category);
}

async function selectFile(category, file) {
  const res = await api('POST', '/api/files/' + category + '/select', { file });
  if (res && res.ok) {
    showToast('適用しました: ' + file, 'success');
    loadCategoryFiles(category);
  }
}

async function deleteFile(category, file) {
  if (!await showConfirm('このファイルを削除しますか？\n' + file, { title: '削除', okLabel: '削除', danger: true })) return;
  try {
    const r = await fetch('/api/files/' + category + '?file=' + encodeURIComponent(file), { method: 'DELETE' });
    const data = await r.json();
    showToast(data.ok ? '削除しました' : (data.error || '削除失敗'), data.ok ? 'success' : 'error');
  } catch (e) {
    showToast('削除失敗: ' + e.message, 'error');
  }
  loadCategoryFiles(category);
}

// --- 初期化 ---
const initTab = location.hash.slice(1);
if (TAB_NAMES.includes(initTab)) switchTab(initTab);

loadVolumes();
loadLayout();
loadCharacter();
loadLightingPresets();
loadBgmTracks();
loadTopicStatus();
loadTopicScripts();
refreshStatus();
setInterval(refreshStatus, 5000);
checkServerUpdate();
setInterval(checkServerUpdate, 3000);
captureRefreshSources();
setInterval(captureRefreshSources, 10000);
loadCustomTexts();
setInterval(syncBgmVolumes, 3000);


// ===== 開発実況 =====

async function loadDevstream() {
  try {
    const r = await fetch('/api/dev-stream/repos');
    const d = await r.json();
    const el = document.getElementById('ds-repos');
    if (!d.repos.length) {
      el.innerHTML = '<span style="color:#9a88b5;">リポジトリなし</span>';
      return;
    }
    el.innerHTML = d.repos.map(repo => {
      const active = repo.active ? true : false;
      const hash = repo.last_commit_hash ? repo.last_commit_hash.substring(0, 8) : '-';
      const toggleLabel = active ? '有効' : '無効';
      const toggleColor = active ? '#2e7d32' : '#999';
      const opacity = active ? '1' : '0.6';
      const border = active ? 'border-left:3px solid #4caf50; padding-left:8px;' : '';
      return `<div style="display:flex; align-items:center; gap:8px; padding:8px 0; border-bottom:1px solid #e8e0f0; opacity:${opacity}; ${border}">
        <div style="flex:1; min-width:0;">
          <div style="font-weight:600; font-size:0.9rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${esc(repo.name)}</div>
          <div style="font-size:0.75rem; color:#9a88b5;">
            ${esc(repo.branch)} / ${hash}${active ? ' — 監視中・TODO表示中' : ''}
          </div>
        </div>
        <button onclick="dsToggleRepo(${repo.id}, ${!active})" style="padding:2px 10px; font-size:0.75rem; background:${toggleColor}; color:#fff; border:none; border-radius:4px; cursor:pointer;">${toggleLabel}</button>
        <button onclick="dsCheckRepo(${repo.id})" style="padding:2px 10px; font-size:0.75rem; background:#1565c0; color:#fff; border:none; border-radius:4px; cursor:pointer;">Check</button>
        <button onclick="dsDeleteRepo(${repo.id}, '${esc(repo.name)}')" style="padding:2px 10px; font-size:0.75rem; background:#c62828; color:#fff; border:none; border-radius:4px; cursor:pointer;">削除</button>
      </div>`;
    }).join('');
  } catch (e) { console.error('devstream repos error', e); }
}

async function dsAddRepo() {
  const url = document.getElementById('ds-url').value.trim();
  const branch = document.getElementById('ds-branch').value.trim() || 'main';
  const errEl = document.getElementById('ds-add-error');
  const btn = document.getElementById('ds-add-btn');
  errEl.style.display = 'none';
  if (!url) { errEl.textContent = 'URLを入力してください'; errEl.style.display = 'block'; return; }
  btn.disabled = true;
  btn.textContent = 'clone中...';
  try {
    const r = await fetch('/api/dev-stream/repos', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, branch }),
    });
    const d = await r.json();
    if (!d.ok) {
      errEl.textContent = d.error || '追加に失敗しました';
      errEl.style.display = 'block';
      return;
    }
    document.getElementById('ds-url').value = '';
    await loadDevstream();
  } catch (e) {
    errEl.textContent = '通信エラー';
    errEl.style.display = 'block';
  } finally {
    btn.disabled = false;
    btn.textContent = '追加';
  }
}

async function dsToggleRepo(id, active) {
  await fetch(`/api/dev-stream/repos/${id}/toggle`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ active }),
  });
  await loadDevstream();
}

async function dsCheckRepo(id) {
  const r = await fetch(`/api/dev-stream/repos/${id}/check`, { method: 'POST' });
  const d = await r.json();
  if (d.ok) {
    log(`チェック完了: ${d.commits}件のコミット`);
  }
  await loadDevstream();
}

async function dsDeleteRepo(id, name) {
  if (!await showConfirm(`「${name}」を削除しますか？`, { title: '削除', okLabel: '削除', danger: true })) return;
  await fetch(`/api/dev-stream/repos/${id}`, { method: 'DELETE' });
  await loadDevstream();
}
