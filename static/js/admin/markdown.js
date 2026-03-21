// Markdownレンダリング・ドキュメントモーダル

function simpleMarkdownToHtml(md) {
  const lines = md.split('\n');
  let html = '';
  let inCode = false;
  let inTable = false;
  let inList = false;
  let inAdmonition = false;
  let admonitionContent = '';

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (line.startsWith('```')) {
      if (inCode) { html += '</code></pre>'; inCode = false; }
      else { html += '<pre><code>'; inCode = true; }
      continue;
    }
    if (inCode) { html += esc(line) + '\n'; continue; }

    if (line.match(/^!!!\s+\w+/)) {
      const title = line.replace(/^!!!\s+\w+\s*/, '').trim() || line.match(/^!!!\s+(\w+)/)[1];
      inAdmonition = true;
      admonitionContent = `<div class="admonition"><div class="admonition-title">${esc(title)}</div>`;
      continue;
    }
    if (inAdmonition) {
      if (line.startsWith('    ')) {
        admonitionContent += '<p>' + inlineMarkdown(line.trim()) + '</p>';
        continue;
      } else {
        html += admonitionContent + '</div>';
        inAdmonition = false;
      }
    }

    if (line.match(/^\|.+\|$/)) {
      if (line.match(/^\|[\s-:|]+\|$/)) continue;
      const cells = line.split('|').slice(1, -1).map(c => c.trim());
      if (!inTable) {
        html += '<table><thead><tr>' + cells.map(c => '<th>' + inlineMarkdown(c) + '</th>').join('') + '</tr></thead><tbody>';
        inTable = true;
      } else {
        html += '<tr>' + cells.map(c => '<td>' + inlineMarkdown(c) + '</td>').join('') + '</tr>';
      }
      continue;
    }
    if (inTable) { html += '</tbody></table>'; inTable = false; }

    if (line.match(/^\s*-\s/)) {
      if (!inList) { html += '<ul>'; inList = true; }
      html += '<li>' + inlineMarkdown(line.replace(/^\s*-\s/, '')) + '</li>';
      continue;
    }
    if (inList && !line.match(/^\s*-\s/)) { html += '</ul>'; inList = false; }

    if (line.startsWith('### ')) { html += '<h3>' + inlineMarkdown(line.slice(4)) + '</h3>'; continue; }
    if (line.startsWith('## ')) { html += '<h2>' + inlineMarkdown(line.slice(3)) + '</h2>'; continue; }
    if (line.startsWith('# ')) { html += '<h1>' + inlineMarkdown(line.slice(2)) + '</h1>'; continue; }

    if (!line.trim()) { continue; }

    html += '<p>' + inlineMarkdown(line) + '</p>';
  }
  if (inTable) html += '</tbody></table>';
  if (inList) html += '</ul>';
  if (inAdmonition) html += admonitionContent + '</div>';
  if (inCode) html += '</code></pre>';
  return html;
}

function inlineMarkdown(text) {
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>');
}

async function showCharacterPromptDoc() {
  const existing = document.querySelector('.doc-modal-overlay');
  if (existing) { existing.remove(); return; }

  const overlay = document.createElement('div');
  overlay.className = 'doc-modal-overlay';
  overlay.innerHTML = `<div class="doc-modal">
    <div class="doc-modal-header">
      <h3>会話生成の仕組み</h3>
      <button class="doc-modal-close" title="閉じる">&times;</button>
    </div>
    <div class="doc-modal-body"><p style="color:#9a88b5;">読み込み中...</p></div>
  </div>`;

  overlay.addEventListener('click', e => {
    if (e.target === overlay) overlay.remove();
  });
  overlay.querySelector('.doc-modal-close').addEventListener('click', () => overlay.remove());
  document.addEventListener('keydown', function handler(e) {
    if (e.key === 'Escape') { overlay.remove(); document.removeEventListener('keydown', handler); }
  });
  document.body.appendChild(overlay);

  try {
    let res = await fetch('/api/docs/character-prompt');
    if (!res.ok) res = await fetch('/static/docs/character-prompt.md');
    if (!res.ok) throw new Error('取得失敗');
    const md = await res.text();
    overlay.querySelector('.doc-modal-body').innerHTML = simpleMarkdownToHtml(md);
  } catch (e) {
    overlay.querySelector('.doc-modal-body').innerHTML = '<p style="color:#c62828;">ドキュメントの読み込みに失敗しました</p>';
  }
}
