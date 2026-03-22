// 教師モード管理画面
let _currentLessonId = null;

const SECTION_ICONS = {
  introduction: '\u{1F3AC}',
  explanation: '\u{1F4D6}',
  example: '\u{1F4DD}',
  question: '\u{2753}',
  summary: '\u{1F3C1}',
};

function switchConvSubtab(name, el) {
  document.querySelectorAll('#tab-convmode .char-subtab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('#tab-convmode .char-subcontent').forEach(t => t.classList.remove('active'));
  document.getElementById('conv-sub-' + name).classList.add('active');
  if (el) el.classList.add('active');
}

// --- コンテンツ一覧 ---

async function loadLessons() {
  const res = await api('GET', '/api/lessons');
  if (!res || !res.ok) return;
  const tabs = document.getElementById('lesson-tabs');
  tabs.innerHTML = '';
  for (const l of res.lessons) {
    const btn = document.createElement('button');
    btn.textContent = l.name;
    btn.className = 'lesson-tab' + (l.id === _currentLessonId ? ' active' : '');
    btn.style.cssText = 'padding:4px 12px; border:1px solid #555; border-radius:4px; cursor:pointer; font-size:0.8rem;'
      + (l.id === _currentLessonId ? ' background:#7b1fa2; color:#fff;' : ' background:#2a2a3e; color:#ccc;');
    btn.onclick = () => selectLesson(l.id);
    tabs.appendChild(btn);
  }
  if (_currentLessonId) {
    loadLessonDetail(_currentLessonId);
  }
}

async function createLesson() {
  const name = await showModal('コンテンツ名を入力してください', {
    title: '新規コンテンツ',
    input: '例: English 1-1',
    okLabel: '作成',
  });
  if (!name) return;
  const res = await api('POST', '/api/lessons', { name });
  if (res && res.ok) {
    _currentLessonId = res.lesson.id;
    showToast('コンテンツ作成: ' + name, 'success');
    loadLessons();
  }
}

function selectLesson(id) {
  _currentLessonId = id;
  loadLessons();
}

// --- コンテンツ詳細 ---

async function loadLessonDetail(lessonId) {
  const res = await api('GET', '/api/lessons/' + lessonId);
  if (!res || !res.ok) {
    document.getElementById('lesson-detail').style.display = 'none';
    return;
  }
  document.getElementById('lesson-detail').style.display = 'block';
  document.getElementById('lesson-name').value = res.lesson.name;
  document.getElementById('lesson-extracted-text').textContent = res.lesson.extracted_text || '(なし)';

  // ソース一覧
  renderSources(res.sources);
  // セクション一覧
  renderSections(res.sections);
  // 授業ステータス
  loadLessonStatus();
  startLessonStatusPolling();
}

async function saveLessonName() {
  if (!_currentLessonId) return;
  const name = document.getElementById('lesson-name').value.trim();
  if (!name) return;
  const res = await api('PUT', '/api/lessons/' + _currentLessonId, { name });
  if (res && res.ok) {
    showToast('名前を更新しました', 'success');
    loadLessons();
  }
}

async function deleteLesson() {
  if (!_currentLessonId) return;
  const ok = await showConfirm('このコンテンツを削除しますか？', { danger: true, title: 'コンテンツ削除' });
  if (!ok) return;
  const res = await api('DELETE', '/api/lessons/' + _currentLessonId);
  if (res && res.ok) {
    showToast('コンテンツを削除しました', 'success');
    _currentLessonId = null;
    document.getElementById('lesson-detail').style.display = 'none';
    loadLessons();
  }
}

// --- 教材ソース ---

function renderSources(sources) {
  const el = document.getElementById('lesson-sources');
  document.getElementById('source-count').textContent = sources.length ? `(${sources.length}件)` : '';
  el.innerHTML = '';
  for (const s of sources) {
    const div = document.createElement('div');
    div.style.cssText = 'position:relative; display:inline-block;';
    if (s.source_type === 'image' && s.file_path) {
      div.innerHTML = `<div style="width:80px; height:80px; border:1px solid #555; border-radius:4px; overflow:hidden; position:relative;">
        <img src="/${esc(s.file_path)}" style="width:100%; height:100%; object-fit:cover;">
        <button onclick="deleteLessonSource(${s.id})" style="position:absolute; top:2px; right:2px; width:18px; height:18px; background:rgba(198,40,40,0.9); color:#fff; border:none; border-radius:50%; cursor:pointer; font-size:0.65rem; line-height:18px; padding:0;" title="削除">\u00D7</button>
      </div>
      <div style="font-size:0.6rem; color:#999; max-width:80px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${esc(s.original_name)}</div>`;
    } else if (s.source_type === 'url') {
      div.innerHTML = `<div style="padding:6px 10px; background:#1a1a2e; border:1px solid #555; border-radius:4px; display:flex; align-items:center; gap:6px;">
        <span style="font-size:0.75rem; color:#81d4fa; max-width:150px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${esc(s.url)}">${esc(s.url)}</span>
        <button onclick="deleteLessonSource(${s.id})" style="width:18px; height:18px; background:rgba(198,40,40,0.9); color:#fff; border:none; border-radius:50%; cursor:pointer; font-size:0.65rem; line-height:18px; padding:0;" title="削除">\u00D7</button>
      </div>`;
    }
    el.appendChild(div);
  }
}

async function uploadLessonImage(input) {
  if (!_currentLessonId || !input.files || !input.files.length) return;
  const statusEl = document.getElementById('lesson-upload-status');
  for (const file of input.files) {
    statusEl.textContent = '\u30A2\u30C3\u30D7\u30ED\u30FC\u30C9\u4E2D: ' + file.name + '...';
    try {
      const formData = new FormData();
      formData.append('file', file);
      const r = await fetch('/api/lessons/' + _currentLessonId + '/upload-image', { method: 'POST', body: formData });
      const data = await r.json();
      if (data.ok) {
        showToast('\u30A2\u30C3\u30D7\u30ED\u30FC\u30C9\u5B8C\u4E86: ' + file.name, 'success');
      } else {
        showToast('\u30A2\u30C3\u30D7\u30ED\u30FC\u30C9\u5931\u6557: ' + (data.error || ''), 'error');
      }
    } catch (e) {
      showToast('\u30A2\u30C3\u30D7\u30ED\u30FC\u30C9\u5931\u6557: ' + e.message, 'error');
    }
  }
  input.value = '';
  statusEl.textContent = '';
  loadLessonDetail(_currentLessonId);
}

async function addLessonUrl() {
  const url = await showModal('URLを入力してください', {
    title: 'URL追加',
    input: 'https://...',
    okLabel: '追加',
  });
  if (!url) return;
  const statusEl = document.getElementById('lesson-upload-status');
  statusEl.textContent = 'URL\u53D6\u5F97\u4E2D...';
  const res = await api('POST', '/api/lessons/' + _currentLessonId + '/add-url', { url });
  statusEl.textContent = '';
  if (res && res.ok) {
    showToast('URL\u8FFD\u52A0\u5B8C\u4E86', 'success');
    loadLessonDetail(_currentLessonId);
  }
}

async function deleteLessonSource(sourceId) {
  if (!_currentLessonId) return;
  const ok = await showConfirm('\u3053\u306E\u30BD\u30FC\u30B9\u3092\u524A\u9664\u3057\u307E\u3059\u304B\uFF1F');
  if (!ok) return;
  await api('DELETE', '/api/lessons/' + _currentLessonId + '/sources/' + sourceId);
  loadLessonDetail(_currentLessonId);
}

// --- 授業スクリプト ---

async function generateScript() {
  if (!_currentLessonId) return;
  const btn = document.getElementById('btn-generate-script');
  const statusEl = document.getElementById('script-status');
  btn.disabled = true;
  statusEl.textContent = '\u751F\u6210\u4E2D...';
  try {
    const res = await api('POST', '/api/lessons/' + _currentLessonId + '/generate-script');
    if (res && res.ok) {
      showToast('\u30B9\u30AF\u30EA\u30D7\u30C8\u751F\u6210\u5B8C\u4E86 (' + res.sections.length + '\u30BB\u30AF\u30B7\u30E7\u30F3)', 'success');
      loadLessonDetail(_currentLessonId);
    }
  } finally {
    btn.disabled = false;
    statusEl.textContent = '';
  }
}

function renderSections(sections) {
  const el = document.getElementById('lesson-sections');
  el.innerHTML = '';
  if (!sections || !sections.length) {
    el.innerHTML = '<div style="color:#666; font-size:0.8rem; padding:8px;">\u30B9\u30AF\u30EA\u30D7\u30C8\u304C\u3042\u308A\u307E\u305B\u3093\u3002\u300C\u30B9\u30AF\u30EA\u30D7\u30C8\u751F\u6210\u300D\u3092\u62BC\u3057\u3066\u304F\u3060\u3055\u3044\u3002</div>';
    return;
  }
  for (let i = 0; i < sections.length; i++) {
    const s = sections[i];
    const icon = SECTION_ICONS[s.section_type] || '\u{1F4D6}';
    const div = document.createElement('div');
    div.className = 'lesson-section';
    div.style.cssText = 'border:1px solid #444; border-radius:6px; padding:10px; margin-bottom:8px; background:#1e1e30;';

    let html = `<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
      <div>
        <span style="font-size:0.9rem;">${icon}</span>
        <span style="font-weight:600; font-size:0.8rem; margin-left:4px;">${i + 1}. ${esc(s.section_type)}</span>
        <span style="font-size:0.7rem; color:#b39ddb; margin-left:8px;">[${esc(s.emotion)}]</span>
      </div>
      <div style="display:flex; gap:4px;">
        <button onclick="moveSectionUp(${s.id})" style="width:24px; height:24px; background:#333; color:#ccc; border:1px solid #555; border-radius:3px; cursor:pointer; font-size:0.7rem;" ${i === 0 ? 'disabled' : ''}>\u25B2</button>
        <button onclick="moveSectionDown(${s.id})" style="width:24px; height:24px; background:#333; color:#ccc; border:1px solid #555; border-radius:3px; cursor:pointer; font-size:0.7rem;" ${i === sections.length - 1 ? 'disabled' : ''}>\u25BC</button>
        <button onclick="deleteSection(${s.id})" style="width:24px; height:24px; background:#c62828; color:#fff; border:none; border-radius:3px; cursor:pointer; font-size:0.7rem;">\u00D7</button>
      </div>
    </div>`;

    // 発話テキスト
    html += sectionField('\u767A\u8A71', 'content', s.id, s.content);
    // TTS
    html += sectionField('TTS', 'tts_text', s.id, s.tts_text);
    // 画面表示
    html += sectionField('\u753B\u9762', 'display_text', s.id, s.display_text);

    // questionセクション
    if (s.section_type === 'question') {
      html += sectionField('Q', 'question', s.id, s.question);
      html += sectionField('A', 'answer', s.id, s.answer);
      html += `<div style="display:flex; align-items:center; gap:6px; margin-top:4px;">
        <span style="font-size:0.7rem; color:#999; min-width:36px;">\u5F85\u3061:</span>
        <input type="number" value="${s.wait_seconds}" min="0" max="60" style="width:50px; padding:2px 4px; background:#1a1a2e; color:#e0e0e0; border:1px solid #444; border-radius:3px; font-size:0.75rem;"
          onchange="updateSectionField(${s.id}, 'wait_seconds', parseInt(this.value))">
        <span style="font-size:0.7rem; color:#999;">\u79D2</span>
      </div>`;
    }

    div.innerHTML = html;
    el.appendChild(div);
  }
}

function sectionField(label, field, sectionId, value) {
  return `<div style="display:flex; gap:6px; margin-top:4px; align-items:flex-start;">
    <span style="font-size:0.7rem; color:#999; min-width:36px; padding-top:4px;">${esc(label)}:</span>
    <textarea rows="2" style="flex:1; padding:4px 6px; background:#1a1a2e; color:#e0e0e0; border:1px solid #444; border-radius:3px; font-size:0.75rem; resize:vertical;"
      onchange="updateSectionField(${sectionId}, '${field}', this.value)">${esc(value || '')}</textarea>
  </div>`;
}

async function updateSectionField(sectionId, field, value) {
  if (!_currentLessonId) return;
  const body = {};
  body[field] = value;
  await api('PUT', '/api/lessons/' + _currentLessonId + '/sections/' + sectionId, body);
}

async function deleteSection(sectionId) {
  if (!_currentLessonId) return;
  await api('DELETE', '/api/lessons/' + _currentLessonId + '/sections/' + sectionId);
  loadLessonDetail(_currentLessonId);
}

async function moveSectionUp(sectionId) {
  await _reorderSection(sectionId, -1);
}

async function moveSectionDown(sectionId) {
  await _reorderSection(sectionId, 1);
}

async function _reorderSection(sectionId, direction) {
  if (!_currentLessonId) return;
  // 現在のセクション一覧を取得して並び替え
  const res = await api('GET', '/api/lessons/' + _currentLessonId);
  if (!res || !res.ok) return;
  const ids = res.sections.map(s => s.id);
  const idx = ids.indexOf(sectionId);
  if (idx < 0) return;
  const newIdx = idx + direction;
  if (newIdx < 0 || newIdx >= ids.length) return;
  // swap
  [ids[idx], ids[newIdx]] = [ids[newIdx], ids[idx]];
  await api('PUT', '/api/lessons/' + _currentLessonId + '/sections/reorder', { section_ids: ids });
  loadLessonDetail(_currentLessonId);
}

// --- 授業制御 ---

async function startLesson() {
  if (!_currentLessonId) return;
  const res = await api('POST', '/api/lessons/' + _currentLessonId + '/start');
  if (res && res.ok) {
    showToast('\u6388\u696D\u958B\u59CB', 'success');
    updateLessonControlUI(res.status);
  }
}

async function pauseLesson() {
  const res = await api('POST', '/api/lessons/pause');
  if (res && res.ok) updateLessonControlUI(res.status);
}

async function resumeLesson() {
  const res = await api('POST', '/api/lessons/resume');
  if (res && res.ok) updateLessonControlUI(res.status);
}

async function stopLesson() {
  const res = await api('POST', '/api/lessons/stop');
  if (res && res.ok) {
    showToast('\u6388\u696D\u505C\u6B62', 'success');
    updateLessonControlUI(res.status);
  }
}

function updateLessonControlUI(status) {
  if (!status) return;
  const stateEl = document.getElementById('lesson-state');
  const startBtn = document.getElementById('btn-lesson-start');
  const pauseBtn = document.getElementById('btn-lesson-pause');
  const resumeBtn = document.getElementById('btn-lesson-resume');
  const stopBtn = document.getElementById('btn-lesson-stop');
  const progressEl = document.getElementById('lesson-progress');

  const labels = { idle: '\u505C\u6B62\u4E2D', running: '\u5B9F\u884C\u4E2D', paused: '\u4E00\u6642\u505C\u6B62' };
  stateEl.textContent = labels[status.state] || status.state;

  startBtn.style.display = status.state === 'idle' ? '' : 'none';
  pauseBtn.style.display = status.state === 'running' ? '' : 'none';
  resumeBtn.style.display = status.state === 'paused' ? '' : 'none';
  stopBtn.style.display = status.state !== 'idle' ? '' : 'none';

  if (status.state !== 'idle' && status.total_sections > 0) {
    progressEl.textContent = `\u30BB\u30AF\u30B7\u30E7\u30F3 ${status.current_index + 1} / ${status.total_sections}`;
  } else {
    progressEl.textContent = '';
  }
}

async function loadLessonStatus() {
  const res = await api('GET', '/api/lessons/status');
  if (res && res.ok) updateLessonControlUI(res.status);
}

// 定期的にステータスポーリング（授業進行表示用）
let _lessonStatusTimer = null;
function startLessonStatusPolling() {
  if (_lessonStatusTimer) return;
  _lessonStatusTimer = setInterval(loadLessonStatus, 3000);
}
function stopLessonStatusPolling() {
  if (_lessonStatusTimer) { clearInterval(_lessonStatusTimer); _lessonStatusTimer = null; }
}
