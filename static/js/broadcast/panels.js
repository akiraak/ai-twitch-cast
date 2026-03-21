// 字幕・トピック・TODO パネル表示

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

// === トピックパネル ===
// トピック画像の状態管理
let _topicImageUrls = [];
let _topicImageIndex = 0;

function updateTopicPanel(data) {
  const titleEl = document.getElementById('topic-title-text');
  const descEl = document.getElementById('topic-desc-text');
  const statsEl = document.getElementById('topic-stats');
  const dotEl = document.getElementById('topic-dot');
  const imagesEl = document.getElementById('topic-images');
  const isIdle = !data || !data.active || data.paused;

  if (isIdle) {
    topicPanelEl.classList.add('idle');
    titleEl.textContent = '----';
    descEl.textContent = '';
    descEl.style.display = 'none';
    imagesEl.style.display = 'none';
    _topicImageUrls = [];
    _topicImageIndex = 0;
    statsEl.textContent = '';
    dotEl.classList.add('paused');
    return;
  }
  topicPanelEl.classList.remove('idle');
  titleEl.textContent = data.topic.title;
  descEl.textContent = data.topic.description || '';
  descEl.style.display = data.topic.description ? '' : 'none';

  // 画像表示
  if (data.image_urls && data.image_urls.length > 0) {
    _topicImageUrls = data.image_urls;
    _topicImageIndex = 0;
    showTopicImage(0);
  } else {
    imagesEl.style.display = 'none';
    _topicImageUrls = [];
  }

  const parts = [];
  if (data.remaining_scripts != null) parts.push(`残り ${data.remaining_scripts}件`);
  if (data.spoken_count != null) parts.push(`発話済み ${data.spoken_count}件`);
  statsEl.textContent = parts.join(' / ');
  dotEl.classList.toggle('paused', false);
}

function showTopicImage(index) {
  const imagesEl = document.getElementById('topic-images');
  const imgEl = document.getElementById('topic-image');
  const counterEl = document.getElementById('topic-image-counter');

  if (!_topicImageUrls.length || index < 0 || index >= _topicImageUrls.length) {
    imagesEl.style.display = 'none';
    return;
  }
  _topicImageIndex = index;
  imgEl.src = _topicImageUrls[index];
  imagesEl.style.display = '';
  if (_topicImageUrls.length > 1) {
    counterEl.textContent = `${index + 1} / ${_topicImageUrls.length}`;
  } else {
    counterEl.textContent = '';
  }
}

async function loadTopicPanel() {
  try {
    const res = await fetch('/api/topic');
    const data = await res.json();
    updateTopicPanel(data);
  } catch (e) {}
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
