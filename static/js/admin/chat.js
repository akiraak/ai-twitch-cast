// チャットログ
let _chatOffset = 0;
const _chatLimit = 50;

const _chatHeaderHtml = '<div class="chat-header"><span class="chat-c-time">日時</span><span class="chat-c-name">発言者</span><span class="chat-c-msg">内容</span></div>';

function _chatFormatTime(iso) {
  if (!iso) {
    const now = new Date();
    return `${String(now.getMonth()+1).padStart(2,'0')}/${String(now.getDate()).padStart(2,'0')} ${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`;
  }
  const d = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z');
  return `${String(d.getMonth()+1).padStart(2,'0')}/${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
}

function chatRowHtml(c) {
  const time = _chatFormatTime(c.created_at);
  if (c.type === 'avatar_comment') {
    const speech = esc(c.speech || '');
    return `<div class="chat-row chat-avatar"><span class="chat-c-time">${time}</span><span class="chat-c-name">ちょビ</span><span class="chat-c-resp" title="${escHtml(c.speech || '')}">${speech}</span></div>`;
  }
  const name = esc(c.author || '');
  const msg = esc(c.trigger_text || '');
  return `<div class="chat-row"><span class="chat-c-time">${time}</span><span class="chat-c-name">${name}</span><span class="chat-c-msg" title="${escHtml(c.trigger_text || '')}">${msg}</span></div>`;
}

function prependChatMessage(data) {
  const el = document.getElementById('chat-messages');
  if (!el || _chatOffset > 0) return;
  const avatarRow = chatRowHtml({type: 'avatar_comment', speech: data.speech, created_at: data.created_at});
  const commentRow = chatRowHtml({type: 'comment', author: data.author, trigger_text: data.trigger_text, created_at: data.created_at});
  const html = avatarRow + commentRow;
  const header = el.querySelector('.chat-header');
  if (header) {
    header.insertAdjacentHTML('afterend', html);
  } else {
    el.insertAdjacentHTML('afterbegin', html);
  }
}

async function loadChatHistory() {
  try {
    const res = await fetch(`/api/chat/history?limit=${_chatLimit}&offset=${_chatOffset}`);
    const d = await res.json();
    const el = document.getElementById('chat-messages');
    const countEl = document.getElementById('chat-count');
    countEl.textContent = d.total ? `(${d.total}件)` : '';
    el.innerHTML = _chatHeaderHtml + d.comments.map(chatRowHtml).join('');
    const page = Math.floor(_chatOffset / _chatLimit) + 1;
    const totalPages = Math.ceil((d.total || 0) / _chatLimit);
    const pagerHtml = totalPages > 1
      ? `<button onclick="chatPage(-1)" ${_chatOffset === 0 ? 'disabled' : ''} style="font-size:0.75rem;">新しい</button>` +
        `<span style="font-size:0.8rem; color:#6a5590;">${page} / ${totalPages}</span>` +
        `<button onclick="chatPage(1)" ${page >= totalPages ? 'disabled' : ''} style="font-size:0.75rem;">古い</button>`
      : '';
    document.getElementById('chat-pager-top').innerHTML = pagerHtml;
    document.getElementById('chat-pager').innerHTML = pagerHtml;
  } catch (e) {}
}

function chatPage(dir) {
  _chatOffset = Math.max(0, _chatOffset + dir * _chatLimit);
  const pg = Math.floor(_chatOffset / _chatLimit) + 1;
  location.hash = pg > 1 ? `chat:${pg}` : 'chat';
  loadChatHistory();
}
