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
  const plans = res.plans || {};
  const lang = _getLessonLang(lessonId);
  const sections = allSections.filter(s => (s.lang || 'ja') === lang);
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

  step1Body.innerHTML = step1Html;
  step1.innerHTML = '<div class="lesson-step-num">1</div>';
  step1.appendChild(step1Body);
  body.appendChild(step1);

  // === 言語タブ ===
  const langTabsDiv = document.createElement('div');
  langTabsDiv.innerHTML = _buildLangTabs(lessonId, plans, allSections);
  body.appendChild(langTabsDiv);

  // === STEP 2a: プラン生成（三者視点） ===
  const langPlan = plans[lang] || {};
  const hasPlan = !!(langPlan.plan_json);
  const step2a = document.createElement('div');
  step2a.className = 'lesson-step' + (hasPlan ? ' step-done' : hasExtractedText ? ' step-active' : ' step-disabled');
  const step2aBody = document.createElement('div');
  step2aBody.className = 'lesson-step-body';
  const planLabel = lang === 'en' ? 'Plan Generation (3 experts)' : 'プラン生成（三者視点）';
  let planHtml = `<div class="lesson-step-title">${planLabel}${hasPlan ? ' ✓' : ''}</div>
    <div style="display:flex; align-items:center; gap:8px; margin-bottom:6px;">
      <button onclick="generatePlan(${lessonId}, '${lang}')" style="padding:5px 14px; background:#1565c0; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:0.8rem;">${hasPlan ? (lang === 'en' ? 'Regenerate' : 'プラン再生成') : (lang === 'en' ? 'Generate Plan' : 'プラン生成')}</button>
      <span class="plan-status"></span>
    </div>`;

  // 既存プランの表示（プロンプト+結果の可視化）
  if (hasPlan) {
    const etLen = (lesson.extracted_text || '').length;
    const imgCount = sources.filter(s => s.source_type === 'image').length;
    const _preStyle = 'margin-top:4px; background:#fafafa; padding:6px; border:1px solid #ddd; border-radius:4px; font-size:0.65rem; max-height:250px; overflow-y:auto; white-space:pre-wrap; word-break:break-word; color:#333;';
    const _outPreStyle = (bg, border, color) => `margin-top:4px; background:${bg}; padding:6px; border:1px solid ${border}; border-radius:4px; font-size:0.7rem; max-height:200px; overflow-y:auto; white-space:pre-wrap; word-break:break-word; color:${color};`;

    // 知識先生のユーザープロンプトを再構成（全文 — 切り詰めない）
    const knowledgeUserPrompt = lang === 'en'
      ? `# Lesson title: ${lesson.name || ''}\n\n# Source text:\n${lesson.extracted_text || ''}`
      : `# 授業タイトル: ${lesson.name || ''}\n\n# 教材テキスト:\n${lesson.extracted_text || ''}`;
    // エンタメ先生のユーザープロンプト（全文）
    const entertainmentUserPrompt = knowledgeUserPrompt + (lang === 'en'
      ? `\n\n---\n\n# Knowledge Expert's analysis:\n${langPlan.knowledge || ''}`
      : `\n\n---\n\n# 知識先生の分析:\n${langPlan.knowledge || ''}`);
    // 監督のユーザープロンプト（全文）
    const directorUserPrompt = lang === 'en'
      ? `# Knowledge Expert's analysis:\n${langPlan.knowledge || ''}\n\n---\n\n# Entertainment Expert's structure:\n${langPlan.entertainment || ''}`
      : `# 知識先生の分析:\n${langPlan.knowledge || ''}\n\n---\n\n# エンタメ先生の構成:\n${langPlan.entertainment || ''}`;

    // --- 2a-1: 知識先生 ---
    planHtml += `<div style="margin-top:8px; border:1px solid #bbdefb; border-radius:6px; overflow:hidden;">`;
    planHtml += `<div style="background:#e3f2fd; padding:6px 10px; font-size:0.78rem; font-weight:600; color:#1565c0;">\u{1F4DA} ${lang === 'en' ? 'Step 1: Knowledge Expert' : 'Step 1: 知識先生'} <span style="font-weight:400; font-size:0.68rem; color:#666;">temp=0.5</span></div>`;
    planHtml += `<div style="padding:8px 10px; font-size:0.72rem;">`;
    planHtml += `<div style="color:#666; margin-bottom:4px;">${lang === 'en' ? 'Input' : '入力'}: ${lang === 'en' ? 'extracted text' : '抽出テキスト'} (${etLen}${lang === 'en' ? ' chars' : '文字'})${imgCount ? ` + ${lang === 'en' ? 'images' : '画像'} (${imgCount})` : ''}</div>`;
    planHtml += `<details style="margin-bottom:4px;"><summary style="cursor:pointer; color:#888; font-size:0.68rem;">\u{1F4E4} ${lang === 'en' ? 'System Prompt' : 'システムプロンプト'}</summary>
      <pre style="${_preStyle}">${esc(lang === 'en'
        ? 'You are the "Knowledge Expert". As the subject lead, analyze the source material and organize the key concepts to teach.\n\n## Your role\n- Accurately grasp the core of the material and identify key points to teach\n- Design the optimal learning sequence (prerequisites → core → application)\n- Point out common misconceptions and tricky areas\n- Don\'t miss important facts, numbers, or concepts in the material\n\n## Output format\n### Key points to teach\n### Recommended learning sequence\n### Common misconceptions & pitfalls\n### Recommended section structure'
        : 'あなたは「知識先生」です。教科主任として、教材を分析し授業で教えるべき内容を整理してください。\n\n## あなたの役割\n- 教材の核心を正確に把握し、教えるべき要点を洗い出す\n- 学習者にとって最適な順序���前提知識→核心→応用）を設計する\n- よくある誤解や注意すべきポイントを指摘する\n- 教材に含まれる重要な事実・数値・概念を漏らさない\n\n## 出力形式\n### 教えるべ��要点\n### 推奨する学習順序\n### 注意すべき誤解・難所\n### 推奨セクション構成')}</pre></details>`;
    planHtml += `<details style="margin-bottom:4px;"><summary style="cursor:pointer; color:#888; font-size:0.68rem;">\u{1F4E5} ${lang === 'en' ? 'User Prompt' : 'ユーザープロンプト'}</summary>
      <pre style="${_preStyle}">${esc(knowledgeUserPrompt)}</pre></details>`;
    if (langPlan.knowledge) {
      planHtml += `<details open><summary style="cursor:pointer; color:#1565c0; font-size:0.72rem; font-weight:600;">\u{1F4E4} ${lang === 'en' ? 'Output' : '出力'} (${langPlan.knowledge.length}${lang === 'en' ? ' chars' : '文字'})</summary>
        <pre style="${_outPreStyle('#f0f4ff','#bbdefb','#1a237e')}">${esc(langPlan.knowledge)}</pre></details>`;
    }
    planHtml += `</div></div>`;

    // --- 矢印 ---
    planHtml += `<div style="text-align:center; color:#999; font-size:0.9rem; margin:2px 0;">\u25BC</div>`;

    // --- 2a-2: エンタメ先生 ---
    planHtml += `<div style="border:1px solid #ffe0b2; border-radius:6px; overflow:hidden;">`;
    planHtml += `<div style="background:#fff3e0; padding:6px 10px; font-size:0.78rem; font-weight:600; color:#e65100;">\u{1F3AD} ${lang === 'en' ? 'Step 2: Entertainment Expert' : 'Step 2: エンタメ先生'} <span style="font-weight:400; font-size:0.68rem; color:#666;">temp=0.8</span></div>`;
    planHtml += `<div style="padding:8px 10px; font-size:0.72rem;">`;
    planHtml += `<div style="color:#666; margin-bottom:4px;">${lang === 'en' ? 'Input' : '入力'}: ${lang === 'en' ? 'extracted text' : '抽出テキスト'} + <strong style="color:#1565c0;">${lang === 'en' ? 'Knowledge output' : '知識先生の出力'}</strong> \u2190 Step 1</div>`;
    planHtml += `<details style="margin-bottom:4px;"><summary style="cursor:pointer; color:#888; font-size:0.68rem;">\u{1F4E4} ${lang === 'en' ? 'System Prompt' : 'システムプロンプト'}</summary>
      <pre style="${_preStyle}">${esc(lang === 'en'
        ? 'You are the "Entertainment Expert". As a popular Twitch instructor who keeps viewers entertained, structure the lesson using a compelling narrative arc.\n\n## Your role\n- Building on the Knowledge Expert\'s analysis, restructure using a 4-act narrative arc (Setup → Development → Twist → Resolution)\n- Design a structure that keeps viewers watching until the end\n\n## Narrative arc guidelines\n### [Setup] Hook & Introduction\n### [Development] Build-up\n### [Twist] Surprise & Reversal\n### [Resolution] Payoff & Conclusion\n\n## Output format\n### Narrative arc structure\n### Payoff design\n### Production notes'
        : 'あなたは「エンタメ先生」です。Twitch配信で視聴者を楽しませる人気講師として、授業を起承転結で構成してください。\n\n## あなたの役割\n- 知識先生の分析を踏まえつつ、起承転結の物語構造で授業を再構成する\n- 視聴者が最後まで見たくなる構成を設計する\n\n## 起承転結の設計指針\n### 【起】導入・フック\n### 【承】展開・積み上げ\n### 【転】転換・驚き\n### 【結】オチ・締め\n\n## 出力形式\n### 起承転結の構成\n### オチの設計\n### 演出ポイント')}</pre></details>`;
    planHtml += `<details style="margin-bottom:4px;"><summary style="cursor:pointer; color:#888; font-size:0.68rem;">\u{1F4E5} ${lang === 'en' ? 'User Prompt' : 'ユーザープロンプト'} (${lang === 'en' ? 'includes Knowledge output' : '知識先生の出力を含む'})</summary>
      <pre style="${_preStyle}">${esc(entertainmentUserPrompt)}</pre></details>`;
    if (langPlan.entertainment) {
      planHtml += `<details open><summary style="cursor:pointer; color:#e65100; font-size:0.72rem; font-weight:600;">\u{1F4E4} ${lang === 'en' ? 'Output' : '出力'} (${langPlan.entertainment.length}${lang === 'en' ? ' chars' : '文字'})</summary>
        <pre style="${_outPreStyle('#fff3e0','#ffe0b2','#bf360c')}">${esc(langPlan.entertainment)}</pre></details>`;
    }
    planHtml += `</div></div>`;

    // --- 矢印 ---
    planHtml += `<div style="text-align:center; color:#999; font-size:0.9rem; margin:2px 0;">\u25BC</div>`;

    // --- 2a-3: 監督 ---
    planHtml += `<div style="border:1px solid #a5d6a7; border-radius:6px; overflow:hidden;">`;
    planHtml += `<div style="background:#e8f5e9; padding:6px 10px; font-size:0.78rem; font-weight:600; color:#2e7d32;">\u{1F3AC} ${lang === 'en' ? 'Step 3: Director' : 'Step 3: 監督'} <span style="font-weight:400; font-size:0.68rem; color:#666;">temp=0.5, JSON</span></div>`;
    planHtml += `<div style="padding:8px 10px; font-size:0.72rem;">`;
    planHtml += `<div style="color:#666; margin-bottom:4px;">${lang === 'en' ? 'Input' : '入力'}: <strong style="color:#1565c0;">${lang === 'en' ? 'Knowledge output' : '知識先生の出力'}</strong> + <strong style="color:#e65100;">${lang === 'en' ? 'Entertainment output' : 'エンタメ先生の出力'}</strong></div>`;
    planHtml += `<div style="color:#c62828; margin-bottom:4px; font-size:0.68rem;">\u26A0 ${lang === 'en' ? 'Source text and images are NOT passed to Director' : '教材テキスト・画像は監督には渡されない'}</div>`;
    planHtml += `<details style="margin-bottom:4px;"><summary style="cursor:pointer; color:#888; font-size:0.68rem;">\u{1F4E4} ${lang === 'en' ? 'System Prompt' : 'システムプロンプト'}</summary>
      <pre style="${_preStyle}">${esc(lang === 'en'
        ? 'You are the "Director". Integrate the Knowledge Expert\'s and Entertainment Expert\'s proposals to finalize the lesson plan.\n\n## Your role\n### Overall balance\n- Balance accuracy/coverage with narrative arc\n- Keep section count appropriate (3-15)\n\n### Writing titles\n- Max 5 words, specific nouns/verbs\n\n### Pacing ("wait_seconds")\n- Natural conversation: 1-2s\n- After key points: 3-4s\n- After surprising facts: 4-5s\n- Questions: 8-15s\n- Final summary: 2-3s\n\n## Output: JSON array\n[{section_type, title, summary, emotion, has_question, wait_seconds}]'
        : 'あなたは「監督」です。知識先生とエンタメ先生の提案を統合し、最終的な授業プランを決定してください。\n\n## あなたの役割\n### 全体のバランス調整\n- 正確性・網羅性と起承転結・演出を両立\n- セクション数3〜15に調整\n\n### titleの書き方\n- 10文字以内、具体的な名詞・動詞\n\n### 「間」の設計 (wait_seconds)\n- 自然な説明: 1〜2秒\n- 重要ポイント後: 3〜4秒\n- 驚きの事実後: 4〜5秒\n- 問いかけ: 8〜15秒\n- まとめ: 2〜3秒\n\n## 出力: JSON配列\n[{section_type, title, summary, emotion, has_question, wait_seconds}]')}</pre></details>`;
    planHtml += `<details style="margin-bottom:4px;"><summary style="cursor:pointer; color:#888; font-size:0.68rem;">\u{1F4E5} ${lang === 'en' ? 'User Prompt' : 'ユーザープロンプト'} (${lang === 'en' ? 'NO source text — only expert outputs' : '教材テキストなし — エキスパート出力のみ'})</summary>
      <pre style="${_preStyle}">${esc(directorUserPrompt)}</pre></details>`;

    try {
      const planSections = JSON.parse(langPlan.plan_json);
      if (planSections.length) {
        planHtml += `<div style="margin-top:4px; font-size:0.72rem; color:#2e7d32; font-weight:600;">\u{1F4E4} ${lang === 'en' ? 'Output' : '出力'}: ${planSections.length} ${lang === 'en' ? 'sections' : 'セクション'}</div>`;
        for (let i = 0; i < planSections.length; i++) {
          const ps = planSections[i];
          const icon = SECTION_ICONS[ps.section_type] || '\u{1F4D6}';
          const waitInfo = ps.wait_seconds ? `${ps.wait_seconds}${lang === 'en' ? 's' : '秒'}` : '';
          planHtml += `<div style="padding:4px 8px; margin-bottom:3px; background:#f1f8e9; border-radius:4px; font-size:0.72rem;">
            <span>${icon}</span>
            <strong>${i + 1}. ${esc(ps.title || ps.section_type)}</strong>
            <span style="color:#558b2f; margin-left:6px;">[${esc(ps.emotion || 'neutral')}]</span>
            ${waitInfo ? `<span style="color:#795548; margin-left:4px;">\u23F1${waitInfo}</span>` : ''}
            ${ps.has_question ? '<span style="color:#e65100; margin-left:4px;">\u2753</span>' : ''}
            <div style="color:#33691e; margin-top:2px;">${esc(ps.summary || '')}</div>
          </div>`;
        }
      }
    } catch(e) {}
    planHtml += `</div></div>`;
  }

  step2aBody.innerHTML = planHtml;
  step2a.innerHTML = '<div class="lesson-step-num">2a</div>';
  step2a.appendChild(step2aBody);
  body.appendChild(step2a);

  // === STEP 2b: スクリプ��生成 ===
  // キャラ設定取得
  const charsRes = await api('GET', '/api/characters');
  const charList = Array.isArray(charsRes) ? charsRes : [];
  const teacherChar = charList.find(c => c.role === 'teacher');
  const studentChar = charList.find(c => c.role === 'student');

  const step2b = document.createElement('div');
  step2b.className = 'lesson-step' + (hasSections ? ' step-done' : hasPlan || hasExtractedText ? ' step-active' : ' step-disabled');
  const step2bBody = document.createElement('div');
  step2bBody.className = 'lesson-step-body';
  const scriptLabel = hasPlan
    ? (lang === 'en' ? 'Generate Script+Audio from Plan' : 'プランからスクリプト+音声生成')
    : (lang === 'en' ? 'Generate Script+Audio' : 'スクリプト+音声生成');

  // 入力情報
  const etLen = (lesson.extracted_text || '').length;
  const planSecCount = hasPlan ? (() => { try { return JSON.parse(langPlan.plan_json).length; } catch(e) { return '?'; } })() : 0;
  let totalDlgs = 0;
  for (const s of sections) {
    try { totalDlgs += JSON.parse(s.dialogues || '[]').length; } catch(e) {}
  }

  let step2bHtml = `<div class="lesson-step-title">${lang === 'en' ? 'Script Generation' : 'スクリプト生成'}${hasSections ? ' (' + sections.length + (lang === 'en' ? ' sections' : 'セクション') + ', ' + totalDlgs + (lang === 'en' ? ' utterances' : '発話') + ')' : ''}</div>`;

  // 入力データ表示
  step2bHtml += `<div style="margin-bottom:8px; padding:6px 10px; background:#f5f0ff; border:1px solid #d0c0e8; border-radius:4px; font-size:0.72rem; color:#555;">`;
  step2bHtml += `<div style="font-weight:600; color:#7b1fa2; margin-bottom:4px;">${lang === 'en' ? 'Input' : '入力'}:</div>`;
  if (hasPlan) {
    step2bHtml += `<div>\u{1F3AC} ${lang === 'en' ? 'Director plan' : '監督プラン'} (${planSecCount} ${lang === 'en' ? 'sections' : 'セクション'}) \u2190 Step 2a</div>`;
  }
  step2bHtml += `<div>\u{1F4DD} ${lang === 'en' ? 'Extracted text' : '抽出テキスト'} (${etLen}${lang === 'en' ? ' chars' : '文字'}) \u2190 Step 1</div>`;

  // キャラ設定サマリー
  if (teacherChar || studentChar) {
    step2bHtml += `<div style="margin-top:4px; font-weight:600; color:#7b1fa2;">${lang === 'en' ? 'Characters' : 'キャ���設定'} (${lang === 'en' ? 'used in prompt' : 'プロンプトに使用'}):</div>`;
    if (teacherChar) {
      const tPrompt = (teacherChar.system_prompt || '').substring(0, 60);
      step2bHtml += `<div>\u{1F393} ${esc(teacherChar.name || 'teacher')} &mdash; voice: ${esc(teacherChar.tts_voice || '?')} / style: ${esc((teacherChar.tts_style || '').substring(0, 20))}...</div>`;
      step2bHtml += `<details style="margin-left:20px;"><summary style="cursor:pointer; color:#1565c0; font-size:0.68rem;">system_prompt</summary><pre style="font-size:0.65rem; max-height:100px; overflow-y:auto; white-space:pre-wrap; background:#fff; padding:4px; border:1px solid #ddd; border-radius:3px;">${esc(teacherChar.system_prompt || '')}</pre></details>`;
    }
    if (studentChar) {
      step2bHtml += `<div>\u{1F64B} ${esc(studentChar.name || 'student')} &mdash; voice: ${esc(studentChar.tts_voice || '?')} / style: ${esc((studentChar.tts_style || '').substring(0, 20))}...</div>`;
      step2bHtml += `<details style="margin-left:20px;"><summary style="cursor:pointer; color:#e65100; font-size:0.68rem;">system_prompt</summary><pre style="font-size:0.65rem; max-height:100px; overflow-y:auto; white-space:pre-wrap; background:#fff; padding:4px; border:1px solid #ddd; border-radius:3px;">${esc(studentChar.system_prompt || '')}</pre></details>`;
    }
  }
  step2bHtml += `<div style="margin-top:4px; color:#888; font-size:0.68rem;">${lang === 'en' ? 'Method: Single LLM call generates all sections and all character lines at once' : '生成方法: 1回のLLM呼び出しで全セ��ション・全キャラのセリフを一括生成'}</div>`;
  step2bHtml += `<div style="color:#888; font-size:0.68rem;">LLM: temperature=0.7, max_tokens=8192, response=JSON</div>`;
  step2bHtml += `</div>`;

  step2bHtml += `<div style="display:flex; align-items:center; gap:8px; margin-bottom:6px;">
      <button onclick="generateScript(${lessonId}, '${lang}')" style="padding:5px 14px; background:#e65100; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:0.8rem;">${hasSections ? (lang === 'en' ? 'Regenerate' : '再生成') : esc(scriptLabel)}</button>
      <span class="script-status"></span>
    </div>`;
  step2bBody.innerHTML = step2bHtml;

  // TTSキャッシュ情報取得
  let ttsCacheMap = {};
  if (hasSections) {
    const cacheRes = await api('GET', '/api/lessons/' + lessonId + '/tts-cache?lang=' + lang);
    if (cacheRes && cacheRes.ok) {
      for (const c of cacheRes.sections) {
        ttsCacheMap[c.order_index] = c.parts;
      }
    }
  }

  // セクション一覧
  const secContainer = document.createElement('div');
  renderSectionsInto(secContainer, sections, lessonId, ttsCacheMap, {teacher: teacherChar, student: studentChar});
  step2bBody.appendChild(secContainer);

  step2b.innerHTML = '<div class="lesson-step-num">2b</div>';
  step2b.appendChild(step2bBody);
  body.appendChild(step2b);

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
    _clearDownstreamSteps(lessonId, ['2a', '2b', '3']);
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
      _clearDownstreamSteps(lessonId, ['2a', '2b', '3']);
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
  _clearDownstreamSteps(lessonId, ['2a', '2b', '3']);
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

// --- SSEストリーミング共通 ---

function _streamSSE(url, statusEl, onComplete) {
  return new Promise((resolve) => {
    fetch(url, { method: 'POST' }).then(response => {
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      function read() {
        reader.read().then(({ done, value }) => {
          if (done) { resolve(null); return; }
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop();
          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            try {
              const data = JSON.parse(line.slice(6));
              if (data.ok !== undefined) {
                // 最終結果
                resolve(data);
              } else if (data.step !== undefined && statusEl) {
                // 進捗更新
                _showSpinner(statusEl, data.message);
              }
            } catch(e) {}
          }
          read();
        });
      }
      read();
    }).catch(e => {
      resolve({ ok: false, error: e.message });
    });
  });
}

// --- プラン生成 ---

async function generatePlan(lessonId, lang) {
  lang = lang || _getLessonLang(lessonId);
  _clearDownstreamSteps(lessonId, ['2b', '3']);
  const items = document.querySelectorAll('.lesson-item');
  let statusEl = null;
  let btn = null;
  for (const item of items) {
    const b = item.querySelector(`button[onclick*="generatePlan(${lessonId}"]`);
    if (b) {
      btn = b;
      statusEl = b.parentElement.querySelector('.plan-status');
      break;
    }
  }
  if (btn) btn.disabled = true;
  if (statusEl) _showSpinner(statusEl, lang === 'en' ? 'Generating plan...' : 'プラン生成開始...');
  const res = await _streamSSE('/api/lessons/' + lessonId + '/generate-plan?lang=' + lang, statusEl);
  if (btn) btn.disabled = false;
  if (statusEl) _hideSpinner(statusEl);
  if (res && res.ok) {
    showToast('プラン生成完了 (' + res.plan_sections.length + 'セクション構成)', 'success');
  } else {
    const errMsg = res && res.error ? res.error : '不明なエラー';
    showToast('プラン生成失敗: ' + errMsg, 'error');
    if (statusEl) {
      statusEl.innerHTML = '<span style="color:#c62828; font-size:0.8rem; font-weight:600;">❌ ' + esc(errMsg) + '</span>';
    }
  }
  _openLessonIds.add(lessonId);
  await loadLessons();
}

// --- 授業スクリプト ---

async function generateScript(lessonId, lang) {
  lang = lang || _getLessonLang(lessonId);
  _clearDownstreamSteps(lessonId, ['3']);
  const items = document.querySelectorAll('.lesson-item');
  let statusEl = null;
  let btn = null;
  for (const item of items) {
    const b = item.querySelector(`button[onclick*="generateScript(${lessonId}"]`);
    if (b) {
      btn = b;
      statusEl = b.parentElement.querySelector('.script-status');
      break;
    }
  }
  if (btn) btn.disabled = true;
  // 既存セクション一覧を即座にクリア
  const secContainer = btn ? btn.closest('.lesson-step-body').querySelector('div:last-child') : null;
  if (secContainer) renderSectionsInto(secContainer, [], lessonId, {});
  if (statusEl) _showSpinner(statusEl, lang === 'en' ? 'Generating script...' : 'スクリプト生成開始...');
  const res = await _streamSSE('/api/lessons/' + lessonId + '/generate-script?lang=' + lang, statusEl);
  if (btn) btn.disabled = false;
  if (statusEl) _hideSpinner(statusEl);
  if (res && res.ok) {
    let msg = 'スクリプト+音声生成完了 (' + res.sections.length + 'セクション';
    if (res.tts_generated !== undefined) msg += ', TTS ' + res.tts_generated + '件';
    if (res.tts_errors) msg += ', エラー ' + res.tts_errors + '件';
    msg += ')';
    showToast(msg, 'success');
  } else {
    const errMsg = res && res.error ? res.error : '不明なエラー';
    showToast('スクリプト生成失敗: ' + errMsg, 'error');
    if (statusEl) {
      statusEl.innerHTML = '<span style="color:#c62828; font-size:0.8rem; font-weight:600;">❌ ' + esc(errMsg) + '</span>';
    }
  }
  _openLessonIds.add(lessonId);
  await loadLessons();
}

function renderSectionsInto(container, sections, lessonId, ttsCacheMap, charInfo) {
  container.innerHTML = '';
  if (!sections || !sections.length) {
    container.innerHTML = '<div style="color:#8a7a9a; font-size:0.8rem; padding:8px;">スクリプトがありません。「スクリプト生成」を押してください。</div>';
    return;
  }
  ttsCacheMap = ttsCacheMap || {};
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
    try { _dlgs = typeof s.dialogues === 'string' ? JSON.parse(s.dialogues) : (s.dialogues || []); } catch(e) {}
    const _ci = charInfo || {};
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
  await api('DELETE', '/api/lessons/' + lessonId + '/tts-cache/' + orderIndex);
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

async function startLesson(lessonId, lang) {
  lang = lang || _getLessonLang(lessonId);
  const res = await api('POST', '/api/lessons/' + lessonId + '/start?lang=' + lang);
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
  const cacheRes = await api('GET', `/api/lessons/${lessonId}/tts-cache?lang=${lang}`);
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

// ステータスポーリング不要（loadLessonsで全更新）
let _lessonStatusTimer = null;
function startLessonStatusPolling() {}
function stopLessonStatusPolling() {
  if (_lessonStatusTimer) { clearInterval(_lessonStatusTimer); _lessonStatusTimer = null; }
}
