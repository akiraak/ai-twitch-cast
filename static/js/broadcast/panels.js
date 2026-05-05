// 字幕・TODO パネル表示

// === 言語タグ除去（最終防御: [lang:xx] + SSML <lang> 両方） ===
function stripLangTags(text) {
  if (!text) return '';
  return text.replace(/\[\/?(lang(?::\w+)?)\]/g, '').replace(/<lang\b[^>]*>/gi, '').replace(/<\/lang>/gi, '');
}

// === 字幕 ===
function _getSubtitleEl(avatarId) {
  return avatarId === 'student' ? subtitle2El : subtitleEl;
}

// z-indexカウンタ: 最後に表示された字幕を上に
let _subtitleZCounter = 20;

// チャンクタイマー管理（アバターIDごと）
const _chunkTimers = { teacher: [], student: [] };
const SUBTITLE_CHUNK_MAX_LEN = 80;

function clearChunkTimers(avatarId) {
  const key = avatarId === 'student' ? 'student' : 'teacher';
  _chunkTimers[key].forEach(t => clearTimeout(t));
  _chunkTimers[key] = [];
}

function splitSubtitleChunks(text, maxLen) {
  if (text.length <= maxLen) return [text];
  const chunks = [];
  let remaining = text;
  while (remaining.length > maxLen) {
    let cut = -1;
    // 優先1: 句読点
    for (let i = maxLen - 1; i >= maxLen * 0.4; i--) {
      if ('。！？.!?'.includes(remaining[i])) { cut = i + 1; break; }
    }
    // 優先2: 読点・カンマ
    if (cut < 0) {
      for (let i = maxLen - 1; i >= maxLen * 0.4; i--) {
        if ('、,，'.includes(remaining[i])) { cut = i + 1; break; }
      }
    }
    // 優先3: スペース
    if (cut < 0) {
      for (let i = maxLen - 1; i >= maxLen * 0.4; i--) {
        if (remaining[i] === ' ') { cut = i + 1; break; }
      }
    }
    // 強制分割
    if (cut < 0) cut = maxLen;
    chunks.push(remaining.slice(0, cut).trim());
    remaining = remaining.slice(cut).trim();
  }
  if (remaining) chunks.push(remaining);
  return chunks;
}

function showSubtitle(data) {
  const el = _getSubtitleEl(data.avatar_id);
  const isStudent = data.avatar_id === 'student';
  const timer = isStudent ? fadeTimerStudent : fadeTimerTeacher;
  clearTimeout(timer);
  clearChunkTimers(data.avatar_id);

  // もう一方の字幕を速めにフェードアウト（重なり軽減）
  const otherEl = isStudent ? subtitleEl : subtitle2El;
  if (otherEl.classList.contains('visible')) {
    const otherTimerKey = isStudent ? 'fadeTimerTeacher' : 'fadeTimerStudent';
    clearTimeout(isStudent ? fadeTimerTeacher : fadeTimerStudent);
    otherEl.classList.add('fading-fast');
    otherEl.classList.remove('visible');
    const tid = setTimeout(() => { otherEl.classList.remove('fading-fast'); }, 600);
    if (isStudent) fadeTimerTeacher = tid; else fadeTimerStudent = tid;
  }

  // 新しい字幕を上に表示
  _subtitleZCounter++;
  el.style.zIndex = _subtitleZCounter;
  el.classList.remove('fading');
  el.classList.remove('fading-fast');
  el.querySelector('.author').textContent = '';
  el.querySelector('.trigger-text').textContent = stripLangTags(data.trigger_text);
  el.querySelector('.translation').textContent = stripLangTags(data.translation || '');
  el.classList.add('visible');

  // チャンク分割表示
  const speechText = stripLangTags(data.speech);
  const speechEl = el.querySelector('.speech');
  const chunks = splitSubtitleChunks(speechText, SUBTITLE_CHUNK_MAX_LEN);

  if (chunks.length <= 1) {
    // 短文: 従来通り一括表示
    speechEl.textContent = speechText;
    return;
  }

  // 長文: タイマーで順次切り替え
  const totalMs = (data.duration || 5) * 1000;
  const intervalMs = totalMs / chunks.length;
  const timerKey = isStudent ? 'student' : 'teacher';

  speechEl.textContent = chunks[0];
  for (let i = 1; i < chunks.length; i++) {
    const tid = setTimeout(() => {
      speechEl.textContent = chunks[i];
    }, intervalMs * i);
    _chunkTimers[timerKey].push(tid);
  }
}

function fadeSubtitle(avatarId, opts = {}) {
  // avatarId未指定時は両方フェード
  if (!avatarId) {
    fadeSubtitle('teacher', opts);
    fadeSubtitle('student', opts);
    return;
  }
  clearChunkTimers(avatarId);
  const el = _getSubtitleEl(avatarId);
  // opts.delaySeconds が指定されていれば dataset.fadeDuration より優先（授業モード用）
  const delaySec = (opts.delaySeconds != null)
    ? opts.delaySeconds
    : parseFloat(el.dataset.fadeDuration || 3);
  const duration = delaySec * 1000;
  const apply = () => {
    el.classList.add('fading');
    el.classList.remove('visible');
  };
  let timerId = null;
  if (duration <= 0) {
    apply();
  } else {
    timerId = setTimeout(apply, duration);
  }
  if (avatarId === 'student') {
    fadeTimerStudent = timerId;
  } else {
    fadeTimerTeacher = timerId;
  }
}

// テキスト変数展開は lib/text-variables.js の replaceTextVariables() を使用

// === TODO読み込み ===
function renderTodoItems(items) {
  todoListEl.innerHTML = '';
  const fs = todoSettings.fontSize;
  let lastSection = null;
  for (const item of items) {
    const text_val = typeof item === 'string' ? item : item.text;
    const status = typeof item === 'string' ? 'todo' : item.status;
    const section = item.section || '';
    if (section && section !== lastSection) {
      const sectionEl = document.createElement('div');
      sectionEl.className = 'todo-section';
      sectionEl.textContent = section;
      todoListEl.appendChild(sectionEl);
      lastSection = section;
    }
    const div = document.createElement('div');
    div.className = 'todo-item' + (status === 'in_progress' ? ' in-progress' : '');
    if (status === 'in_progress') {
      const arrow = document.createElement('span');
      arrow.className = 'todo-arrow';
      arrow.textContent = '\u25B6';
      div.appendChild(arrow);
    }
    const cb = document.createElement('span');
    cb.className = 'todo-checkbox';
    const text = document.createElement('span');
    text.textContent = text_val;
    if (fs) text.style.fontSize = fs + 'vw';
    div.appendChild(cb);
    div.appendChild(text);
    todoListEl.appendChild(div);
  }
}

async function loadTodo() {
  try {
    const res = await fetch('/api/todo');
    const data = await res.json();
    renderTodoItems(data.items);
  } catch (e) {
    console.log('TODO読み込みエラー:', e.message);
  }
}

// --- 授業テキストパネル ---

// テキスト長から推定するフォールバック値（display_properties が欠けたとき用）
function _autoSizeFromText(text) {
  const s = text || '';
  const len = s.length;
  const lines = s.split('\n').length;
  if (len < 60 && lines <= 2)  return { maxHeight: 25, width: 40, fontSize: 2.0 };
  if (len < 200 && lines <= 5) return { maxHeight: 40, width: 50, fontSize: 1.7 };
  return { maxHeight: 60, width: 60, fontSize: 1.5 };
}

function showLessonText(text, displayProperties) {
  const panel = document.getElementById('lesson-text-panel');
  const content = document.getElementById('lesson-text-content');
  if (!panel || !content) return;

  // 明示指定があれば優先、欠けたフィールドはテキスト長から自動推定で補う
  const auto = _autoSizeFromText(text);
  const dp = displayProperties || {};
  const maxHeight = (dp.maxHeight != null) ? Number(dp.maxHeight) : auto.maxHeight;
  const width     = (dp.width     != null) ? Number(dp.width)     : auto.width;
  const fontSize  = (dp.fontSize  != null) ? Number(dp.fontSize)  : auto.fontSize;

  const w = Math.max(10, Math.min(95, width));
  panel.style.maxHeight   = Math.max(10, Math.min(90, maxHeight)) + '%';
  panel.style.width       = w + '%';
  // width が動的に変わるので left も連動させて常に水平中央寄せにする
  panel.style.left        = ((100 - w) / 2) + '%';
  // フォントサイズの下限は 1.4vw（旧プロンプトで生成された 1.0-1.3 等の小さすぎる値を救済）
  content.style.fontSize  = Math.max(1.4, Math.min(3.0, fontSize)) + 'vw';

  content.textContent = stripLangTags(text);
  panel.style.display = 'block';
  // デザイン設定はinit時・WebSocket経由で既に適用済み（再適用不要）
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      panel.classList.add('visible');
    });
  });
}

function hideLessonText() {
  const panel = document.getElementById('lesson-text-panel');
  if (!panel) return;
  panel.classList.remove('visible');
  // フェードアウト完了後に非表示 + セクション別オーバーライドをリセット
  setTimeout(() => {
    if (!panel.classList.contains('visible')) {
      panel.style.display = 'none';
      panel.style.maxHeight = '';
      panel.style.width = '';
      panel.style.left = '';
      const content = document.getElementById('lesson-text-content');
      if (content) content.style.fontSize = '';
    }
  }, 600);
}

// --- 授業進捗パネル ---

const PROGRESS_ICONS = {
  introduction: '\u{1F3AC}',
  explanation: '\u{1F4D6}',
  example: '\u{1F4DD}',
  question: '\u{2753}',
  summary: '\u{1F3C1}',
};

function _updateProgressTitle(currentIndex, total) {
  const titleEl = document.getElementById('lesson-progress-title');
  if (!titleEl) return;
  titleEl.innerHTML = `<span class="lp-title-text">授業の流れ</span><span class="lp-title-count">${currentIndex + 1}/${total}</span>`;
  // datasetから保存済みスタイルを復元（innerHTMLで再生成されるため）
  const panel = document.getElementById('lesson-progress-panel');
  if (!panel) return;
  const d = panel.dataset;
  const textEl = titleEl.querySelector('.lp-title-text');
  const countEl = titleEl.querySelector('.lp-title-count');
  if (textEl) {
    if (d.titleColor) textEl.style.color = d.titleColor;
    if (typeof _applyStroke === 'function') _applyStroke(textEl, d.titleStrokeSize, d.titleStrokeColor, d.titleStrokeOpacity);
  }
  if (countEl) {
    if (d.countFontSize) countEl.style.fontSize = d.countFontSize + 'vw';
    if (d.countColor) countEl.style.color = d.countColor;
    if (typeof _applyStroke === 'function') _applyStroke(countEl, d.countStrokeSize, d.countStrokeColor, d.countStrokeOpacity);
  }
}

function showLessonProgress(sections, currentIndex) {
  const panel = document.getElementById('lesson-progress-panel');
  const list = document.getElementById('lesson-progress-list');
  if (!panel || !list) return;
  _updateProgressTitle(currentIndex, sections.length);
  const itemFs = panel.dataset.itemFontSize;
  list.innerHTML = '';
  for (let i = 0; i < sections.length; i++) {
    const s = sections[i];
    const icon = PROGRESS_ICONS[s.type] || '\u{1F4D6}';
    const cls = i < currentIndex ? 'done' : i === currentIndex ? 'current' : '';
    const div = document.createElement('div');
    div.className = 'lesson-progress-item ' + cls;
    div.innerHTML = `<span class="lp-icon">${icon}</span> ${_escHtml(s.summary)}`;
    if (itemFs) div.style.fontSize = itemFs + 'vw';
    list.appendChild(div);
  }
  panel.style.display = 'block';
  requestAnimationFrame(() => {
    requestAnimationFrame(() => { panel.classList.add('visible'); });
  });
}

function updateLessonProgress(currentIndex) {
  const items = document.querySelectorAll('.lesson-progress-item');
  _updateProgressTitle(currentIndex, items.length);
  items.forEach((el, i) => {
    el.classList.remove('done', 'current');
    if (i < currentIndex) el.classList.add('done');
    else if (i === currentIndex) el.classList.add('current');
  });
  // 現在のセクションが見えるようにスクロール
  const current = document.querySelector('.lesson-progress-item.current');
  if (current) current.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}

function hideLessonProgress() {
  const panel = document.getElementById('lesson-progress-panel');
  if (!panel) return;
  panel.classList.remove('visible');
  setTimeout(() => {
    if (!panel.classList.contains('visible')) {
      panel.style.display = 'none';
      const titleEl = document.getElementById('lesson-progress-title');
      if (titleEl) titleEl.textContent = '授業の流れ';
    }
  }, 600);
}

function _escHtml(s) {
  return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// --- 授業タイトルパネル ---

function showLessonTitle(name) {
  const panel = document.getElementById('lesson-title-panel');
  const text = document.getElementById('lesson-title-text');
  if (!panel || !text) return;
  text.textContent = name;
  panel.style.display = 'block';
  requestAnimationFrame(() => {
    requestAnimationFrame(() => { panel.classList.add('visible'); });
  });
}

function hideLessonTitle() {
  const panel = document.getElementById('lesson-title-panel');
  if (!panel) return;
  panel.classList.remove('visible');
  setTimeout(() => {
    if (!panel.classList.contains('visible')) panel.style.display = 'none';
  }, 600);
}

// --- 授業モード（パネル表示切替） ---

let _lessonMode = false;

function setLessonMode(active) {
  if (_lessonMode === active) return;
  _lessonMode = active;
  // TODO パネルの表示/非表示はユーザの永続設定（DB visible）に委ねるため、ここでは触らない
  const customTexts = document.getElementById('custom-text-container');
  if (active) {
    if (customTexts) customTexts.style.display = 'none';
  } else {
    if (customTexts) customTexts.style.display = '';
    hideLessonText();
    hideLessonProgress();
    hideLessonTitle();
  }
}
