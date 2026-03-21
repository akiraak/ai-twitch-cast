// 字幕・TODO パネル表示

// === 字幕 ===
function showSubtitle(data) {
  clearTimeout(fadeTimer);
  subtitleEl.classList.remove('fading');
  subtitleEl.querySelector('.author').textContent = '';
  subtitleEl.querySelector('.trigger-text').textContent = data.trigger_text;
  subtitleEl.querySelector('.speech').textContent = data.speech;
  subtitleEl.querySelector('.translation').textContent = data.translation || '';
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
