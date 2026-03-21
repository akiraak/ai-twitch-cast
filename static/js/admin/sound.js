// サウンド（TTS・BGM・YouTube DL）

async function ttsTest(pattern) {
  await api('POST', '/api/tts/test', { pattern });
}

async function emotionTest(emotion) {
  await api('POST', '/api/tts/test-emotion', { emotion });
}

const bgmTracksEl = document.getElementById('bgm-tracks');

async function loadBgmTracks() {
  const res = await fetch('/api/bgm/list');
  const data = await res.json();
  const currentTrack = data.track || '';
  bgmTracksEl.innerHTML = '';
  for (const t of data.tracks) {
    const isPlaying = t.file === currentTrack;
    const volPct = Math.round((t.volume ?? 1) * 100);
    const row = document.createElement('div');
    row.dataset.file = t.file;
    row.style.cssText = 'padding:8px 6px; border-bottom:1px solid #d0c0e8;'
      + (isPlaying ? ' background:#ece5fa; border-radius:6px;' : '');
    row.innerHTML = `
      <div style="display:flex; gap:8px; align-items:center;">
        ${isPlaying ? '<span style="font-size:0.8rem; margin-right:2px;">▶</span>' : ''}
        <span style="flex:1; font-size:0.9rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;${isPlaying ? ' font-weight:600; color:#7b1fa2;' : ''}">${
          t.source_url
            ? `<a href="${escHtml(t.source_url)}" target="_blank" rel="noopener" style="color:inherit; text-decoration:underline dotted; text-underline-offset:3px;" title="${escHtml(t.source_url)}">${esc(t.name)}</a>`
            : esc(t.name)
        }</span>
        ${isPlaying
          ? `<button class="secondary" data-bgm-stop style="font-size:0.75rem;">停止</button>`
          : `<button data-bgm-play="${esc(t.file)}" style="font-size:0.75rem;">再生</button>`}
        <button class="danger" data-bgm-del="${esc(t.file)}" style="font-size:0.7rem; padding:2px 6px;" title="削除">×</button>
      </div>
      <div class="vol-row" style="margin-top:4px;">
        <span class="vol-label">曲音量</span>
        <input type="range" min="0" max="100" step="1" value="${volPct}" class="vol-slider"
          oninput="this.nextElementSibling.textContent=this.value+'%'"
          onchange="setTrackVolume('${esc(t.file)}', this.value)">
        <span class="vol-pct">${volPct}%</span>
      </div>
    `;
    bgmTracksEl.appendChild(row);
  }
  if (data.tracks.length === 0) {
    bgmTracksEl.innerHTML = '<div style="color:#9a88b5; font-size:0.85rem;">BGMファイルがありません</div>';
  }
  bgmTracksEl.querySelectorAll('[data-bgm-play]').forEach(btn =>
    btn.addEventListener('click', () => bgmPlay(btn.dataset.bgmPlay)));
  bgmTracksEl.querySelectorAll('[data-bgm-stop]').forEach(btn =>
    btn.addEventListener('click', () => bgmStop()));
  bgmTracksEl.querySelectorAll('[data-bgm-del]').forEach(btn =>
    btn.addEventListener('click', () => bgmDelete(btn.dataset.bgmDel)));
}

async function setTrackVolume(file, pct) {
  await api('POST', '/api/bgm/track-volume', { file, volume: parseInt(pct) / 100 });
}

async function syncBgmVolumes() {
  try {
    const res = await fetch('/api/bgm/list');
    const data = await res.json();
    for (const t of data.tracks) {
      const row = bgmTracksEl.querySelector(`[data-file="${CSS.escape(t.file)}"]`);
      if (!row) continue;
      const slider = row.querySelector('.vol-slider');
      const label = row.querySelector('.vol-pct');
      const newVal = Math.round((t.volume ?? 1) * 100);
      if (slider && slider.value != newVal && !slider.matches(':active')) {
        slider.value = newVal;
        if (label) label.textContent = newVal + '%';
      }
    }
  } catch {}
}

async function bgmPlay(file) {
  const res = await api('POST', '/api/bgm', { action: 'play', track: file });
  if (res && res.ok) loadBgmTracks();
}

async function bgmStop() {
  await api('POST', '/api/bgm', { action: 'stop' });
  loadBgmTracks();
}

async function bgmDelete(file) {
  if (!await showConfirm('このトラックを削除しますか？', { title: '削除', okLabel: '削除', danger: true })) return;
  try {
    const r = await fetch('/api/bgm/track?file=' + encodeURIComponent(file), { method: 'DELETE' });
    const data = await r.json();
    showToast(data.ok ? '削除しました' : (data.error || '削除失敗'), data.ok ? 'success' : 'error');
  } catch (e) {
    showToast('削除失敗: ' + e.message, 'error');
  }
  loadBgmTracks();
}

// === SE（効果音）管理 ===

const seTracksEl = document.getElementById('se-tracks');

async function loadSeTracks() {
  if (!seTracksEl) return;
  try {
    const res = await fetch('/api/se/list');
    const data = await res.json();

    // テスト再生ボタンを生成
    const testBtns = document.getElementById('se-test-buttons');
    if (testBtns) {
      testBtns.innerHTML = '';
      if (data.tracks.length === 0) {
        testBtns.innerHTML = '<span style="color:#9a88b5; font-size:0.8rem;">SEなし</span>';
      }
      for (const t of data.tracks) {
        const btn = document.createElement('button');
        btn.textContent = t.category || t.name;
        btn.style.cssText = 'font-size:0.75rem; padding:4px 10px;';
        btn.title = t.file;
        btn.addEventListener('click', () => sePlay(t.file));
        testBtns.appendChild(btn);
      }
    }

    seTracksEl.innerHTML = '';
    for (const t of data.tracks) {
      const volPct = Math.round((t.volume ?? 1) * 100);
      const row = document.createElement('div');
      row.style.cssText = 'padding:6px; border-bottom:1px solid #d0c0e8;';
      row.innerHTML = `
        <div style="display:flex; gap:6px; align-items:center;">
          <span style="flex:1; font-size:0.85rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
            <strong>${esc(t.category || t.name)}</strong>
            <span style="color:#9a88b5; font-size:0.75rem;">${esc(t.file)}</span>
          </span>
          <button data-se-play="${esc(t.file)}" style="font-size:0.7rem; padding:2px 8px;">&#9654;</button>
          <button class="danger" data-se-del="${esc(t.file)}" style="font-size:0.7rem; padding:2px 6px;" title="削除">&times;</button>
        </div>
        <div class="vol-row" style="margin-top:2px;">
          <span class="vol-label">音量</span>
          <input type="range" min="0" max="100" step="1" value="${volPct}" class="vol-slider"
            oninput="this.nextElementSibling.textContent=this.value+'%'"
            onchange="setSeTrackVolume('${esc(t.file)}', '${esc(t.category)}', this.value)">
          <span class="vol-pct">${volPct}%</span>
        </div>
      `;
      seTracksEl.appendChild(row);
    }
    if (data.tracks.length === 0) {
      seTracksEl.innerHTML = '<div style="color:#9a88b5; font-size:0.85rem;">SEファイルがありません</div>';
    }
    seTracksEl.querySelectorAll('[data-se-play]').forEach(btn =>
      btn.addEventListener('click', () => sePlay(btn.dataset.sePlay)));
    seTracksEl.querySelectorAll('[data-se-del]').forEach(btn =>
      btn.addEventListener('click', () => seDelete(btn.dataset.seDel)));
  } catch (e) {
    console.error('SE一覧取得失敗:', e);
  }
}

async function sePlay(file) {
  await api('POST', '/api/se/play', { file });
}

async function setSeTrackVolume(file, category, pct) {
  await api('POST', '/api/se/track', { file, category, volume: parseInt(pct) / 100 });
}

async function seDelete(file) {
  if (!await showConfirm('このSEを削除しますか？', { title: '削除', okLabel: '削除', danger: true })) return;
  try {
    const r = await fetch('/api/se/track?file=' + encodeURIComponent(file), { method: 'DELETE' });
    const data = await r.json();
    showToast(data.ok ? '削除しました' : (data.error || '削除失敗'), data.ok ? 'success' : 'error');
  } catch (e) {
    showToast('削除失敗: ' + e.message, 'error');
  }
  loadSeTracks();
}

async function seUpload() {
  const input = document.getElementById('se-upload-file');
  if (!input || !input.files.length) return;
  const file = input.files[0];
  const formData = new FormData();
  formData.append('file', file);
  try {
    const res = await fetch('/api/se/upload', { method: 'POST', body: formData });
    const data = await res.json();
    showToast(data.ok ? 'アップロード完了' : (data.error || '失敗'), data.ok ? 'success' : 'error');
    input.value = '';
    loadSeTracks();
  } catch (e) {
    showToast('アップロード失敗: ' + e.message, 'error');
  }
}

// ページ読み込み時にSE一覧も取得
if (seTracksEl) loadSeTracks();

async function ytDownload() {
  const url = document.getElementById('yt-url').value.trim();
  if (!url) return;
  setStatus('yt-status', 'ダウンロード中...', '');
  try {
    const res = await fetch('/api/bgm/youtube', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    const data = await res.json();
    if (data.ok) {
      setStatus('yt-status', '完了: ' + (data.title || data.file), 'ok');
      document.getElementById('yt-url').value = '';
      loadBgmTracks();
    } else {
      setStatus('yt-status', 'エラー: ' + data.error, 'err');
    }
  } catch (e) {
    setStatus('yt-status', 'エラー: ' + e.message, 'err');
  }
}
