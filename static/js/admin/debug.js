// アバター制御テスト
async function avatarTest(avatarId, testType) {
  const st = document.getElementById('avatar-test-status');
  st.textContent = `${avatarId}/${testType} 送信中...`;
  st.style.color = '#9a88b5';
  try {
    const res = await api('POST', '/api/debug/avatar-test', { avatar_id: avatarId, test_type: testType });
    if (res?.ok) {
      st.textContent = `${avatarId}/${testType} 送信OK`;
      st.style.color = '#2e7d32';
    } else {
      st.textContent = res?.error || '失敗';
      st.style.color = '#c62828';
    }
  } catch (e) {
    st.textContent = 'エラー: ' + e.message;
    st.style.color = '#c62828';
  }
}

// スクリーンショット

async function takeScreenshot() {
  const btn = document.getElementById('btn-screenshot');
  const st = document.getElementById('screenshot-status');
  btn.disabled = true;
  btn.textContent = '撮影中...';
  st.textContent = '';
  try {
    const res = await api('POST', '/api/capture/screenshot');
    if (res?.ok) {
      st.textContent = res.file + ' (' + Math.round(res.size / 1024) + 'KB)';
      st.style.color = '#2e7d32';
      loadScreenshots();
    } else {
      st.textContent = res?.detail || 'スクリーンショット失敗';
      st.style.color = '#c62828';
    }
  } catch (e) {
    st.textContent = 'エラー: ' + e.message;
    st.style.color = '#c62828';
  } finally {
    btn.disabled = false;
    btn.textContent = 'スクリーンショット撮影';
  }
}

async function loadScreenshots() {
  try {
    const data = await (await fetch('/api/capture/screenshots')).json();
    const el = document.getElementById('screenshot-list');
    const countEl = document.getElementById('screenshot-count');
    countEl.textContent = data.files.length ? `(${data.files.length}件)` : '';
    if (!data.files.length) {
      el.innerHTML = '<span style="color:#9a88b5;">スクリーンショットなし</span>';
      return;
    }
    el.innerHTML = data.files.map(f => {
      const sizeKB = Math.round(f.size / 1024);
      const dt = f.created.replace('T', ' ').substring(0, 19);
      return `<div style="display:flex; align-items:center; gap:10px; padding:8px 6px; border-bottom:1px solid #e8e0f0;">
        <img src="/api/capture/screenshots/${f.name}" style="width:160px; height:90px; object-fit:contain; background:#1a1a2e; border-radius:4px; cursor:pointer;" onclick="window.open('/api/capture/screenshots/${f.name}','_blank')">
        <div style="flex:1; min-width:0;">
          <div style="font-size:0.85rem; font-weight:500; word-break:break-all;">${esc(f.name)}</div>
          <div style="font-size:0.75rem; color:#9a88b5;">${dt} / ${sizeKB}KB</div>
          <div style="font-size:0.7rem; color:#6a5590; margin-top:2px;">パス: /tmp/screenshots/${esc(f.name)}</div>
        </div>
        <button class="danger" style="font-size:0.75rem; padding:4px 10px;" onclick="deleteScreenshot('${esc(f.name)}')">削除</button>
      </div>`;
    }).join('');
  } catch (e) {}
}

async function deleteScreenshot(name) {
  await fetch('/api/capture/screenshots/' + encodeURIComponent(name), { method: 'DELETE' });
  loadScreenshots();
}
