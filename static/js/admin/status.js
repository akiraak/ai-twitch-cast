// 音量制御・ステータス更新

function onVolume(source, slider) {
  const pct = slider.value;
  document.getElementById(`vol-${source}-pct`).textContent = pct + '%';
  clearTimeout(_volTimer);
  _volTimer = setTimeout(() => {
    api('POST', '/api/broadcast/volume', { source, volume: pct / 100 });
  }, 150);
}

function onSyncDelay(slider) {
  document.getElementById('sync-delay-pct').textContent = slider.value + 'ms';
  clearTimeout(_syncDelayTimer);
  _syncDelayTimer = setTimeout(() => {
    api('POST', '/api/overlay/settings', { sync: { lipsyncDelay: parseInt(slider.value) } });
  }, 150);
}
let _syncDelayTimer;

async function loadVolumes() {
  try {
    const data = await (await fetch('/api/broadcast/volume')).json();
    for (const key of ['master', 'tts', 'bgm']) {
      const slider = document.getElementById(`vol-${key}`);
      if (document.activeElement === slider) continue;
      const val = data[key] ?? 1.0;
      const pct = Math.round(val * 100);
      slider.value = pct;
      document.getElementById(`vol-${key}-pct`).textContent = pct + '%';
    }
  } catch (e) {}
  // syncDelay読み込み
  try {
    const s = await (await fetch('/api/overlay/settings')).json();
    const delay = s?.sync?.lipsyncDelay ?? 500;
    document.getElementById('sync-delay').value = delay;
    document.getElementById('sync-delay-pct').textContent = delay + 'ms';
  } catch (e) {}
}

async function refreshStatus() {
  try {
    const data = await (await fetch('/api/broadcast/status')).json();

    const streaming = data.streaming;
    document.getElementById('sb-stream').className = 'status-dot ' + (streaming ? 'live' : 'off');
    document.getElementById('sb-stream-text').textContent = streaming ? '配信中' : '停止中';
    document.getElementById('status-bar').classList.toggle('streaming', streaming);
  } catch (e) {}
  // バージョン表示（初回のみ）
  const verEl = document.getElementById('app-version');
  if (verEl && !verEl.textContent) {
    try {
      const st = await (await fetch('/api/status')).json();
      let text = st.version ? `v${st.version}` : '';
      if (st.updated_at) {
        const d = new Date(st.updated_at);
        text += ` (${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')})`;
      }
      verEl.textContent = text;
    } catch (e) {}
  }
  loadVolumes();
}
