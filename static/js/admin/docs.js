// Docs閲覧（plans/ docs/ のMarkdownファイル）
let _docsCurrentDir = 'plans';
let _docsCurrentFile = '';

function switchDocsDir(dir) {
  _docsCurrentDir = dir;
  _docsCurrentFile = '';
  document.getElementById('docs-dir-plans').classList.toggle('active', dir === 'plans');
  document.getElementById('docs-dir-docs').classList.toggle('active', dir === 'docs');
  loadDocFiles();
  resetDocsContent();
}

async function loadDocFiles() {
  try {
    const res = await fetch(`/api/docs/files?dir=${_docsCurrentDir}`);
    const data = await res.json();
    const el = document.getElementById('docs-file-list');
    el.innerHTML = data.files.map(f =>
      `<button class="db-tab${f.name === _docsCurrentFile ? ' active' : ''}"
              onclick="selectDocFile('${esc(f.name)}')">${esc(f.name)}</button>`
    ).join('');
  } catch(e) {}
}

async function selectDocFile(name) {
  _docsCurrentFile = name;
  loadDocFiles();
  document.getElementById('docs-file-name').textContent = name;

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
