// 会話デモ — 起動時に既存データを復元
async function convDemoLoadStatus() {
  try {
    const res = await api('GET', '/api/debug/conversation-demo/status');
    if (!res?.has_data) return;
    const log = document.getElementById('conv-demo-log');
    const st = document.getElementById('conv-demo-status');
    const btnPlay = document.getElementById('btn-conv-play');
    const topicInput = document.getElementById('conv-demo-topic');
    if (topicInput && res.topic) topicInput.value = res.topic;
    log.innerHTML = '';
    let teacherName = '';
    for (let i = 0; i < res.dialogues.length; i++) {
      const d = res.dialogues[i];
      if (i === 0) teacherName = d.speaker;
      log.dataset.teacherName = teacherName;
      const color = d.speaker === teacherName ? '#7b1fa2' : '#c2185b';
      const wavLink = d.wav_url ? ` <a href="${d.wav_url}" target="_blank" style="color:#5c6bc0; font-size:0.7rem;">&#9654; wav</a>` : ' <span style="color:#c62828; font-size:0.7rem;">wav無し</span>';
      log.innerHTML += `<div style="font-size:0.8rem; margin:2px 0;"><span style="color:${color}; font-weight:600;">${esc(d.speaker)}</span> <span style="color:#888;">[${d.emotion}]</span> ${esc(d.content)}${wavLink}</div>`;
    }
    st.textContent = `生成済み（${res.dialogues_count}発話）— 再生ボタンで再生`;
    st.style.color = '#2e7d32';
    btnPlay.disabled = false;
  } catch {}
}

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

// 会話デモ — 生成
async function convDemoGenerate() {
  const topic = document.getElementById('conv-demo-topic').value.trim();
  if (!topic) return;
  const btnGen = document.getElementById('btn-conv-generate');
  const btnPlay = document.getElementById('btn-conv-play');
  const st = document.getElementById('conv-demo-status');
  const log = document.getElementById('conv-demo-log');
  btnGen.disabled = true;
  btnPlay.disabled = true;
  st.textContent = '会話生成中...';
  st.style.color = '#9a88b5';
  log.innerHTML = '';

  try {
    const resp = await fetch('/api/debug/conversation-demo/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ topic }),
    });
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        let data;
        try { data = JSON.parse(line.slice(6)); } catch { continue; }

        if (data.phase === 'generate') {
          st.textContent = data.message;
        } else if (data.phase === 'script') {
          const color = data.speaker === (log.dataset.teacherName || '') ? '#7b1fa2' : '#c2185b';
          if (data.index === 0) log.dataset.teacherName = data.speaker;
          log.innerHTML += `<div style="font-size:0.8rem; margin:2px 0;"><span style="color:${color}; font-weight:600;">${esc(data.speaker)}</span> <span style="color:#888;">[${data.emotion}]</span> ${esc(data.content)}</div>`;
        } else if (data.phase === 'tts') {
          st.textContent = data.message;
        } else if (data.ok === true) {
          st.textContent = `生成完了（${data.dialogues_count}発話）— 再生ボタンで再生`;
          st.style.color = '#2e7d32';
          btnPlay.disabled = false;
          convDemoLoadStatus();
        } else if (data.ok === false) {
          st.textContent = data.error || '失敗';
          st.style.color = '#c62828';
        }
      }
    }
  } catch (e) {
    st.textContent = 'エラー: ' + e.message;
    st.style.color = '#c62828';
  } finally {
    btnGen.disabled = false;
  }
}

// 会話デモ — 再生
async function convDemoPlay() {
  const btnPlay = document.getElementById('btn-conv-play');
  const st = document.getElementById('conv-demo-status');
  btnPlay.disabled = true;
  st.textContent = '再生中...';
  st.style.color = '#2e7d32';
  try {
    const res = await api('POST', '/api/debug/conversation-demo/play');
    if (res?.ok) {
      st.textContent = `再生開始（${res.dialogues_count}発話）`;
    } else {
      st.textContent = res?.error || '再生失敗';
      st.style.color = '#c62828';
    }
  } catch (e) {
    st.textContent = 'エラー: ' + e.message;
    st.style.color = '#c62828';
  } finally {
    btnPlay.disabled = false;
  }
}

// Claude Watcher ステータス
async function cwRefreshStatus() {
  try {
    const res = await api('GET', '/api/claude-watcher/status');
    const dot = document.getElementById('cw-status-dot');
    const text = document.getElementById('cw-status-text');
    const session = document.getElementById('cw-session');
    const conv = document.getElementById('cw-last-conv');
    const interval = document.getElementById('cw-interval');

    if (res.active) {
      dot.style.background = '#4caf50';
      const min = Math.floor((res.elapsed_seconds || 0) / 60);
      text.textContent = `監視中（${min}分経過）`;
      text.style.color = '#2e7d32';
    } else if (res.running) {
      dot.style.background = '#ff9800';
      text.textContent = '待機中（セッションなし）';
      text.style.color = '#e65100';
    } else {
      dot.style.background = '#ccc';
      text.textContent = '停止中';
      text.style.color = '#9a88b5';
    }

    if (interval && res.interval !== undefined) {
      interval.value = res.interval;
    }

    if (res.transcript_path) {
      const fname = res.transcript_path.split('/').pop();
      session.textContent = `transcript: ${fname}`;
    } else {
      session.textContent = '';
    }

    if (res.last_conversation && res.last_conversation.length > 0) {
      conv.innerHTML = res.last_conversation.map(t =>
        `<div style="margin:1px 0;">${esc(t)}</div>`
      ).join('');
    } else {
      conv.innerHTML = '<span style="color:#9a88b5;">直近の会話なし</span>';
    }
  } catch (e) {
    document.getElementById('cw-status-text').textContent = 'エラー';
    document.getElementById('cw-status-text').style.color = '#c62828';
  }
}

async function cwApplyConfig() {
  const interval = parseInt(document.getElementById('cw-interval').value) || 480;
  try {
    await api('POST', '/api/claude-watcher/config', { interval_seconds: interval });
    cwRefreshStatus();
  } catch (e) {}
}

// 定期更新（30秒ごと）
setInterval(cwRefreshStatus, 30000);

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
