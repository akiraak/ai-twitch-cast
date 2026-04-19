// 録画ファイル管理タブ — 一覧表示・ダウンロード・削除

async function loadRecordings() {
  const listEl = document.getElementById('recordings-list');
  const countEl = document.getElementById('recordings-count');
  if (!listEl) return;
  listEl.textContent = '読み込み中...';
  try {
    const resp = await fetch('/api/recordings');
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    const items = data.recordings || [];
    if (countEl) countEl.textContent = `(${items.length}件)`;

    if (items.length === 0) {
      listEl.innerHTML = '<p style="color:#9a88b5;">録画ファイルはありません</p>';
      return;
    }

    const rows = items.map(item => {
      const size = formatRecordingSize(item.size_bytes);
      const date = formatRecordingDate(item.created_at);
      const name = esc(item.filename);
      return `
        <tr>
          <td style="padding:6px 8px; font-family:monospace;">${name}</td>
          <td style="padding:6px 8px; white-space:nowrap; color:#9a88b5;">${date}</td>
          <td style="padding:6px 8px; text-align:right; white-space:nowrap;">${size}</td>
          <td style="padding:6px 8px; white-space:nowrap;">
            <a href="/api/recordings/${encodeURIComponent(item.filename)}/download"
               download="${name}"
               style="margin-right:6px; text-decoration:none; color:#7b1fa2;" title="ダウンロード">⬇️</a>
            <button onclick="deleteRecording('${encodeURIComponent(item.filename)}')"
                    style="background:none; border:none; cursor:pointer; color:#c62828; padding:0;"
                    title="削除">🗑</button>
          </td>
        </tr>`;
    }).join('');

    listEl.innerHTML = `
      <table style="width:100%; border-collapse:collapse; font-size:0.8rem;">
        <thead>
          <tr style="border-bottom:1px solid #e0d8f0; color:#6a5590;">
            <th style="padding:6px 8px; text-align:left;">ファイル名</th>
            <th style="padding:6px 8px; text-align:left;">作成日時</th>
            <th style="padding:6px 8px; text-align:right;">サイズ</th>
            <th style="padding:6px 8px; text-align:left;">操作</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>`;
  } catch (err) {
    listEl.innerHTML = `<p style="color:#c62828;">読み込み失敗: ${esc(err.message)}</p>`;
    if (countEl) countEl.textContent = '';
  }
}

async function deleteRecording(encodedName) {
  const name = decodeURIComponent(encodedName);
  const ok = await showConfirm(`録画 "${name}" を削除しますか？`, {
    title: '録画の削除',
    okLabel: '削除',
    danger: true,
  });
  if (!ok) return;
  try {
    const resp = await fetch(`/api/recordings/${encodedName}`, { method: 'DELETE' });
    if (!resp.ok) {
      const body = await resp.text();
      throw new Error(`HTTP ${resp.status}: ${body}`);
    }
    showToast(`削除しました: ${name}`);
    loadRecordings();
  } catch (err) {
    showToast(`削除失敗: ${err.message}`, 'error');
  }
}

function formatRecordingSize(bytes) {
  if (bytes == null) return '-';
  if (bytes >= 1073741824) return (bytes / 1073741824).toFixed(2) + ' GB';
  if (bytes >= 1048576) return (bytes / 1048576).toFixed(1) + ' MB';
  if (bytes >= 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return bytes + ' B';
}

function formatRecordingDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}/${pad(d.getMonth() + 1)}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
