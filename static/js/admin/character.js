// キャラクター設定・プロンプトレイヤー・視聴者メモ

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
    // バナー更新
    try {
      const langData = await (await fetch('/api/language')).json();
      updateCharacterBanner(data, langData);
    } catch (e2) {
      updateCharacterBanner(data, null);
    }
  } catch (e) {
    document.getElementById('char-status').textContent = 'エラー: ' + e.message;
  }
}

function updateCharacterBanner(charData, langData) {
  const nameEl = document.getElementById('cb-name');
  if (nameEl) nameEl.textContent = charData.name || '---';

  const langEl = document.getElementById('cb-lang');
  if (langEl && langData) {
    const langs = langData.languages || [];
    const pName = (langs.find(l => l.code === langData.primary) || {}).name || langData.primary || '---';
    const sName = langData.sub !== 'none' ? (langs.find(l => l.code === langData.sub) || {}).name : null;
    langEl.textContent = sName ? `${pName} + ${sName}` : pName;
  }

  const personalityEl = document.getElementById('cb-personality');
  if (personalityEl) {
    const prompt = charData.system_prompt || '';
    const match = prompt.match(/##\s*性格\s*\n([\s\S]*?)(?=\n##|$)/);
    if (match) {
      const traits = match[1]
        .split('\n')
        .map(l => l.replace(/^[-\s*]+/, '').trim())
        .filter(l => l.length > 0)
        .slice(0, 3)
        .join(' / ');
      personalityEl.textContent = traits;
      personalityEl.title = match[1].trim();
    } else {
      const firstLine = prompt.split('\n').find(l => l.trim()) || '';
      personalityEl.textContent = firstLine.substring(0, 50);
      personalityEl.title = prompt;
    }
  }

  const rulesEl = document.getElementById('cb-rules');
  if (rulesEl) {
    rulesEl.textContent = 'ルール ' + (charData.rules || []).length + '件';
  }

  const emoEl = document.getElementById('cb-emotions');
  if (emoEl) {
    const emotions = Object.keys(charData.emotions || {});
    emoEl.innerHTML = emotions.map(e => '<span class="cb-emo">' + esc(e) + '</span>').join('');
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

// --- プロンプトレイヤー表示 ---
let _layerData = {};

async function loadCharacterLayers() {
  try {
    const d = await (await fetch('/api/character/layers')).json();
    _layerData = d;

    // 第2層: ペルソナ
    const personaEl = document.getElementById('layer-persona');
    if (d.persona) {
      personaEl.innerHTML = `<div class="layer-text">${esc(d.persona)}</div>`;
    } else {
      personaEl.innerHTML = '<div class="layer-empty">未生成（応答が10件以上になると自動生成されます）</div>';
    }

    // 第3層: セルフメモ
    const selfEl = document.getElementById('layer-self-note');
    if (d.self_note) {
      selfEl.innerHTML = `<div class="layer-text">${esc(d.self_note)}</div>`;
    } else {
      selfEl.innerHTML = '<div class="layer-empty">未生成（配信中の会話から自動生成されます）</div>';
    }

    // 第4層: 視聴者メモ
    const viewerEl = document.getElementById('layer-viewer-notes');
    const countEl = document.getElementById('layer-viewer-count');
    if (countEl) countEl.textContent = d.viewer_notes && d.viewer_notes.length > 0 ? `(${d.viewer_notes.length}人)` : '';
    if (d.viewer_notes && d.viewer_notes.length > 0) {
      viewerEl.innerHTML = d.viewer_notes.map(u =>
        `<div class="viewer-note-item" data-user-id="${u.id}">` +
        `<div class="viewer-note-header">` +
        `<span class="viewer-note-name">${esc(u.name)}</span>` +
        `<span class="viewer-note-count">${u.comment_count}回</span>` +
        `<button class="viewer-note-edit-btn" onclick="startViewerNoteEdit(this, ${u.id}, '${esc(u.name)}')">編集</button>` +
        `</div>` +
        `<div class="viewer-note-text">${esc(u.note)}</div>` +
        `</div>`
      ).join('');
    } else {
      viewerEl.innerHTML = '<div class="layer-empty">視聴者メモなし</div>';
    }
  } catch (e) {
    document.getElementById('layer-persona').innerHTML = '<div class="layer-empty">サーバー再起動後に表示されます</div>';
    document.getElementById('layer-self-note').innerHTML = '<div class="layer-empty">サーバー再起動後に表示されます</div>';
    document.getElementById('layer-viewer-notes').innerHTML = '<div class="layer-empty">サーバー再起動後に表示されます</div>';
  }
}

// --- 視聴者メモ編集 ---
function startViewerNoteEdit(btn, userId, userName) {
  const item = btn.closest('.viewer-note-item');
  const textEl = item.querySelector('.viewer-note-text');
  const currentText = textEl.textContent;
  textEl.style.display = 'none';
  btn.style.display = 'none';

  const editDiv = document.createElement('div');
  editDiv.className = 'viewer-note-edit';
  editDiv.innerHTML = `<textarea rows="3">${esc(currentText)}</textarea>` +
    `<div class="btn-row" style="margin-top:4px;">` +
    `<button style="font-size:0.7rem; padding:3px 10px;" onclick="saveViewerNote(this, ${userId})">保存</button>` +
    `<button class="secondary" style="font-size:0.7rem; padding:3px 10px;" onclick="cancelViewerNoteEdit(this)">キャンセル</button>` +
    `</div>`;
  item.appendChild(editDiv);
}

function cancelViewerNoteEdit(btn) {
  const item = btn.closest('.viewer-note-item');
  item.querySelector('.viewer-note-edit').remove();
  item.querySelector('.viewer-note-text').style.display = '';
  item.querySelector('.viewer-note-edit-btn').style.display = '';
}

async function saveViewerNote(btn, userId) {
  const item = btn.closest('.viewer-note-item');
  const text = item.querySelector('.viewer-note-edit textarea').value.trim();
  try {
    const res = await fetch('/api/character/viewer-note', {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({user_id: userId, note: text}),
    });
    const d = await res.json();
    if (d.ok) loadCharacterLayers();
  } catch (e) {
    console.error('視聴者メモ保存失敗:', e);
  }
}

// --- レイヤー編集 ---
function startLayerEdit(type) {
  const key = type === 'self-note' ? 'self_note' : type;
  const textarea = document.getElementById(`layer-${type}-textarea`);
  textarea.value = _layerData[key] || '';
  document.getElementById(`layer-${type}`).style.display = 'none';
  document.getElementById(`layer-${type}-edit`).style.display = 'block';
}

function cancelLayerEdit(type) {
  document.getElementById(`layer-${type}-edit`).style.display = 'none';
  document.getElementById(`layer-${type}`).style.display = '';
}

async function saveLayerMemory(type) {
  const textarea = document.getElementById(`layer-${type}-textarea`);
  const text = textarea.value.trim();
  try {
    const res = await fetch(`/api/character/${type}`, {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({text}),
    });
    const d = await res.json();
    if (d.ok) {
      cancelLayerEdit(type);
      loadCharacterLayers();
    }
  } catch (e) {
    console.error('レイヤー保存失敗:', e);
  }
}

async function generatePersonaFromPrompt() {
  if (!await showConfirm('システムプロンプトからペルソナをAI生成します。現在のペルソナは上書きされます。', { title: 'ペルソナ初期生成', okLabel: '生成' })) return;
  const personaEl = document.getElementById('layer-persona');
  personaEl.innerHTML = '<div class="layer-empty">AI生成中...</div>';
  try {
    const res = await fetch('/api/character/persona/generate', {method: 'POST'});
    const d = await res.json();
    if (d.ok) {
      loadCharacterLayers();
    }
  } catch (e) {
    console.error('ペルソナ生成失敗:', e);
    personaEl.innerHTML = '<div class="layer-empty">生成失敗</div>';
  }
}

async function regenerateSelfNote() {
  if (!await showConfirm('直近の会話からセルフメモをAI再生成します。現在のメモは上書きされます。', { title: 'セルフメモ再生成', okLabel: '生成' })) return;
  const selfEl = document.getElementById('layer-self-note');
  selfEl.innerHTML = '<div class="layer-empty">AI生成中...</div>';
  try {
    const res = await fetch('/api/character/self-note/generate', {method: 'POST'});
    const d = await res.json();
    if (d.ok) {
      loadCharacterLayers();
    }
  } catch (e) {
    console.error('セルフメモ生成失敗:', e);
    selfEl.innerHTML = '<div class="layer-empty">生成失敗</div>';
  }
}
