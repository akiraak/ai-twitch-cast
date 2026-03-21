// DB閲覧
let _dbCurrentTable = '';
let _dbOffset = 0;
const _dbLimit = 50;

async function loadDbTables() {
  try {
    const r = await fetch('/api/db/tables');
    const d = await r.json();
    const el = document.getElementById('db-tables');
    el.innerHTML = d.tables.map(t =>
      `<button class="db-tab${t.name === _dbCurrentTable ? ' active' : ''}" onclick="selectDbTable('${t.name}')">${esc(t.name)}<span class="db-tab-count">(${t.count})</span></button>`
    ).join('');
  } catch(e) {}
}

async function updateUserNotes() {
  const btn = document.getElementById('btn-update-notes');
  btn.disabled = true;
  btn.textContent = '更新中...';
  try {
    const r = await fetch('/api/db/update-notes', { method: 'POST' });
    const d = await r.json();
    showToast(`メモ更新完了: ${d.updated}人`, 'success');
    if (_dbCurrentTable === 'users') await loadDbData();
  } catch(e) {
    showToast('メモ更新失敗', 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'メモ更新';
  }
}

async function selectDbTable(name) {
  _dbCurrentTable = name;
  _dbOffset = 0;
  loadDbTables();
  await loadDbData();
}

async function loadDbData() {
  if (!_dbCurrentTable) return;
  try {
    const r = await fetch(`/api/db/${_dbCurrentTable}?limit=${_dbLimit}&offset=${_dbOffset}`);
    const d = await r.json();
    if (d.error) return;
    document.getElementById('db-table-name').textContent = d.table;
    document.getElementById('db-table-count').textContent = `${d.total}件`;
    const thead = document.getElementById('db-thead');
    const tbody = document.getElementById('db-tbody');
    thead.innerHTML = '<tr>' + d.columns.map(c => `<th>${esc(c)}</th>`).join('') + '</tr>';
    tbody.innerHTML = d.rows.map(row =>
      '<tr>' + d.columns.map(c => {
        let v = row[c];
        if (v === null) v = '';
        return `<td title="${escHtml(String(v))}">${esc(String(v))}</td>`;
      }).join('') + '</tr>'
    ).join('');
    const pager = document.getElementById('db-pager');
    const page = Math.floor(_dbOffset / _dbLimit) + 1;
    const totalPages = Math.ceil(d.total / _dbLimit);
    pager.innerHTML = '';
    if (totalPages > 1) {
      pager.innerHTML =
        `<button onclick="dbPage(-1)" ${_dbOffset === 0 ? 'disabled' : ''} style="font-size:0.75rem;">前</button>` +
        `<span style="font-size:0.8rem; color:#6a5590;">${page} / ${totalPages}</span>` +
        `<button onclick="dbPage(1)" ${page >= totalPages ? 'disabled' : ''} style="font-size:0.75rem;">次</button>`;
    }
  } catch(e) {}
}

function dbPage(dir) {
  _dbOffset = Math.max(0, _dbOffset + dir * _dbLimit);
  loadDbData();
}
