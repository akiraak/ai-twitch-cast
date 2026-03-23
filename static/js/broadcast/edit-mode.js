// 編集モード（ドラッグ・リサイズ・スナップガイド・editSave）

let _editingEl = null;

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

function getElZIndex(el) {
  if (el._savedZIndex != null) return parseInt(el._savedZIndex) || 0;
  return parseInt(el.style.zIndex) || parseInt(getComputedStyle(el).zIndex) || 0;
}

function _clampToViewport(el) {
  const rect = el.getBoundingClientRect();
  const maxX = window.innerWidth - rect.width;
  const maxY = window.innerHeight - rect.height;
  if (rect.left > maxX) el.style.left = Math.max(0, maxX) + 'px';
  if (rect.top > maxY) el.style.top = Math.max(0, maxY) + 'px';
}

// 右クリック → 直接設定パネルを開く
function showContextMenu(el, x, y) {
  selectEditable(el);
  _selectedEditable = el;
  el.classList.add('selected');
  openSettingsPanel(x, y);
}

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
  if (el._savedZIndex == null) {
    el._savedZIndex = el.style.zIndex || getComputedStyle(el).zIndex || '0';
  }
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
  if (_selectedEditable) {
    _selectedEditable.classList.remove('selected');
    _selectedEditable = null;
  }
}

// パーツ外クリックで閉じる
document.addEventListener('mousedown', (e) => {
  // 設定パネル内のクリックは無視
  if (_spPanel.contains(e.target)) return;
  {
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

// === スナップ計算 ===
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

function _getRefSize(el) {
  // 子パネルは親パネルの幅/高さを基準にする
  if (el.dataset.parentId) {
    const parentEl = el.parentElement;
    return { w: parentEl.offsetWidth, h: parentEl.offsetHeight };
  }
  return { w: window.innerWidth, h: window.innerHeight };
}

// === ドラッグ移動 ===
function startDrag(el, e) {
  el.classList.add('dragging');
  const startX = e.clientX, startY = e.clientY;
  const rect = el.getBoundingClientRect();
  const origVisualLeft = rect.left, origVisualTop = rect.top;
  const elW = rect.width, elH = rect.height;
  let didDrag = false;
  const isChild = !!el.dataset.parentId;
  const otherRects = isChild ? [] : getOtherEditableRects(el);

  function onMove(e) {
    didDrag = true;
    let newLeft = origVisualLeft + e.clientX - startX;
    let newTop = origVisualTop + e.clientY - startY;

    if (isChild) {
      // 子パネル: 親パネルの端・中央にスナップ
      const parentRect = el.parentElement.getBoundingClientRect();
      const pw = parentRect.width, ph = parentRect.height;
      const vLines = [{ px: parentRect.left, isCenter: false }, { px: parentRect.left + pw / 2, isCenter: true }, { px: parentRect.right, isCenter: false }];
      const hLines = [{ px: parentRect.top, isCenter: false }, { px: parentRect.top + ph / 2, isCenter: true }, { px: parentRect.bottom, isCenter: false }];
      // 兄弟子パネルの端・中央もスナップ対象
      el.parentElement.querySelectorAll('.child-panel').forEach(sib => {
        if (sib === el || sib.style.display === 'none') return;
        const sr = sib.getBoundingClientRect();
        if (sr.width === 0 && sr.height === 0) return;
        vLines.push({ px: sr.left }, { px: sr.right }, { px: (sr.left + sr.right) / 2 });
        hLines.push({ px: sr.top }, { px: sr.bottom }, { px: (sr.top + sr.bottom) / 2 });
      });
      const vEdges = [newLeft, newLeft + elW, newLeft + elW / 2];
      const hEdges = [newTop, newTop + elH, newTop + elH / 2];
      const snappedV = applySnap(vEdges, vLines, SNAP_THRESHOLD_PX);
      const snappedH = applySnap(hEdges, hLines, SNAP_THRESHOLD_PX);
      if (snappedV) newLeft -= snappedV.delta;
      if (snappedH) newTop -= snappedH.delta;
      el.style.left = ((newLeft - parentRect.left) / pw * 100) + '%';
      el.style.top = ((newTop - parentRect.top) / ph * 100) + '%';
      el.style.transform = 'none';
      showActiveGuides(snappedV, snappedH);
    } else {
      const ww = window.innerWidth, wh = window.innerHeight;
      const { vLines, hLines } = calcSnapPoints(otherRects, ww, wh);
      const vEdges = [newLeft, newLeft + elW, newLeft + elW / 2];
      const hEdges = [newTop, newTop + elH, newTop + elH / 2];

      const snappedV = applySnap(vEdges, vLines, SNAP_THRESHOLD_PX);
      const snappedH = applySnap(hEdges, hLines, SNAP_THRESHOLD_PX);

      if (snappedV) newLeft -= snappedV.delta;
      if (snappedH) newTop -= snappedH.delta;

      // 字幕パネルは水平中央固定、垂直のみ移動（bottom基準）
      if (el.dataset.editable === 'subtitle') {
        const bottomPct = 100 - ((newTop + elH) / wh * 100);
        el.style.bottom = bottomPct + '%';
        el.style.top = '';
        el.style.left = '50%';
        el.style.transform = 'translateX(-50%)';
      } else {
        el.style.left = (newLeft / ww * 100) + '%';
        el.style.top = (newTop / wh * 100) + '%';
        el.style.transform = 'none';
      }

      showActiveGuides(snappedV, snappedH);
    }
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

// === 編集可能要素のセットアップ ===
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
      const hc = handle.classList;
      const isLeft = hc.contains('sw') || hc.contains('nw') || hc.contains('w');
      const isRight = hc.contains('se') || hc.contains('ne') || hc.contains('e');
      const isTop = hc.contains('ne') || hc.contains('nw') || hc.contains('n');
      const isBottom = hc.contains('se') || hc.contains('sw') || hc.contains('s');
      const resizeH = isLeft || isRight;
      const resizeV = isTop || isBottom;
      const isChild = !!el.dataset.parentId;
      const otherRects = isChild ? [] : getOtherEditableRects(el);

      function onMove(e) {
        const dx = e.clientX - startX, dy = e.clientY - startY;
        const ref = _getRefSize(el);
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

        // スナップ対応（ルート: 画面+他パーツ、子: 親の端・中央+兄弟）
        let snapVLines, snapHLines;
        if (isChild) {
          // 子パネル: 親パネルの端・中央（offsetピクセル座標）
          snapVLines = [{ px: 0 }, { px: ref.w / 2, isCenter: true }, { px: ref.w }];
          snapHLines = [{ px: 0 }, { px: ref.h / 2, isCenter: true }, { px: ref.h }];
          el.parentElement.querySelectorAll('.child-panel').forEach(sib => {
            if (sib === el || sib.style.display === 'none') return;
            const sl = sib.offsetLeft, st = sib.offsetTop, sw = sib.offsetWidth, sh = sib.offsetHeight;
            snapVLines.push({ px: sl }, { px: sl + sw }, { px: sl + sw / 2 });
            snapHLines.push({ px: st }, { px: st + sh }, { px: st + sh / 2 });
          });
        } else {
          const sp = calcSnapPoints(otherRects, ref.w, ref.h);
          snapVLines = sp.vLines; snapHLines = sp.hLines;
        }
        {
          const vEdges = resizeH ? (isLeft ? [newLeft] : [newLeft + newW]) : [];
          if (resizeH) vEdges.push(newLeft + newW / 2);
          const hEdges = resizeV ? (isTop ? [newTop] : [newTop + newH]) : [];
          if (resizeV) hEdges.push(newTop + newH / 2);

          const snappedV = resizeH ? applySnap(vEdges, snapVLines, SNAP_THRESHOLD_PX) : null;
          const snappedH = resizeV ? applySnap(hEdges, snapHLines, SNAP_THRESHOLD_PX) : null;

          if (snappedV) {
            if (isLeft) { newLeft -= snappedV.delta; newW += snappedV.delta; }
            else { newW -= snappedV.delta; }
          }
          if (snappedH) {
            if (isTop) { newTop -= snappedH.delta; newH += snappedH.delta; }
            else { newH -= snappedH.delta; }
          }
          if (isChild) {
            // ガイド線を画面座標に変換して表示
            const parentRect = el.parentElement.getBoundingClientRect();
            if (snappedV) snappedV.line = { ...snappedV.line, px: snappedV.line.px + parentRect.left };
            if (snappedH) snappedH.line = { ...snappedH.line, px: snappedH.line.px + parentRect.top };
          }
          showActiveGuides(snappedV, snappedH);
        }

        if (resizeH) el.style.width = (newW / ref.w * 100) + '%';
        if (resizeV) el.style.height = (newH / ref.h * 100) + '%';
        if (isLeft) { el.style.left = (newLeft / ref.w * 100) + '%'; el.style.transform = 'none'; }
        if (isTop) { el.style.top = (newTop / ref.h * 100) + '%'; el.style.transform = 'none'; }
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

// === レイアウト保存 ===
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
    if (!item.skipVisible) {
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

  // lesson_text固有プロパティの保存
  if (overlaySettings.lesson_text) {
    const ltp = document.getElementById('lesson-text-panel');
    if (ltp) {
      const maxH = parseFloat(ltp.style.maxHeight);
      if (!isNaN(maxH)) overlaySettings.lesson_text.maxHeight = maxH;
      const ltc = document.getElementById('lesson-text-content');
      if (ltc) {
        const fs = parseFloat(ltc.style.fontSize);
        if (!isNaN(fs)) overlaySettings.lesson_text.fontSize = fs;
        const lh = parseFloat(ltc.style.lineHeight);
        if (!isNaN(lh)) overlaySettings.lesson_text.lineHeight = lh;
      }
    }
  }

  // アイテム固有プロパティの保存（保存漏れ修正）
  if (overlaySettings.subtitle) {
    // 字幕は水平中央固定なのでpositionXは常に50、positionYは不使用（bottom基準）
    overlaySettings.subtitle.positionX = 50;
    overlaySettings.subtitle.positionY = 0;
    const bottom = parseFloat(subtitleEl.style.bottom);
    if (!isNaN(bottom)) overlaySettings.subtitle.bottom = bottom;
    const respFs = parseFloat(subtitleEl.querySelector('.speech')?.style.fontSize);
    if (!isNaN(respFs)) overlaySettings.subtitle.fontSize = respFs;
    const maxW = parseFloat(subtitleEl.style.maxWidth);
    if (!isNaN(maxW)) overlaySettings.subtitle.maxWidth = maxW;
    overlaySettings.subtitle.fadeDuration = parseFloat(subtitleEl.dataset.fadeDuration) || 3;
    const bgOp = parseFloat(subtitleEl.style.getPropertyValue('--bg-opacity'));
    if (!isNaN(bgOp)) overlaySettings.subtitle.bgOpacity = bgOp;
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

  // 子パネルのレイアウト保存
  for (const [childId, el] of Object.entries(childPanelEls)) {
    const layout = {
      positionX: parseFloat(el.style.left) || 0,
      positionY: parseFloat(el.style.top) || 0,
      width: parseFloat(el.style.width) || 90,
      height: parseFloat(el.style.height) || 20,
      zIndex: getRealZIndex(el, 10),
    };
    try {
      await fetch(`/api/items/${encodeURIComponent(childId)}/layout`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(layout),
      });
    } catch (e) {}
  }
  _saving = false;
}

// === 編集モード初期化 ===
function initEditMode() {
  // 授業テキストパネルを編集用に表示（プレビュー用テキスト付き）
  const ltp = document.getElementById('lesson-text-panel');
  if (ltp) {
    ltp.style.display = 'block';
    ltp.style.opacity = '1';
    const ltc = document.getElementById('lesson-text-content');
    if (ltc && !ltc.textContent.trim()) ltc.textContent = '授業テキストのプレビュー\n\nここに教材の内容が表示されます。\n背景・文字・位置を右クリックで編集できます。';
  }

  document.querySelectorAll('[data-editable]').forEach(setupEditable);

  // 非editableエリアでもブラウザデフォルトの右クリックメニューを抑制
  document.addEventListener('contextmenu', (e) => {
    if (!e.target.closest('[data-editable]')) e.preventDefault();
  });

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
