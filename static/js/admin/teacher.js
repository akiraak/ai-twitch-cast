// 教師モード管理画面
// 各コンテンツが独立した折りたたみブロックとして縦に並ぶ

const SECTION_ICONS = {
  introduction: '\u{1F3AC}',
  explanation: '\u{1F4D6}',
  example: '\u{1F4DD}',
  question: '\u{2753}',
  summary: '\u{1F3C1}',
};

// 開閉状態を保持（リロード時に復元）
let _openLessonIds = new Set();

// 言語タブ状態（lesson_id → 'ja' or 'en'）
let _lessonLangTab = {};

// バージョン選択状態（`${lessonId}_${lang}` → version_number）
let _lessonVersionTab = {};

// カテゴリ一覧キャッシュ
let _lessonCategories = null;

// 選択中のカテゴリslug（null = 全て表示）
let _selectedCategory = null;

// TTS事前生成ポーリングタイマー（key → intervalId）
let _ttsPregenTimers = {};


function _getLessonLang(lessonId) {
  return _lessonLangTab[lessonId] || 'ja';
}

function _buildLangTabs(lessonId, plans, sections) {
  const currentLang = _getLessonLang(lessonId);
  const jaHasPlan = !!(plans && plans.ja && plans.ja.plan_json);
  const enHasPlan = !!(plans && plans.en && plans.en.plan_json);
  const jaSections = (sections || []).filter(s => (s.lang || 'ja') === 'ja');
  const enSections = (sections || []).filter(s => (s.lang || 'ja') === 'en');
  const jaBadge = jaHasPlan || jaSections.length ? ' ✅' : '';
  const enBadge = enHasPlan || enSections.length ? ' ✅' : '';
  return `<div style="display:flex; gap:4px; margin-bottom:10px;">
    <button onclick="_switchLessonLang(${lessonId}, 'ja')" style="padding:4px 14px; border:1px solid #d0c0e8; border-radius:4px; cursor:pointer; font-size:0.8rem; font-weight:600;
      ${currentLang === 'ja' ? 'background:#7b1fa2; color:#fff;' : 'background:#faf7ff; color:#7b1fa2;'}">🇯🇵 日本語${jaBadge}</button>
    <button onclick="_switchLessonLang(${lessonId}, 'en')" style="padding:4px 14px; border:1px solid #d0c0e8; border-radius:4px; cursor:pointer; font-size:0.8rem; font-weight:600;
      ${currentLang === 'en' ? 'background:#7b1fa2; color:#fff;' : 'background:#faf7ff; color:#7b1fa2;'}">🇺🇸 English${enBadge}</button>
  </div>`;
}

async function _switchLessonLang(lessonId, lang) {
  _lessonLangTab[lessonId] = lang;
  _openLessonIds.add(lessonId);
  await loadLessons();
}

function _getLessonVersion(lessonId, lang) {
  return _lessonVersionTab[`${lessonId}_${lang}`] || null;
}

async function _switchLessonVersion(lessonId, lang, vn) {
  _lessonVersionTab[`${lessonId}_${lang}`] = vn;
  _openLessonIds.add(lessonId);
  await loadLessons();
}

async function _loadCategories() {
  const res = await api('GET', '/api/lesson-categories');
  _lessonCategories = (res && res.ok) ? res.categories : [];
}

function switchConvSubtab(name, el) {
  document.querySelectorAll('#tab-convmode .char-subtab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('#tab-convmode .char-subcontent').forEach(t => t.classList.remove('active'));
  document.getElementById('conv-sub-' + name).classList.add('active');
  if (el) el.classList.add('active');
}

// --- コンテンツ一覧（各コンテンツを縦に並べる） ---

let _cachedLessonStatus = null;

async function loadLessons() {
  const res = await api('GET', '/api/lessons');
  if (!res || !res.ok) return;
  // カテゴリとステータスを取得
  if (!_lessonCategories) await _loadCategories();
  const statusRes = await api('GET', '/api/lessons/status');
  _cachedLessonStatus = statusRes;
  // カテゴリタブバー（専用カードに描画）
  const catContainer = document.getElementById('category-tabs-container');
  if (catContainer) {
    catContainer.innerHTML = '';
    _renderCategoryTabs(catContainer);
  }
  const list = document.getElementById('lesson-list');
  list.innerHTML = '';
  // 間のスケールスライダー
  await _renderPaceScaleSlider(list);
  // カテゴリでフィルタ
  const filtered = _selectedCategory === null
    ? res.lessons
    : res.lessons.filter(l => (l.category || '') === _selectedCategory);
  for (const l of filtered) {
    const item = await buildLessonItem(l.id);
    if (item) list.appendChild(item);
  }
  // 学習ダッシュボード（コンテンツ一覧の下に統合）
  _renderLearningSection(list);
}

async function _renderPaceScaleSlider(container) {
  const paceRes = await api('GET', '/api/lessons/pace-scale');
  const currentScale = paceRes && paceRes.ok ? paceRes.pace_scale : 1.0;
  const div = document.createElement('div');
  div.style.cssText = 'margin-bottom:12px; padding:10px 14px; background:#f5f0ff; border:1px solid #d0c0e8; border-radius:6px; display:flex; align-items:center; gap:12px;';
  div.innerHTML = `
    <span style="font-size:0.8rem; font-weight:600; color:#2a1f40; white-space:nowrap;">間のスケール:</span>
    <span style="font-size:0.75rem; color:#8a7a9a;">速い</span>
    <input type="range" min="0.5" max="2.0" step="0.1" value="${currentScale}"
      style="flex:1; accent-color:#7b1fa2;"
      oninput="this.nextElementSibling.textContent = parseFloat(this.value).toFixed(1) + 'x'"
      onchange="updatePaceScale(parseFloat(this.value))">
    <span style="font-size:0.85rem; font-weight:600; color:#7b1fa2; min-width:32px;">${currentScale.toFixed(1)}x</span>
    <span style="font-size:0.75rem; color:#8a7a9a;">ゆっくり</span>
  `;
  container.appendChild(div);
}

async function updatePaceScale(value) {
  await api('PUT', '/api/lessons/pace-scale', { pace_scale: value });
}

async function buildLessonItem(lessonId) {
  const lang = _getLessonLang(lessonId);
  const generator = 'claude';

  // バージョン解決: 選択中のバージョンがあればそれを使い、なければ最新
  let selectedVersion = _getLessonVersion(lessonId, lang);
  let apiUrl = '/api/lessons/' + lessonId;
  if (selectedVersion) apiUrl += '?version=' + selectedVersion;

  const res = await api('GET', apiUrl);
  if (!res || !res.ok) return null;

  const lesson = res.lesson;
  const sources = res.sources;
  const allSections = res.sections;
  const allVersions = res.versions || [];
  const sectionsByGenerator = res.sections_by_generator || {};
  const plans = res.plans || {};

  // 現在の lang+generator に対応するバージョン一覧
  const langVersions = allVersions.filter(v => v.lang === lang && v.generator === generator);
  const sections = allSections.filter(s => (s.lang || 'ja') === lang && (s.generator || 'claude') === generator);

  // バージョン番号確定（未選択なら最新）
  const currentVersion = selectedVersion || (langVersions.length ? langVersions[langVersions.length - 1].version_number : 1);

  const hasSources = sources.length > 0;
  const hasSections = sections.length > 0;

  // 授業ステータス（loadLessonsでキャッシュ済み）
  const statusRes = _cachedLessonStatus;
  const lState = statusRes ? statusRes.status.state : 'idle';
  const runningThisLesson = statusRes && statusRes.status.lesson_id === lessonId && lState !== 'idle';

  // バッジ
  const badges = [];
  if (sources.length) badges.push(sources.length + '\u30BD\u30FC\u30B9');
  const jaSec = allSections.filter(s => (s.lang || 'ja') === 'ja');
  const enSec = allSections.filter(s => (s.lang || 'ja') === 'en');
  if (jaSec.length || enSec.length) {
    const langBadges = [];
    if (jaSec.length) langBadges.push('JA:' + jaSec.length);
    if (enSec.length) langBadges.push('EN:' + enSec.length);
    badges.push(langBadges.join('/'));
  }
  // generator別バッジ
  const geminiSec = allSections.filter(s => (s.generator || 'claude') === 'gemini');
  const claudeSec = allSections.filter(s => (s.generator || 'claude') === 'claude');
  if (claudeSec.length) {
    badges.push('G:' + geminiSec.length + '/C:' + claudeSec.length);
  }
  const badgeText = badges.length ? ' (' + badges.join(' / ') + ')' : '';


  const details = document.createElement('details');
  details.className = 'lesson-item';
  details.style.cssText = 'border:1px solid #d0c0e8; border-radius:6px; padding:12px; margin-bottom:8px; background:#ffffff;';
  if (_openLessonIds.has(lessonId)) details.open = true;
  details.addEventListener('toggle', () => {
    if (details.open) _openLessonIds.add(lessonId);
    else _openLessonIds.delete(lessonId);
  });

  // summary
  const summary = document.createElement('summary');
  summary.style.cssText = 'cursor:pointer; font-weight:600; font-size:0.9rem; color:#2a1f40; list-style:none; display:flex; align-items:center; gap:8px;';
  summary.innerHTML = `<span class="lesson-arrow" style="color:#7b1fa2; font-size:0.75rem;">&#9660;</span>`
    + `<span style="font-size:0.65rem; color:#aaa; min-width:28px;">#${lessonId}</span>`
    + `<span>${esc(lesson.name)}</span>`
    + `<span style="font-size:0.7rem; color:#8a7a9a;">${esc(badgeText)}</span>`;
  details.appendChild(summary);

  // body
  const body = document.createElement('div');
  body.style.marginTop = '12px';

  // コンテンツ名編集 + カテゴリ選択
  const catOptions = (_lessonCategories || []).map(c =>
    `<option value="${esc(c.slug)}"${lesson.category === c.slug ? ' selected' : ''}>${esc(c.name)}</option>`
  ).join('');
  body.innerHTML = `<div style="display:flex; align-items:center; gap:8px; margin-bottom:14px; flex-wrap:wrap;">
    <span style="font-weight:600; font-size:0.85rem; color:#2a1f40;">コンテンツ名:</span>
    <input type="text" class="lesson-name-input" value="${esc(lesson.name)}" style="flex:1; min-width:120px; padding:4px 8px; background:#faf7ff; color:#2a1f40; border:1px solid #d0c0e8; border-radius:4px;">
    <button onclick="saveLessonName(${lessonId}, this)" style="padding:4px 12px; background:#7b1fa2; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:0.8rem;">保存</button>
    <select onchange="saveLessonCategory(${lessonId}, this.value)" style="padding:4px 8px; border:1px solid #d0c0e8; border-radius:4px; font-size:0.78rem; background:#faf7ff; color:#2a1f40;">
      <option value=""${!lesson.category ? ' selected' : ''}>カテゴリなし</option>
      ${catOptions}
    </select>
  </div>`;

  const hasExtractedText = !!(lesson.extracted_text);
  const hasImageSources = sources.some(s => s.source_type === 'image');

  // === STEP 1: ソース追加 ===
  const step1 = document.createElement('div');
  step1.className = 'lesson-step' + (hasSources ? ' step-done' : ' step-active');
  const step1Body = document.createElement('div');
  step1Body.className = 'lesson-step-body';

  // 現在のソース表示（複数画像対応）
  let srcInfo = '';
  if (sources.length) {
    const imageSrcs = sources.filter(s => s.source_type === 'image' && s.file_path);
    const urlSrcs = sources.filter(s => s.source_type === 'url');
    if (imageSrcs.length) {
      srcInfo = '<div style="display:flex; gap:6px; flex-wrap:wrap; margin-bottom:8px;">';
      for (const s of imageSrcs) {
        srcInfo += `<div style="width:60px; height:60px; border:1px solid #d0c0e8; border-radius:4px; overflow:hidden;">
          <img src="/${esc(s.file_path)}" style="width:100%; height:100%; object-fit:cover;" title="${esc(s.original_name)}">
        </div>`;
      }
      srcInfo += '</div>';
    }
    if (urlSrcs.length) {
      srcInfo += `<div style="margin-bottom:8px; font-size:0.8rem; color:#1565c0;" title="${esc(urlSrcs[0].url)}">${esc(urlSrcs[0].url)}</div>`;
    }
  }

  const btnLabel = hasSources ? 'ソース変更' : 'ソース追加';
  let step1Html = `<div class="lesson-step-title">ソース追加${sources.length ? ' (' + sources.length + '件)' : ''}</div>`
    + srcInfo
    + `<div style="display:flex; gap:8px; align-items:center;">
        <button onclick="addLessonSource(${lessonId})" style="padding:5px 14px; background:#7b1fa2; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:0.8rem;">${btnLabel}</button>
        <span class="lesson-upload-status"></span>
      </div>`;

  if (!hasSources) {
    step1Html += `<div style="margin-top:8px; padding:6px 10px; background:#f3e5f5; border-radius:4px; font-size:0.78rem; color:#6a1b9a;">→ 「ソース追加」から教材画像をアップロードしてください</div>`;
  } else if (hasImageSources) {
    step1Html += `<div style="margin-top:10px; display:flex; align-items:center; gap:8px;">
      <button onclick="extractLessonText(${lessonId})" class="btn-extract" style="padding:5px 14px; background:#1565c0; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:0.8rem;">${hasExtractedText ? 'テキスト再抽出' : 'テキスト抽出'}</button>
      <span class="extract-status"></span>`;
    if (!hasExtractedText) {
      step1Html += `<span style="color:#1565c0; font-size:0.78rem;">→ テキスト抽出で画像を読み取り、Step 2へ</span>`;
    } else {
      step1Html += `<span style="color:#2e7d32; font-size:0.78rem;">✅ 抽出済み → Step 2でスクリプト生成</span>`;
    }
    step1Html += `</div>`;
  }

  // 抽出テキスト（Step 1 の中に折りたたみ表示）
  if (hasExtractedText) {
    step1Html += `<details style="margin-top:10px; font-size:0.8rem;">
      <summary style="cursor:pointer; color:#7b1fa2; font-weight:500;">抽出テキスト</summary>
      <pre style="margin-top:6px; background:#fff; padding:8px; border:1px solid #d0c0e8; border-radius:4px; font-size:0.75rem; max-height:200px; overflow-y:auto; white-space:pre-wrap; word-break:break-word; color:#2a1f40;">${esc(lesson.extracted_text)}</pre>
    </details>`;
  }

  // メインコンテンツ（Step 1 の中に折りたたみ表示）
  if (lesson.main_content) {
    try {
      const mainContent = JSON.parse(lesson.main_content);
      if (Array.isArray(mainContent) && mainContent.length > 0) {
        const typeIcons = { conversation: '💬', passage: '📄', word_list: '📝', table: '📊' };
        const typeColors = { conversation: '#1565c0', passage: '#2e7d32', word_list: '#e65100', table: '#6a1b9a' };
        const itemsHtml = mainContent.map((item, idx) => {
          const ct = item.content_type || 'passage';
          const icon = typeIcons[ct] || '📄';
          const color = typeColors[ct] || '#333';
          const role = item.role || (idx === 0 ? 'main' : 'sub');
          const isMain = role === 'main';
          const borderWidth = isMain ? '5px' : '3px';
          const bg = isMain ? '#fffde7' : '#fafafa';
          const roleLabel = isMain ? ' ★' : '';
          return `<div style="margin-bottom:8px; padding:6px 8px; border-left:${borderWidth} solid ${color}; background:${bg}; border-radius:0 4px 4px 0;${isMain ? ' box-shadow: 0 1px 3px rgba(0,0,0,0.1);' : ''}">
            <div style="font-weight:${isMain ? '700' : '500'}; color:${color};">${icon}${roleLabel} ${idx + 1}. [${esc(ct)}] ${esc(item.label || '')}</div>
            <pre style="margin:4px 0 0; white-space:pre-wrap; word-break:break-word; font-size:0.72rem; color:#444;">${esc(item.content || '')}</pre>
          </div>`;
        }).join('');
        const mainCount = mainContent.filter(i => (i.role || (mainContent.indexOf(i) === 0 ? 'main' : 'sub')) === 'main').length;
        const subCount = mainContent.length - mainCount;
        step1Html += `<details style="margin-top:10px; font-size:0.8rem;">
          <summary style="cursor:pointer; color:#7b1fa2; font-weight:500;">コンテンツ（★主要${mainCount}件 + 補助${subCount}件）</summary>
          <div style="margin-top:6px; max-height:300px; overflow-y:auto;">${itemsHtml}</div>
        </details>`;
      }
    } catch (e) { /* main_content JSONパース失敗は無視 */ }
  }

  step1Body.innerHTML = step1Html;
  step1.innerHTML = '<div class="lesson-step-num">1</div>';
  step1.appendChild(step1Body);
  body.appendChild(step1);

  // === 言語タブ ===
  const langTabsDiv = document.createElement('div');
  langTabsDiv.innerHTML = _buildLangTabs(lessonId, plans, allSections);
  body.appendChild(langTabsDiv);


  // === STEP 2: スクリプト生成 ===
  const charsRes = await api('GET', '/api/characters');
  const charList = Array.isArray(charsRes) ? charsRes : [];
  const teacherChar = charList.find(c => c.role === 'teacher');
  const studentChar = charList.find(c => c.role === 'student');

  let totalDlgs = 0;
  for (const s of sections) {
    try { totalDlgs += JSON.parse(s.dialogues || '[]').length; } catch(e) {}
  }

  const step2 = document.createElement('div');
  step2.className = 'lesson-step' + (hasSections ? ' step-done' : hasSources ? ' step-active' : ' step-disabled');
  const step2Body = document.createElement('div');
  step2Body.className = 'lesson-step-body';

  let step2Html = `<div class="lesson-step-title">スクリプト生成</div>`;

  if (hasSections) {
    // モードB: インポート済み
    step2Html += `<div class="lesson-success-banner">\u2705 ${sections.length} セクション、${totalDlgs} 発話をインポート済み</div>`;
    step2Html += `<details style="margin-bottom:8px;">
      <summary style="cursor:pointer; font-weight:600; font-size:0.78rem; color:#6a1b9a; padding:4px 0;">再インポート / 更新</summary>
      <div style="margin-top:6px;">${_buildImportArea(lessonId, lang, lesson.name, sources.length)}</div>
    </details>`;
  } else {
    // モードA: 未作成 — 手順ガイド付き
    step2Html += _buildImportArea(lessonId, lang, lesson.name, sources.length);
  }

  // プロンプト折りたたみ（共通）
  step2Html += `<details style="margin-bottom:8px;" class="prompt-details-${lessonId}-${lang}">
    <summary style="cursor:pointer; font-weight:600; font-size:0.75rem; color:#6a1b9a; padding:4px 0;">\u{1F4DD} 生成プロンプト</summary>
    <div class="prompt-content-area" style="margin-top:4px;">
      <div class="prompt-display" style="padding:8px 10px; background:#faf7ff; border:1px solid #d0c0e8; border-radius:4px; font-size:0.72rem; max-height:300px; overflow-y:auto; margin-bottom:6px;"><span class="lesson-spinner">読み込み中...</span></div>
      <div style="border:1px solid #d0c0e8; border-radius:4px; padding:8px; background:#f5f0ff;">
        <div style="font-weight:600; font-size:0.72rem; color:#6a1b9a; margin-bottom:4px;">AI編集</div>
        <div style="display:flex; gap:6px; margin-bottom:6px;">
          <input type="text" class="prompt-ai-instruction" placeholder="編集指示を入力..." style="flex:1; padding:4px 8px; border:1px solid #d0c0e8; border-radius:4px; font-size:0.75rem;">
          <button class="prompt-ai-run-btn" style="padding:4px 12px; background:#6a1b9a; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:0.75rem; white-space:nowrap;">実行</button>
        </div>
        <div class="prompt-ai-status" style="display:none;"></div>
        <div class="prompt-diff-area" style="display:none;">
          <div class="diff-container prompt-diff-display"></div>
          <div style="display:flex; gap:6px; margin-top:6px;">
            <button class="prompt-apply-btn" style="padding:4px 10px; background:#2e7d32; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:0.72rem;">適用</button>
            <button class="prompt-retry-btn" style="padding:4px 10px; background:#6a1b9a; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:0.72rem;">やり直す</button>
            <button class="prompt-cancel-btn" style="padding:4px 10px; background:#888; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:0.72rem;">キャンセル</button>
          </div>
        </div>
      </div>
    </div>
  </details>`;

  step2Body.innerHTML = step2Html;
  _setupPromptUI(step2Body);
  step2.innerHTML = '<div class="lesson-step-num">2</div>';
  step2.appendChild(step2Body);
  body.appendChild(step2);

  // === STEP 3: セクション確認・編集 ===
  const step3 = document.createElement('div');
  step3.className = 'lesson-step' + (hasSections ? ' step-active' : ' step-disabled');
  const step3Body = document.createElement('div');
  step3Body.className = 'lesson-step-body';
  step3Body.innerHTML = `<div class="lesson-step-title">セクション確認・編集${hasSections ? ' (' + sections.length + 'セクション)' : ''}</div>`;

  // バージョンセレクタ
  if (langVersions.length > 0) {
    const verDiv = document.createElement('div');
    verDiv.innerHTML = _buildVersionSelector(lessonId, lang, generator, langVersions, currentVersion, sections);
    step3Body.appendChild(verDiv);
  }

  let ttsCacheMap = {};
  if (hasSections) {
    const cacheRes = await api('GET', '/api/lessons/' + lessonId + '/tts-cache?lang=' + lang + '&generator=' + generator + '&version=' + currentVersion);
    if (cacheRes && cacheRes.ok) {
      for (const c of cacheRes.sections) {
        ttsCacheMap[c.order_index] = c.parts;
      }
    }
  }
  const secContainer = document.createElement('div');
  renderSectionsInto(secContainer, sections, lessonId, ttsCacheMap, {teacher: teacherChar, student: studentChar}, plans[lang], currentVersion);
  step3Body.appendChild(secContainer);

  step3.innerHTML = '<div class="lesson-step-num">3</div>';
  step3.appendChild(step3Body);
  body.appendChild(step3);

  // TTS事前生成の進行中タスクがあればポーリング再開
  if (hasSections) {
    const pregenRes = await api('GET', `/api/lessons/${lessonId}/tts-pregen-status?lang=${lang}&generator=${generator}&version=${currentVersion}`);
    if (pregenRes && pregenRes.ok && pregenRes.state === 'running') {
      startTtsPregenPolling(lessonId, lang, generator, currentVersion);
    }
  }

  // === STEP 4: 授業再生 ===
  const isRunning = runningThisLesson && lState === 'running';
  const isPaused = runningThisLesson && lState === 'paused';
  const isActive = isRunning || isPaused;
  const step4 = document.createElement('div');
  step4.className = 'lesson-step' + (isActive ? ' step-done' : hasSections ? ' step-active' : ' step-disabled');
  const step4Body = document.createElement('div');
  step4Body.className = 'lesson-step-body';
  const progressInfo = isActive ? `${statusRes.status.current_index + 1} / ${statusRes.status.total_sections} セクション` : '';
  step4Body.innerHTML = `<div class="lesson-step-title">授業再生${isActive ? '（実行中）' : ''}</div>
    <div style="display:flex; gap:6px; align-items:center; flex-wrap:wrap;">
      <button onclick="startLesson(${lessonId}, '${lang}', ${currentVersion})" class="btn-lesson-start" style="padding:5px 14px; background:#2e7d32; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:0.8rem;${isActive ? ' display:none;' : ''}">${lang === 'en' ? 'Start Lesson' : '授業開始'} (v${currentVersion})</button>
      <button onclick="pauseLesson()" class="btn-lesson-pause" style="padding:5px 14px; background:#f57f17; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:0.8rem;${isRunning ? '' : ' display:none;'}">一時停止</button>
      <button onclick="resumeLesson()" class="btn-lesson-resume" style="padding:5px 14px; background:#2e7d32; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:0.8rem;${isPaused ? '' : ' display:none;'}">再開</button>
      <button onclick="stopLesson()" class="btn-lesson-stop" style="padding:5px 14px; background:#c62828; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:0.8rem;${isActive ? '' : ' display:none;'}">終了</button>
      <span class="lesson-state" style="font-size:0.8rem; color:#8a7a9a;">${isRunning ? '再生中' : isPaused ? '一時停止中' : ''}</span>
      <button onclick="window.open('/broadcast', '_blank', 'width=1920,height=1080')" style="padding:5px 14px; background:#6a1b9a; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:0.8rem;">配信プレビュー</button>
    </div>
    <div class="lesson-progress" style="margin-top:4px; font-size:0.75rem; color:#8a7a9a;">${progressInfo}</div>`;

  step4.innerHTML = '<div class="lesson-step-num">4</div>';
  step4.appendChild(step4Body);
  body.appendChild(step4);

  // 削除ボタン
  const delRow = document.createElement('div');
  delRow.style.cssText = 'display:flex; justify-content:flex-end; margin-top:12px; padding-top:10px; border-top:1px solid #ece4f5;';
  delRow.innerHTML = `<button onclick="deleteLesson(${lessonId})" style="padding:4px 12px; background:#c62828; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:0.8rem;">コンテンツ削除</button>`;
  body.appendChild(delRow);

  details.appendChild(body);
  return details;
}

async function createLesson() {
  // カテゴリがないと授業を作成できない
  if (!_lessonCategories || _lessonCategories.length === 0) {
    const ok = await showConfirm('授業を作成するには、まずカテゴリを作成してください。\n今すぐカテゴリを作成しますか？', {
      title: 'カテゴリが必要です',
      okLabel: 'カテゴリを作成',
    });
    if (ok) createCategory();
    return;
  }
  const cats = _lessonCategories || [];
  const result = await _showCreateLessonModal(cats);
  if (!result) return;
  const res = await api('POST', '/api/lessons', { name: result.name, category: result.category });
  if (res && res.ok) {
    _openLessonIds.add(res.lesson.id);
    showToast('コンテンツ作成: ' + result.name, 'success');
    await loadLessons();
  }
}

function _showCreateLessonModal(cats) {
  return new Promise(resolve => {
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    const options = cats.map(c => `<option value="${esc(c.slug)}">${esc(c.name)}</option>`).join('');
    overlay.innerHTML = `<div class="modal-box">
      <h3>新規コンテンツ</h3>
      <div style="display:flex; flex-direction:column; gap:8px;">
        <select id="_lesson_cat" class="modal-input" style="padding:6px 8px;">
          <option value="" disabled selected>カテゴリを選択</option>
          ${options}
        </select>
        <input type="text" id="_lesson_name" class="modal-input" placeholder="コンテンツ名">
      </div>
      <div class="btn-group" style="margin-top:12px;">
        <button class="primary" data-action="ok">作成</button>
        <button class="secondary" data-action="cancel">キャンセル</button>
      </div>
    </div>`;

    const catEl = overlay.querySelector('#_lesson_cat');
    const nameEl = overlay.querySelector('#_lesson_name');

    const doResolve = (action) => {
      if (action === 'ok') {
        const category = catEl.value;
        const name = nameEl.value.trim();
        if (!category) { catEl.style.borderColor = '#c62828'; catEl.focus(); return; }
        if (!name) { nameEl.style.borderColor = '#c62828'; nameEl.focus(); return; }
        overlay.remove();
        resolve({ name, category });
      } else {
        overlay.remove();
        resolve(null);
      }
    };

    overlay.addEventListener('click', e => {
      const action = e.target.dataset?.action;
      if (action) doResolve(action);
    });
    nameEl.addEventListener('keydown', e => {
      if (e.key === 'Enter') doResolve('ok');
      if (e.key === 'Escape') doResolve('cancel');
    });

    document.body.appendChild(overlay);
    catEl.focus();
  });
}

async function saveLessonName(lessonId, btn) {
  const input = btn.parentElement.querySelector('.lesson-name-input');
  const name = input.value.trim();
  if (!name) return;
  const res = await api('PUT', '/api/lessons/' + lessonId, { name });
  if (res && res.ok) {
    showToast('名前を更新しました', 'success');
    await loadLessons();
  }
}

async function deleteLesson(lessonId) {
  const ok = await showConfirm('このコンテンツを削除しますか？', { danger: true, title: 'コンテンツ削除' });
  if (!ok) return;
  const res = await api('DELETE', '/api/lessons/' + lessonId);
  if (res && res.ok) {
    _openLessonIds.delete(lessonId);
    showToast('コンテンツを削除しました', 'success');
    await loadLessons();
  }
}

// --- 後工程クリア ---

function _clearDownstreamSteps(lessonId, stepNums) {
  const item = _findLessonItem(lessonId);
  if (!item) return;
  for (const step of item.querySelectorAll('.lesson-step')) {
    const numEl = step.querySelector('.lesson-step-num');
    if (numEl && stepNums.includes(numEl.textContent.trim())) {
      const body = step.querySelector('.lesson-step-body');
      if (body) body.innerHTML = '<div style="color:#bbb; font-size:0.75rem; padding:4px;">前工程の処理中…</div>';
      step.className = 'lesson-step step-disabled';
    }
  }
}

// --- 教材ソース ---

function _showSpinner(el, msg) {
  el.innerHTML = `<span class="lesson-spinner">${esc(msg)}</span>`;
}
function _hideSpinner(el) {
  el.innerHTML = '';
}

async function addLessonSource(lessonId) {
  const choice = await showModal('ソースの種類を選択してください', {
    title: 'ソース追加',
    okLabel: '画像',
    cancelLabel: 'URL',
  });
  if (choice === true) {
    _clearDownstreamSteps(lessonId, ['2', '3', '4', '5']);
    // 既存データをクリア
    await api('POST', '/api/lessons/' + lessonId + '/clear-sources');
    // 画像: 複数ファイル選択
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.png,.jpg,.jpeg,.webp,.gif';
    input.multiple = true;
    input.onchange = () => uploadLessonImages(lessonId, input);
    input.click();
  } else if (choice === false) {
    // URL入力
    const url = await showModal('URLを入力してください', {
      title: 'URL追加',
      input: 'https://...',
      okLabel: '追加',
    });
    if (url) {
      _clearDownstreamSteps(lessonId, ['2', '3', '4', '5']);
      await doAddLessonUrl(lessonId, url);
    }
  }
}

async function uploadLessonImages(lessonId, input) {
  if (!input.files || !input.files.length) return;
  const statusEl = _findStatusEl(lessonId);
  const total = input.files.length;
  let done = 0;
  for (const file of input.files) {
    done++;
    const msg = total > 1
      ? `アップロード中 (${done}/${total}): ${file.name}`
      : `アップロード中: ${file.name}`;
    if (statusEl) _showSpinner(statusEl, msg);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const r = await fetch('/api/lessons/' + lessonId + '/upload-image', { method: 'POST', body: formData });
      const data = await r.json();
      if (!data.ok) {
        showToast('アップロード失敗: ' + (data.error || ''), 'error');
      }
    } catch (e) {
      showToast('アップロード失敗: ' + e.message, 'error');
    }
  }
  if (statusEl) _hideSpinner(statusEl);
  showToast(total + '件アップロード完了', 'success');
  _openLessonIds.add(lessonId);
  await loadLessons();
}

async function extractLessonText(lessonId) {
  _clearDownstreamSteps(lessonId, ['2', '3', '4', '5']);
  const item = _findLessonItem(lessonId);
  const statusEl = item ? item.querySelector('.extract-status') : null;
  const btn = item ? item.querySelector('.btn-extract') : null;
  if (btn) btn.disabled = true;
  if (statusEl) _showSpinner(statusEl, '抽出中...');
  const res = await api('POST', '/api/lessons/' + lessonId + '/extract-text');
  if (btn) btn.disabled = false;
  if (statusEl) _hideSpinner(statusEl);
  if (res && res.ok) {
    showToast('テキスト抽出完了', 'success');
  } else {
    showToast('テキスト抽出失敗: ' + (res && res.error ? res.error : '不明なエラー'), 'error');
  }
  _openLessonIds.add(lessonId);
  await loadLessons();
}

async function doAddLessonUrl(lessonId, url) {
  const statusEl = _findStatusEl(lessonId);
  if (statusEl) _showSpinner(statusEl, 'URL取得中 — テキスト抽出中...');
  const res = await api('POST', '/api/lessons/' + lessonId + '/add-url', { url });
  if (statusEl) _hideSpinner(statusEl);
  if (res && res.ok) {
    showToast('URL追加完了', 'success');
  }
  _openLessonIds.add(lessonId);
  await loadLessons();
}

function _findLessonItem(lessonId) {
  for (const item of document.querySelectorAll('.lesson-item')) {
    if (item.querySelector(`button[onclick="addLessonSource(${lessonId})"]`)) return item;
  }
  return null;
}

function _findStatusEl(lessonId) {
  const item = _findLessonItem(lessonId);
  return item ? item.querySelector('.lesson-upload-status') : null;
}

function renderSectionsInto(container, sections, lessonId, ttsCacheMap, charInfo, langPlan, versionNumber) {
  container.innerHTML = '';
  if (!sections || !sections.length) {
    container.innerHTML = '<div style="color:#8a7a9a; font-size:0.8rem; padding:8px;">スクリプトがありません。「JSONインポート」でセクションを追加してください。</div>';
    return;
  }
  ttsCacheMap = ttsCacheMap || {};
  // v3: 監督のdialogue_directionsをパース
  let _planSections = [];
  try {
    if (langPlan && langPlan.plan_json) {
      _planSections = JSON.parse(langPlan.plan_json);
    }
  } catch(e) {}
  for (let i = 0; i < sections.length; i++) {
    const s = sections[i];
    const icon = SECTION_ICONS[s.section_type] || '\u{1F4D6}';
    const cacheParts = ttsCacheMap[s.order_index] || [];
    const hasCacheFlag = cacheParts.length > 0;
    const div = document.createElement('div');
    div.style.cssText = 'border:1px solid #d0c0e8; border-radius:6px; padding:10px; margin-bottom:8px; background:#faf7ff;';

    let html = `<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
      <div>
        <span style="font-size:0.9rem;">${icon}</span>
        <span style="font-weight:600; font-size:0.8rem; margin-left:4px; color:#2a1f40;">${i + 1}. ${esc(s.section_type)}</span>
        <span style="font-size:0.7rem; color:#7b1fa2; margin-left:8px;">[${esc(s.emotion)}]</span>
        ${hasCacheFlag ? '<span style="font-size:0.65rem; color:#2e7d32; margin-left:6px; background:#e8f5e9; padding:1px 5px; border-radius:3px;">TTS cached</span>' : ''}
        ${hasCacheFlag ? `<button onclick="playSectionAudio(this, ${s.order_index}, ${lessonId}, ${versionNumber || 1})" style="width:26px; height:26px; background:#1565c0; color:#fff; border:none; border-radius:50%; cursor:pointer; font-size:0.75rem; line-height:26px; text-align:center;" title="セクション再生">\u25B6</button>` : ''}
      </div>
      <div style="display:flex; gap:4px;">
        <button onclick="moveSectionUp(${lessonId}, ${s.id})" style="width:24px; height:24px; background:#f0ecf5; color:#6a5590; border:1px solid #d0c0e8; border-radius:3px; cursor:pointer; font-size:0.7rem;" ${i === 0 ? 'disabled' : ''}>\u25B2</button>
        <button onclick="moveSectionDown(${lessonId}, ${s.id})" style="width:24px; height:24px; background:#f0ecf5; color:#6a5590; border:1px solid #d0c0e8; border-radius:3px; cursor:pointer; font-size:0.7rem;" ${i === sections.length - 1 ? 'disabled' : ''}>\u25BC</button>
        <button onclick="deleteSection(${lessonId}, ${s.id})" style="width:24px; height:24px; background:#c62828; color:#fff; border:none; border-radius:3px; cursor:pointer; font-size:0.7rem;">\u00D7</button>
      </div>
    </div>`;

    // 注釈UI
    html += _buildAnnotationUI(lessonId, s);

    // 対話モード: dialoguesがあれば発話一覧を表示
    let _dlgs = [];
    let _originalDlgs = null;
    let _reviewData = null;
    let _reviewGeneration = null;
    let _reviewOverallFeedback = '';
    try {
      let _parsed = typeof s.dialogues === 'string' ? JSON.parse(s.dialogues) : (s.dialogues || []);
      // v4: {dialogues: [...], review: {...}} 形式に対応
      if (_parsed && !Array.isArray(_parsed) && _parsed.dialogues) {
        _dlgs = _parsed.dialogues || [];
        _originalDlgs = _parsed.original_dialogues || null;
        _reviewData = _parsed.review || null;
        _reviewGeneration = _parsed.review_generation || null;
        _reviewOverallFeedback = _parsed.review_overall_feedback || '';
      } else {
        _dlgs = Array.isArray(_parsed) ? _parsed : [];
      }
    } catch(e) {}
    const _ci = charInfo || {};

    // 監督レビュー結果の表示
    if (_reviewData) {
      const rvApproved = _reviewData.approved;
      const rvIcon = rvApproved ? '\u2705' : '\u274C';
      const rvLabel = rvApproved ? '合格' : '不合格';
      const rvBg = rvApproved ? '#e8f5e9' : '#fbe9e7';
      const rvBc = rvApproved ? '#a5d6a7' : '#ffab91';
      let rvHtml = `<div style="margin-bottom:6px; padding:6px 8px; background:${rvBg}; border:1px solid ${rvBc}; border-radius:4px;">
        <div style="font-size:0.72rem; font-weight:600;">${rvIcon} 監督レビュー: ${rvLabel}${_reviewData.is_regenerated ? ' (再生成済み)' : ''}</div>`;
      if (_reviewData.feedback) {
        rvHtml += `<div style="font-size:0.68rem; color:#555; margin-top:2px;">${esc(_reviewData.feedback)}</div>`;
      }
      if (_reviewGeneration) {
        rvHtml += `<details style="margin-top:4px;">
          <summary style="cursor:pointer; color:#6a1b9a; font-size:0.62rem;">\u{1F50D} レビュープロンプト (model: ${esc(_reviewGeneration.model || '?')})</summary>
          <div style="padding:4px 8px; background:#f3e5f5; border:1px solid #ce93d8; border-radius:4px; margin-top:2px;">
            <details style="margin-bottom:4px;">
              <summary style="cursor:pointer; color:#888; font-size:0.62rem;">\u{1F9E0} System Prompt</summary>
              <pre style="font-size:0.6rem; max-height:200px; overflow-y:auto; white-space:pre-wrap; word-break:break-all; margin:2px 0; padding:4px; background:#fafafa; border-radius:3px;">${esc(_reviewGeneration.system_prompt || '')}</pre>
            </details>
            <details style="margin-bottom:4px;">
              <summary style="cursor:pointer; color:#888; font-size:0.62rem;">\u{1F4AC} User Prompt</summary>
              <pre style="font-size:0.6rem; max-height:200px; overflow-y:auto; white-space:pre-wrap; word-break:break-all; margin:2px 0; padding:4px; background:#fafafa; border-radius:3px;">${esc(_reviewGeneration.user_prompt || '')}</pre>
            </details>
            <details>
              <summary style="cursor:pointer; color:#888; font-size:0.62rem;">\u{1F4DD} Raw Output</summary>
              <pre style="font-size:0.6rem; max-height:200px; overflow-y:auto; white-space:pre-wrap; word-break:break-all; margin:2px 0; padding:4px; background:#fafafa; border-radius:3px;">${esc(_reviewGeneration.raw_output || '')}</pre>
            </details>
          </div>
        </details>`;
      }
      // revised_directions（監督の修正指示）
      const rvDirs = _reviewData.revised_directions || [];
      if (rvDirs.length > 0) {
        rvHtml += `<details style="margin-top:4px;">
          <summary style="cursor:pointer; color:#e65100; font-size:0.62rem;">\u{1F3AC} 監督の修正指示 (revised_directions: ${rvDirs.length}件)</summary>
          <div style="padding:4px 8px; background:#fff3e0; border:1px solid #ffcc80; border-radius:4px; margin-top:2px;">`;
        for (const rd of rvDirs) {
          const rdIcon = rd.speaker === 'teacher' ? '\u{1F393}' : '\u{1F64B}';
          rvHtml += `<div style="margin-bottom:3px; padding:3px 6px; background:#fff8e1; border-left:3px solid #ffa726; border-radius:2px; font-size:0.65rem;">
            <span style="font-weight:600;">${rdIcon} ${esc(rd.speaker || '?')}</span>
            <div style="color:#555; margin-top:1px;">${esc(rd.direction || '')}</div>
            ${rd.key_content ? `<div style="color:#e65100; margin-top:1px;">key: ${esc(rd.key_content)}</div>` : ''}
          </div>`;
        }
        rvHtml += `</div></details>`;
      }
      // 再生成前のセリフ（original_dialogues）
      if (_originalDlgs && _originalDlgs.length > 0) {
        rvHtml += `<details style="margin-top:4px;">
          <summary style="cursor:pointer; color:#c62828; font-size:0.62rem;">\u{1F5D1} 再生成前のセリフ (${_originalDlgs.length}件)</summary>
          <div style="padding:4px 8px; background:#fce4ec; border:1px solid #ef9a9a; border-radius:4px; margin-top:2px;">`;
        for (const od of _originalDlgs) {
          const odIsT = od.speaker === 'teacher';
          const odCh = odIsT ? _ci.teacher : _ci.student;
          const odSpk = odIsT ? '\u{1F393}' + (odCh ? odCh.name : '先生') : '\u{1F64B}' + (odCh ? odCh.name : '生徒');
          const odBg = odIsT ? '#fce4ec' : '#fff3e0';
          const odBc = odIsT ? '#ef9a9a' : '#ffcc80';
          let odGenHtml = '';
          if (od.generation) {
            const gen = od.generation;
            odGenHtml = `<details style="margin-top:3px; margin-left:12px;">
              <summary style="cursor:pointer; color:#888; font-size:0.62rem;">\u{1F50D} 生成プロンプト (model: ${esc(gen.model || '?')})</summary>
              <div style="padding:4px 8px; background:#fafafa; border:1px solid #e0e0e0; border-radius:4px; margin-top:2px;">
                <details style="margin-bottom:4px;">
                  <summary style="cursor:pointer; color:#888; font-size:0.62rem;">\u{1F9E0} System Prompt</summary>
                  <pre style="font-size:0.6rem; max-height:200px; overflow-y:auto; white-space:pre-wrap; word-break:break-all; margin:2px 0; padding:4px; background:#fafafa; border-radius:3px;">${esc(gen.system_prompt || '')}</pre>
                </details>
                <details style="margin-bottom:4px;">
                  <summary style="cursor:pointer; color:#888; font-size:0.62rem;">\u{1F4AC} User Prompt</summary>
                  <pre style="font-size:0.6rem; max-height:200px; overflow-y:auto; white-space:pre-wrap; word-break:break-all; margin:2px 0; padding:4px; background:#fafafa; border-radius:3px;">${esc(gen.user_prompt || '')}</pre>
                </details>
                <details>
                  <summary style="cursor:pointer; color:#888; font-size:0.62rem;">\u{1F4DD} Raw Output</summary>
                  <pre style="font-size:0.6rem; max-height:200px; overflow-y:auto; white-space:pre-wrap; word-break:break-all; margin:2px 0; padding:4px; background:#fafafa; border-radius:3px;">${esc(gen.raw_output || '')}</pre>
                </details>
              </div>
            </details>`;
          }
          rvHtml += `<div style="margin-bottom:3px; padding:4px 8px; background:${odBg}; border-left:3px solid ${odBc}; border-radius:3px; font-size:0.72rem; opacity:0.8;">
            <span style="font-weight:600; color:#555;">${odSpk}</span>
            <span style="font-size:0.65rem; color:#7b1fa2; margin-left:4px;">[${esc(od.emotion || '')}]</span>
            <div style="margin-top:2px; color:#555; text-decoration:line-through;">${esc(od.content || '')}</div>
            ${odGenHtml}
          </div>`;
        }
        rvHtml += `</div></details>`;
      }
      rvHtml += `</div>`;
      html += rvHtml;
    }

    if (_dlgs.length > 0) {
      html += `<div style="margin-bottom:6px; padding:6px 8px; background:#f0ecf5; border-radius:4px; border:1px solid #e0d4f0;">`;
      for (let di = 0; di < _dlgs.length; di++) {
        const dlg = _dlgs[di];
        const isT = dlg.speaker === 'teacher';
        const ch = isT ? _ci.teacher : _ci.student;
        const spk = isT ? '\u{1F393}' + (ch ? ch.name : '先生') : '\u{1F64B}' + (ch ? ch.name : '生徒');
        const voice = ch ? (ch.tts_voice || '?') : '?';
        const bg = isT ? '#e3f2fd' : '#fff3e0';
        const bc = isT ? '#90caf9' : '#ffcc80';
        // v3: 監督のdialogue_directionsから対応する指示を取得
        const _ps = _planSections[i];
        const _dd = _ps && _ps.dialogue_directions && _ps.dialogue_directions[di];
        // dlgキャッシュ: section_XX_dlg_YY.wav
        const dlgCacheKey = `section_${String(s.order_index).padStart(2,'0')}_dlg_${String(di).padStart(2,'0')}`;
        const dlgCache = (cacheParts || []).find(p => p.path && p.path.includes(dlgCacheKey));
        const dlgCacheHtml = dlgCache
          ? `<button onclick="playAudioInline(this, '/${esc(dlgCache.path)}')" style="padding:0 4px; background:#1565c0; color:#fff; border:none; border-radius:2px; cursor:pointer; font-size:0.58rem; margin-left:4px;">\u25B6</button><span style="color:#558b2f; font-size:0.6rem; margin-left:2px;">${(dlgCache.size/1024).toFixed(0)}KB</span>`
          : '<span style="color:#c62828; font-size:0.6rem; margin-left:4px;">TTS未生成</span>';
        let genHtml = '';
        if (dlg.generation) {
          const gen = dlg.generation;
          const detBg = isT ? '#f0f4ff' : '#fff8f0';
          const detBc = isT ? '#bbdefb' : '#ffe0b2';
          const detColor = isT ? '#1565c0' : '#e65100';
          genHtml = `<details style="margin-top:3px; margin-left:12px;">
            <summary style="cursor:pointer; color:${detColor}; font-size:0.62rem;">
              \u{1F50D} 生成プロンプト (model: ${esc(gen.model || '?')}, temp: ${gen.temperature || '?'})
            </summary>
            <div style="padding:4px 8px; background:${detBg}; border:1px solid ${detBc}; border-radius:4px; margin-top:2px;">
              <details style="margin-bottom:4px;">
                <summary style="cursor:pointer; color:#888; font-size:0.62rem;">\u{1F9E0} System Prompt</summary>
                <pre style="font-size:0.6rem; max-height:200px; overflow-y:auto; white-space:pre-wrap; word-break:break-all; margin:2px 0; padding:4px; background:#fafafa; border-radius:3px;">${esc(gen.system_prompt || '')}</pre>
              </details>
              <details style="margin-bottom:4px;">
                <summary style="cursor:pointer; color:#888; font-size:0.62rem;">\u{1F4AC} User Prompt</summary>
                <pre style="font-size:0.6rem; max-height:200px; overflow-y:auto; white-space:pre-wrap; word-break:break-all; margin:2px 0; padding:4px; background:#fafafa; border-radius:3px;">${esc(gen.user_prompt || '')}</pre>
              </details>
              <details>
                <summary style="cursor:pointer; color:#888; font-size:0.62rem;">\u{1F4DD} Raw Output</summary>
                <pre style="font-size:0.6rem; max-height:200px; overflow-y:auto; white-space:pre-wrap; word-break:break-all; margin:2px 0; padding:4px; background:#fafafa; border-radius:3px;">${esc(gen.raw_output || '')}</pre>
              </details>
            </div>
          </details>`;
        }
        html += `<div style="margin-bottom:3px; padding:4px 8px; background:${bg}; border-left:3px solid ${bc}; border-radius:3px; font-size:0.72rem;">
          <span style="font-weight:600; color:#555;">${spk}</span>
          <span style="font-size:0.65rem; color:#7b1fa2; margin-left:4px;">[${esc(dlg.emotion || '')}]</span>
          <span style="font-size:0.6rem; color:#888; margin-left:6px;">\u{1F50A}${esc(voice)}</span>
          ${dlgCacheHtml}
          ${_dd ? `<div style="margin-top:3px; padding:3px 6px; background:rgba(106,27,154,0.06); border-left:2px solid #ce93d8; border-radius:2px; font-size:0.65rem;">
            <span style="color:#6a1b9a; font-weight:500;">\u{1F3AC} 監督:</span> <span style="color:#555;">${esc(_dd.direction || '')}</span>
            ${_dd.key_content ? `<div style="color:#6a1b9a; margin-top:1px;">key: ${esc(_dd.key_content)}</div>` : ''}
          </div>` : ''}
          <div style="margin-top:2px; color:#2a1f40;">${esc(dlg.content || '')}</div>
          ${genHtml}
        </div>`;
      }
      html += `</div>`;
    } else {
      html += sectionField('発話', 'content', lessonId, s.id, s.content);
    }
    html += sectionField('TTS', 'tts_text', lessonId, s.id, s.tts_text);
    html += sectionField('画面', 'display_text', lessonId, s.id, s.display_text);

    if (s.section_type === 'question') {
      html += sectionField('Q', 'question', lessonId, s.id, s.question);
      html += sectionField('A', 'answer', lessonId, s.id, s.answer);
      html += `<div style="display:flex; align-items:center; gap:6px; margin-top:4px;">
        <span style="font-size:0.7rem; color:#6a5590; min-width:36px;">待ち:</span>
        <input type="number" value="${s.wait_seconds}" min="0" max="60" style="width:50px; padding:2px 4px; background:#fff; color:#2a1f40; border:1px solid #d0c0e8; border-radius:3px; font-size:0.75rem;"
          onchange="updateSectionField(${lessonId}, ${s.id}, 'wait_seconds', parseInt(this.value))">
        <span style="font-size:0.7rem; color:#6a5590;">秒</span>
      </div>`;
    }

    // TTSキャッシュ — インライン再生ボタン
    if (cacheParts.length) {
      html += `<div style="margin-top:6px; padding:4px 8px; background:#e8f5e9; border-radius:4px; font-size:0.65rem; color:#2e7d32; display:flex; flex-wrap:wrap; gap:4px 10px; align-items:center;">`;
      for (const cp of cacheParts) {
        const sizeKB = (cp.size / 1024).toFixed(0);
        const url = '/' + cp.path;
        html += `<button onclick="playAudioInline(this, '${esc(url)}')" style="padding:1px 6px; background:#1565c0; color:#fff; border:none; border-radius:3px; cursor:pointer; font-size:0.6rem;">\u25B6 part${cp.part_index}</button><span style="color:#558b2f;">(${sizeKB}KB)</span>`;
      }
      html += `</div>`;
    }

    div.innerHTML = html;
    container.appendChild(div);
  }
}

function sectionField(label, field, lessonId, sectionId, value) {
  return `<div style="display:flex; gap:6px; margin-top:4px; align-items:flex-start;">
    <span style="font-size:0.7rem; color:#6a5590; min-width:36px; padding-top:4px;">${esc(label)}:</span>
    <textarea rows="2" style="flex:1; padding:4px 6px; background:#fff; color:#2a1f40; border:1px solid #d0c0e8; border-radius:3px; font-size:0.75rem; resize:vertical;"
      onchange="updateSectionField(${lessonId}, ${sectionId}, '${field}', this.value)">${esc(value || '')}</textarea>
  </div>`;
}

async function updateSectionField(lessonId, sectionId, field, value) {
  const body = {};
  body[field] = value;
  await api('PUT', '/api/lessons/' + lessonId + '/sections/' + sectionId, body);
}

async function deleteSection(lessonId, sectionId) {
  await api('DELETE', '/api/lessons/' + lessonId + '/sections/' + sectionId);
  _openLessonIds.add(lessonId);
  await loadLessons();
}

async function clearSectionCache(lessonId, orderIndex) {
  await api('DELETE', `/api/lessons/${lessonId}/tts-cache/${orderIndex}?generator=claude`);
  showToast('TTSキャッシュ削除', 'success');
  _openLessonIds.add(lessonId);
  await loadLessons();
}

async function moveSectionUp(lessonId, sectionId) {
  await _reorderSection(lessonId, sectionId, -1);
}

async function moveSectionDown(lessonId, sectionId) {
  await _reorderSection(lessonId, sectionId, 1);
}

async function _reorderSection(lessonId, sectionId, direction) {
  const res = await api('GET', '/api/lessons/' + lessonId);
  if (!res || !res.ok) return;
  const ids = res.sections.map(s => s.id);
  const idx = ids.indexOf(sectionId);
  if (idx < 0) return;
  const newIdx = idx + direction;
  if (newIdx < 0 || newIdx >= ids.length) return;
  [ids[idx], ids[newIdx]] = [ids[newIdx], ids[idx]];
  await api('PUT', '/api/lessons/' + lessonId + '/sections/reorder', { section_ids: ids });
  _openLessonIds.add(lessonId);
  await loadLessons();
}

// --- 授業制御 ---

async function startLesson(lessonId, lang, version) {
  lang = lang || _getLessonLang(lessonId);
  let url = `/api/lessons/${lessonId}/start?lang=${lang}&generator=claude`;
  if (version) url += `&version=${version}`;
  const res = await api('POST', url);
  if (res && res.ok) {
    showToast(lang === 'en' ? 'Lesson started' : '授業開始', 'success');
    await loadLessons();
  } else if (res && res.error) {
    showToast('Error: ' + res.error, 'error');
  } else {
    showToast('授業開始に失敗しました', 'error');
  }
}

async function pauseLesson() {
  const res = await api('POST', '/api/lessons/pause');
  if (res && res.ok) await loadLessons();
}

async function resumeLesson() {
  const res = await api('POST', '/api/lessons/resume');
  if (res && res.ok) await loadLessons();
}

async function stopLesson() {
  const res = await api('POST', '/api/lessons/stop');
  if (res && res.ok) {
    showToast('授業停止', 'success');
    await loadLessons();
  }
}

// --- インライン音声再生 ---

let _currentAudio = null;
let _currentPlayBtn = null;

function _stopCurrentAudio() {
  if (_currentAudio) {
    _currentAudio.pause();
    _currentAudio.currentTime = 0;
    _currentAudio = null;
  }
  if (_currentPlayBtn) {
    _currentPlayBtn.textContent = '\u25B6';
    _currentPlayBtn.style.background = '#1565c0';
    _currentPlayBtn = null;
  }
}

function playAudioInline(btn, url) {
  // 同じボタンを押したら停止
  if (_currentPlayBtn === btn && _currentAudio && !_currentAudio.paused) {
    _stopCurrentAudio();
    return;
  }
  _stopCurrentAudio();
  const audio = new Audio(url);
  _currentAudio = audio;
  _currentPlayBtn = btn;
  btn.textContent = '\u25A0';
  btn.style.background = '#c62828';
  audio.play();
  audio.onended = () => {
    btn.textContent = '\u25B6';
    btn.style.background = '#1565c0';
    _currentAudio = null;
    _currentPlayBtn = null;
  };
}

async function playSectionAudio(btn, orderIndex, lessonId, version) {
  // セクション全パートを連続再生
  _stopCurrentAudio();
  const lang = _getLessonLang(lessonId);
  let cacheUrl = `/api/lessons/${lessonId}/tts-cache?lang=${lang}&generator=claude`;
  if (version) cacheUrl += `&version=${version}`;
  const cacheRes = await api('GET', cacheUrl);
  if (!cacheRes || !cacheRes.ok) return;
  const section = (cacheRes.sections || []).find(s => s.order_index === orderIndex);
  if (!section || !section.parts || !section.parts.length) { showToast('TTSキャッシュなし', 'error'); return; }

  const urls = section.parts.map(p => '/' + p.path);
  if (!urls.length) { showToast('TTSファイルなし', 'error'); return; }

  const origText = btn.textContent;
  btn.textContent = '\u25A0';
  btn.style.background = '#c62828';
  _currentPlayBtn = btn;

  let idx = 0;
  function playNext() {
    if (idx >= urls.length) {
      btn.textContent = origText;
      btn.style.background = '#1565c0';
      _currentAudio = null;
      _currentPlayBtn = null;
      return;
    }
    const audio = new Audio(urls[idx++]);
    _currentAudio = audio;
    audio.onended = playNext;
    audio.play();
  }
  playNext();
}

// --- JSONインポート（Claude Code用） ---

async function importClaudeSections(lessonId, lang) {
  lang = lang || _getLessonLang(lessonId);
  const json = await showModal('Claude Codeが生成したセクションJSONを貼り付けてください', {
    title: '🧠 Claude Code セクションインポート',
    textarea: true,
    okLabel: 'インポート',
    placeholder: '[{"section_type": "introduction", "emotion": "joy", ...}]',
  });
  if (!json) return;

  let parsed;
  try {
    parsed = JSON.parse(json);
  } catch(e) {
    showToast('JSONパースエラー: ' + e.message, 'error');
    return;
  }

  // 配列またはオブジェクト（{sections: [...]}）を受け付ける
  let sections;
  let planSummary = null;
  if (Array.isArray(parsed)) {
    sections = parsed;
  } else if (parsed.sections && Array.isArray(parsed.sections)) {
    sections = parsed.sections;
    planSummary = parsed.plan_summary || null;
  } else {
    showToast('不正なフォーマット: 配列または {sections: [...]} が必要です', 'error');
    return;
  }

  const ok = await showConfirm(
    `${sections.length}セクションをインポートします。既存のClaude Codeセクション（${lang}）は上書きされます。`,
    { title: 'インポート確認' }
  );
  if (!ok) return;

  const body = { sections };
  if (planSummary) body.plan_summary = planSummary;
  const res = await api('POST', `/api/lessons/${lessonId}/import-sections?lang=${lang}&generator=claude`, body);
  if (res && res.ok) {
    showToast(`インポート完了: ${res.count}セクション`, 'success');
    _openLessonIds.add(lessonId);
    await loadLessons();
    if (res.tts_pregeneration_started && res.version_number) {
      startTtsPregenPolling(lessonId, lang, 'claude', res.version_number);
    }
  } else {
    showToast('インポート失敗: ' + (res && res.error ? res.error : '不明なエラー'), 'error');
  }
}

// --- インラインJSONインポート ---

function _buildImportArea(lessonId, lang, lessonName, sourceCount) {
  const cliCmd = `授業生成「#${lessonId} ${lessonName || ''} (${sourceCount || 0}ソース)」`;
  const stepStyle = 'display:flex; align-items:flex-start; gap:6px; margin-bottom:6px;';
  const numStyle = 'flex-shrink:0; width:20px; height:20px; background:#7b1fa2; color:#fff; border-radius:50%; font-size:0.7rem; font-weight:700; display:flex; align-items:center; justify-content:center;';
  const textStyle = 'font-size:0.8rem; color:#333; line-height:1.5;';
  return `<div style="margin-bottom:10px;">
      <div style="${stepStyle}">
        <span style="${numStyle}">1</span>
        <span style="${textStyle}">下のコマンドをコピー</span>
      </div>
      <div class="lesson-cli-command" style="margin-left:26px; margin-bottom:8px;">
        <code>${esc(cliCmd)}</code>
        <button onclick="_copyToClipboard('${esc(cliCmd.replace(/'/g, "\\'"))}', this)" style="padding:3px 10px; background:#6a1b9a; color:#fff; border:none; border-radius:3px; cursor:pointer; font-size:0.72rem; white-space:nowrap;">コピー</button>
      </div>
      <div style="${stepStyle}">
        <span style="${numStyle}">2</span>
        <span style="${textStyle}">Claude Codeに貼り付けて実行 → スクリプトが自動生成される</span>
      </div>
      <div style="${stepStyle}">
        <span style="${numStyle}">3</span>
        <span style="${textStyle}">生成されたJSONを下に貼り付けて「インポート」</span>
      </div>
    </div>
    <div class="lesson-import-area">
      <textarea rows="6" placeholder='Claude Codeが出力したJSONをここに貼り付け&#10;[{"section_type": "introduction", ...}]'></textarea>
      <div style="display:flex; align-items:center; gap:8px; margin-top:8px;">
        <button onclick="importClaudeSectionsInline(${lessonId}, '${lang}', this)" style="padding:6px 18px; background:#6a1b9a; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:0.85rem; font-weight:600;">インポート</button>
        <span class="import-inline-status" style="font-size:0.75rem; color:#8a7a9a;"></span>
      </div>
    </div>`;
}

function _copyToClipboard(text, btn) {
  navigator.clipboard.writeText(text).then(() => {
    const orig = btn.textContent;
    btn.textContent = '\u2713 Copied!';
    setTimeout(() => { btn.textContent = orig; }, 1500);
  });
}

async function importClaudeSectionsInline(lessonId, lang, btnEl) {
  const area = btnEl.closest('.lesson-import-area');
  const textarea = area.querySelector('textarea');
  const statusEl = area.querySelector('.import-inline-status');
  const json = (textarea.value || '').trim();

  if (!json) {
    showToast('JSONを貼り付けてください', 'error');
    return;
  }

  let parsed;
  try {
    parsed = JSON.parse(json);
  } catch(e) {
    showToast('JSONパースエラー: ' + e.message, 'error');
    return;
  }

  let sections;
  let planSummary = null;
  if (Array.isArray(parsed)) {
    sections = parsed;
  } else if (parsed.sections && Array.isArray(parsed.sections)) {
    sections = parsed.sections;
    planSummary = parsed.plan_summary || null;
  } else {
    showToast('不正なフォーマット: 配列または {sections: [...]} が必要です', 'error');
    return;
  }

  const ok = await showConfirm(
    `${sections.length}セクションをインポートします。既存のClaude Codeセクション（${lang}）は上書きされます。`,
    { title: 'インポート確認' }
  );
  if (!ok) return;

  if (statusEl) statusEl.innerHTML = '<span class="lesson-spinner">インポート中...</span>';

  const body = { sections };
  if (planSummary) body.plan_summary = planSummary;
  const res = await api('POST', `/api/lessons/${lessonId}/import-sections?lang=${lang}&generator=claude`, body);
  if (res && res.ok) {
    showToast(`インポート完了: ${res.count}セクション`, 'success');
    _openLessonIds.add(lessonId);
    await loadLessons();
    if (res.tts_pregeneration_started && res.version_number) {
      startTtsPregenPolling(lessonId, lang, 'claude', res.version_number);
    }
  } else {
    if (statusEl) statusEl.textContent = '';
    showToast('インポート失敗: ' + (res && res.error ? res.error : '不明なエラー'), 'error');
  }
}

// ステータスポーリング不要（loadLessonsで全更新）
let _lessonStatusTimer = null;
function startLessonStatusPolling() {}
function stopLessonStatusPolling() {
  if (_lessonStatusTimer) { clearInterval(_lessonStatusTimer); _lessonStatusTimer = null; }
}

// --- プロンプト管理UI ---

const PROMPT_FILE = 'lesson_generate.md';

async function _loadPromptContent(displayEl) {
  try {
    const res = await fetch('/api/prompts/' + PROMPT_FILE);
    if (!res.ok) { displayEl.textContent = 'プロンプト読み込みエラー'; return; }
    const md = await res.text();
    displayEl.innerHTML = simpleMarkdownToHtml(md);
  } catch(e) {
    displayEl.textContent = 'プロンプト読み込みエラー: ' + e.message;
  }
}

function _setupPromptUI(container) {
  const details = container.querySelector('details[class*="prompt-details"]');
  if (!details) return;

  const displayEl = container.querySelector('.prompt-display');
  const instructionInput = container.querySelector('.prompt-ai-instruction');
  const runBtn = container.querySelector('.prompt-ai-run-btn');
  const statusEl = container.querySelector('.prompt-ai-status');
  const diffArea = container.querySelector('.prompt-diff-area');
  const diffDisplay = container.querySelector('.prompt-diff-display');
  const applyBtn = container.querySelector('.prompt-apply-btn');
  const retryBtn = container.querySelector('.prompt-retry-btn');
  const cancelBtn = container.querySelector('.prompt-cancel-btn');

  let _modifiedContent = null;

  // 折りたたみ展開時にプロンプトを読み込む
  details.addEventListener('toggle', () => {
    if (details.open) _loadPromptContent(displayEl);
  });

  // AI編集 実行
  runBtn.addEventListener('click', async () => {
    const instruction = instructionInput.value.trim();
    if (!instruction) { showToast('編集指示を入力してください', 'error'); return; }

    statusEl.style.display = '';
    statusEl.innerHTML = '<span class="lesson-spinner">AI編集中...</span>';
    diffArea.style.display = 'none';
    _modifiedContent = null;

    try {
      const res = await api('POST', '/api/prompts/ai-edit', {
        name: PROMPT_FILE,
        instruction: instruction,
      });
      statusEl.style.display = 'none';
      if (res && res.ok) {
        _modifiedContent = res.modified;
        diffDisplay.innerHTML = res.diff_html;
        diffArea.style.display = '';
      } else {
        showToast('AI編集エラー: ' + (res && res.error ? res.error : '不明'), 'error');
      }
    } catch(e) {
      statusEl.style.display = 'none';
      showToast('AI編集エラー: ' + e.message, 'error');
    }
  });

  // 適用
  applyBtn.addEventListener('click', async () => {
    if (!_modifiedContent) return;
    try {
      const res = await fetch('/api/prompts/' + PROMPT_FILE, {
        method: 'PUT',
        headers: { 'Content-Type': 'text/plain' },
        body: _modifiedContent,
      });
      const data = await res.json();
      if (data.ok) {
        showToast('プロンプト更新完了', 'success');
        _loadPromptContent(displayEl);
        diffArea.style.display = 'none';
        _modifiedContent = null;
        instructionInput.value = '';
      } else {
        showToast('保存エラー: ' + (data.error || ''), 'error');
      }
    } catch(e) {
      showToast('保存エラー: ' + e.message, 'error');
    }
  });

  // やり直す
  retryBtn.addEventListener('click', () => {
    diffArea.style.display = 'none';
    _modifiedContent = null;
    instructionInput.focus();
  });

  // キャンセル
  cancelBtn.addEventListener('click', () => {
    diffArea.style.display = 'none';
    _modifiedContent = null;
    instructionInput.value = '';
  });
}

// =============================================================
// カテゴリ管理
// =============================================================

function _renderCategoryTabs(container) {
  const cats = _lessonCategories || [];
  const div = document.createElement('div');
  div.className = 'cat-tabs';

  let html = '';

  if (cats.length === 0) {
    // カテゴリなし — 目立つ追加ボタン
    html += `<span class="cat-tabs-empty">カテゴリがありません</span>`;
    html += `<button onclick="createCategory()" class="cat-tab cat-tab--add">+ カテゴリを追加</button>`;
  } else {
    // 「全て」タブ
    const allActive = _selectedCategory === null;
    html += `<button onclick="selectCategory(null)" class="cat-tab${allActive ? ' active' : ''}">全て</button>`;

    // 各カテゴリタブ
    for (const c of cats) {
      const isActive = _selectedCategory === c.slug;
      html += `<button onclick="selectCategory('${esc(c.slug)}')" class="cat-tab${isActive ? ' active' : ''}">${esc(c.name)}</button>`;
    }

    // 「+ 新規」ボタン
    html += `<button onclick="createCategory()" class="cat-tab cat-tab--add">+ 新規</button>`;

    // 「⚙ 管理」ボタン
    html += `<button onclick="openCategoryManager()" class="cat-tab cat-tab--manage">\u2699 管理</button>`;
  }

  div.innerHTML = html;
  container.appendChild(div);
}

function selectCategory(slug) {
  _selectedCategory = slug;
  loadLessons();
}

function openCategoryManager() {
  const cats = _lessonCategories || [];
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  const listHtml = cats.map(c =>
    `<div style="display:flex; align-items:center; gap:6px; padding:5px 8px; background:#f5f0ff; border:1px solid #e0d4f0; border-radius:4px;">
      <span style="font-size:0.8rem; font-weight:600; color:#2a1f40;">${esc(c.name)}</span>
      <span style="font-size:0.7rem; color:#8a7a9a;">(${esc(c.slug)})</span>
      ${c.description ? `<span style="font-size:0.7rem; color:#6a5590;" title="${esc(c.description)}">&#8505;</span>` : ''}
      <button onclick="deleteCategoryFromManager(${c.id})" style="padding:2px 6px; background:#c62828; color:#fff; border:none; border-radius:3px; cursor:pointer; font-size:0.65rem; margin-left:auto;">\u00D7</button>
    </div>`
  ).join('');
  overlay.innerHTML = `<div class="modal-box">
    <h3>カテゴリ管理</h3>
    <div style="display:flex; flex-direction:column; gap:6px; max-height:300px; overflow-y:auto;">
      ${listHtml || '<span style="font-size:0.8rem; color:#8a7a9a;">カテゴリなし</span>'}
    </div>
    <div class="btn-group" style="margin-top:12px;">
      <button class="primary" data-action="close">閉じる</button>
    </div>
  </div>`;
  overlay.addEventListener('click', e => {
    if (e.target.dataset?.action === 'close') overlay.remove();
  });
  document.body.appendChild(overlay);
}

async function deleteCategoryFromManager(categoryId) {
  const ok = await showConfirm('このカテゴリを削除しますか？', { danger: true, title: 'カテゴリ削除' });
  if (!ok) return;
  const res = await api('DELETE', '/api/lesson-categories/' + categoryId);
  if (res && res.ok) {
    _lessonCategories = null;
    showToast('カテゴリ削除', 'success');
    // モーダルを閉じて再読み込み
    document.querySelector('.modal-overlay')?.remove();
    await loadLessons();
  } else {
    showToast('カテゴリ削除失敗: ' + (res && res.error ? res.error : '不明なエラー'), 'error');
  }
}

function _nameToSlug(name) {
  return name.trim().toLowerCase()
    .replace(/[\s\u3000]+/g, '_')
    .replace(/[^a-z0-9_\u3040-\u309f\u30a0-\u30ff\u4e00-\u9faf]/g, '')
    .slice(0, 50) || 'category';
}

async function createCategory() {
  return new Promise(resolve => {
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.innerHTML = `<div class="modal-box">
      <h3>新規カテゴリ</h3>
      <div style="display:flex; flex-direction:column; gap:8px;">
        <input type="text" id="_cat_name" class="modal-input" placeholder="カテゴリ名">
      </div>
      <div class="btn-group" style="margin-top:12px;">
        <button class="primary" data-action="ok">作成</button>
        <button class="secondary" data-action="cancel">キャンセル</button>
      </div>
    </div>`;

    const nameEl = overlay.querySelector('#_cat_name');

    const doResolve = async (action) => {
      if (action === 'ok') {
        const name = nameEl.value.trim();
        const slug = _nameToSlug(name);
        if (!name) { nameEl.style.borderColor = '#c62828'; nameEl.focus(); return; }
        overlay.remove();
        try {
          const res = await api('POST', '/api/lesson-categories', { slug, name, description: '' });
          if (res && res.ok) {
            _lessonCategories = null;
            showToast('カテゴリ作成: ' + name, 'success');
            await loadLessons();
          } else {
            showToast('カテゴリ作成失敗: ' + (res && res.error ? res.error : '不明なエラー'), 'error');
          }
        } catch (e) {
          showToast('カテゴリ作成エラー: ' + e.message, 'error');
        }
      } else {
        overlay.remove();
      }
      resolve();
    };

    overlay.addEventListener('click', e => {
      const action = e.target.dataset?.action;
      if (action) doResolve(action);
    });
    nameEl.addEventListener('keydown', e => {
      if (e.key === 'Enter') doResolve('ok');
      if (e.key === 'Escape') doResolve('cancel');
    });

    document.body.appendChild(overlay);
    nameEl.focus();
  });
}

async function deleteCategory(categoryId) {
  const ok = await showConfirm('このカテゴリを削除しますか？', { danger: true, title: 'カテゴリ削除' });
  if (!ok) return;
  const res = await api('DELETE', '/api/lesson-categories/' + categoryId);
  if (res && res.ok) {
    _lessonCategories = null;
    showToast('カテゴリ削除', 'success');
    await loadLessons();
  } else {
    showToast('カテゴリ削除失敗: ' + (res && res.error ? res.error : '不明なエラー'), 'error');
  }
}

async function saveLessonCategory(lessonId, category) {
  await api('PUT', '/api/lessons/' + lessonId, { category });
  showToast('カテゴリ更新', 'success');
}

// =============================================================
// バージョンセレクタ
// =============================================================

function _buildVersionSelector(lessonId, lang, generator, versions, currentVersion, sections) {
  if (!versions || versions.length === 0) return '';

  const currentVer = versions.find(v => v.version_number === currentVersion);
  let btns = versions.map(v => {
    const sel = v.version_number === currentVersion;
    const hasImprove = v.improve_source_version ? '\u2605' : '';
    const bg = sel ? 'background:#7b1fa2; color:#fff;' : 'background:#faf7ff; color:#7b1fa2;';
    return `<button onclick="_switchLessonVersion(${lessonId}, '${lang}', ${v.version_number})" style="padding:3px 10px; border:1px solid #d0c0e8; border-radius:4px; cursor:pointer; font-size:0.75rem; font-weight:600; ${bg}">v${v.version_number}${hasImprove}</button>`;
  }).join('');

  let metaHtml = '';
  if (currentVer) {
    if (currentVer.note) {
      metaHtml += `<span style="font-size:0.7rem; color:#6a5590; margin-left:6px;">${esc(currentVer.note)}</span>`;
    }
    if (currentVer.improve_source_version) {
      metaHtml += `<span style="font-size:0.65rem; color:#1565c0; margin-left:6px;">v${currentVer.improve_source_version}から改善</span>`;
    }
    if (currentVer.improve_summary) {
      metaHtml += `<div style="font-size:0.65rem; color:#555; margin-top:2px;">${esc(currentVer.improve_summary)}</div>`;
    }
  }

  // 検証結果（既存）
  let verifyHtml = '';
  if (currentVer && currentVer.verify_json) {
    try {
      const vj = JSON.parse(currentVer.verify_json);
      verifyHtml = `<details style="margin-top:6px;"><summary style="cursor:pointer; font-size:0.7rem; color:#1565c0; font-weight:500;">前回の検証結果</summary>
        <div style="margin-top:4px;">${_buildVerifyResultsHtml(vj)}</div></details>`;
    } catch(e) {}
  }

  return `<div style="margin-bottom:10px; padding:8px 10px; background:#f5f0ff; border:1px solid #d0c0e8; border-radius:6px;">
    <div style="display:flex; align-items:center; gap:4px; flex-wrap:wrap;">
      <span style="font-size:0.75rem; font-weight:600; color:#2a1f40;">バージョン:</span>
      ${btns}
      ${metaHtml}
    </div>
    <div style="display:flex; gap:4px; margin-top:6px; flex-wrap:wrap;">
      <button onclick="_editVersionNote(${lessonId}, ${currentVersion}, '${lang}', '${generator}')" style="padding:2px 8px; background:#f5f0ff; color:#6a5590; border:1px solid #d0c0e8; border-radius:3px; cursor:pointer; font-size:0.68rem;">メモ編集</button>
      <button onclick="_copyVersion(${lessonId}, ${currentVersion}, '${lang}', '${generator}')" style="padding:2px 8px; background:#f5f0ff; color:#6a5590; border:1px solid #d0c0e8; border-radius:3px; cursor:pointer; font-size:0.68rem;">コピー</button>
      <button onclick="verifyVersion(${lessonId}, '${lang}', '${generator}', ${currentVersion})" style="padding:2px 8px; background:#1565c0; color:#fff; border:none; border-radius:3px; cursor:pointer; font-size:0.68rem;">検証</button>
      <button onclick="showImprovePanel(${lessonId}, '${lang}', '${generator}', ${currentVersion})" style="padding:2px 8px; background:#e65100; color:#fff; border:none; border-radius:3px; cursor:pointer; font-size:0.68rem;">改善</button>
      <button onclick="showVersionDiff(${lessonId}, '${lang}', '${generator}', ${currentVersion})" style="padding:2px 8px; background:#f5f0ff; color:#6a5590; border:1px solid #d0c0e8; border-radius:3px; cursor:pointer; font-size:0.68rem;">比較...</button>
      <button onclick="triggerTtsPregen(${lessonId}, '${lang}', '${generator}', ${currentVersion})" style="padding:2px 8px; background:#4a148c; color:#fff; border:none; border-radius:3px; cursor:pointer; font-size:0.68rem;">TTS一括生成</button>
      ${versions.length > 1 ? `<button onclick="_deleteVersion(${lessonId}, ${currentVersion}, '${lang}', '${generator}')" style="padding:2px 8px; background:#c62828; color:#fff; border:none; border-radius:3px; cursor:pointer; font-size:0.68rem;">削除</button>` : ''}
    </div>
    ${verifyHtml}
    <div class="tts-pregen-bar-${lessonId}-${currentVersion}" style="margin-top:6px;"></div>
    <div class="verify-results-${lessonId}-${currentVersion}"></div>
    <div class="improve-panel-${lessonId}-${currentVersion}" style="display:none;"></div>
    <div class="diff-panel-${lessonId}" style="display:none;"></div>
  </div>`;
}

async function _editVersionNote(lessonId, vn, lang, generator) {
  const note = await showModal('バージョンメモ', {
    title: `v${vn} メモ編集`, input: '', okLabel: '保存',
  });
  if (note === null) return;
  await api('PUT', `/api/lessons/${lessonId}/versions/${vn}?lang=${lang}&generator=${generator}`, { note });
  showToast('メモ更新', 'success');
  _openLessonIds.add(lessonId);
  await loadLessons();
}

async function _copyVersion(lessonId, vn, lang, generator) {
  const res = await api('POST', `/api/lessons/${lessonId}/versions`, { lang, generator, copy_from: vn });
  if (res && res.ok) {
    _lessonVersionTab[`${lessonId}_${lang}`] = res.version.version_number;
    showToast(`v${res.version.version_number} 作成（v${vn}からコピー）`, 'success');
    _openLessonIds.add(lessonId);
    await loadLessons();
  }
}

async function _deleteVersion(lessonId, vn, lang, generator) {
  const ok = await showConfirm(`v${vn} を削除しますか？`, { danger: true, title: 'バージョン削除' });
  if (!ok) return;
  await api('DELETE', `/api/lessons/${lessonId}/versions/${vn}?lang=${lang}&generator=${generator}`);
  delete _lessonVersionTab[`${lessonId}_${lang}`];
  showToast(`v${vn} 削除`, 'success');
  _openLessonIds.add(lessonId);
  await loadLessons();
}

// =============================================================
// セクション注釈UI
// =============================================================

function _buildAnnotationUI(lessonId, section) {
  const rating = section.annotation_rating || '';
  const comment = section.annotation_comment || '';
  const sid = section.id;

  const btnStyle = (r, color, label) => {
    const sel = rating === r;
    const bg = sel ? color : '#faf7ff';
    const fg = sel ? '#fff' : color;
    const bw = sel ? '2px' : '1px';
    return `<button onclick="setAnnotationRating(${lessonId}, ${sid}, '${r}')" style="padding:2px 8px; background:${bg}; color:${fg}; border:${bw} solid ${color}; border-radius:3px; cursor:pointer; font-size:0.7rem; font-weight:${sel ? '700' : '400'};">${label}</button>`;
  };

  return `<div style="display:flex; align-items:center; gap:4px; margin:4px 0; flex-wrap:wrap;">
    ${btnStyle('good', '#2e7d32', '\u25CE良い')}
    ${btnStyle('needs_improvement', '#e65100', '\u25B3要改善')}
    ${btnStyle('redo', '#c62828', '\u2715作り直し')}
    <input type="text" value="${esc(comment)}" placeholder="コメント..."
      onblur="saveAnnotationComment(${lessonId}, ${sid}, this.value)"
      style="flex:1; min-width:100px; padding:2px 6px; border:1px solid #d0c0e8; border-radius:3px; font-size:0.7rem; background:#fff; color:#2a1f40;">
  </div>`;
}

async function setAnnotationRating(lessonId, sectionId, rating) {
  await api('PUT', `/api/lessons/${lessonId}/sections/${sectionId}/annotation`, { rating });
  _openLessonIds.add(lessonId);
  await loadLessons();
}

async function saveAnnotationComment(lessonId, sectionId, comment) {
  await api('PUT', `/api/lessons/${lessonId}/sections/${sectionId}/annotation`, { comment });
}

// =============================================================
// 整合性チェック（検証）
// =============================================================

async function verifyVersion(lessonId, lang, generator, versionNumber) {
  const el = document.querySelector(`.verify-results-${lessonId}-${versionNumber}`);
  if (!el) return;
  el.innerHTML = '<span class="lesson-spinner">検証中...</span>';

  const res = await api('POST', `/api/lessons/${lessonId}/verify`, {
    lang, generator, version_number: versionNumber,
  });

  if (!res || !res.ok) {
    el.innerHTML = `<div style="color:#c62828; font-size:0.75rem;">検証エラー: ${esc(res && res.error ? res.error : '不明')}</div>`;
    return;
  }

  let html = _buildVerifyResultsHtml(res.verify_result);

  // プロンプト・出力表示（CLAUDE.md準拠）
  html += _buildLlmCallDisplay('検証', res.prompt, res.raw_output);

  el.innerHTML = `<details open style="margin-top:6px;">
    <summary style="cursor:pointer; font-size:0.75rem; font-weight:600; color:#1565c0;">検証結果</summary>
    <div style="margin-top:4px;">${html}</div>
  </details>`;
}

function _buildVerifyResultsHtml(result) {
  if (!result) return '<div style="font-size:0.7rem; color:#888;">結果なし</div>';
  let html = '';
  const coverage = result.coverage || [];
  const contradictions = result.contradictions || [];

  const counts = { covered: 0, weak: 0, missing: 0 };
  for (const c of coverage) counts[c.status] = (counts[c.status] || 0) + 1;

  html += `<div style="font-size:0.72rem; margin-bottom:4px;">
    <span style="color:#2e7d32;">カバー: ${counts.covered}</span> /
    <span style="color:#e65100;">弱い: ${counts.weak}</span> /
    <span style="color:#c62828;">抜け: ${counts.missing}</span> /
    <span style="color:#6a1b9a;">矛盾: ${contradictions.length}</span>
  </div>`;

  if (coverage.length) {
    html += '<div style="max-height:200px; overflow-y:auto;">';
    for (const c of coverage) {
      const colors = { covered: '#e8f5e9', weak: '#fff3e0', missing: '#fbe9e7' };
      const borders = { covered: '#a5d6a7', weak: '#ffcc80', missing: '#ef9a9a' };
      html += `<div style="padding:3px 6px; margin-bottom:2px; background:${colors[c.status] || '#f5f5f5'}; border-left:3px solid ${borders[c.status] || '#ccc'}; border-radius:2px; font-size:0.68rem;">
        <span style="font-weight:600;">[${c.status}]</span> ${esc(c.source_item || '')}
        ${c.detail ? `<div style="color:#555; margin-top:1px;">${esc(c.detail)}</div>` : ''}
      </div>`;
    }
    html += '</div>';
  }

  if (contradictions.length) {
    html += '<div style="margin-top:4px;">';
    for (const c of contradictions) {
      html += `<div style="padding:3px 6px; margin-bottom:2px; background:#fce4ec; border-left:3px solid #ef9a9a; border-radius:2px; font-size:0.68rem;">
        <span style="font-weight:600; color:#c62828;">矛盾</span> sec${c.section_index}: ${esc(c.issue || '')}
      </div>`;
    }
    html += '</div>';
  }

  return html;
}

// =============================================================
// 部分改善
// =============================================================

async function showImprovePanel(lessonId, lang, generator, currentVersion) {
  const el = document.querySelector(`.improve-panel-${lessonId}-${currentVersion}`);
  if (!el) return;
  if (el.style.display !== 'none') { el.style.display = 'none'; return; }

  // バージョン一覧とセクション取得
  const res = await api('GET', `/api/lessons/${lessonId}?version=${currentVersion}`);
  if (!res || !res.ok) return;
  const sections = (res.sections || []).filter(s => (s.lang || 'ja') === lang && (s.generator || 'claude') === generator);
  const versions = (res.versions || []).filter(v => v.lang === lang && v.generator === generator);

  let versionOptions = versions.map(v =>
    `<option value="${v.version_number}"${v.version_number === currentVersion ? ' selected' : ''}>v${v.version_number}${v.note ? ' - ' + v.note : ''}</option>`
  ).join('');

  let sectionChecks = sections.map((s, i) => {
    const autoCheck = s.annotation_rating === 'needs_improvement' || s.annotation_rating === 'redo';
    const ratingLabel = s.annotation_rating ? ` [${s.annotation_rating === 'good' ? '\u25CE' : s.annotation_rating === 'needs_improvement' ? '\u25B3' : '\u2715'}]` : '';
    return `<label style="display:flex; align-items:center; gap:4px; font-size:0.72rem; padding:2px 0;">
      <input type="checkbox" class="improve-sec-check" value="${s.order_index}"${autoCheck ? ' checked' : ''}>
      ${i + 1}. ${esc(s.section_type)}${ratingLabel}
      ${s.annotation_comment ? `<span style="color:#888; font-size:0.65rem;">${esc(s.annotation_comment.substring(0, 30))}</span>` : ''}
    </label>`;
  }).join('');

  el.innerHTML = `<div style="margin-top:8px; padding:8px; background:#fff3e0; border:1px solid #ffcc80; border-radius:4px;">
    <div style="font-weight:600; font-size:0.78rem; color:#e65100; margin-bottom:6px;">部分改善</div>
    <div style="display:flex; gap:8px; align-items:center; margin-bottom:6px;">
      <span style="font-size:0.72rem;">改善元:</span>
      <select class="improve-source-version" style="padding:2px 6px; border:1px solid #ffcc80; border-radius:3px; font-size:0.72rem;">${versionOptions}</select>
    </div>
    <div style="margin-bottom:6px;">
      <div style="font-size:0.72rem; font-weight:500; margin-bottom:3px;">対象セクション:</div>
      ${sectionChecks}
    </div>
    <textarea class="improve-instructions" rows="2" placeholder="追加の改善指示（任意）..." style="width:100%; padding:4px 6px; border:1px solid #ffcc80; border-radius:3px; font-size:0.72rem; margin-bottom:6px; box-sizing:border-box;"></textarea>
    <div style="display:flex; gap:6px;">
      <button onclick="executeImprove(${lessonId}, '${lang}', '${generator}', this)" style="padding:4px 12px; background:#e65100; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:0.75rem;">改善を実行</button>
      <button onclick="this.closest('.improve-panel-${lessonId}-${currentVersion}').style.display='none'" style="padding:4px 12px; background:#888; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:0.75rem;">キャンセル</button>
    </div>
    <div class="improve-status" style="margin-top:6px;"></div>
  </div>`;
  el.style.display = '';
}

async function executeImprove(lessonId, lang, generator, btn) {
  const panel = btn.closest('div[class*="improve-panel"]');
  const statusEl = panel.querySelector('.improve-status');
  const sourceVersion = parseInt(panel.querySelector('.improve-source-version').value);
  const checks = panel.querySelectorAll('.improve-sec-check:checked');
  const targetSections = Array.from(checks).map(c => parseInt(c.value));
  const instructions = panel.querySelector('.improve-instructions').value.trim();

  if (targetSections.length === 0) {
    showToast('改善対象セクションを選択してください', 'error');
    return;
  }

  statusEl.innerHTML = '<span class="lesson-spinner">改善中（数分かかります）...</span>';
  btn.disabled = true;

  const res = await api('POST', `/api/lessons/${lessonId}/improve`, {
    source_version: sourceVersion,
    lang, generator,
    target_sections: targetSections,
    user_instructions: instructions,
  });

  btn.disabled = false;

  if (res && res.ok) {
    // プロンプト・出力表示
    let resultHtml = `<div style="color:#2e7d32; font-weight:600; font-size:0.75rem; margin-bottom:4px;">改善完了 → v${res.version_number}</div>`;
    resultHtml += _buildLlmCallDisplay('改善', res.prompt, res.raw_output);
    statusEl.innerHTML = resultHtml;

    _lessonVersionTab[`${lessonId}_${lang}`] = res.version_number;
    showToast(`改善完了: v${res.version_number} 作成`, 'success');
    _openLessonIds.add(lessonId);
    setTimeout(() => {
      loadLessons().then(() => {
        if (res.tts_pregeneration_started && res.version_number) {
          startTtsPregenPolling(lessonId, lang, generator, res.version_number);
        }
      });
    }, 1500);
  } else {
    let errHtml = `<div style="color:#c62828; font-size:0.75rem;">改善エラー: ${esc(res && res.error ? res.error : '不明')}</div>`;
    if (res && res.prompt) errHtml += _buildLlmCallDisplay('改善', res.prompt, res.raw_output);
    statusEl.innerHTML = errHtml;
  }
}

// =============================================================
// バージョン差分比較
// =============================================================

async function showVersionDiff(lessonId, lang, generator, versionA) {
  const versionsRes = await api('GET', `/api/lessons/${lessonId}/versions?lang=${lang}&generator=${generator}`);
  if (!versionsRes || !versionsRes.ok || versionsRes.versions.length < 2) {
    showToast('比較するバージョンが2つ以上必要です', 'error');
    return;
  }
  const others = versionsRes.versions.filter(v => v.version_number !== versionA);
  const hint = others.map(v => `${v.version_number}`).join(', ');
  const input = await showModal(`比較先バージョン番号を入力 (${hint})`, {
    title: `v${versionA} と比較`,
    input: String(others[0].version_number),
    okLabel: '比較',
  });
  if (!input) return;
  const versionB = parseInt(input);
  if (!others.find(v => v.version_number === versionB)) {
    showToast('無効なバージョン番号です', 'error');
    return;
  }

  // 両バージョンのセクション取得
  const [resA, resB] = await Promise.all([
    api('GET', `/api/lessons/${lessonId}?version=${versionA}`),
    api('GET', `/api/lessons/${lessonId}?version=${versionB}`),
  ]);
  if (!resA || !resA.ok || !resB || !resB.ok) return;

  const secsA = (resA.sections || []).filter(s => (s.lang || 'ja') === lang && (s.generator || 'claude') === generator);
  const secsB = (resB.sections || []).filter(s => (s.lang || 'ja') === lang && (s.generator || 'claude') === generator);
  const verB = (resB.versions || []).find(v => v.version_number === versionB);
  const improvedIdxs = new Set();
  if (verB && verB.improved_sections) {
    try { JSON.parse(verB.improved_sections).forEach(idx => improvedIdxs.add(idx)); } catch(e) {}
  }

  // 差分表示
  const panel = document.querySelector(`.diff-panel-${lessonId}`);
  if (!panel) return;

  let html = `<div style="margin-top:8px; padding:8px; background:#e3f2fd; border:1px solid #90caf9; border-radius:4px;">
    <div style="font-weight:600; font-size:0.78rem; color:#1565c0; margin-bottom:6px;">v${versionA} \u2194 v${versionB} 差分</div>`;

  const maxLen = Math.max(secsA.length, secsB.length);
  for (let i = 0; i < maxLen; i++) {
    const a = secsA[i];
    const b = secsB[i];
    const aContent = a ? (a.content || '') : '';
    const bContent = b ? (b.content || '') : '';
    const changed = aContent !== bContent;
    const isImproved = improvedIdxs.has(i);
    const label = a ? `${i + 1}. ${a.section_type}` : `${i + 1}. (新規)`;
    const tag = isImproved ? ' <span style="color:#e65100; font-size:0.6rem;">[AI改善]</span>' : '';

    if (!changed) {
      html += `<details style="margin-bottom:3px;">
        <summary style="cursor:pointer; font-size:0.7rem; color:#888;">${esc(label)} — 変更なし</summary>
        <pre style="font-size:0.65rem; color:#888; max-height:80px; overflow-y:auto; white-space:pre-wrap; padding:4px;">${esc(aContent.substring(0, 200))}</pre>
      </details>`;
    } else {
      html += `<details open style="margin-bottom:4px;">
        <summary style="cursor:pointer; font-size:0.72rem; font-weight:600; color:#1565c0;">${esc(label)} — 変更あり${tag}</summary>
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:4px; margin-top:3px;">
          <div style="padding:4px; background:#fce4ec; border:1px solid #ef9a9a; border-radius:3px;">
            <div style="font-size:0.6rem; color:#c62828; font-weight:600;">v${versionA}</div>
            <pre style="font-size:0.65rem; white-space:pre-wrap; max-height:120px; overflow-y:auto;">${esc(aContent)}</pre>
          </div>
          <div style="padding:4px; background:#e8f5e9; border:1px solid #a5d6a7; border-radius:3px;">
            <div style="font-size:0.6rem; color:#2e7d32; font-weight:600;">v${versionB}</div>
            <pre style="font-size:0.65rem; white-space:pre-wrap; max-height:120px; overflow-y:auto;">${esc(bContent)}</pre>
          </div>
        </div>
      </details>`;
    }
  }

  html += `<button onclick="this.closest('.diff-panel-${lessonId}').style.display='none'" style="margin-top:6px; padding:3px 10px; background:#888; color:#fff; border:none; border-radius:3px; cursor:pointer; font-size:0.7rem;">閉じる</button>`;
  html += '</div>';
  panel.innerHTML = html;
  panel.style.display = '';
}

// =============================================================
// LLM呼び出し表示（共通ヘルパー）
// =============================================================

function _buildLlmCallDisplay(label, prompt, rawOutput) {
  if (!prompt && !rawOutput) return '';
  let html = `<details style="margin-top:4px;">
    <summary style="cursor:pointer; font-size:0.65rem; color:#6a1b9a;">\u{1F50D} ${esc(label)} プロンプト・出力</summary>
    <div style="padding:4px 8px; background:#f3e5f5; border:1px solid #ce93d8; border-radius:4px; margin-top:2px;">`;
  if (prompt) {
    html += `<details style="margin-bottom:4px;">
      <summary style="cursor:pointer; color:#888; font-size:0.62rem;">\u{1F4AC} プロンプト</summary>
      <pre style="font-size:0.6rem; max-height:300px; overflow-y:auto; white-space:pre-wrap; word-break:break-all; margin:2px 0; padding:4px; background:#fafafa; border-radius:3px;">${esc(typeof prompt === 'string' ? prompt : JSON.stringify(prompt, null, 2))}</pre>
    </details>`;
  }
  if (rawOutput) {
    html += `<details>
      <summary style="cursor:pointer; color:#888; font-size:0.62rem;">\u{1F4DD} Raw Output</summary>
      <pre style="font-size:0.6rem; max-height:300px; overflow-y:auto; white-space:pre-wrap; word-break:break-all; margin:2px 0; padding:4px; background:#fafafa; border-radius:3px;">${esc(rawOutput)}</pre>
    </details>`;
  }
  html += '</div></details>';
  return html;
}

// =============================================================
// 学習ダッシュボード（教師モード内に統合）
// =============================================================

function _renderLearningSection(container) {
  const section = document.createElement('div');
  section.id = 'learning-section';
  section.innerHTML = `
    <div class="learning-header">
      <h3>学習ダッシュボード</h3>
      <button onclick="loadLearningsDashboard()">読み込み</button>
    </div>
    <div id="learnings-dashboard"></div>`;
  container.appendChild(section);
}

async function loadLearningsDashboard() {
  const container = document.getElementById('learnings-dashboard');
  if (!container) return;
  container.innerHTML = '<span class="lesson-spinner">読み込み中...</span>';

  const [statsRes, catsRes] = await Promise.all([
    api('GET', '/api/lessons/learnings'),
    api('GET', '/api/lesson-categories'),
  ]);

  if (!statsRes || !statsRes.ok) {
    container.innerHTML = '<div style="color:#888; font-size:0.8rem;">学習データの読み込みに失敗しました</div>';
    return;
  }

  const stats = statsRes.stats || [];
  const categories = (catsRes && catsRes.ok) ? catsRes.categories : [];
  const catMap = {};
  for (const c of categories) catMap[c.slug] = c;

  // 選択カテゴリでフィルタ
  const filtered = _selectedCategory === null
    ? stats
    : stats.filter(st => st.category === _selectedCategory);

  let html = '';

  if (filtered.length === 0) {
    html = '<div style="color:#8a7a9a; font-size:0.8rem;">該当する学習データがありません</div>';
  }

  for (const st of filtered) {
    const cat = catMap[st.category] || {};
    const ac = st.annotation_counts || {};
    const good = ac.good || 0;
    const ni = ac.needs_improvement || 0;
    const redo = ac.redo || 0;
    const total = good + ni + redo;
    const lessonCount = st.lesson_count || 0;
    const lastAnalysis = st.latest_learning ? st.latest_learning.created_at : 'なし';

    const catName = st.category_name || st.category || '未分類';
    const promptFile = cat.prompt_file || '';

    html += `<div class="learning-card">
      <div class="learning-card-head">
        <span class="learning-card-name">${esc(catName)}</span>
        <span class="learning-card-meta">${lessonCount}授業 / 注釈${total}件</span>
      </div>
      <div class="learning-card-stats">
        <span class="good">\u25CE ${good}</span> /
        <span class="warn">\u25B3 ${ni}</span> /
        <span class="bad">\u2715 ${redo}</span>
        <span class="last">最終分析: ${esc(lastAnalysis)}</span>
      </div>
      <div class="learning-card-actions">
        <button onclick="executeLearningAnalysis('${esc(st.category)}')" class="learning-btn learning-btn--analyze">分析を実行</button>
        <button onclick="executePromptImprove('${esc(st.category)}')" class="learning-btn learning-btn--improve">プロンプトを改善</button>
        ${st.category && !promptFile ? `<button onclick="createCategoryPrompt('${esc(st.category)}')" class="learning-btn learning-btn--create">専用プロンプト作成</button>` : ''}
        ${promptFile ? `<span class="learning-prompt-badge">${esc(promptFile)}</span>` : ''}
      </div>`;

    // 学習結果表示
    if (st.learnings_md) {
      html += `<details class="learning-detail" style="margin-top:6px;">
        <summary>学習結果</summary>
        <div class="learning-detail-body">
          ${simpleMarkdownToHtml(st.learnings_md)}
        </div>
      </details>`;
    }

    html += `<div class="learning-status-${st.category}" style="margin-top:4px;"></div>`;
    html += '</div>';
  }

  container.innerHTML = html;
}

async function executeLearningAnalysis(category) {
  const statusEl = document.querySelector(`.learning-status-${category || ''}`);
  if (statusEl) statusEl.innerHTML = '<span class="lesson-spinner">分析中（数分かかります）...</span>';

  const res = await api('POST', '/api/lessons/analyze-learnings', { category });

  if (res && res.ok) {
    let html = `<div style="color:#2e7d32; font-weight:600; font-size:0.75rem;">分析完了</div>`;
    html += _buildLlmCallDisplay('学習分析', res.prompt, res.raw_output);
    if (statusEl) statusEl.innerHTML = html;
    showToast('学習分析完了', 'success');
    setTimeout(() => loadLearningsDashboard(), 2000);
  } else {
    let errHtml = `<div style="color:#c62828; font-size:0.75rem;">分析エラー: ${esc(res && res.error ? res.error : '不明')}</div>`;
    if (res && res.prompt) errHtml += _buildLlmCallDisplay('学習分析', res.prompt, res.raw_output);
    if (statusEl) statusEl.innerHTML = errHtml;
  }
}

async function executePromptImprove(category) {
  const statusEl = document.querySelector(`.learning-status-${category || ''}`);
  if (statusEl) statusEl.innerHTML = '<span class="lesson-spinner">プロンプト改善案を生成中...</span>';

  const res = await api('POST', '/api/lessons/improve-prompt', { category });

  if (!res || !res.ok) {
    let errHtml = `<div style="color:#c62828; font-size:0.75rem;">エラー: ${esc(res && res.error ? res.error : '不明')}</div>`;
    if (res && res.prompt) errHtml += _buildLlmCallDisplay('プロンプト改善', res.prompt, res.raw_output);
    if (statusEl) statusEl.innerHTML = errHtml;
    return;
  }

  // diff表示 + 適用/却下ボタン
  const diffInstructions = res.diff_instructions || [];
  const promptFile = res.prompt_file || '';
  let html = `<div style="padding:8px; background:#fff; border:1px solid #ce93d8; border-radius:4px; margin-top:4px;">
    <div style="font-weight:600; font-size:0.75rem; color:#6a1b9a; margin-bottom:4px;">プロンプト改善提案 (${esc(promptFile)})</div>`;

  if (res.summary) {
    html += `<div style="font-size:0.72rem; color:#333; margin-bottom:6px;">${esc(res.summary)}</div>`;
  }

  for (const di of diffInstructions) {
    const actionColor = di.action === 'add' ? '#2e7d32' : di.action === 'replace' ? '#e65100' : '#c62828';
    html += `<div style="padding:4px 6px; margin-bottom:3px; background:#f5f0ff; border-left:3px solid ${actionColor}; border-radius:2px; font-size:0.68rem;">
      <span style="font-weight:600; color:${actionColor};">[${esc(di.action)}]</span>
      ${di.location ? `<span style="color:#888;"> at: ${esc(di.location)}</span>` : ''}
      ${di.find ? `<div style="color:#c62828; margin-top:2px;">- ${esc(di.find)}</div>` : ''}
      ${di.content ? `<div style="color:#2e7d32; margin-top:1px;">+ ${esc(di.content)}</div>` : ''}
    </div>`;
  }

  html += _buildLlmCallDisplay('プロンプト改善', res.prompt, res.raw_output);

  html += `<div style="display:flex; gap:6px; margin-top:6px;">
    <button onclick="applyPromptDiff('${esc(promptFile)}', this)" style="padding:4px 12px; background:#2e7d32; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:0.72rem;">適用</button>
    <button onclick="this.closest('.learning-status-${category || ''}').innerHTML=''" style="padding:4px 12px; background:#888; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:0.72rem;">却下</button>
  </div>`;
  html += '</div>';

  if (statusEl) {
    statusEl.innerHTML = html;
    // diffInstructionsをdata属性に保持
    statusEl._diffInstructions = diffInstructions;
  }
}

async function applyPromptDiff(promptFile, btn) {
  const statusEl = btn.closest('div[class*="learning-status"]');
  const diffInstructions = statusEl ? statusEl._diffInstructions : null;
  if (!diffInstructions) { showToast('diff指示がありません', 'error'); return; }

  const res = await api('POST', '/api/lessons/apply-prompt-diff', {
    prompt_file: promptFile,
    diff_instructions: diffInstructions,
  });

  if (res && res.ok) {
    showToast('プロンプト更新完了', 'success');
    if (statusEl) statusEl.innerHTML = '<div style="color:#2e7d32; font-size:0.75rem;">適用完了</div>';
  } else {
    showToast('適用エラー: ' + (res && res.error ? res.error : '不明'), 'error');
  }
}

async function createCategoryPrompt(slug) {
  const ok = await showConfirm(`カテゴリ「${slug}」の専用プロンプトを作成しますか？`, { title: '専用プロンプト作成' });
  if (!ok) return;

  showToast('専用プロンプト生成中...', 'info');
  const res = await api('POST', `/api/lesson-categories/${slug}/create-prompt`);
  if (res && res.ok) {
    _lessonCategories = null;
    showToast('専用プロンプト作成完了: ' + (res.prompt_file || ''), 'success');
    await loadLearningsDashboard();
  } else {
    showToast('作成エラー: ' + (res && res.error ? res.error : '不明'), 'error');
  }
}

// =============================================================
// TTS事前生成 進捗ポーリング・UI
// =============================================================

function _ttsPregenTimerKey(lessonId, lang, generator, version) {
  return `${lessonId}_${lang}_${generator}_${version}`;
}

function startTtsPregenPolling(lessonId, lang, generator, version) {
  const key = _ttsPregenTimerKey(lessonId, lang, generator, version);
  // 既にポーリング中なら重複起動しない
  if (_ttsPregenTimers[key]) return;

  // 即座に1回更新
  _updateTtsPregenUI(lessonId, lang, generator, version);

  _ttsPregenTimers[key] = setInterval(async () => {
    const done = await _updateTtsPregenUI(lessonId, lang, generator, version);
    if (done) stopTtsPregenPolling(lessonId, lang, generator, version);
  }, 3000);
}

function stopTtsPregenPolling(lessonId, lang, generator, version) {
  const key = _ttsPregenTimerKey(lessonId, lang, generator, version);
  if (_ttsPregenTimers[key]) {
    clearInterval(_ttsPregenTimers[key]);
    delete _ttsPregenTimers[key];
  }
}

async function _updateTtsPregenUI(lessonId, lang, generator, version) {
  const res = await api('GET', `/api/lessons/${lessonId}/tts-pregen-status?lang=${lang}&generator=${generator}&version=${version}`);
  if (!res || !res.ok) return true;

  const el = document.querySelector(`.tts-pregen-bar-${lessonId}-${version}`);
  if (!el) return true;

  const state = res.state;
  const total = res.total || 0;
  const completed = res.completed || 0;
  const generated = res.generated || 0;
  const cached = res.cached || 0;
  const failed = res.failed || 0;
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0;

  if (state === 'idle') {
    el.innerHTML = '';
    return true;
  }

  if (state === 'running') {
    el.innerHTML = `
      <div style="display:flex; align-items:center; gap:8px; padding:6px 10px; background:#f3e5f5; border:1px solid #ce93d8; border-radius:4px; margin-bottom:6px;">
        <span class="lesson-spinner" style="font-size:0.7rem;">TTS生成中</span>
        <div style="flex:1; background:#e1bee7; border-radius:3px; height:8px; overflow:hidden;">
          <div style="width:${pct}%; height:100%; background:#7b1fa2; transition:width 0.3s;"></div>
        </div>
        <span style="font-size:0.7rem; color:#4a148c; font-weight:600; white-space:nowrap;">${completed}/${total}</span>
        <span style="font-size:0.65rem; color:#6a1b9a;">(生成:${generated} キャッシュ:${cached}${failed ? ' 失敗:' + failed : ''})</span>
        <button onclick="cancelTtsPregen(${lessonId}, '${lang}', '${generator}', ${version})" style="padding:2px 8px; background:#c62828; color:#fff; border:none; border-radius:3px; cursor:pointer; font-size:0.65rem;">中止</button>
      </div>`;
    return false;
  }

  if (state === 'completed') {
    el.innerHTML = `
      <div style="display:flex; align-items:center; gap:8px; padding:6px 10px; background:#e8f5e9; border:1px solid #a5d6a7; border-radius:4px; margin-bottom:6px;">
        <span style="font-size:0.7rem; color:#2e7d32; font-weight:600;">TTS生成完了</span>
        <span style="font-size:0.65rem; color:#388e3c;">(生成:${generated} キャッシュ:${cached}${failed ? ' 失敗:' + failed : ''})</span>
      </div>`;
    // 5秒後にフェードアウト
    setTimeout(() => { if (el) el.innerHTML = ''; }, 5000);
    // TTSキャッシュ表示を更新するためloadLessonsを呼ぶ
    _openLessonIds.add(lessonId);
    setTimeout(() => loadLessons(), 1000);
    return true;
  }

  if (state === 'error') {
    el.innerHTML = `
      <div style="display:flex; align-items:center; gap:8px; padding:6px 10px; background:#ffebee; border:1px solid #ef9a9a; border-radius:4px; margin-bottom:6px;">
        <span style="font-size:0.7rem; color:#c62828; font-weight:600;">TTS生成エラー</span>
        <span style="font-size:0.65rem; color:#d32f2f;">${esc(res.error || '不明')}</span>
      </div>`;
    return true;
  }

  return true;
}

async function triggerTtsPregen(lessonId, lang, generator, version) {
  const res = await api('POST', `/api/lessons/${lessonId}/tts-pregen?lang=${lang}&generator=${generator}&version=${version}`);
  if (res && res.ok) {
    showToast('TTS一括生成を開始', 'success');
    startTtsPregenPolling(lessonId, lang, generator, version);
  } else {
    showToast('TTS生成開始エラー: ' + (res && res.error ? res.error : '不明'), 'error');
  }
}

async function cancelTtsPregen(lessonId, lang, generator, version) {
  const res = await api('POST', `/api/lessons/${lessonId}/tts-pregen-cancel?lang=${lang}&generator=${generator}&version=${version}`);
  if (res && res.ok) {
    showToast('TTS生成を中止しました', 'info');
    stopTtsPregenPolling(lessonId, lang, generator, version);
    const el = document.querySelector(`.tts-pregen-bar-${lessonId}-${version}`);
    if (el) el.innerHTML = '';
  }
}
