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

    // ルート vs サブディレクトリにグループ分け
    const rootFiles = [];
    const groups = {};
    data.files.forEach(f => {
      const slashIdx = f.name.indexOf('/');
      if (slashIdx === -1) {
        rootFiles.push(f);
      } else {
        const dir = f.name.substring(0, slashIdx);
        if (!groups[dir]) groups[dir] = [];
        groups[dir].push(f);
      }
    });

    // 各グループを修正日時の新しい順でソート
    const sortByDate = (a, b) => b.modified - a.modified;
    rootFiles.sort(sortByDate);
    Object.values(groups).forEach(g => g.sort(sortByDate));

    const el = document.getElementById('docs-file-list');
    let html = '';

    // サブディレクトリ（archive以外）を先に表示
    const dirNames = Object.keys(groups).sort();
    const nonArchive = dirNames.filter(d => d !== 'archive');
    const archiveDirs = dirNames.filter(d => d === 'archive');

    for (const dir of nonArchive) {
      html += renderDocGroup(dir, groups[dir]);
    }

    // ルートファイル
    rootFiles.forEach(f => { html += renderDocFileBtn(f); });

    // archiveは末尾に表示
    for (const dir of archiveDirs) {
      html += renderDocGroup(dir, groups[dir]);
    }

    el.innerHTML = html;

    // 選択中ファイルがフォルダ内の場合、そのフォルダを自動展開
    if (_docsCurrentFile && _docsCurrentFile.includes('/')) {
      const folderDetails = el.querySelectorAll('details.docs-folder');
      folderDetails.forEach(d => {
        if (d.querySelector(`button.docs-file-btn.active`)) {
          d.open = true;
        }
      });
    }
  } catch(e) {}
}

function renderDocGroup(dir, files) {
  const inner = files.map(f => renderDocFileBtn(f)).join('');
  return `<details class="docs-folder">
    <summary>${esc(dir)} <span class="docs-folder-count">(${files.length})</span></summary>
    <div class="docs-folder-body">${inner}</div>
  </details>`;
}

function renderDocFileBtn(f) {
  const baseName = f.name.includes('/') ? f.name.split('/').pop() : f.name;
  const title = f.title || baseName;
  const activeClass = f.name === _docsCurrentFile ? ' active' : '';
  return `<button class="docs-file-btn${activeClass}"
    onclick="selectDocFile('${esc(f.name)}')"
    title="${esc(f.name)}">
    <span class="docs-file-title">${esc(title)}</span>
    <span class="docs-file-name">${esc(baseName)}</span>
  </button>`;
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
