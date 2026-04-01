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
  // ステータスを1回だけ取得
  const statusRes = await api('GET', '/api/lessons/status');
  _cachedLessonStatus = statusRes;
  const list = document.getElementById('lesson-list');
  list.innerHTML = '';
  // 間のスケールスライダー
  await _renderPaceScaleSlider(list);
  for (const l of res.lessons) {
    const item = await buildLessonItem(l.id);
    if (item) list.appendChild(item);
  }
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
  const res = await api('GET', '/api/lessons/' + lessonId);
  if (!res || !res.ok) return null;

  const lesson = res.lesson;
  const sources = res.sources;
  const allSections = res.sections;
  const sectionsByGenerator = res.sections_by_generator || {};
  const plans = res.plans || {};
  const lang = _getLessonLang(lessonId);
  const generator = 'claude';
  const sections = allSections.filter(s => (s.lang || 'ja') === lang && (s.generator || 'claude') === generator);
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

  // スコアバッジ
  let scoreBadge = '';
  if (lesson.analysis_json) {
    try {
      const a = JSON.parse(lesson.analysis_json);
      const rc = (RANK_COLORS[a.rank] || '#888');
      const score = Math.round(a.total_score);
      scoreBadge = `<span style="font-size:0.85rem; font-weight:700; color:#fff; background:${rc}; border-radius:4px; padding:1px 7px; letter-spacing:0.5px;">${a.rank} ${score}点</span>`;
    } catch (_) {}
  }

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
    + scoreBadge
    + `<span style="font-size:0.7rem; color:#8a7a9a;">${esc(badgeText)}</span>`;
  details.appendChild(summary);

  // body
  const body = document.createElement('div');
  body.style.marginTop = '12px';

  // コンテンツ名編集
  body.innerHTML = `<div style="display:flex; align-items:center; gap:8px; margin-bottom:14px;">
    <span style="font-weight:600; font-size:0.85rem; color:#2a1f40;">コンテンツ名:</span>
    <input type="text" class="lesson-name-input" value="${esc(lesson.name)}" style="flex:1; padding:4px 8px; background:#faf7ff; color:#2a1f40; border:1px solid #d0c0e8; border-radius:4px;">
    <button onclick="saveLessonName(${lessonId}, this)" style="padding:4px 12px; background:#7b1fa2; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:0.8rem;">保存</button>
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
    step1Html += `<div style="margin-top:8px; color:#7b1fa2; font-size:0.78rem;">画像またはURLを追加してください</div>`;
  } else if (hasImageSources) {
    step1Html += `<div style="margin-top:10px; display:flex; align-items:center; gap:8px;">
      <button onclick="extractLessonText(${lessonId})" class="btn-extract" style="padding:5px 14px; background:#1565c0; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:0.8rem;">${hasExtractedText ? 'テキスト再抽出' : 'テキスト抽出'}</button>
      <span class="extract-status"></span>`;
    if (!hasExtractedText) {
      step1Html += `<span style="color:#1565c0; font-size:0.78rem;">画像からテキストを読み取ります</span>`;
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


  // === STEP 2: スクリプト（Claude Code） ===
  // キャラ設定取得
  const charsRes = await api('GET', '/api/characters');
  const charList = Array.isArray(charsRes) ? charsRes : [];
  const teacherChar = charList.find(c => c.role === 'teacher');
  const studentChar = charList.find(c => c.role === 'student');

  const step2b = document.createElement('div');
  step2b.className = 'lesson-step' + (hasSections ? ' step-done' : hasSources ? ' step-active' : ' step-disabled');
  const step2bBody = document.createElement('div');
  step2bBody.className = 'lesson-step-body';

  let totalDlgs = 0;
  for (const s of sections) {
    try { totalDlgs += JSON.parse(s.dialogues || '[]').length; } catch(e) {}
  }

  let step2bHtml = '';
  step2bHtml += `<div style="margin-bottom:4px; padding:4px 8px; background:#f3e5f5; border-radius:4px; font-size:0.72rem; font-weight:600; color:#6a1b9a;">🧠 Claude Code: ${lang === 'en' ? 'Imported Sections' : 'インポートセクション'}</div>`;
  step2bHtml += `<div class="lesson-step-title">🧠 Claude Code ${lang === 'en' ? 'Script' : 'スクリプト'}${hasSections ? ' (' + sections.length + (lang === 'en' ? ' sections' : 'セクション') + ', ' + totalDlgs + (lang === 'en' ? ' utterances' : '発話') + ')' : ''}</div>`;

  // Claude Code: JSONインポート + ガイド + プロンプト管理
  step2bHtml += `<div style="display:flex; align-items:center; gap:8px; margin-bottom:6px;">
      <button onclick="importClaudeSections(${lessonId}, '${lang}')" style="padding:5px 14px; background:#6a1b9a; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:0.8rem;">📋 JSONインポート</button>
      <span class="import-status" style="font-size:0.75rem; color:#8a7a9a;"></span>
    </div>
    <details style="margin-bottom:8px;" open>
      <summary style="cursor:pointer; font-weight:600; font-size:0.82rem; color:#6a1b9a; padding:6px 0;">📖 授業生成ガイド</summary>
      <div style="padding:10px 12px; background:#f3e5f5; border:1px solid #ce93d8; border-radius:4px; font-size:0.78rem; color:#333; margin-top:4px; line-height:1.6;">
        <div style="font-weight:600; color:#6a1b9a; margin-bottom:6px;">Claude Code CLIで授業スクリプトを生成する手順:</div>
        <div style="margin-bottom:8px;">
          <div style="font-weight:600; color:#4a148c;">Step 1: Claude Codeに指示を出す</div>
          <div style="margin-left:8px; margin-top:2px;">
            Claude Code CLIを開き、以下のように指示します:<br>
            <code style="display:block; margin:4px 0; padding:6px 8px; background:#fff; border:1px solid #d0c0e8; border-radius:3px; font-size:0.75rem; white-space:pre-wrap;">授業ID ${lessonId} の教材画像を読み取って、prompts/lesson_generate.md に従って授業スクリプトを生成して</code>
            Claude Codeが自動的に以下を行います:<br>
            ・教材画像の読み取り（<code>resources/images/lessons/${lessonId}/</code>）<br>
            ・キャラクター設定の取得（API経由）<br>
            ・授業プランの設計<br>
            ・セクションJSON の生成
          </div>
        </div>
        <div style="margin-bottom:8px;">
          <div style="font-weight:600; color:#4a148c;">Step 2: 生成されたJSONをインポート</div>
          <div style="margin-left:8px; margin-top:2px;">
            Claude Codeが出力したJSONをコピーして、上の「📋 JSONインポート」ボタンを押し、貼り付けます。<br>
            または、Claude Codeに直接APIを叩かせることもできます:<br>
            <code style="display:block; margin:4px 0; padding:6px 8px; background:#fff; border:1px solid #d0c0e8; border-radius:3px; font-size:0.75rem; white-space:pre-wrap;">生成したJSONを POST /api/lessons/${lessonId}/import-sections?lang=${lang}&generator=claude でインポートして</code>
          </div>
        </div>
        <div>
          <div style="font-weight:600; color:#4a148c;">Step 3: TTS生成 → 授業再生</div>
          <div style="margin-left:8px; margin-top:2px;">
            インポート後、下のセクション一覧から「TTS生成」→「授業開始」で再生できます。
          </div>
        </div>
      </div>
    </details>
    <details style="margin-bottom:8px;" class="prompt-details-${lessonId}-${lang}">
      <summary style="cursor:pointer; font-weight:600; font-size:0.75rem; color:#6a1b9a; padding:4px 0;">📝 生成プロンプト</summary>
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
  step2bBody.innerHTML = step2bHtml;

  // プロンプト表示・AI編集のイベント設定
  _setupPromptUI(step2bBody);

  // TTSキャッシュ情報取得
  let ttsCacheMap = {};
  if (hasSections) {
    const cacheRes = await api('GET', '/api/lessons/' + lessonId + '/tts-cache?lang=' + lang + '&generator=' + generator);
    if (cacheRes && cacheRes.ok) {
      for (const c of cacheRes.sections) {
        ttsCacheMap[c.order_index] = c.parts;
      }
    }
  }

  // セクション一覧
  const secContainer = document.createElement('div');
  renderSectionsInto(secContainer, sections, lessonId, ttsCacheMap, {teacher: teacherChar, student: studentChar}, plans[lang]);
  step2bBody.appendChild(secContainer);

  step2b.innerHTML = '<div class="lesson-step-num">2</div>';
  step2b.appendChild(step2bBody);
  body.appendChild(step2b);

  // === 品質分析 ===
  if (hasSections) {
    const qaDiv = document.createElement('div');
    qaDiv.className = 'lesson-step step-active';
    qaDiv.innerHTML = `<div class="lesson-step-num" style="background:#1565c0;">QA</div>`;
    const qaBody = document.createElement('div');
    qaBody.className = 'lesson-step-body';
    qaBody.innerHTML = `<div class="lesson-step-title">品質分析</div>
      <div style="display:flex; gap:6px; align-items:center; flex-wrap:wrap; margin-bottom:8px;">
        <button onclick="analyzeLesson(${lessonId}, '${lang}')" style="padding:5px 14px; background:#1565c0; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:0.8rem;">アルゴリズム分析</button>
        <span class="qa-status" style="font-size:0.75rem; color:#8a7a9a;"></span>
      </div>
      <div class="qa-result" id="qa-result-${lessonId}"></div>`;
    qaDiv.appendChild(qaBody);
    body.appendChild(qaDiv);
    // DB保存済み分析結果があれば自動表示
    if (lesson.analysis_json) {
      try {
        const saved = JSON.parse(lesson.analysis_json);
        const el = qaBody.querySelector('.qa-result');
        if (el) _renderAnalysisResult(el, saved);
      } catch(e) {}
    }
  }

  // === STEP 3: 授業開始 ===
  const isRunning = runningThisLesson && lState === 'running';
  const isPaused = runningThisLesson && lState === 'paused';
  const isActive = isRunning || isPaused;
  const step3 = document.createElement('div');
  step3.className = 'lesson-step' + (isActive ? ' step-done' : hasSections ? ' step-active' : ' step-disabled');
  const step3Body = document.createElement('div');
  step3Body.className = 'lesson-step-body';
  const progressInfo = isActive ? `${statusRes.status.current_index + 1} / ${statusRes.status.total_sections} セクション` : '';
  step3Body.innerHTML = `<div class="lesson-step-title">授業${isActive ? '（実行中）' : ''}</div>
    <div style="display:flex; gap:6px; align-items:center; flex-wrap:wrap;">
      <button onclick="startLesson(${lessonId}, '${lang}')" class="btn-lesson-start" style="padding:5px 14px; background:#2e7d32; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:0.8rem;${isActive ? ' display:none;' : ''}">${lang === 'en' ? 'Start Lesson' : '授業開始'}</button>
      <button onclick="pauseLesson()" class="btn-lesson-pause" style="padding:5px 14px; background:#f57f17; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:0.8rem;${isRunning ? '' : ' display:none;'}">一時停止</button>
      <button onclick="resumeLesson()" class="btn-lesson-resume" style="padding:5px 14px; background:#2e7d32; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:0.8rem;${isPaused ? '' : ' display:none;'}">再開</button>
      <button onclick="stopLesson()" class="btn-lesson-stop" style="padding:5px 14px; background:#c62828; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:0.8rem;${isActive ? '' : ' display:none;'}">終了</button>
      <span class="lesson-state" style="font-size:0.8rem; color:#8a7a9a;">${isRunning ? '再生中' : isPaused ? '一時停止中' : ''}</span>
      <button onclick="window.open('/broadcast', '_blank', 'width=1920,height=1080')" style="padding:5px 14px; background:#6a1b9a; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:0.8rem;">配信プレビュー</button>
    </div>
    <div class="lesson-progress" style="margin-top:4px; font-size:0.75rem; color:#8a7a9a;">${progressInfo}</div>`;

  step3.innerHTML = '<div class="lesson-step-num">3</div>'; // Step 3: 授業開始
  step3.appendChild(step3Body);
  body.appendChild(step3);

  // 削除ボタン
  const delRow = document.createElement('div');
  delRow.style.cssText = 'display:flex; justify-content:flex-end; margin-top:12px; padding-top:10px; border-top:1px solid #ece4f5;';
  delRow.innerHTML = `<button onclick="deleteLesson(${lessonId})" style="padding:4px 12px; background:#c62828; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:0.8rem;">コンテンツ削除</button>`;
  body.appendChild(delRow);

  details.appendChild(body);
  return details;
}

async function createLesson() {
  const name = await showModal('コンテンツ名を入力してください', {
    title: '新規コンテンツ',
    input: '例: English 1-1',
    okLabel: '作成',
  });
  if (!name) return;
  const res = await api('POST', '/api/lessons', { name });
  if (res && res.ok) {
    _openLessonIds.add(res.lesson.id);
    showToast('コンテンツ作成: ' + name, 'success');
    await loadLessons();
  }
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
    _clearDownstreamSteps(lessonId, ['2', '3']);
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
      _clearDownstreamSteps(lessonId, ['2', '3']);
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
  _clearDownstreamSteps(lessonId, ['2', '3']);
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

function renderSectionsInto(container, sections, lessonId, ttsCacheMap, charInfo, langPlan) {
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
        ${hasCacheFlag ? `<button onclick="playSectionAudio(this, ${s.order_index}, ${lessonId})" style="width:26px; height:26px; background:#1565c0; color:#fff; border:none; border-radius:50%; cursor:pointer; font-size:0.75rem; line-height:26px; text-align:center;" title="セクション再生">\u25B6</button>` : ''}
      </div>
      <div style="display:flex; gap:4px;">
        <button onclick="moveSectionUp(${lessonId}, ${s.id})" style="width:24px; height:24px; background:#f0ecf5; color:#6a5590; border:1px solid #d0c0e8; border-radius:3px; cursor:pointer; font-size:0.7rem;" ${i === 0 ? 'disabled' : ''}>\u25B2</button>
        <button onclick="moveSectionDown(${lessonId}, ${s.id})" style="width:24px; height:24px; background:#f0ecf5; color:#6a5590; border:1px solid #d0c0e8; border-radius:3px; cursor:pointer; font-size:0.7rem;" ${i === sections.length - 1 ? 'disabled' : ''}>\u25BC</button>
        <button onclick="deleteSection(${lessonId}, ${s.id})" style="width:24px; height:24px; background:#c62828; color:#fff; border:none; border-radius:3px; cursor:pointer; font-size:0.7rem;">\u00D7</button>
      </div>
    </div>`;

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

// --- 品質分析 ---

const RANK_COLORS = { S: '#d4af37', A: '#2e7d32', B: '#1565c0', C: '#e65100', D: '#c62828' };

function _renderAnalysisResult(resultEl, a) {
  const rankColor = RANK_COLORS[a.rank] || '#888';

  let html = `<div style="display:flex; align-items:center; gap:12px; margin-bottom:10px; padding:8px 12px; background:#faf7ff; border:2px solid ${rankColor}; border-radius:8px;">
    <div style="font-size:2rem; font-weight:700; color:${rankColor};">${a.rank}</div>
    <div>
      <div style="font-size:1.1rem; font-weight:600;">${a.total_score} / ${a.max_score}</div>
      <div style="font-size:0.7rem; color:#8a7a9a;">総合スコア</div>
    </div>
  </div>`;

  // アルゴリズム指標
  html += `<div style="font-size:0.8rem; font-weight:600; margin-bottom:4px;">アルゴリズム指標</div>`;
  const algoLabels = {
    display_text_coverage: 'カバー率',
    dialogue_balance: '対話バランス',
    section_diversity: '構成多様性',
    question_richness: 'クイズ充実度',
    pacing: 'ペーシング',
  };
  for (const [key, sd] of Object.entries(a.algorithmic_scores)) {
    html += _renderScoreBar(algoLabels[key] || key, sd);
  }

  // 改善提案
  if (a.suggestions && a.suggestions.length > 0) {
    html += `<details style="margin-top:8px;"><summary style="cursor:pointer; font-size:0.75rem; color:#1565c0; font-weight:600;">改善提案（${a.suggestions.length}件）</summary>
      <ul style="font-size:0.72rem; margin:4px 0 0 16px; color:#2a1f40;">`;
    for (const s of a.suggestions) {
      html += `<li style="margin-bottom:2px;">${esc(s)}</li>`;
    }
    html += `</ul></details>`;
  }

  resultEl.innerHTML = html;
}

async function analyzeLesson(lessonId, lang) {
  const statusEl = document.querySelector(`#qa-result-${lessonId}`)?.closest('.lesson-step-body')?.querySelector('.qa-status');
  const resultEl = document.getElementById('qa-result-' + lessonId);
  if (!resultEl) return;
  if (statusEl) statusEl.textContent = '分析中...';
  resultEl.innerHTML = '';

  const res = await api('POST', '/api/lessons/' + lessonId + '/analyze?lang=' + lang);
  if (statusEl) statusEl.textContent = '';
  if (!res || !res.ok) {
    resultEl.innerHTML = `<div style="color:#c62828; font-size:0.8rem;">${res?.error || 'エラーが発生しました'}</div>`;
    return;
  }
  _renderAnalysisResult(resultEl, res.analysis);
}

function _renderScoreBar(label, sd) {
  const pct = sd.max_score > 0 ? Math.round(sd.score / sd.max_score * 100) : 0;
  const barColor = pct >= 80 ? '#2e7d32' : pct >= 60 ? '#1565c0' : pct >= 40 ? '#e65100' : '#c62828';
  let html = `<div style="margin-bottom:6px;">
    <div style="display:flex; justify-content:space-between; font-size:0.72rem; margin-bottom:1px;">
      <span>${esc(label)}</span>
      <span style="font-weight:600;">${sd.score} / ${sd.max_score}</span>
    </div>
    <div style="background:#e8e0f0; border-radius:3px; height:8px; overflow:hidden;">
      <div style="background:${barColor}; height:100%; width:${pct}%; border-radius:3px; transition:width 0.3s;"></div>
    </div>`;
  if (sd.details) {
    html += `<div style="font-size:0.65rem; color:#8a7a9a; margin-top:1px;">${esc(sd.details)}</div>`;
  }
  html += `</div>`;
  return html;
}

// --- 授業制御 ---

async function startLesson(lessonId, lang) {
  lang = lang || _getLessonLang(lessonId);
  const res = await api('POST', `/api/lessons/${lessonId}/start?lang=${lang}&generator=claude`);
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

async function playSectionAudio(btn, orderIndex, lessonId) {
  // セクション全パートを連続再生
  _stopCurrentAudio();
  const lang = _getLessonLang(lessonId);
  const cacheRes = await api('GET', `/api/lessons/${lessonId}/tts-cache?lang=${lang}&generator=claude`);
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
  } else {
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
