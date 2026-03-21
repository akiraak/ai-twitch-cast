// ウィンドウキャプチャ・カスタムテキスト・子パネル管理UI

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
  const el = document.getElementById('capture-panels');
  if (!saved.length) { el.innerHTML = ''; return; }
  const activeByName = {};
  for (const a of active) { if (a.name) activeByName[a.name] = a; }
  _capSavedList = saved;
  _capActiveByName = activeByName;
  el.innerHTML = saved.map((s, idx) => {
    const wname = s.window_name || '';
    const a = activeByName[wname];
    const isActive = !!a;
    const label = escHtml(s.label || wname);
    const statusBadge = isActive
      ? '<span style="color:#4caf50; font-size:0.7rem; margin-left:6px;">● 配信中</span>'
      : '<span style="color:#999; font-size:0.7rem; margin-left:6px;">○ 停止</span>';
    return `<details class="panel-item" data-cap-idx="${idx}">
      <summary>キャプチャ - ${label}${statusBadge}<button class="summary-delete-btn" data-action="delete" data-idx="${idx}" onclick="event.preventDefault()">削除</button></summary>
      <div class="panel-body">
      </div>
    </details>`;
  }).join('');
  // 共通コントロールを注入（broadcast_itemsのcapture:{id}セクション）
  saved.forEach((s, idx) => {
    const detail = el.querySelector(`[data-cap-idx="${idx}"]`);
    if (!detail) return;
    const biId = `capture:${s.id}`;
    detail.dataset.section = biId;
    _injectCommonProps(detail, biId);
  });
  _initToggles(el);
  el.onclick = _capListClick;
  // layoutSettingsに値があればUIに反映（loadLayout完了後の再描画対応）
  if (Object.keys(layoutSettings).length > 0) {
    _applyLayoutToUI(layoutSettings);
  }
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
  const el = document.getElementById('custom-text-panels');
  if (!items.length) { el.innerHTML = ''; return; }
  el.innerHTML = items.map(item => {
    const label = escHtml(item.label || `テキスト ${item.id}`);
    return `<details class="panel-item" data-ct-id="${item.id}">
      <summary>テキスト - ${label}<button class="summary-delete-btn" onclick="event.preventDefault(); deleteCustomText(${item.id})">削除</button></summary>
      <div class="panel-body">
        ${renderTextEditUI({
          label: item.label,
          content: item.content,
          onLabelChange: `updateCustomText(${item.id}, {label: this.value})`,
          onContentChange: `updateCustomText(${item.id}, {content: this.value})`,
        })}
      </div>
    </details>`;
  }).join('');
  // 共通コントロール + 子パネルUIを注入
  items.forEach(item => {
    const detail = el.querySelector(`[data-ct-id="${item.id}"]`);
    if (!detail) return;
    const biId = `customtext:${item.id}`;
    detail.dataset.section = biId;
    _injectCommonProps(detail, biId);
    const panelBody = detail.querySelector('.panel-body');
    if (panelBody) injectChildPanelSection(panelBody, biId);
  });
  _initToggles(el);
  // layoutSettingsに値があればUIに反映（loadLayout完了後の再描画対応）
  if (Object.keys(layoutSettings).length > 0) {
    _applyLayoutToUI(layoutSettings);
  }
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

// --- 子パネル管理 ---

async function loadChildPanels(parentId, containerEl) {
  try {
    const item = await (await fetch(`/api/items/${encodeURIComponent(parentId)}`)).json();
    const children = item.children || [];
    containerEl.innerHTML = '';
    if (!children.length) return;
    children.forEach(child => {
      const childEl = document.createElement('details');
      childEl.className = 'panel-item child-panel-item';
      childEl.dataset.section = child.id;
      childEl.innerHTML = `
        <summary>子テキスト - ${escHtml(child.label || 'テキスト')}
          <button class="summary-delete-btn" onclick="event.preventDefault(); deleteChildPanel('${escHtml(child.id)}', '${escHtml(parentId)}')">削除</button>
        </summary>
        <div class="panel-body">
          ${renderTextEditUI({
            label: child.label || '',
            content: child.content || '',
            onLabelChange: `updateChildPanel('${escHtml(child.id)}', {label: this.value})`,
            onContentChange: `updateChildPanel('${escHtml(child.id)}', {content: this.value})`,
          })}
        </div>`;
      containerEl.appendChild(childEl);
      // 共通プロパティコントロールを注入
      _injectCommonProps(childEl, child.id);
    });
    _initToggles(containerEl);
    // layoutSettingsに値があればUIに反映
    if (Object.keys(layoutSettings).length > 0) {
      _applyLayoutToUI(layoutSettings);
    }
  } catch (e) {}
}

async function addChildPanel(parentId) {
  await api('POST', `/api/items/${encodeURIComponent(parentId)}/children`, { type: 'child_text', label: 'テキスト', content: '' });
  showToast('子パネル追加', 'success');
  // リロード
  const container = document.querySelector(`[data-children-for="${parentId}"]`);
  if (container) loadChildPanels(parentId, container);
}

async function updateChildPanel(childId, changes) {
  const item = await (await fetch(`/api/items/${encodeURIComponent(childId)}`)).json();
  if (!item || item.error) return;
  await api('PUT', `/api/items/${encodeURIComponent(childId)}`, changes);
}

async function deleteChildPanel(childId, parentId) {
  if (!await showConfirm('この子パネルを削除しますか？', { title: '削除', okLabel: '削除', danger: true })) return;
  await api('DELETE', `/api/items/${encodeURIComponent(childId)}`);
  showToast('子パネル削除', 'success');
  const container = document.querySelector(`[data-children-for="${parentId}"]`);
  if (container) loadChildPanels(parentId, container);
}
