// 配信言語設定

async function loadLanguageModes() {
  try {
    const d = await (await fetch('/api/language')).json();
    const el = document.getElementById('language-modes');
    const mixInfo = {
      low:    {label: '少し',     desc: '挨拶・感嘆詞くらい', bar: 1},
      medium: {label: 'ほどほど', desc: 'フレーズ単位で混ぜる', bar: 2},
      high:   {label: 'たくさん', desc: '文単位で両方使う',     bar: 3},
    };
    const langOptions = (selected) => d.languages.map(l =>
      `<option value="${l.code}" ${l.code === selected ? 'selected' : ''}>${esc(l.name)}</option>`
    ).join('');
    const subOptions = `<option value="none" ${d.sub === 'none' ? 'selected' : ''}>なし</option>` + langOptions(d.sub);
    const mixButtons = d.mix_levels.map(lvl => {
      const m = mixInfo[lvl] || {label: lvl, desc: '', bar: 1};
      const active = lvl === d.mix;
      const bars = '<span style="display:inline-flex; gap:2px; margin-right:4px;">'
        + [1,2,3].map(i => `<span style="display:inline-block; width:3px; height:${8+i*3}px; border-radius:1px; background:${i <= m.bar ? (active ? '#7b1fa2' : '#b0a0c0') : '#e0d0f0'}; vertical-align:bottom;"></span>`).join('')
        + '</span>';
      return `<button class="${active ? '' : 'secondary'}" onclick="setStreamLangMix('${lvl}')" style="font-size:0.78rem; padding:6px 14px;" title="${esc(m.desc)}">${bars}${esc(m.label)}</button>`;
    }).join('');
    el.innerHTML = `
      <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
        <label style="font-size:0.82rem;">基本言語:
          <select id="lang-primary" onchange="saveStreamLang()" style="padding:4px 8px; font-size:0.82rem;">${langOptions(d.primary)}</select>
        </label>
        <label style="font-size:0.82rem;">サブ言語:
          <select id="lang-sub" onchange="saveStreamLang()" style="padding:4px 8px; font-size:0.82rem;">${subOptions}</select>
        </label>
      </div>
      <div id="lang-mix-row" style="margin-top:10px; display:flex; gap:8px; align-items:center;${d.sub === 'none' ? ' visibility:hidden;' : ''}">
        <span style="font-size:0.82rem;">${esc((d.languages.find(l => l.code === d.sub) || {}).name || d.sub)}を混ぜる量:</span> ${mixButtons}
      </div>`;
    const descEl = document.getElementById('lang-description');
    if (d.text_rules || d.tts_style) {
      const rulesHtml = (d.text_rules || []).map(r => r ? `<li>${esc(r)}</li>` : '').join('');
      descEl.innerHTML = `<details><summary style="cursor:pointer; font-size:0.82rem; font-weight:600; color:#6a5590;">生成プロンプト プレビュー</summary>`
        + `<div style="margin-top:8px;"><strong>テキスト生成ルール:</strong><ul style="margin:4px 0 8px; padding-left:20px;">${rulesHtml}</ul></div>`
        + `<div><strong>TTSスタイル:</strong><div style="margin-top:4px; padding:6px 10px; background:#fff; border-radius:4px; font-size:0.8rem; color:#333;">${esc(d.tts_style || '')}</div></div>`
        + `</details>`;
      descEl.style.display = '';
    } else {
      descEl.style.display = 'none';
    }
  } catch(e) {}
}

async function saveStreamLang() {
  const primary = document.getElementById('lang-primary').value;
  const sub = document.getElementById('lang-sub').value;
  const actualSub = (sub === primary) ? 'none' : sub;
  const activeBtn = document.querySelector('#lang-mix-row button:not(.secondary)');
  const mix = activeBtn ? activeBtn.getAttribute('onclick').match(/'(\w+)'/)[1] : 'low';
  try {
    const r = await fetch('/api/language', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({primary, sub: actualSub, mix}) });
    const d = await r.json();
    if (d.ok) {
      showToast('配信言語を更新しました', 'success');
      loadLanguageModes();
      loadCharacter();
    } else {
      showToast(d.error || '変更失敗', 'error');
    }
  } catch(e) { showToast('配信言語変更失敗', 'error'); }
}

async function setStreamLangMix(mix) {
  const primary = document.getElementById('lang-primary').value;
  const sub = document.getElementById('lang-sub').value;
  try {
    const r = await fetch('/api/language', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({primary, sub, mix}) });
    const d = await r.json();
    if (d.ok) {
      showToast('混ぜ具合を更新しました', 'success');
      loadLanguageModes();
      loadCharacter();
    } else {
      showToast(d.error || '変更失敗', 'error');
    }
  } catch(e) { showToast('配信言語変更失敗', 'error'); }
}
