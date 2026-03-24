// 配信画面レイアウト設定・共通プロパティUI
let layoutSettings = {};
let _layoutTimer = null;

let _pendingLayoutChanges = {};

function _updateLayout(key, val) {
  const dotIdx = key.indexOf('.');
  const section = key.substring(0, dotIdx);
  const prop = key.substring(dotIdx + 1);
  if (!layoutSettings[section]) layoutSettings[section] = {};
  layoutSettings[section][prop] = val;
  // capture/customtext/child は items API を使用
  if (section.startsWith('capture:') || section.startsWith('customtext:') || section.startsWith('child:')) {
    if (!_pendingLayoutChanges[section]) _pendingLayoutChanges[section] = {};
    _pendingLayoutChanges[section][prop] = val;
    clearTimeout(_layoutTimer);
    _layoutTimer = setTimeout(() => {
      for (const [sec, props] of Object.entries(_pendingLayoutChanges)) {
        if (sec.startsWith('capture:') || sec.startsWith('customtext:') || sec.startsWith('child:')) {
          api('PUT', `/api/items/${encodeURIComponent(sec)}`, props);
        }
      }
      _pendingLayoutChanges = {};
    }, 200);
    return;
  }
  // 固定アイテム
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

function onLayoutColor(input) {
  _updateLayout(input.dataset.key, input.value);
}

function onLayoutToggle(cb) {
  _updateLayout(cb.dataset.key, cb.checked ? 1 : 0);
}

function onLayoutSelect(sel) {
  _updateLayout(sel.dataset.key, sel.value);
}

function cssColorToHex(color) {
  if (!color) return '#000000';
  if (color.startsWith('#')) return color.substring(0, 7);
  const m = color.match(/rgba?\(\s*(\d+),\s*(\d+),\s*(\d+)/);
  if (m) {
    const r = parseInt(m[1]).toString(16).padStart(2, '0');
    const g = parseInt(m[2]).toString(16).padStart(2, '0');
    const b = parseInt(m[3]).toString(16).padStart(2, '0');
    return `#${r}${g}${b}`;
  }
  return '#000000';
}

// スキーマAPIから取得した共通プロパティ定義（起動時に1回取得）
let _commonSchema = null;

async function _loadCommonSchema() {
  try {
    const res = await fetch('/api/items/schema');
    _commonSchema = await res.json();
  } catch (e) { _commonSchema = null; }
}

function _commonPropsHTML(s, skipGroups) {
  if (!_commonSchema || !_commonSchema.groups) return '';
  const skip = skipGroups || [];
  const row = (label, body) => `<div class="layout-row common-row"><span class="layout-label">${label}</span>${body}</div>`;
  const group = (title) => `<div style="font-size:0.7rem; color:#7b1fa2; font-weight:600; margin:10px 0 4px; padding:2px 6px; background:rgba(124,77,255,0.06); border-radius:3px; border-left:2px solid #7b1fa2;">${title}</div>`;

  return _commonSchema.groups.filter(g => !skip.includes(g.title)).map(g => {
    const header = group(g.title);
    const rows = g.fields.map(f => row(f.label, _renderFieldControl(s, f))).join('');
    return header + rows;
  }).join('');
}

function _renderFieldControl(section, field) {
  const key = `${section}.${field.key}`;
  switch (field.type) {
    case 'slider':
      return `<input type="range" class="vol-slider layout-slider" min="${field.min}" max="${field.max}" step="${field.step}" data-key="${key}" oninput="onLayoutSlider(this)">` +
        `<input type="number" class="layout-num" id="lv-${section}-${field.key}" min="${field.min}" max="${field.max}" step="${field.step}" data-key="${key}" oninput="onLayoutNum(this)">`;
    case 'color':
      return `<input type="color" class="layout-color" data-key="${key}" oninput="onLayoutColor(this)" style="width:40px; height:24px; border:1px solid #ccc; border-radius:4px; cursor:pointer;">`;
    case 'toggle':
      return `<label style="position:relative; display:inline-block; width:36px; height:20px; margin-left:8px;">` +
        `<input type="checkbox" class="layout-toggle" data-key="${key}" onchange="onLayoutToggle(this)" style="opacity:0; width:0; height:0;">` +
        `<span style="position:absolute; cursor:pointer; inset:0; background:#ccc; border-radius:20px; transition:.2s;"></span>` +
        `<span class="toggle-knob" style="position:absolute; left:2px; top:2px; width:16px; height:16px; background:#fff; border-radius:50%; transition:.2s;"></span></label>`;
    case 'select': {
      const opts = field.options.map(([v, l]) => `<option value="${v}">${l}</option>`).join('');
      return `<select class="layout-select" data-key="${key}" onchange="onLayoutSelect(this)" style="padding:2px 6px; font-size:0.8rem; border:1px solid #ccc; border-radius:4px;">${opts}</select>`;
    }
    case 'text':
      return `<input type="text" class="layout-text" data-key="${key}" oninput="onLayoutSelect(this)" style="padding:2px 6px; font-size:0.8rem; border:1px solid #ccc; border-radius:4px; width:100%;">`;
    default:
      return '';
  }
}

function _injectCommonProps(el, section) {
  const body = el.querySelector('.panel-body');
  if (!body) return;
  const skipAttr = el.dataset.skipGroups;
  const skipGroups = skipAttr ? skipAttr.split(',').map(s => s.trim()) : [];
  body.insertAdjacentHTML('afterbegin', _commonPropsHTML(section, skipGroups));
  // 固有パラメータがあればグループヘッダーを追加
  const specificRows = body.querySelectorAll('.layout-row:not(.common-row)');
  if (specificRows.length > 0) {
    specificRows[0].insertAdjacentHTML('beforebegin',
      '<div style="font-size:0.7rem; color:#e67e22; font-weight:600; margin:10px 0 4px; padding:2px 6px; background:rgba(230,126,34,0.06); border-radius:3px; border-left:2px solid #e67e22;">固有設定</div>');
  }
}

function _initToggles(container) {
  container.querySelectorAll('.layout-toggle').forEach(cb => {
    cb.addEventListener('change', () => {
      const track = cb.nextElementSibling;
      const knob = track?.nextElementSibling;
      if (track) track.style.background = cb.checked ? '#7b1fa2' : '#ccc';
      if (knob) knob.style.left = cb.checked ? '16px' : '2px';
    });
  });
}

function initCommonProps() {
  document.querySelectorAll('.panel-item[data-section]').forEach(el => {
    _injectCommonProps(el, el.dataset.section);
  });
  _initToggles(document);
}

async function loadLayout() {
  try {
    const data = await (await fetch('/api/overlay/settings')).json();
    // /api/itemsから動的アイテム(capture/customtext/child)のデータもマージ
    try {
      const items = await (await fetch('/api/items')).json();
      for (const item of items) {
        if (item.id && !data[item.id]) data[item.id] = item;
        // 子パネルもフラットに展開
        if (item.children) {
          for (const child of item.children) {
            if (child.id) data[child.id] = child;
          }
        }
      }
    } catch (e) {}
    layoutSettings = data;
    _applyLayoutToUI(data);
  } catch (e) {}
}

// スキーマからフィールドのデフォルト値を取得する
function _getSchemaDefault(prop) {
  if (!_commonSchema) return undefined;
  for (const g of _commonSchema.groups || []) {
    for (const f of g.fields || []) {
      if (f.key === prop && f.default !== undefined) return f.default;
    }
  }
  return undefined;
}

// アイテム固有スキーマからデフォルト値を取得する
let _specificSchemaCache = {};
async function _getSpecificDefault(section, prop) {
  if (!_specificSchemaCache[section]) {
    try {
      const res = await fetch(`/api/items/schema?item_id=${encodeURIComponent(section)}`);
      _specificSchemaCache[section] = await res.json();
    } catch (e) { _specificSchemaCache[section] = {}; }
  }
  const schema = _specificSchemaCache[section];
  for (const g of schema.groups || []) {
    for (const f of g.fields || []) {
      if (f.key === prop && f.default !== undefined) return f.default;
    }
  }
  return undefined;
}

function _applyLayoutToUI(data) {
  document.querySelectorAll('.layout-num[data-key]').forEach(numEl => {
    const key = numEl.dataset.key;
    const dotIdx = key.indexOf('.');
    const section = key.substring(0, dotIdx);
    const prop = key.substring(dotIdx + 1);
    let val = data[section]?.[prop];
    if (val == null) val = _getSchemaDefault(prop);
    if (val != null) {
      numEl.value = val;
      const slider = numEl.closest('.layout-row')?.querySelector('.layout-slider');
      if (slider) slider.value = val;
    }
  });
  // カラーピッカー・トグル初期化
  document.querySelectorAll('.layout-color[data-key]').forEach(el => {
    const key = el.dataset.key;
    const dotIdx = key.indexOf('.');
    const section = key.substring(0, dotIdx);
    const prop = key.substring(dotIdx + 1);
    let val = data[section]?.[prop];
    if (!val) val = _getSchemaDefault(prop);
    if (val) el.value = cssColorToHex(String(val));
  });
  document.querySelectorAll('.layout-toggle[data-key]').forEach(el => {
    const key = el.dataset.key;
    const dotIdx = key.indexOf('.');
    const section = key.substring(0, dotIdx);
    const prop = key.substring(dotIdx + 1);
    let val = data[section]?.[prop];
    if (val == null) val = _getSchemaDefault(prop);
    if (val != null) {
      el.checked = !!Number(val);
      const track = el.nextElementSibling;
      const knob = track?.nextElementSibling;
      if (track) track.style.background = el.checked ? '#7b1fa2' : '#ccc';
      if (knob) knob.style.left = el.checked ? '16px' : '2px';
    }
  });
  // セレクトボックス初期化
  document.querySelectorAll('.layout-select[data-key]').forEach(el => {
    const key = el.dataset.key;
    const dotIdx = key.indexOf('.');
    const section = key.substring(0, dotIdx);
    const prop = key.substring(dotIdx + 1);
    let val = data[section]?.[prop];
    if (val == null) val = _getSchemaDefault(prop);
    if (val != null) el.value = val;
  });

  // 固有スキーマのデフォルト値も適用（非同期）
  _applySpecificDefaults(data);
}

async function _applySpecificDefaults(data) {
  const sections = new Set();
  document.querySelectorAll('.layout-num[data-key], .layout-slider[data-key]').forEach(el => {
    const key = el.dataset.key;
    const section = key.substring(0, key.indexOf('.'));
    sections.add(section);
  });
  for (const section of sections) {
    for (const numEl of document.querySelectorAll(`.layout-num[data-key^="${section}."]`)) {
      const key = numEl.dataset.key;
      const prop = key.substring(key.indexOf('.') + 1);
      if (data[section]?.[prop] != null) continue;
      if (_getSchemaDefault(prop) != null) continue;
      const def = await _getSpecificDefault(section, prop);
      if (def != null) {
        numEl.value = def;
        const slider = numEl.closest('.layout-row')?.querySelector('.layout-slider');
        if (slider) slider.value = def;
      }
    }
  }
}
