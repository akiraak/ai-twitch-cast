// トピック管理
let _topicPollTimer = null;

async function loadTopicStatus() {
  try {
    const r = await fetch('/api/topic');
    const d = await r.json();
    const el = document.getElementById('topic-current');
    if (d.active) {
      const desc = d.topic.description ? `<br><small style="color:#6a5590;">${esc(d.topic.description)}</small>` : '';
      el.innerHTML =
        `<div style="padding:8px 12px; background:#ede7f6; border-radius:6px; border-left:3px solid #7b1fa2;">` +
        `<strong>${esc(d.topic.title)}</strong>${desc}<br>` +
        `<small style="color:#9a88b5;">` +
        `待機: ${d.remaining_scripts}件 / 発話済み: ${d.spoken_count}件` +
        `${d.generating ? ' / 生成中...' : ''}` +
        ` / モデル: ${esc(d.model || '?')}</small></div>`;
      document.getElementById('topic-idle').value = d.idle_threshold;
      document.getElementById('topic-interval').value = d.min_interval;
    } else {
      el.innerHTML = '<span style="color:#9a88b5;">トピック未設定</span>';
    }
    const pauseBtn = document.getElementById('topic-pause-btn');
    if (d.paused) {
      pauseBtn.textContent = '再開';
      pauseBtn.style.background = '#2e7d32';
    } else {
      pauseBtn.textContent = '停止';
      pauseBtn.style.background = '#e65100';
    }
    if (d.active && d.paused) {
      el.querySelector('div').style.borderLeftColor = '#e65100';
    }
    if (d.generating && !_topicPollTimer) {
      _topicPollTimer = setInterval(() => { loadTopicStatus(); loadTopicScripts(); }, 3000);
    } else if (!d.generating && _topicPollTimer) {
      clearInterval(_topicPollTimer);
      _topicPollTimer = null;
      loadTopicScripts();
    }
  } catch(e) {}
}

async function setTopic() {
  const title = document.getElementById('topic-title').value.trim();
  if (!title) return;
  const desc = document.getElementById('topic-desc').value.trim();
  const st = document.getElementById('topic-status');
  st.textContent = '設定中...';
  try {
    const r = await fetch('/api/topic', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({title, description: desc}),
    });
    const d = await r.json();
    st.textContent = d.ok ? 'トピック設定完了' : d.error;
    document.getElementById('topic-title').value = '';
    document.getElementById('topic-desc').value = '';
    loadTopicStatus();
    if (!_topicPollTimer) {
      _topicPollTimer = setInterval(() => { loadTopicStatus(); loadTopicScripts(); }, 3000);
    }
  } catch(e) { st.textContent = 'エラー: ' + e; }
}

async function clearTopic() {
  await fetch('/api/topic', {method: 'DELETE'});
  document.getElementById('topic-status').textContent = 'トピック解除';
  loadTopicStatus();
  loadTopicScripts();
}

async function topicSpeakNow() {
  const st = document.getElementById('topic-status');
  st.textContent = '発話中...';
  try {
    const r = await fetch('/api/topic/speak', {method: 'POST'});
    const d = await r.json();
    if (d.ok) {
      const msg = d.count > 1 ? `発話完了（${d.count}セグメント）` : '発話完了';
      st.textContent = msg;
    } else {
      st.textContent = d.error;
    }
    loadTopicStatus();
    loadTopicScripts();
  } catch(e) { st.textContent = 'エラー: ' + e; }
}

async function updateTopicSettings() {
  const idle = document.getElementById('topic-idle').value;
  const interval = document.getElementById('topic-interval').value;
  await fetch('/api/topic/settings', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({idle_threshold: Number(idle), min_interval: Number(interval)}),
  });
  loadTopicStatus();
}

async function toggleTopicPause() {
  const btn = document.getElementById('topic-pause-btn');
  const isPaused = btn.textContent === '再開';
  const endpoint = isPaused ? '/api/topic/resume' : '/api/topic/pause';
  await fetch(endpoint, {method: 'POST'});
  loadTopicStatus();
}

const _emotionColors = {joy:'#4caf50', surprise:'#ff9800', thinking:'#2196f3', neutral:'#9a88b5'};
async function loadTopicScripts() {
  try {
    const r = await fetch('/api/topic/scripts');
    const d = await r.json();
    const el = document.getElementById('topic-scripts');
    const genEl = document.getElementById('topic-generating');
    const badge = document.getElementById('topic-script-badge');
    genEl.style.display = d.generating ? 'block' : 'none';
    if (!d.scripts.length) {
      el.innerHTML = '<span style="color:#9a88b5;">スクリプトなし</span>';
      badge.textContent = '';
      return;
    }
    const spoken = d.scripts.filter(s => s.spoken_at).length;
    badge.textContent = `(${spoken}/${d.scripts.length})`;
    el.innerHTML = d.scripts.map((s, i) => {
      const done = !!s.spoken_at;
      const eColor = _emotionColors[s.emotion] || '#9a88b5';
      return `<div style="padding:8px 10px; margin-bottom:6px; border-radius:6px; background:${done ? '#f5f0ff' : '#fff'}; border:1px solid ${done ? '#e0d8f0' : '#d0c0e8'}; ${done ? 'opacity:0.55;' : ''}">` +
        `<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">` +
        `<span style="font-size:0.75rem; color:${eColor}; font-weight:600;">#${i+1} ${esc(s.emotion)}</span>` +
        `${done ? '<span style="font-size:0.7rem; color:#4caf50;">発話済</span>' : '<span style="font-size:0.7rem; color:#7b1fa2;">待機中</span>'}` +
        `</div>` +
        `<div style="font-size:0.9rem; line-height:1.5;">${esc(s.content)}</div>` +
        `</div>`;
    }).join('');
  } catch(e) {}
}
