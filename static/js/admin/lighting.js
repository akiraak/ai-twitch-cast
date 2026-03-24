// ライティングプリセット
const LIGHTING_PRESETS = {
  default: { brightness: 1.0, contrast: 1.0, temperature: 0.1, saturation: 1.0, ambient: 0.75, directional: 1.0, lightX: 0.5, lightY: 1.5, lightZ: 2.0 },
};

// 現在のキャラクターに応じたlightingセクション名を返す
function _lightingSection() {
  return _currentChar === 'student' ? 'lighting_student' : 'lighting_teacher';
}

// キャラクター切替時にライティングスライダーのdata-keyを更新
function _updateLightingDataKeys() {
  const section = _lightingSection();
  document.querySelectorAll('#char-sub-appearance .layout-slider[data-key^="lighting"]').forEach(el => {
    const prop = el.dataset.key.split('.').pop();
    el.dataset.key = section + '.' + prop;
  });
  document.querySelectorAll('#char-sub-appearance .layout-num[id^="lv-lighting-"]').forEach(el => {
    const prop = el.id.replace('lv-lighting-', '');
    el.dataset.key = section + '.' + prop;
  });
}

function applyLightingValues(p) {
  const section = _lightingSection();
  for (const [key, val] of Object.entries(p)) {
    const numEl = document.getElementById('lv-lighting-' + key);
    if (numEl) numEl.value = val;
    const dataKey = section + '.' + key;
    const slider = document.querySelector(`input[type="range"][data-key="${dataKey}"]`);
    if (slider) slider.value = val;
  }
  const payload = { [section]: p };
  api('POST', '/api/overlay/preview', payload);
  api('POST', '/api/overlay/settings', payload);
}

function applyLightingPreset(name) {
  const p = LIGHTING_PRESETS[name];
  if (p) applyLightingValues(p);
}

function getCurrentLightingValues() {
  const keys = ['brightness', 'contrast', 'temperature', 'saturation', 'ambient', 'directional', 'lightX', 'lightY', 'lightZ'];
  const values = {};
  for (const key of keys) {
    const el = document.getElementById('lv-lighting-' + key);
    if (el) values[key] = parseFloat(el.value);
  }
  return values;
}

// キャラクター切替時にスライダー値をDBから読み込み
function _loadCharLighting() {
  _updateLightingDataKeys();
  const section = _lightingSection();
  if (layoutSettings[section]) {
    const keys = ['brightness', 'contrast', 'temperature', 'saturation', 'ambient', 'directional', 'lightX', 'lightY', 'lightZ'];
    for (const key of keys) {
      const val = layoutSettings[section][key];
      if (val == null) continue;
      const numEl = document.getElementById('lv-lighting-' + key);
      if (numEl) numEl.value = val;
      const slider = document.querySelector(`input[type="range"][data-key="${section}.${key}"]`);
      if (slider) slider.value = val;
    }
  }
}

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
