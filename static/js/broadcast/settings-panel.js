// フローティング設定パネル（スキーマ取得・フィールドレンダリング・保存）

// スキーマ取得（キャッシュ付き）
async function _fetchSchema(itemId) {
  // キャッシュキー: 固定アイテムはID自体、動的アイテムはタイプ
  const cacheKey = itemId.startsWith('customtext:') ? 'custom_text'
                 : itemId.startsWith('capture:') ? 'capture'
                 : itemId.startsWith('child:') ? 'child_text'
                 : itemId;
  if (_schemaCache[cacheKey]) return _schemaCache[cacheKey];
  try {
    const res = await fetch(`/api/items/schema?item_id=${encodeURIComponent(itemId)}`);
    const schema = await res.json();
    _schemaCache[cacheKey] = schema;
    return schema;
  } catch (e) { return null; }
}

// フィールド→HTML
function _renderField(field, value) {
  const dk = `data-sp-key="${field.key}"`;
  switch (field.type) {
    case 'slider': {
      const v = value ?? field.min;
      return `<div class="sp-row"><label>${field.label}</label>` +
        `<input type="range" min="${field.min}" max="${field.max}" step="${field.step}" value="${v}" ${dk} oninput="_onSpSlider(this)">` +
        `<input type="number" min="${field.min}" max="${field.max}" step="${field.step}" value="${v}" ${dk} oninput="_onSpNum(this)"></div>`;
    }
    case 'color': {
      const v = _toHex(value || '#000000');
      return `<div class="sp-row"><label>${field.label}</label>` +
        `<input type="color" value="${v}" ${dk} oninput="_onSpChange(this)"></div>`;
    }
    case 'toggle': {
      const checked = value ? 'checked' : '';
      return `<div class="sp-row"><label>${field.label}</label>` +
        `<label class="sp-toggle-wrap"><input type="checkbox" ${checked} ${dk} onchange="_onSpToggle(this)">` +
        `<span class="sp-toggle-track"></span><span class="sp-toggle-knob"></span></label></div>`;
    }
    case 'select': {
      const opts = field.options.map(([v, l]) =>
        `<option value="${v}"${value === v ? ' selected' : ''}>${l}</option>`
      ).join('');
      return `<div class="sp-row"><label>${field.label}</label>` +
        `<select ${dk} onchange="_onSpChange(this)">${opts}</select></div>`;
    }
    case 'text': {
      return `<div class="sp-row"><label>${field.label}</label>` +
        `<input type="text" value="${_escAttr(value || '')}" ${dk} oninput="_onSpChange(this)"></div>`;
    }
    default: return '';
  }
}

function _escAttr(s) { return s.replace(/"/g, '&quot;').replace(/</g, '&lt;'); }

// rgba/rgb → hex変換
function _toHex(c) {
  if (!c) return '#000000';
  if (c.startsWith('#') && (c.length === 7 || c.length === 4)) return c;
  const m = c.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
  if (m) {
    return '#' + [m[1], m[2], m[3]].map(v => parseInt(v).toString(16).padStart(2, '0')).join('');
  }
  return '#000000';
}

// DOM要素から現在の設定値を読み取る（APIにデータがない場合のフォールバック）
function _readValuesFromDOM(el) {
  const vals = {};
  vals.positionX = parseFloat(el.style.left) || 0;
  vals.positionY = parseFloat(el.style.top) || 0;
  const w = parseFloat(el.style.width);
  if (!isNaN(w)) vals.width = w;
  const h = parseFloat(el.style.height);
  if (!isNaN(h)) vals.height = h;
  vals.zIndex = getElZIndex(el);
  vals.visible = el.style.display !== 'none' ? 1 : 0;
  const cs = getComputedStyle(el);
  if (cs.backgroundColor) vals.bgColor = cs.backgroundColor;
  if (cs.borderRadius) vals.borderRadius = parseFloat(cs.borderRadius) || 0;
  if (cs.fontSize) vals.fontSize = parseFloat(cs.fontSize) / window.innerWidth * 100 || 1;
  if (cs.color) vals.textColor = cs.color;
  return vals;
}

// 設定パネルを開く（右クリック位置に直接表示）
async function openSettingsPanel(x, y) {
  if (!_selectedEditable) return;
  const itemId = _selectedEditable.dataset.editable;
  if (!itemId) return;

  const [schema, rawItemData] = await Promise.all([
    _fetchSchema(itemId),
    fetch(`/api/items/${encodeURIComponent(itemId)}`).then(r => r.json()).catch(() => ({})),
  ]);
  if (!schema || !schema.groups) return;

  // APIからデータが取れない場合（キャプチャ等）、DOM要素から現在値を読み取る
  const hasData = rawItemData && !rawItemData.error && !Array.isArray(rawItemData) && rawItemData.id;
  const itemData = hasData ? rawItemData : _readValuesFromDOM(_selectedEditable);

  _spItemId = itemId;
  _spTitle.textContent = schema.label || itemId;

  // アクションボタン（子パネル追加/削除）
  const isChild = !!_selectedEditable.dataset.parentId;
  const actionsEl = document.getElementById('sp-actions');
  if (isChild) {
    actionsEl.innerHTML = `<button class="sp-action-btn sp-danger" onclick="deleteSelectedChildPanel()">この子パネルを削除</button>`;
  } else {
    actionsEl.innerHTML = `<button class="sp-action-btn" onclick="addChildPanelToSelected()">テキスト子パネルを追加</button>`;
  }

  // グループ→HTML生成（先頭グループは開いた状態）
  _spBody.innerHTML = schema.groups.map((g, i) => {
    const open = i === 0 ? ' open' : '';
    const fields = g.fields.map(f => _renderField(f, itemData[f.key])).join('');
    return `<details class="sp-group"${open}><summary>${g.title}</summary>${fields}</details>`;
  }).join('');

  _spPanel.style.left = (x || 100) + 'px';
  _spPanel.style.top = (y || 100) + 'px';
  _spPanel.classList.add('open');
  _clampToViewport(_spPanel);
}

function closeSettingsPanel() {
  _spPanel.classList.remove('open');
  _spItemId = null;
}

// ヘッダードラッグで移動
(function() {
  const header = document.getElementById('sp-header');
  let dragging = false, offX = 0, offY = 0;
  header.addEventListener('mousedown', (e) => {
    if (e.target.classList.contains('sp-close')) return;
    dragging = true;
    offX = e.clientX - _spPanel.offsetLeft;
    offY = e.clientY - _spPanel.offsetTop;
    e.preventDefault();
  });
  document.addEventListener('mousemove', (e) => {
    if (!dragging) return;
    _spPanel.style.left = (e.clientX - offX) + 'px';
    _spPanel.style.top = (e.clientY - offY) + 'px';
  });
  document.addEventListener('mouseup', () => { dragging = false; });
})();

// 値変更ハンドラ
function _onSpSlider(el) {
  // スライダーと数値入力を同期
  const row = el.closest('.sp-row');
  const numEl = row.querySelector('input[type="number"]');
  if (numEl && numEl !== el) numEl.value = el.value;
  _scheduleSpSave(el.dataset.spKey, parseFloat(el.value));
}
function _onSpNum(el) {
  const row = el.closest('.sp-row');
  const rangeEl = row.querySelector('input[type="range"]');
  if (rangeEl && rangeEl !== el) rangeEl.value = el.value;
  _scheduleSpSave(el.dataset.spKey, parseFloat(el.value));
}
function _onSpToggle(el) {
  _scheduleSpSave(el.dataset.spKey, el.checked ? 1 : 0);
}
function _onSpChange(el) {
  _scheduleSpSave(el.dataset.spKey, el.value);
}

// デバウンス付き保存 + DOM即時反映
function _scheduleSpSave(key, value) {
  if (!_spItemId) return;
  // DOM要素に即座に適用（WebSocket応答を待たない）
  if (_selectedEditable) {
    applyCommonStyle(_selectedEditable, {[key]: value});
    // lesson_progress: 固有プロパティを子要素にも直接適用
    if (_spItemId === 'lesson_progress') {
      if (key === 'fontSize' || key === 'titleFontSize') {
        const title = document.getElementById('lesson-progress-title');
        if (title) title.style.fontSize = value + 'vw';
        if (key === 'titleFontSize') _selectedEditable.dataset.titleFontSize = value;
      }
      if (key === 'fontSize' || key === 'itemFontSize') {
        _selectedEditable.querySelectorAll('.lesson-progress-item').forEach(el =>
          el.style.fontSize = value + 'vw'
        );
        if (key === 'itemFontSize') _selectedEditable.dataset.itemFontSize = value;
      }
      // タイトル文字スタイル
      const _titleKeys = ['titleColor','titleStrokeSize','titleStrokeColor','titleStrokeOpacity'];
      const _countKeys = ['countFontSize','countColor','countStrokeSize','countStrokeColor','countStrokeOpacity'];
      if (_titleKeys.includes(key) || _countKeys.includes(key)) {
        _selectedEditable.dataset[key] = value;
      }
      if (_titleKeys.includes(key)) {
        const textEl = _selectedEditable.querySelector('.lp-title-text');
        if (textEl) {
          const d = _selectedEditable.dataset;
          if (key === 'titleColor') textEl.style.color = value;
          if (key.startsWith('titleStroke')) _applyStroke(textEl, d.titleStrokeSize, d.titleStrokeColor, d.titleStrokeOpacity);
        }
      }
      if (_countKeys.includes(key)) {
        const countEl = _selectedEditable.querySelector('.lp-title-count');
        if (countEl) {
          const d = _selectedEditable.dataset;
          if (key === 'countFontSize') countEl.style.fontSize = value + 'vw';
          if (key === 'countColor') countEl.style.color = value;
          if (key.startsWith('countStroke')) _applyStroke(countEl, d.countStrokeSize, d.countStrokeColor, d.countStrokeOpacity);
        }
      }
    }
  }
  clearTimeout(_spSaveTimer);
  _spSaveTimer = setTimeout(async () => {
    try {
      await fetch(`/api/items/${encodeURIComponent(_spItemId)}`, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({[key]: value}),
      });
    } catch (e) { console.log('設定保存エラー:', e.message); }
  }, 200);
}

// Escで閉じる
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && _spPanel.classList.contains('open')) {
    closeSettingsPanel();
  }
});
