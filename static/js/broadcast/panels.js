// 字幕・TODO パネル表示

// === 言語タグ除去（最終防御: [lang:xx] + SSML <lang> 両方） ===
function stripLangTags(text) {
  if (!text) return '';
  return text.replace(/\[\/?(lang(?::\w+)?)\]/g, '').replace(/<lang\b[^>]*>/gi, '').replace(/<\/lang>/gi, '');
}

// === 字幕 ===
function showSubtitle(data) {
  clearTimeout(fadeTimer);
  subtitleEl.classList.remove('fading');
  subtitleEl.querySelector('.author').textContent = '';
  subtitleEl.querySelector('.trigger-text').textContent = stripLangTags(data.trigger_text);
  subtitleEl.querySelector('.speech').textContent = stripLangTags(data.speech);
  subtitleEl.querySelector('.translation').textContent = stripLangTags(data.translation || '');
  subtitleEl.classList.add('visible');
}

function fadeSubtitle() {
  const duration = parseFloat(subtitleEl.dataset.fadeDuration || 3) * 1000;
  fadeTimer = setTimeout(() => {
    subtitleEl.classList.add('fading');
    subtitleEl.classList.remove('visible');
  }, duration);
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

function showLessonText(text) {
  const panel = document.getElementById('lesson-text-panel');
  const content = document.getElementById('lesson-text-content');
  if (!panel || !content) return;
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
  // フェードアウト完了後に非表示
  setTimeout(() => {
    if (!panel.classList.contains('visible')) {
      panel.style.display = 'none';
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

function showLessonProgress(sections, currentIndex) {
  const panel = document.getElementById('lesson-progress-panel');
  const list = document.getElementById('lesson-progress-list');
  if (!panel || !list) return;
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
    if (!panel.classList.contains('visible')) panel.style.display = 'none';
  }, 600);
}

function _escHtml(s) {
  return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// --- 授業モード（パネル表示切替） ---

let _lessonMode = false;

function setLessonMode(active) {
  if (_lessonMode === active) return;
  _lessonMode = active;
  const todo = document.getElementById('todo-panel');
  const customTexts = document.getElementById('custom-text-container');
  if (active) {
    // 授業に関係ないパネルを非表示（字幕は通常通り表示）
    if (todo) todo.style.display = 'none';
    if (customTexts) customTexts.style.display = 'none';
  } else {
    // パネル復帰 + 授業テキスト・進捗非表示
    if (todo) todo.style.display = '';
    if (customTexts) customTexts.style.display = '';
    hideLessonText();
    hideLessonProgress();
  }
}
