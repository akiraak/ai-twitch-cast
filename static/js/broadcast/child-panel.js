// 子パネル管理

function addChildPanel(parentId, data) {
  const childId = data.id;
  if (childPanelEls[childId]) removeChildPanel(childId);

  // 親要素を探す
  const parentEl = document.querySelector(`[data-editable="${parentId}"]`);
  if (!parentEl) return;

  const div = document.createElement('div');
  div.className = 'child-panel';
  div.dataset.editable = childId;
  div.dataset.childPanelId = childId;
  div.dataset.parentId = parentId;

  // デフォルト座標（data に値がなければ使用）
  div.style.left = (data.positionX || 5) + '%';
  div.style.top = (data.positionY || 75) + '%';
  div.style.width = (data.width || 90) + '%';
  div.style.height = (data.height || 20) + '%';

  // 共通スタイル適用（textStroke・border・backdrop等すべて含む）
  applyCommonStyle(div, data);

  // 編集ラベル
  const labelEl = document.createElement('div');
  labelEl.className = 'edit-label';
  labelEl.textContent = data.label || 'テキスト';
  div.appendChild(labelEl);

  // テキストコンテンツ
  const textEl = document.createElement('div');
  textEl.className = 'child-text-content';
  textEl.dataset.rawContent = data.content || '';
  textEl.textContent = replaceTextVariables(data.content || '');
  if (data.textAlign) textEl.style.textAlign = data.textAlign;
  if (data.verticalAlign) textEl.style.justifyContent = data.verticalAlign === 'center' ? 'center' : data.verticalAlign === 'bottom' ? 'flex-end' : 'flex-start';
  if (data.fontFamily) { textEl.style.fontFamily = data.fontFamily; _loadGoogleFont(data.fontFamily); }
  div.appendChild(textEl);

  parentEl.appendChild(div);
  childPanelEls[childId] = div;
  setupEditable(div);
}

function removeChildPanel(childId) {
  const el = childPanelEls[childId];
  if (el) { el.remove(); delete childPanelEls[childId]; }
}

async function addChildPanelToSelected() {
  closeSettingsPanel();
  if (!_selectedEditable) return;
  const parentId = _selectedEditable.dataset.editable;
  // 子パネルには子パネルを追加不可（1階層のみ）
  if (_selectedEditable.dataset.parentId) return;
  try {
    await fetch(`/api/items/${encodeURIComponent(parentId)}/children`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ type: 'child_text', label: 'テキスト', content: '' }),
    });
  } catch (e) { console.log('子パネル追加エラー:', e.message); }
}

async function deleteSelectedChildPanel() {
  closeSettingsPanel();
  if (!_selectedEditable) return;
  const childId = _selectedEditable.dataset.editable;
  if (!_selectedEditable.dataset.parentId) return;
  try {
    await fetch(`/api/items/${encodeURIComponent(childId)}`, { method: 'DELETE' });
  } catch (e) { console.log('子パネル削除エラー:', e.message); }
}
