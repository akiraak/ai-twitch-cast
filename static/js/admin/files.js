// 素材ファイル管理・サーバー更新検知

function showUpdateDialog() {
  if (document.getElementById('update-dialog')) return;
  const div = document.createElement('div');
  div.id = 'update-dialog';
  div.className = 'update-dialog';
  div.innerHTML = `
    <div class="update-dialog-inner">
      <h3>サーバーが更新されました</h3>
      <p>新しいバージョンが起動しています。ページをリロードしますか？</p>
      <div class="btn-group">
        <button onclick="location.reload()">リロード</button>
        <button class="secondary" onclick="this.closest('.update-dialog').remove()">あとで</button>
      </div>
    </div>
  `;
  document.body.appendChild(div);
}

function _formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

async function loadCategoryFiles(category) {
  const listEl = document.getElementById(category + '-files-list');
  if (!listEl) return;
  try {
    const res = await fetch('/api/files/' + category + '/list');
    const data = await res.json();
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
      const previewHtml = category === 'background'
        ? `<img src="/resources/images/backgrounds/${encodeURIComponent(f.file)}" style="width:48px; height:36px; object-fit:cover; border-radius:4px; border:1px solid #d0c0e8;">`
        : '';
      row.innerHTML = `
        <div style="display:flex; gap:8px; align-items:center;">
          ${previewHtml}
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
      btn.addEventListener('click', () => selectFile(btn.dataset.category, btn.dataset.selectFile)));
    listEl.querySelectorAll('[data-delete-file]').forEach(btn =>
      btn.addEventListener('click', () => deleteFile(btn.dataset.category, btn.dataset.deleteFile)));
  } catch (e) {
    listEl.innerHTML = '<div style="color:#c62828; font-size:0.85rem;">読み込み失敗: ' + esc(e.message) + '</div>';
  }
}

async function uploadFile(category, input) {
  const files = input.files;
  if (!files || files.length === 0) return;
  const statusEl = document.getElementById(category + '-upload-status');

  for (const file of files) {
    if (statusEl) { statusEl.textContent = 'アップロード中: ' + file.name + '...'; statusEl.style.color = '#6a5590'; }
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await fetch('/api/files/' + category + '/upload', { method: 'POST', body: formData });
      const data = await res.json();
      if (data.ok) {
        showToast('アップロード完了: ' + (data.file || file.name), 'success');
      } else {
        showToast('アップロード失敗: ' + (data.error || ''), 'error');
      }
    } catch (e) {
      showToast('アップロード失敗: ' + e.message, 'error');
    }
  }
  input.value = '';
  if (statusEl) statusEl.textContent = '';
  loadCategoryFiles(category);
}

async function selectFile(category, file) {
  const res = await api('POST', '/api/files/' + category + '/select', { file });
  if (res && res.ok) {
    showToast('適用しました: ' + file, 'success');
    loadCategoryFiles(category);
  }
}

async function deleteFile(category, file) {
  if (!await showConfirm('このファイルを削除しますか？\n' + file, { title: '削除', okLabel: '削除', danger: true })) return;
  try {
    const r = await fetch('/api/files/' + category + '?file=' + encodeURIComponent(file), { method: 'DELETE' });
    const data = await r.json();
    showToast(data.ok ? '削除しました' : (data.error || '削除失敗'), data.ok ? 'success' : 'error');
  } catch (e) {
    showToast('削除失敗: ' + e.message, 'error');
  }
  loadCategoryFiles(category);
}
