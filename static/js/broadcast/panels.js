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

function fadeSubtitle(avatarId) {
  // avatarId未指定時は両方フェード
  if (!avatarId) {
    fadeSubtitle('teacher');
    fadeSubtitle('student');
    return;
  }
  clearChunkTimers(avatarId);
  const el = _getSubtitleEl(avatarId);
  const duration = parseFloat(el.dataset.fadeDuration || 3) * 1000;
  const timerId = setTimeout(() => {
    el.classList.add('fading');
    el.classList.remove('visible');
  }, duration);
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

function showLessonText(text, displayProperties) {
  const panel = document.getElementById('lesson-text-panel');
  const content = document.getElementById('lesson-text-content');
  if (!panel || !content) return;

  // セクション別オーバーライド適用（値をクランプして安全に）
  if (displayProperties) {
    if (displayProperties.maxHeight != null) {
      const v = Math.max(10, Math.min(90, Number(displayProperties.maxHeight)));
      panel.style.maxHeight = v + '%';
    }
    if (displayProperties.width != null) {
      const v = Math.max(10, Math.min(95, Number(displayProperties.width)));
      panel.style.width = v + '%';
    }
    if (displayProperties.fontSize != null) {
      const v = Math.max(0.5, Math.min(3.0, Number(displayProperties.fontSize)));
      content.style.fontSize = v + 'vw';
    }
  } else {
    // displayProperties がなければグローバル設定にリセット
    panel.style.maxHeight = '';
    panel.style.width = '';
    content.style.fontSize = '';
  }

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

// --- 授業Dialogueタイムラインパネル ---

function _speakerIcon(speaker) {
  return speaker === 'student' ? '\u{1F9D1}' : '\u{1F469}';
}

function showLessonDialogues() {
  const panel = document.getElementById('lesson-dialogues-panel');
  if (!panel) return;
  renderLessonDialogues();
  panel.style.display = 'flex';
  requestAnimationFrame(() => {
    requestAnimationFrame(() => { panel.classList.add('visible'); });
  });
}

function hideLessonDialogues() {
  const panel = document.getElementById('lesson-dialogues-panel');
  if (!panel) return;
  panel.classList.remove('visible');
  setTimeout(() => {
    if (!panel.classList.contains('visible')) panel.style.display = 'none';
  }, 600);
}

function _setAutoFollow(enable) {
  _timelineState.autoFollow = enable;
  if (_timelineState.followTimer) {
    clearTimeout(_timelineState.followTimer);
    _timelineState.followTimer = null;
  }
  if (!enable) {
    _timelineState.followTimer = setTimeout(() => {
      _timelineState.autoFollow = true;
      if (_timelineState.currentSection >= 0) {
        _timelineState.viewSection = _timelineState.currentSection;
      }
      renderLessonDialogues();
    }, _FOLLOW_RESET_MS);
  }
}

function _selectSection(idx) {
  _timelineState.viewSection = idx;
  _setAutoFollow(false);
  renderLessonDialogues();
}

function renderLessonDialogues() {
  const panel = document.getElementById('lesson-dialogues-panel');
  const tabsEl = document.getElementById('lesson-dialogues-tabs');
  const listEl = document.getElementById('lesson-dialogues-list');
  if (!panel || !tabsEl || !listEl) return;

  const st = _timelineState;
  const sections = st.sections || [];
  if (sections.length === 0) {
    tabsEl.innerHTML = '';
    listEl.innerHTML = '';
    return;
  }

  const viewIdx = Math.max(0, Math.min(st.viewSection, sections.length - 1));
  const curIdx = st.currentSection;

  // タブ
  tabsEl.innerHTML = '';
  sections.forEach((sec, i) => {
    const tab = document.createElement('div');
    const classes = ['ld-tab'];
    if (i === viewIdx) classes.push('active');
    if (curIdx >= 0 && i < curIdx) classes.push('done');
    else if (i === curIdx) classes.push('current');
    tab.className = classes.join(' ');
    tab.textContent = `\u00A7${i + 1}`;
    tab.title = sec.section_type || '';
    tab.addEventListener('click', () => _selectSection(i));
    tabsEl.appendChild(tab);
  });

  // リスト
  listEl.innerHTML = '';
  const sec = sections[viewIdx];
  const mainDlgs = Array.isArray(sec.dialogues) ? sec.dialogues : [];
  const isCurrentSection = viewIdx === curIdx;

  _renderDialogueGroup(listEl, mainDlgs, 'main', isCurrentSection, st.currentKind, st.currentDialogue, curIdx, viewIdx);

  if (sec.question && Array.isArray(sec.question.answer_dialogues) && sec.question.answer_dialogues.length > 0) {
    const header = document.createElement('div');
    header.className = 'ld-group-header';
    header.textContent = '— 回答 —';
    listEl.appendChild(header);
    _renderDialogueGroup(listEl, sec.question.answer_dialogues, 'answer', isCurrentSection, st.currentKind, st.currentDialogue, curIdx, viewIdx);
  }

  // 追従ヒント（手動選択中）
  let hint = panel.querySelector('.ld-follow-hint');
  if (!st.autoFollow && curIdx >= 0 && viewIdx !== curIdx) {
    if (!hint) {
      hint = document.createElement('div');
      hint.className = 'ld-follow-hint';
      hint.textContent = '\u2192 現在地へ';
      hint.addEventListener('click', () => {
        _timelineState.viewSection = _timelineState.currentSection;
        _setAutoFollow(true);
        renderLessonDialogues();
      });
      panel.appendChild(hint);
    }
  } else if (hint) {
    hint.remove();
  }

  // 現在行を可視領域に
  const currentRow = listEl.querySelector('.ld-row.current');
  if (currentRow) currentRow.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}

function _renderDialogueGroup(listEl, dialogues, kind, isCurrentSection, currentKind, currentDialogue, curSection, viewSection) {
  dialogues.forEach((dlg, i) => {
    const row = document.createElement('div');
    let state;
    if (!isCurrentSection) {
      // 他セクション: currentより前なら past、後なら future
      if (curSection < 0) state = 'future';
      else if (viewSection < curSection) state = 'past';
      else state = 'future';
    } else if (kind === currentKind && i === currentDialogue) {
      state = 'current';
    } else if ((kind === 'main' && currentKind === 'answer')
      || (kind === currentKind && i < currentDialogue)) {
      state = 'past';
    } else {
      state = 'future';
    }
    row.className = 'ld-row ' + state;

    const marker = document.createElement('span');
    marker.className = 'ld-marker';
    row.appendChild(marker);

    const speaker = document.createElement('span');
    speaker.className = 'ld-speaker';
    speaker.textContent = _speakerIcon(dlg.speaker);
    row.appendChild(speaker);

    const content = document.createElement('span');
    content.className = 'ld-content';
    content.textContent = dlg.content || '';
    row.appendChild(content);

    listEl.appendChild(row);
  });
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
    // パネル復帰 + 授業テキスト・進捗・タイトル非表示
    if (todo) todo.style.display = '';
    if (customTexts) customTexts.style.display = '';
    hideLessonText();
    hideLessonProgress();
    hideLessonTitle();
    hideLessonDialogues();
  }
}
