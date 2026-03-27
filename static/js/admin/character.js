// キャラクター設定・プロンプトレイヤー・視聴者メモ

// --- 自動保存（デバウンス） ---
let _autoSaveTimer = null;
let _autoSaveLoading = false;  // loadCharacter中はトリガーしない

function _scheduleAutoSave() {
  if (_autoSaveLoading) return;
  if (_autoSaveTimer) clearTimeout(_autoSaveTimer);
  const statusEl = document.getElementById('char-status');
  if (statusEl) statusEl.textContent = '変更あり…';
  _autoSaveTimer = setTimeout(() => {
    _autoSaveTimer = null;
    saveCharacter();
  }, 800);
}

// --- キャラクター切替 ---
let _currentChar = 'teacher';  // role: 'teacher' or 'student'
let _currentCharId = null;     // DB上のキャラクターID
let _allCharacters = [];       // 全キャラクター一覧
const _roleVrmCategories = { teacher: 'avatar', student: 'avatar2' };

function _currentCharVrmCategory() {
  return _roleVrmCategories[_currentChar] || 'avatar';
}

async function loadCharacterList() {
  try {
    const chars = await (await fetch('/api/characters')).json();
    _allCharacters = chars;
    const container = document.getElementById('char-selector');
    if (!container) return;
    container.innerHTML = '';
    for (const c of chars) {
      const btn = document.createElement('button');
      btn.className = 'char-sel-btn' + (c.role === _currentChar ? ' active' : '');
      btn.dataset.char = c.role || 'teacher';
      btn.dataset.charId = c.id;
      btn.textContent = c.name;
      btn.addEventListener('click', () => switchCharacter(c.role || 'teacher', c.id, btn));
      container.appendChild(btn);
    }
    // 初期選択
    if (chars.length > 0 && !_currentCharId) {
      const teacher = chars.find(c => c.role === 'teacher') || chars[0];
      _currentCharId = teacher.id;
    }
    // 配信画面タブのアバターラベルをロール名で更新
    const roleLabel = { teacher: { el: 'avatar1-label', label: 'メイン' }, student: { el: 'avatar2-label', label: 'サブ' } };
    for (const c of chars) {
      const info = roleLabel[c.role];
      const el = info && document.getElementById(info.el);
      if (el) el.textContent = `アバター（${info.label}）`;
    }
  } catch (e) {
    console.error('キャラクター一覧取得失敗:', e);
  }
}

function switchCharacter(role, charId, btn) {
  _currentChar = role;
  _currentCharId = charId;
  // ボタンのactive切替
  document.querySelectorAll('.char-sel-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  // VRMファイルリスト更新
  _loadCharVrmFiles();
  // ライティングスライダー切替 + プリセット再読み込み
  if (typeof _loadCharLighting === 'function') _loadCharLighting();
  if (typeof loadLightingPresets === 'function') loadLightingPresets();
  // キャラクター設定をIDで読み込み
  loadCharacterById(charId);
  // レイヤー（ペルソナ・セルフメモ・視聴者メモ）をリロード
  loadCharacterLayers();
}

function _loadCharVrmFiles() {
  const category = _currentCharVrmCategory();
  const listEl = document.getElementById('char-vrm-files-list');
  const statusEl = document.getElementById('char-vrm-upload-status');
  if (statusEl) statusEl.textContent = '';
  // loadCategoryFiles相当だが、対象要素を差し替える
  // files.jsのloadCategoryFilesはIDベースなので、手動でフェッチ
  if (!listEl) return;
  fetch('/api/files/' + category + '/list')
    .then(r => r.json())
    .then(data => {
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
        row.innerHTML = `
          <div style="display:flex; gap:8px; align-items:center;">
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
        btn.addEventListener('click', async () => {
          await selectFile(btn.dataset.category, btn.dataset.selectFile);
          _loadCharVrmFiles();
        }));
      listEl.querySelectorAll('[data-delete-file]').forEach(btn =>
        btn.addEventListener('click', async () => {
          await deleteFile(btn.dataset.category, btn.dataset.deleteFile);
          _loadCharVrmFiles();
        }));
    })
    .catch(e => {
      listEl.innerHTML = '<div style="color:#c62828; font-size:0.85rem;">読み込み失敗: ' + esc(e.message) + '</div>';
    });
}

async function _uploadCharVrm(input) {
  const files = input.files;
  if (!files || files.length === 0) return;
  const category = _currentCharVrmCategory();
  const statusEl = document.getElementById('char-vrm-upload-status');
  for (const file of files) {
    if (statusEl) { statusEl.textContent = 'アップロード中: ' + file.name + '...'; statusEl.style.color = '#6a5590'; }
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await fetch('/api/files/' + category + '/upload', { method: 'POST', body: formData });
      const data = await res.json();
      if (data.ok) showToast('アップロード完了: ' + (data.file || file.name), 'success');
      else showToast('アップロード失敗: ' + (data.error || ''), 'error');
    } catch (e) {
      showToast('アップロード失敗: ' + e.message, 'error');
    }
  }
  input.value = '';
  if (statusEl) statusEl.textContent = '';
  _loadCharVrmFiles();
}

// --- 言語タブ切替 ---
let _currentLangSuffix = '';  // '', '_en', '_bilingual'

function switchLangTab(suffix, btn) {
  _currentLangSuffix = suffix;
  document.querySelectorAll('.lang-tab').forEach(t => t.classList.remove('active'));
  if (btn) btn.classList.add('active');
  document.querySelectorAll('.lang-pane').forEach(p => {
    p.style.display = p.dataset.langPane === suffix ? '' : 'none';
  });
}

// --- キャラクター設定 ---
let _charEmotions = {};
let _charBlendshapes = {};

async function loadCharacter() {
  // 初回はキャラクターリストをロードしてからデフォルト（先生）を読み込む
  await loadCharacterList();
  if (_currentCharId) {
    await loadCharacterById(_currentCharId);
  } else {
    // フォールバック: 旧API
    await _loadCharacterFromApi('/api/character');
  }
}

async function loadCharacterById(charId) {
  await _loadCharacterFromApi('/api/character/' + charId);
}

async function _loadCharacterFromApi(url) {
  _autoSaveLoading = true;
  try {
    const data = await (await fetch(url)).json();
    if (data.ok === false) {
      document.getElementById('char-status').textContent = 'エラー: ' + (data.error || '');
      return;
    }
    _currentCharId = data.id;
    document.getElementById('char-name').value = data.name || '';
    // 日本語版
    document.getElementById('char-prompt').value = data.system_prompt || '';
    renderRules(data.rules || []);
    document.getElementById('char-tts-style').value = data.tts_style || '';
    // 英語版
    document.getElementById('char-prompt-en').value = data.system_prompt_en || '';
    renderRules(data.rules_en || [], '_en');
    document.getElementById('char-tts-style-en').value = data.tts_style_en || '';
    // バイリンガル版
    document.getElementById('char-prompt-bilingual').value = data.system_prompt_bilingual || '';
    renderRules(data.rules_bilingual || [], '_bilingual');
    document.getElementById('char-tts-style-bilingual').value = data.tts_style_bilingual || '';
    // 共通
    _charEmotions = data.emotions || {};
    _charBlendshapes = data.emotion_blendshapes || {};
    document.getElementById('char-tts-voice').value = data.tts_voice || '';
    renderEmotions();
    renderBlendshapes();
    // 言語タブを日本語に戻す
    switchLangTab('', document.querySelector('.lang-tab[data-lang=""]'));
    document.getElementById('char-status').textContent = '';
    // バナー更新（先生のみ）
    if (_currentChar === 'teacher') {
      try {
        const langData = await (await fetch('/api/language')).json();
        updateCharacterBanner(data, langData);
      } catch (e2) {
        updateCharacterBanner(data, null);
      }
    }
  } catch (e) {
    document.getElementById('char-status').textContent = 'エラー: ' + e.message;
  } finally {
    _autoSaveLoading = false;
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

function renderRules(rules, suffix = '') {
  const el = document.getElementById('char-rules' + suffix);
  el.innerHTML = '';
  const cls = 'char-rule' + suffix.replace(/_/g, '-');
  rules.forEach((rule) => {
    const row = document.createElement('div');
    row.style.cssText = 'display:flex; gap:4px; margin-bottom:3px;';
    row.innerHTML = `<input type="text" class="${cls} text-input" value="${escHtml(rule)}" style="flex:1; padding:2px 6px; font-size:0.8rem;">
      <button class="danger" style="font-size:0.7rem; padding:2px 6px;" onclick="this.parentElement.remove(); _scheduleAutoSave()">×</button>`;
    el.appendChild(row);
  });
}

function addRule(suffix = '') {
  const el = document.getElementById('char-rules' + suffix);
  const cls = 'char-rule' + suffix.replace(/_/g, '-');
  const row = document.createElement('div');
  row.style.cssText = 'display:flex; gap:4px; margin-bottom:3px;';
  row.innerHTML = `<input type="text" class="${cls} text-input" value="" style="flex:1; padding:2px 6px; font-size:0.8rem;">
    <button class="danger" style="font-size:0.7rem; padding:2px 6px;" onclick="this.parentElement.remove(); _scheduleAutoSave()">×</button>`;
  el.appendChild(row);
}

function collectRules(suffix = '') {
  const cls = 'char-rule' + suffix.replace(/_/g, '-');
  return [...document.querySelectorAll('.' + cls)].map(el => el.value).filter(v => v.trim());
}

function renderEmotions() {
  const el = document.getElementById('char-emotions');
  el.innerHTML = '';
  for (const [key, desc] of Object.entries(_charEmotions)) {
    const row = document.createElement('div');
    row.style.cssText = 'display:flex; gap:4px; margin-bottom:3px;';
    row.innerHTML = `<input type="text" class="emo-key text-input" value="${escHtml(key)}" style="width:70px; padding:2px 6px; font-size:0.8rem;" placeholder="キー">
      <input type="text" class="emo-desc text-input" value="${escHtml(desc)}" style="flex:1; padding:2px 6px; font-size:0.8rem;" placeholder="説明">
      <button class="danger" style="font-size:0.7rem; padding:2px 6px;" onclick="this.parentElement.remove(); _scheduleAutoSave()">×</button>`;
    el.appendChild(row);
  }
}

function addEmotion() {
  const el = document.getElementById('char-emotions');
  const row = document.createElement('div');
  row.style.cssText = 'display:flex; gap:4px; margin-bottom:3px;';
  row.innerHTML = `<input type="text" class="emo-key text-input" value="" style="width:70px; padding:2px 6px; font-size:0.8rem;" placeholder="キー">
    <input type="text" class="emo-desc text-input" value="" style="flex:1; padding:2px 6px; font-size:0.8rem;" placeholder="説明">
    <button class="danger" style="font-size:0.7rem; padding:2px 6px;" onclick="this.parentElement.remove(); _scheduleAutoSave()">×</button>`;
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
    <button class="danger" style="font-size:0.65rem; padding:1px 4px;" onclick="this.parentElement.remove(); _scheduleAutoSave()">×</button>`;
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
  const statusEl = document.getElementById('char-status');
  try {
    const body = {
      name: document.getElementById('char-name').value,
      system_prompt: document.getElementById('char-prompt').value,
      rules: collectRules(),
      emotions: collectEmotions(),
      emotion_blendshapes: collectBlendshapes(),
      tts_voice: document.getElementById('char-tts-voice').value || null,
      tts_style: document.getElementById('char-tts-style').value || null,
      // 英語版
      system_prompt_en: document.getElementById('char-prompt-en').value || null,
      rules_en: collectRules('_en').length > 0 ? collectRules('_en') : null,
      tts_style_en: document.getElementById('char-tts-style-en').value || null,
      // バイリンガル版
      system_prompt_bilingual: document.getElementById('char-prompt-bilingual').value || null,
      rules_bilingual: collectRules('_bilingual').length > 0 ? collectRules('_bilingual') : null,
      tts_style_bilingual: document.getElementById('char-tts-style-bilingual').value || null,
    };
    const url = _currentCharId ? '/api/character/' + _currentCharId : '/api/character';
    const res = await api('PUT', url, body);
    if (res?.ok) {
      statusEl.textContent = '保存しました';
      setTimeout(() => { if (statusEl.textContent === '保存しました') statusEl.textContent = ''; }, 2000);
    } else {
      statusEl.textContent = '保存失敗';
    }
  } catch (e) {
    statusEl.textContent = 'エラー: ' + e.message;
  }
}

// 静的フィールドの自動保存リスナー
['char-name', 'char-prompt', 'char-tts-style',
 'char-prompt-en', 'char-tts-style-en',
 'char-prompt-bilingual', 'char-tts-style-bilingual'].forEach(id => {
  document.getElementById(id)?.addEventListener('input', _scheduleAutoSave);
});
document.getElementById('char-tts-voice')?.addEventListener('change', _scheduleAutoSave);

// 動的フィールド（ルール・感情・BlendShape）のイベント委譲
['char-rules', 'char-rules-en', 'char-rules-bilingual',
 'char-emotions', 'char-blendshapes'].forEach(id => {
  document.getElementById(id)?.addEventListener('input', _scheduleAutoSave);
  document.getElementById(id)?.addEventListener('change', _scheduleAutoSave);
});

// --- プロンプトレイヤー表示 ---
let _layerData = {};

async function loadCharacterLayers() {
  try {
    const url = _currentCharId ? `/api/character/${_currentCharId}/layers` : '/api/character/layers';
    const d = await (await fetch(url)).json();
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

// --- ボイスサンプル ---
async function voiceSample() {
  const btn = document.getElementById('btn-voice-sample');
  const status = document.getElementById('voice-sample-status');
  const voice = document.getElementById('char-tts-voice').value || null;
  const style = document.getElementById('char-tts-style').value || null;
  // avatar_idはキャラクターのroleから
  const avatarId = _currentChar || 'teacher';
  btn.disabled = true;
  status.textContent = '生成中...';
  try {
    await api('POST', '/api/tts/voice-sample', { voice, style, avatar_id: avatarId });
    status.textContent = '再生中';
    setTimeout(() => { status.textContent = ''; }, 5000);
  } catch (e) {
    status.textContent = 'エラー: ' + e.message;
  } finally {
    btn.disabled = false;
  }
}

// --- 発話設定 ---
async function loadSpeechSettings() {
  try {
    const d = await (await fetch('/api/speech/settings')).json();
    const slider = document.getElementById('speech-max-chars');
    const label = document.getElementById('speech-max-chars-val');
    if (slider) slider.value = d.max_chars;
    if (label) label.textContent = d.max_chars + '字';
  } catch (e) {}
}

async function setSpeechMaxChars(val) {
  await api('POST', '/api/speech/settings', { max_chars: Number(val) });
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
    const url = _currentCharId ? `/api/character/${_currentCharId}/${type}` : `/api/character/${type}`;
    const res = await fetch(url, {
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
    const url = _currentCharId ? `/api/character/${_currentCharId}/persona/generate` : '/api/character/persona/generate';
    const res = await fetch(url, {method: 'POST'});
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
    const url = _currentCharId ? `/api/character/${_currentCharId}/self-note/generate` : '/api/character/self-note/generate';
    const res = await fetch(url, {method: 'POST'});
    const d = await res.json();
    if (d.ok) {
      loadCharacterLayers();
    }
  } catch (e) {
    console.error('セルフメモ生成失敗:', e);
    selfEl.innerHTML = '<div class="layer-empty">生成失敗</div>';
  }
}
