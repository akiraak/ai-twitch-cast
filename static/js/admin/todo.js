// TODO管理
let _todoFiles = [];
let _todoActive = 'project';
let _todoProjectDir = '';

async function loadTodoFileList() {
  try {
    const d = await (await fetch('/api/todo/files')).json();
    _todoFiles = d.files || [];
    _todoActive = d.active || 'project';
    _todoProjectDir = d.project_dir || '';
    const sel = document.getElementById('todo-file-select');
    const projectLabel = _todoProjectDir ? _todoProjectDir + '/' : 'プロジェクト';
    let html = `<option value="project">${esc(projectLabel)}</option>`;
    for (const f of _todoFiles) {
      const selected = f.id === _todoActive ? ' selected' : '';
      html += `<option value="${esc(f.id)}"${selected}>${esc(f.name)}</option>`;
    }
    if (_todoActive === 'project') {
      html = html.replace('value="project"', 'value="project" selected');
    }
    sel.innerHTML = html;
    const delBtn = document.getElementById('todo-delete-btn');
    delBtn.style.display = _todoActive !== 'project' ? '' : 'none';
  } catch (e) {}
}

async function switchTodoFile(id) {
  try {
    await api('POST', '/api/todo/switch', { id });
    loadTodoList();
  } catch (e) {
    showToast('切り替えエラー', 'error');
  }
}

async function uploadTodoFile(input) {
  const file = input.files[0];
  if (!file) return;
  const text = await file.text();
  const label = await showModal('このTODOファイルの名称を入力してください', {
    title: 'TODO追加',
    okLabel: '追加',
    input: '例: cooking-basket',
    inputValue: file.name.replace(/\.(md|txt)$/i, ''),
  });
  if (label === null) { input.value = ''; return; }
  const name = label.trim() || file.name;
  try {
    const res = await api('POST', '/api/todo/upload', { content: text, name });
    if (res.ok) {
      showToast('TODO追加: ' + name);
      loadTodoList();
    }
  } catch (e) {
    showToast('アップロードエラー', 'error');
  }
  input.value = '';
}

async function deleteActiveTodoFile() {
  if (_todoActive === 'project') return;
  const f = _todoFiles.find(x => x.id === _todoActive);
  const name = f ? f.name : _todoActive;
  if (!await showConfirm(`「${name}」を削除しますか？`, { title: '削除', okLabel: '削除', danger: true })) return;
  try {
    const res = await fetch(`/api/todo/files/${_todoActive}`, { method: 'DELETE' });
    const d = await res.json();
    if (d.ok) {
      showToast('削除: ' + name);
      loadTodoList();
    }
  } catch (e) {
    showToast('削除エラー', 'error');
  }
}

async function loadTodoList() {
  loadTodoFileList();
  try {
    const data = await (await fetch('/api/todo')).json();
    const el = document.getElementById('todo-list');
    if (!data.items || data.items.length === 0) {
      el.innerHTML = '<div style="color:#9a88b5;">TODOはありません</div>';
      return;
    }
    let currentSection = '';
    let html = '';
    for (const item of data.items) {
      if (item.section !== currentSection) {
        currentSection = item.section;
        html += `<div style="font-size:0.8rem; font-weight:600; color:#7b1fa2; margin:12px 0 6px; border-bottom:1px solid #e8ddf5; padding-bottom:4px;">${esc(currentSection)}</div>`;
      }
      const isActive = item.status === 'in_progress';
      const bg = isActive ? 'background:#f3e5f5; border-left:3px solid #7b1fa2;' : 'border-left:3px solid transparent;';
      const checkbox = isActive
        ? '<span style="display:inline-flex; align-items:center; justify-content:center; width:18px; height:18px; border-radius:4px; background:#7b1fa2; flex-shrink:0; font-size:0.7rem; color:#fff;">▶</span>'
        : '<span style="display:inline-flex; align-items:center; justify-content:center; width:18px; height:18px; border:2px solid #d0c0e8; border-radius:4px; flex-shrink:0;"></span>';
      const action = isActive
        ? `onclick="stopTodo(this.parentElement, '${esc(item.text).replace(/'/g, "\\'")}')"`
        : `onclick="startTodo(this.parentElement, '${esc(item.text).replace(/'/g, "\\'")}')"`;
      html += `<div style="padding:8px 12px; margin:4px 0; border-radius:4px; cursor:pointer; ${bg} transition:background 0.15s; display:flex; align-items:center; gap:8px;" onmouseenter="this.style.background='#f0e8ff'" onmouseleave="this.style.background='${isActive ? '#f3e5f5' : ''}'"><span style="flex:1; display:flex; align-items:center; gap:8px;" ${action}>${checkbox}${esc(item.text)}</span><button class="todo-copy-btn" onclick="event.stopPropagation();copyTodo(this,'${esc(item.text).replace(/'/g, "\\'")}')" title="コピー"></button></div>`;
    }
    el.innerHTML = html;
  } catch (e) {
    document.getElementById('todo-list').innerHTML = '<div style="color:#c62828;">読み込みエラー</div>';
  }
}

const ICON_COPY = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='%237b1fa2' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Crect x='9' y='9' width='13' height='13' rx='2'/%3E%3Cpath d='M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1'/%3E%3C/svg%3E";
const ICON_CHECK = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='%234caf50' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='20 6 9 17 4 12'/%3E%3C/svg%3E";
async function copyTodo(btn, text) {
  await navigator.clipboard.writeText(text);
  btn.style.backgroundImage = `url("${ICON_CHECK}")`;
  setTimeout(() => { btn.style.backgroundImage = `url("${ICON_COPY}")`; }, 1000);
}

async function stopTodo(el, text) {
  el.style.opacity = '0.5';
  el.style.pointerEvents = 'none';
  try {
    const res = await api('POST', '/api/todo/stop', { text });
    if (res.ok) {
      showToast('作業解除: ' + text);
    } else {
      showToast(res.error || 'エラー', 'error');
    }
    loadTodoList();
  } catch (e) {
    showToast('エラー', 'error');
    el.style.opacity = '1';
    el.style.pointerEvents = '';
  }
}

async function startTodo(el, text) {
  el.style.opacity = '0.5';
  el.style.pointerEvents = 'none';
  try {
    const res = await api('POST', '/api/todo/start', { text });
    if (res.ok) {
      showToast('作業開始: ' + text);
    } else {
      showToast(res.error || 'エラー', 'error');
    }
    loadTodoList();
  } catch (e) {
    showToast('エラー', 'error');
    el.style.opacity = '1';
    el.style.pointerEvents = '';
  }
}
