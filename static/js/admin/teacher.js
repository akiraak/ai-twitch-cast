// 教師モード管理画面
// 各コンテンツが独立した折りたたみブロックとして縦に並ぶ

const SECTION_ICONS = {
  introduction: '\u{1F3AC}',
  explanation: '\u{1F4D6}',
  example: '\u{1F4DD}',
  question: '\u{2753}',
  summary: '\u{1F3C1}',
};

// 開閉状態を保持（リロード時に復元）
let _openLessonIds = new Set();

function switchConvSubtab(name, el) {
  document.querySelectorAll('#tab-convmode .char-subtab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('#tab-convmode .char-subcontent').forEach(t => t.classList.remove('active'));
  document.getElementById('conv-sub-' + name).classList.add('active');
  if (el) el.classList.add('active');
}

// --- コンテンツ一覧（各コンテンツを縦に並べる） ---

async function loadLessons() {
  const res = await api('GET', '/api/lessons');
  if (!res || !res.ok) return;
  const list = document.getElementById('lesson-list');
  list.innerHTML = '';
  for (const l of res.lessons) {
    const item = await buildLessonItem(l.id);
    if (item) list.appendChild(item);
  }
}

async function buildLessonItem(lessonId) {
  const res = await api('GET', '/api/lessons/' + lessonId);
  if (!res || !res.ok) return null;

  const lesson = res.lesson;
  const sources = res.sources;
  const sections = res.sections;
  const hasSources = sources.length > 0;
  const hasSections = sections.length > 0;

  // バッジ
  const badges = [];
  if (sources.length) badges.push(sources.length + '\u30BD\u30FC\u30B9');
  if (sections.length) badges.push(sections.length + '\u30BB\u30AF\u30B7\u30E7\u30F3');
  const badgeText = badges.length ? ' (' + badges.join(' / ') + ')' : '';

  const details = document.createElement('details');
  details.className = 'lesson-item';
  details.style.cssText = 'border:1px solid #d0c0e8; border-radius:6px; padding:12px; margin-bottom:8px; background:#ffffff;';
  if (_openLessonIds.has(lessonId)) details.open = true;
  details.addEventListener('toggle', () => {
    if (details.open) _openLessonIds.add(lessonId);
    else _openLessonIds.delete(lessonId);
  });

  // summary
  const summary = document.createElement('summary');
  summary.style.cssText = 'cursor:pointer; font-weight:600; font-size:0.9rem; color:#2a1f40; list-style:none; display:flex; align-items:center; gap:8px;';
  summary.innerHTML = `<span class="lesson-arrow" style="color:#7b1fa2; font-size:0.75rem;">&#9660;</span>`
    + `<span>${esc(lesson.name)}</span>`
    + `<span style="font-size:0.7rem; color:#8a7a9a;">${esc(badgeText)}</span>`;
  details.appendChild(summary);

  // body
  const body = document.createElement('div');
  body.style.marginTop = '12px';

  // コンテンツ名編集
  body.innerHTML = `<div style="display:flex; align-items:center; gap:8px; margin-bottom:12px;">
    <span style="font-weight:600; font-size:0.85rem; color:#2a1f40;">コンテンツ名:</span>
    <input type="text" class="lesson-name-input" value="${esc(lesson.name)}" style="flex:1; padding:4px 8px; background:#faf7ff; color:#2a1f40; border:1px solid #d0c0e8; border-radius:4px;">
    <button onclick="saveLessonName(${lessonId}, this)" style="padding:4px 12px; background:#7b1fa2; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:0.8rem;">保存</button>
  </div>`;

  // 教材ソース
  const srcSection = document.createElement('div');
  srcSection.style.marginBottom = '12px';
  srcSection.innerHTML = `<div style="font-weight:600; font-size:0.85rem; color:#7b1fa2; margin-bottom:8px;">教材ソース${sources.length ? ' (' + sources.length + '件)' : ''}</div>`;

  // ソースサムネイル
  const srcList = document.createElement('div');
  srcList.style.cssText = 'display:flex; gap:8px; flex-wrap:wrap; margin-bottom:8px;';
  for (const s of sources) {
    const div = document.createElement('div');
    div.style.cssText = 'position:relative; display:inline-block;';
    if (s.source_type === 'image' && s.file_path) {
      div.innerHTML = `<div style="width:80px; height:80px; border:1px solid #d0c0e8; border-radius:4px; overflow:hidden; position:relative;">
        <img src="/${esc(s.file_path)}" style="width:100%; height:100%; object-fit:cover;">
        <button onclick="deleteLessonSource(${lessonId}, ${s.id})" style="position:absolute; top:2px; right:2px; width:18px; height:18px; background:rgba(198,40,40,0.9); color:#fff; border:none; border-radius:50%; cursor:pointer; font-size:0.65rem; line-height:18px; padding:0;">\u00D7</button>
      </div>
      <div style="font-size:0.6rem; color:#8a7a9a; max-width:80px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${esc(s.original_name)}</div>`;
    } else if (s.source_type === 'url') {
      div.innerHTML = `<div style="padding:6px 10px; background:#faf7ff; border:1px solid #d0c0e8; border-radius:4px; display:flex; align-items:center; gap:6px;">
        <span style="font-size:0.75rem; color:#1565c0; max-width:150px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${esc(s.url)}">${esc(s.url)}</span>
        <button onclick="deleteLessonSource(${lessonId}, ${s.id})" style="width:18px; height:18px; background:rgba(198,40,40,0.9); color:#fff; border:none; border-radius:50%; cursor:pointer; font-size:0.65rem; line-height:18px; padding:0;">\u00D7</button>
      </div>`;
    }
    srcList.appendChild(div);
  }
  srcSection.appendChild(srcList);

  // 追加ボタン
  const btnRow = document.createElement('div');
  btnRow.style.cssText = 'display:flex; gap:8px; align-items:center;';
  btnRow.innerHTML = `<label style="padding:6px 16px; background:#7b1fa2; color:#fff; border-radius:4px; cursor:pointer; font-size:0.85rem;">
      画像追加
      <input type="file" accept=".png,.jpg,.jpeg,.webp,.gif" multiple onchange="uploadLessonImage(${lessonId}, this)" style="display:none;">
    </label>
    <button onclick="addLessonUrl(${lessonId})" style="padding:6px 16px; background:#546e7a; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:0.85rem;">URL追加</button>
    <span class="lesson-upload-status" style="font-size:0.8rem; color:#e65100;"></span>`;
  srcSection.appendChild(btnRow);

  if (!hasSources) {
    const hint = document.createElement('div');
    hint.style.cssText = 'margin-top:10px; padding:10px 14px; background:rgba(124,77,255,0.06); border:1px dashed rgba(124,77,255,0.3); border-radius:6px; color:#7b1fa2; font-size:0.8rem;';
    hint.textContent = '画像またはURLを追加すると、テキスト抽出・スクリプト生成が利用できます';
    srcSection.appendChild(hint);
  }
  body.appendChild(srcSection);

  // ソース追加後の領域
  if (hasSources) {
    // 抽出テキスト
    const extDetails = document.createElement('details');
    extDetails.style.marginBottom = '12px';
    extDetails.innerHTML = `<summary style="cursor:pointer; font-weight:600; font-size:0.85rem; color:#7b1fa2;">抽出テキスト</summary>
      <div style="margin-top:8px;">
        <pre style="background:#faf7ff; padding:8px; border:1px solid #d0c0e8; border-radius:4px; font-size:0.75rem; max-height:200px; overflow-y:auto; white-space:pre-wrap; word-break:break-word; color:#2a1f40;">${esc(lesson.extracted_text || '(なし)')}</pre>
      </div>`;
    body.appendChild(extDetails);

    // スクリプト生成
    const scriptHeader = document.createElement('div');
    scriptHeader.style.cssText = 'display:flex; align-items:center; gap:8px; margin-bottom:8px;';
    scriptHeader.innerHTML = `<span style="font-weight:600; font-size:0.85rem; color:#2a1f40;">授業スクリプト</span>
      <button onclick="generateScript(${lessonId})" style="padding:4px 12px; background:#e65100; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:0.8rem;">スクリプト生成</button>
      <span class="script-status" style="font-size:0.75rem; color:#8a7a9a;"></span>`;
    body.appendChild(scriptHeader);

    // セクション一覧
    const secContainer = document.createElement('div');
    renderSectionsInto(secContainer, sections, lessonId);
    body.appendChild(secContainer);

    // 授業制御（スクリプトがあるときだけ表示）
    if (hasSections) {
      const control = document.createElement('div');
      control.style.cssText = 'margin-top:12px; padding:10px; background:#faf7ff; border:1px solid #d0c0e8; border-radius:6px;';
      control.innerHTML = `<div style="display:flex; align-items:center; gap:8px; margin-bottom:6px;">
          <span style="font-weight:600; font-size:0.85rem; color:#2a1f40;">授業制御</span>
          <span class="lesson-state" style="font-size:0.75rem; color:#8a7a9a;"></span>
        </div>
        <div style="display:flex; gap:6px;">
          <button onclick="startLesson(${lessonId})" class="btn-lesson-start" style="padding:4px 12px; background:#2e7d32; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:0.8rem;">授業開始</button>
          <button onclick="pauseLesson()" class="btn-lesson-pause" style="padding:4px 12px; background:#f57f17; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:0.8rem; display:none;">一時停止</button>
          <button onclick="resumeLesson()" class="btn-lesson-resume" style="padding:4px 12px; background:#2e7d32; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:0.8rem; display:none;">再開</button>
          <button onclick="stopLesson()" class="btn-lesson-stop" style="padding:4px 12px; background:#c62828; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:0.8rem; display:none;">停止</button>
        </div>
        <div class="lesson-progress" style="margin-top:6px; font-size:0.75rem; color:#8a7a9a;"></div>`;
      body.appendChild(control);
    }
  }

  // 削除ボタン
  const delRow = document.createElement('div');
  delRow.style.cssText = 'display:flex; justify-content:flex-end; margin-top:16px;';
  delRow.innerHTML = `<button onclick="deleteLesson(${lessonId})" style="padding:4px 12px; background:#c62828; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:0.8rem;">コンテンツ削除</button>`;
  body.appendChild(delRow);

  details.appendChild(body);
  return details;
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
    _openLessonIds.add(res.lesson.id);
    showToast('コンテンツ作成: ' + name, 'success');
    await loadLessons();
  }
}

async function saveLessonName(lessonId, btn) {
  const input = btn.parentElement.querySelector('.lesson-name-input');
  const name = input.value.trim();
  if (!name) return;
  const res = await api('PUT', '/api/lessons/' + lessonId, { name });
  if (res && res.ok) {
    showToast('名前を更新しました', 'success');
    await loadLessons();
  }
}

async function deleteLesson(lessonId) {
  const ok = await showConfirm('このコンテンツを削除しますか？', { danger: true, title: 'コンテンツ削除' });
  if (!ok) return;
  const res = await api('DELETE', '/api/lessons/' + lessonId);
  if (res && res.ok) {
    _openLessonIds.delete(lessonId);
    showToast('コンテンツを削除しました', 'success');
    await loadLessons();
  }
}

// --- 教材ソース ---

function _showSpinner(el, msg) {
  el.innerHTML = `<span class="lesson-spinner">${esc(msg)}</span>`;
}
function _hideSpinner(el) {
  el.innerHTML = '';
}

async function uploadLessonImage(lessonId, input) {
  if (!input.files || !input.files.length) return;
  const statusEl = input.closest('div').querySelector('.lesson-upload-status');
  const total = input.files.length;
  let done = 0;
  for (const file of input.files) {
    done++;
    const msg = total > 1
      ? `アップロード中 (${done}/${total}): ${file.name} — テキスト抽出中...`
      : `アップロード中: ${file.name} — テキスト抽出中...`;
    _showSpinner(statusEl, msg);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const r = await fetch('/api/lessons/' + lessonId + '/upload-image', { method: 'POST', body: formData });
      const data = await r.json();
      if (data.ok) {
        showToast('アップロード完了: ' + file.name, 'success');
      } else {
        showToast('アップロード失敗: ' + (data.error || ''), 'error');
      }
    } catch (e) {
      showToast('アップロード失敗: ' + e.message, 'error');
    }
  }
  input.value = '';
  _hideSpinner(statusEl);
  _openLessonIds.add(lessonId);
  await loadLessons();
}

async function addLessonUrl(lessonId) {
  const url = await showModal('URLを入力してください', {
    title: 'URL追加',
    input: 'https://...',
    okLabel: '追加',
  });
  if (!url) return;
  const item = [...document.querySelectorAll('.lesson-item')].find(el => {
    const b = el.querySelector(`button[onclick="addLessonUrl(${lessonId})"]`);
    return !!b;
  });
  let statusEl = item ? item.querySelector('.lesson-upload-status') : null;
  if (statusEl) _showSpinner(statusEl, 'URL取得中 — テキスト抽出中...');
  const res = await api('POST', '/api/lessons/' + lessonId + '/add-url', { url });
  if (statusEl) _hideSpinner(statusEl);
  if (res && res.ok) {
    showToast('URL追加完了', 'success');
    _openLessonIds.add(lessonId);
    await loadLessons();
  }
}

async function deleteLessonSource(lessonId, sourceId) {
  const ok = await showConfirm('このソースを削除しますか？');
  if (!ok) return;
  await api('DELETE', '/api/lessons/' + lessonId + '/sources/' + sourceId);
  _openLessonIds.add(lessonId);
  await loadLessons();
}

// --- 授業スクリプト ---

async function generateScript(lessonId) {
  const items = document.querySelectorAll('.lesson-item');
  let statusEl = null;
  let btn = null;
  for (const item of items) {
    const b = item.querySelector(`button[onclick="generateScript(${lessonId})"]`);
    if (b) {
      btn = b;
      statusEl = b.parentElement.querySelector('.script-status');
      break;
    }
  }
  if (btn) btn.disabled = true;
  if (statusEl) _showSpinner(statusEl, 'スクリプト生成中...');
  const res = await api('POST', '/api/lessons/' + lessonId + '/generate-script');
  if (res && res.ok) {
    showToast('スクリプト生成完了 (' + res.sections.length + 'セクション)', 'success');
  } else {
    if (btn) btn.disabled = false;
    if (statusEl) _hideSpinner(statusEl);
    return;
  }
  _openLessonIds.add(lessonId);
  await loadLessons();
}

function renderSectionsInto(container, sections, lessonId) {
  container.innerHTML = '';
  if (!sections || !sections.length) {
    container.innerHTML = '<div style="color:#8a7a9a; font-size:0.8rem; padding:8px;">スクリプトがありません。「スクリプト生成」を押してください。</div>';
    return;
  }
  for (let i = 0; i < sections.length; i++) {
    const s = sections[i];
    const icon = SECTION_ICONS[s.section_type] || '\u{1F4D6}';
    const div = document.createElement('div');
    div.style.cssText = 'border:1px solid #d0c0e8; border-radius:6px; padding:10px; margin-bottom:8px; background:#faf7ff;';

    let html = `<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
      <div>
        <span style="font-size:0.9rem;">${icon}</span>
        <span style="font-weight:600; font-size:0.8rem; margin-left:4px; color:#2a1f40;">${i + 1}. ${esc(s.section_type)}</span>
        <span style="font-size:0.7rem; color:#7b1fa2; margin-left:8px;">[${esc(s.emotion)}]</span>
      </div>
      <div style="display:flex; gap:4px;">
        <button onclick="moveSectionUp(${lessonId}, ${s.id})" style="width:24px; height:24px; background:#f0ecf5; color:#6a5590; border:1px solid #d0c0e8; border-radius:3px; cursor:pointer; font-size:0.7rem;" ${i === 0 ? 'disabled' : ''}>\u25B2</button>
        <button onclick="moveSectionDown(${lessonId}, ${s.id})" style="width:24px; height:24px; background:#f0ecf5; color:#6a5590; border:1px solid #d0c0e8; border-radius:3px; cursor:pointer; font-size:0.7rem;" ${i === sections.length - 1 ? 'disabled' : ''}>\u25BC</button>
        <button onclick="deleteSection(${lessonId}, ${s.id})" style="width:24px; height:24px; background:#c62828; color:#fff; border:none; border-radius:3px; cursor:pointer; font-size:0.7rem;">\u00D7</button>
      </div>
    </div>`;

    html += sectionField('発話', 'content', lessonId, s.id, s.content);
    html += sectionField('TTS', 'tts_text', lessonId, s.id, s.tts_text);
    html += sectionField('画面', 'display_text', lessonId, s.id, s.display_text);

    if (s.section_type === 'question') {
      html += sectionField('Q', 'question', lessonId, s.id, s.question);
      html += sectionField('A', 'answer', lessonId, s.id, s.answer);
      html += `<div style="display:flex; align-items:center; gap:6px; margin-top:4px;">
        <span style="font-size:0.7rem; color:#6a5590; min-width:36px;">待ち:</span>
        <input type="number" value="${s.wait_seconds}" min="0" max="60" style="width:50px; padding:2px 4px; background:#fff; color:#2a1f40; border:1px solid #d0c0e8; border-radius:3px; font-size:0.75rem;"
          onchange="updateSectionField(${lessonId}, ${s.id}, 'wait_seconds', parseInt(this.value))">
        <span style="font-size:0.7rem; color:#6a5590;">秒</span>
      </div>`;
    }

    div.innerHTML = html;
    container.appendChild(div);
  }
}

function sectionField(label, field, lessonId, sectionId, value) {
  return `<div style="display:flex; gap:6px; margin-top:4px; align-items:flex-start;">
    <span style="font-size:0.7rem; color:#6a5590; min-width:36px; padding-top:4px;">${esc(label)}:</span>
    <textarea rows="2" style="flex:1; padding:4px 6px; background:#fff; color:#2a1f40; border:1px solid #d0c0e8; border-radius:3px; font-size:0.75rem; resize:vertical;"
      onchange="updateSectionField(${lessonId}, ${sectionId}, '${field}', this.value)">${esc(value || '')}</textarea>
  </div>`;
}

async function updateSectionField(lessonId, sectionId, field, value) {
  const body = {};
  body[field] = value;
  await api('PUT', '/api/lessons/' + lessonId + '/sections/' + sectionId, body);
}

async function deleteSection(lessonId, sectionId) {
  await api('DELETE', '/api/lessons/' + lessonId + '/sections/' + sectionId);
  _openLessonIds.add(lessonId);
  await loadLessons();
}

async function moveSectionUp(lessonId, sectionId) {
  await _reorderSection(lessonId, sectionId, -1);
}

async function moveSectionDown(lessonId, sectionId) {
  await _reorderSection(lessonId, sectionId, 1);
}

async function _reorderSection(lessonId, sectionId, direction) {
  const res = await api('GET', '/api/lessons/' + lessonId);
  if (!res || !res.ok) return;
  const ids = res.sections.map(s => s.id);
  const idx = ids.indexOf(sectionId);
  if (idx < 0) return;
  const newIdx = idx + direction;
  if (newIdx < 0 || newIdx >= ids.length) return;
  [ids[idx], ids[newIdx]] = [ids[newIdx], ids[idx]];
  await api('PUT', '/api/lessons/' + lessonId + '/sections/reorder', { section_ids: ids });
  _openLessonIds.add(lessonId);
  await loadLessons();
}

// --- 授業制御 ---

async function startLesson(lessonId) {
  const res = await api('POST', '/api/lessons/' + lessonId + '/start');
  if (res && res.ok) {
    showToast('授業開始', 'success');
    await loadLessons();
  }
}

async function pauseLesson() {
  const res = await api('POST', '/api/lessons/pause');
  if (res && res.ok) await loadLessons();
}

async function resumeLesson() {
  const res = await api('POST', '/api/lessons/resume');
  if (res && res.ok) await loadLessons();
}

async function stopLesson() {
  const res = await api('POST', '/api/lessons/stop');
  if (res && res.ok) {
    showToast('授業停止', 'success');
    await loadLessons();
  }
}

// ステータスポーリング不要（loadLessonsで全更新）
let _lessonStatusTimer = null;
function startLessonStatusPolling() {}
function stopLessonStatusPolling() {
  if (_lessonStatusTimer) { clearInterval(_lessonStatusTimer); _lessonStatusTimer = null; }
}
