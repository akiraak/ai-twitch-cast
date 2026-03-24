// 共通ユーティリティ（タブ切替・トースト・モーダル・API）
let _volTimer = null;
const TAB_NAMES = ['character', 'convmode', 'layout', 'sound', 'chat', 'todo', 'debug', 'db'];

function switchCharSubtab(name, el) {
  document.querySelectorAll('.char-subtab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.char-subcontent').forEach(t => t.classList.remove('active'));
  document.getElementById('char-sub-' + name).classList.add('active');
  if (el) el.classList.add('active');
}

function switchTab(name, el) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  if (!el) {
    const idx = TAB_NAMES.indexOf(name);
    el = document.querySelectorAll('.tab')[idx];
  }
  el.classList.add('active');
  if (name === 'chat') {
    const pg = Math.floor(_chatOffset / _chatLimit) + 1;
    location.hash = pg > 1 ? `chat:${pg}` : 'chat';
    loadChatHistory();
  } else {
    location.hash = name;
  }
  if (name === 'db') loadDbTables();
  if (name === 'character') { loadLanguageModes(); loadCharacterLayers(); loadSpeechSettings(); }
  if (name === 'sound') loadBgmTracks();
  if (name === 'todo') loadTodoList();
  if (name === 'debug') { loadScreenshots(); }
  if (name === 'layout') loadCustomTexts();
  if (name === 'convmode') { loadLessons(); } else { if (typeof stopLessonStatusPolling === 'function') stopLessonStatusPolling(); }
}


function log(msg) {
  console.log(msg);
}

function showToast(msg, type = 'success', duration = 5000) {
  const el = document.createElement('div');
  el.className = 'toast ' + type;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), duration);
}

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

/**
 * 汎用モーダルダイアログ
 * @param {string} message - メッセージ
 * @param {object} opts
 * @param {string} opts.title - タイトル
 * @param {string} opts.okLabel - OKボタンラベル
 * @param {string} opts.cancelLabel - キャンセルボタンラベル
 * @param {boolean} opts.danger - 赤いOKボタン
 * @param {string|null} opts.input - テキスト入力のプレースホルダー（nullなら入力なし）
 * @param {string} opts.inputValue - テキスト入力の初期値
 * @returns {Promise} 確認ダイアログ: true/false、入力ダイアログ: 文字列/null
 */
function showModal(message, { title = '確認', okLabel = 'OK', cancelLabel = 'キャンセル', danger = false, input = null, inputValue = '' } = {}) {
  return new Promise(resolve => {
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    const btnClass = danger ? 'danger' : 'primary';
    const inputHtml = input !== null
      ? `<input type="text" class="modal-input" placeholder="${esc(input)}" value="${esc(inputValue)}">`
      : '';
    overlay.innerHTML = `<div class="modal-box">
      <h3>${esc(title)}</h3>
      <p>${esc(message)}</p>
      ${inputHtml}
      <div class="btn-group">
        <button class="${btnClass}" data-action="ok">${esc(okLabel)}</button>
        <button class="secondary" data-action="cancel">${esc(cancelLabel)}</button>
      </div>
    </div>`;
    const inputEl = overlay.querySelector('.modal-input');
    const doResolve = (action) => {
      overlay.remove();
      if (action === 'ok') {
        resolve(input !== null ? (inputEl ? inputEl.value : '') : true);
      } else {
        resolve(input !== null ? null : false);
      }
    };
    overlay.addEventListener('click', e => {
      const action = e.target.dataset?.action;
      if (action) doResolve(action);
    });
    if (inputEl) {
      inputEl.addEventListener('keydown', e => {
        if (e.key === 'Enter') doResolve('ok');
        if (e.key === 'Escape') doResolve('cancel');
      });
    }
    document.body.appendChild(overlay);
    if (inputEl) { inputEl.focus(); inputEl.select(); }
  });
}

function showConfirm(message, opts = {}) {
  return showModal(message, opts);
}

function setStatus(id, msg, type) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = msg;
  el.style.color = type === 'err' ? '#c62828' : type === 'ok' ? '#2e7d32' : '#6a5590';
}

// api() は /static/js/lib/api-client.js から読み込み済み
// index.html 用ラッパー: log + showToast 付き
const _apiBase = api;
api = (method, url, body) => _apiBase(method, url, body, {
  onError: msg => showToast(msg, 'error'),
  onLog: msg => log(msg),
});
