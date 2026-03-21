// カスタムテキストレイヤー管理

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
  textEl.dataset.rawContent = content || '';
  textEl.textContent = replaceTextVariables(content || '');
  if (layout) {
    if (layout.textAlign) textEl.style.textAlign = layout.textAlign;
    if (layout.verticalAlign) textEl.style.justifyContent = layout.verticalAlign === 'center' ? 'center' : layout.verticalAlign === 'bottom' ? 'flex-end' : 'flex-start';
    if (layout.fontFamily) { textEl.style.fontFamily = layout.fontFamily; _loadGoogleFont(layout.fontFamily); }
  }
  div.appendChild(textEl);

  customTextContainer.appendChild(div);
  customTextLayers[id] = div;
  setupEditable(div);
}

function updateCustomTextLayer(id, data) {
  const el = customTextLayers[id];
  if (!el) return;
  if (data.content != null) {
    const ct = el.querySelector('.custom-text-content');
    ct.dataset.rawContent = data.content;
    ct.textContent = replaceTextVariables(data.content);
  }
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
