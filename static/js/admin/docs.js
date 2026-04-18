// Docs閲覧（plans/ docs/ のMarkdownファイル）
let _docsCurrentDir = 'plans';
let _docsCurrentFile = '';
let _docsFiles = [];

function switchDocsDir(dir) {
  _docsCurrentDir = dir;
  _docsCurrentFile = '';
  location.hash = `docs:${dir}`;
  document.getElementById('docs-dir-plans').classList.toggle('active', dir === 'plans');
  document.getElementById('docs-dir-docs').classList.toggle('active', dir === 'docs');
  document.getElementById('docs-dir-prompts').classList.toggle('active', dir === 'prompts');
  loadDocFiles();
  resetDocsContent();
}

async function loadDocFiles() {
  try {
    const res = await fetch(`/api/docs/files?dir=${_docsCurrentDir}`);
    const data = await res.json();
    if (!data.ok) return;
    _docsFiles = data.files;

    // ファイルリストをパスからツリー構造に組み立てる
    const tree = buildDocTree(data.files);
    const el = document.getElementById('docs-file-list');
    const isPlansDir = _docsCurrentDir === 'plans';

    // トップレベル: archive以外のディレクトリ → ルートファイル → archiveディレクトリ
    const topDirs = Object.entries(tree.dirs).sort((a, b) => a[0].localeCompare(b[0]));
    const nonArchive = topDirs.filter(([k]) => k !== 'archive');
    const archiveEntry = topDirs.find(([k]) => k === 'archive');
    const rootFiles = [...tree.files].sort((a, b) => b.modified - a.modified);

    let html = '';
    for (const [dir, node] of nonArchive) {
      html += renderDocTreeNode(dir, node, { archivable: isPlansDir });
    }
    rootFiles.forEach(f => { html += renderDocFileBtn(f); });
    if (archiveEntry) {
      html += renderDocTreeNode('archive', archiveEntry[1], { archivable: false });
    }

    el.innerHTML = html;

    // 選択中ファイルが含まれるフォルダ（祖先を含む）を自動展開
    if (_docsCurrentFile && _docsCurrentFile.includes('/')) {
      el.querySelectorAll('details.docs-folder').forEach(d => {
        if (d.querySelector('button.docs-file-btn.active')) {
          d.open = true;
        }
      });
    }
  } catch(e) {}
}

// ファイル一覧からディレクトリツリーを組み立てる
function buildDocTree(files) {
  const root = { files: [], dirs: {} };
  files.forEach(f => {
    const parts = f.name.split('/');
    parts.pop(); // ファイル名を除く
    let node = root;
    parts.forEach(seg => {
      if (!node.dirs[seg]) node.dirs[seg] = { files: [], dirs: {} };
      node = node.dirs[seg];
    });
    node.files.push(f);
  });
  return root;
}

// ノード配下のファイル総数（再帰）
function docTreeCount(node) {
  return node.files.length + Object.values(node.dirs).reduce((a, d) => a + docTreeCount(d), 0);
}

// ディレクトリノードを <details> として再帰描画
function renderDocTreeNode(dirName, node, { archivable = false } = {}) {
  const subDirs = Object.entries(node.dirs).sort((a, b) => a[0].localeCompare(b[0]));
  const files = [...node.files].sort((a, b) => b.modified - a.modified);

  let inner = '';
  for (const [sd, sn] of subDirs) {
    // 入れ子のディレクトリはアーカイブ対象外
    inner += renderDocTreeNode(sd, sn, { archivable: false });
  }
  files.forEach(f => { inner += renderDocFileBtn(f); });

  const archiveBtn = archivable
    ? `<span class="docs-folder-archive-btn" title="plans/archive/ に移動"
        onclick="event.stopPropagation(); event.preventDefault(); archivePlan('${esc(dirName)}')">📦</span>`
    : '';
  const total = docTreeCount(node);
  return `<details class="docs-folder">
    <summary>${esc(dirName)} <span class="docs-folder-count">(${total})</span>${archiveBtn}</summary>
    <div class="docs-folder-body">${inner}</div>
  </details>`;
}

function renderDocFileBtn(f) {
  const baseName = f.name.includes('/') ? f.name.split('/').pop() : f.name;
  const title = f.title || baseName;
  const activeClass = f.name === _docsCurrentFile ? ' active' : '';
  const isRootPlan = _docsCurrentDir === 'plans' && !f.name.includes('/');
  const archiveBtn = isRootPlan
    ? `<span class="docs-file-archive-btn" title="plans/archive/ に移動"
        onclick="event.stopPropagation(); archivePlan('${esc(f.name)}')">📦</span>`
    : '';
  return `<button class="docs-file-btn${activeClass}"
    onclick="selectDocFile('${esc(f.name)}')"
    title="${esc(f.name)}">
    <span class="docs-file-title">${esc(title)}</span>
    <span class="docs-file-name">${esc(baseName)}</span>
    ${archiveBtn}
  </button>`;
}

async function archivePlan(name) {
  if (!await showConfirm(`${name} を plans/archive/ に移動しますか？`, { title: 'アーカイブ', okLabel: '移動' })) return;
  try {
    const res = await fetch(`/api/docs/archive-plan?name=${encodeURIComponent(name)}`, { method: 'POST' });
    const data = await res.json();
    if (!data.ok) {
      showToast(`移動失敗: ${data.error || '不明なエラー'}`, 'error');
      return;
    }
    if (_docsCurrentFile === name || _docsCurrentFile.startsWith(name + '/')) {
      _docsCurrentFile = '';
      resetDocsContent();
    }
    loadDocFiles();
    showToast(`${name} をアーカイブしました`);
  } catch (e) {
    showToast(`移動失敗: ${e.message || e}`, 'error');
  }
}

async function selectDocFile(name) {
  _docsCurrentFile = name;
  location.hash = `docs:${_docsCurrentDir}:${name}`;
  loadDocFiles();
  const fileInfo = _docsFiles.find(f => f.name === name);
  const displayName = fileInfo?.title || name;
  document.getElementById('docs-file-name').textContent = displayName;

  try {
    const res = await fetch(`/api/docs/file?dir=${_docsCurrentDir}&name=${encodeURIComponent(name)}`);
    if (!res.ok) {
      document.getElementById('docs-content').innerHTML = '<p style="color:#c62828;">ファイルの読み込みに失敗しました</p>';
      return;
    }
    const md = await res.text();
    document.getElementById('docs-file-meta').textContent = `${md.length}文字`;
    document.getElementById('docs-content').innerHTML = simpleMarkdownToHtml(md);
  } catch(e) {
    document.getElementById('docs-content').innerHTML = '<p style="color:#c62828;">ファイルの読み込みに失敗しました</p>';
  }
}

function resetDocsContent() {
  document.getElementById('docs-file-name').textContent = 'ファイルを選択してください';
  document.getElementById('docs-file-meta').textContent = '';
  document.getElementById('docs-content').innerHTML =
    '<p style="color:#9a88b5;">← ファイルを選択すると内容が表示されます</p>';
}
