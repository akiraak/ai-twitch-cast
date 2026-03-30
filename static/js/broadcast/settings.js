// 設定適用（applySettings, _applyLighting）

// === 縁取り適用ヘルパー ===
function _applyStroke(el, size, color, opacity) {
  const sz = size != null ? Number(size) : null;
  if (sz == null) return;
  if (sz > 0) {
    let c = color || '#000000';
    const a = opacity != null ? parseFloat(opacity) : 0.8;
    if (c.startsWith('#')) {
      const r = parseInt(c.slice(1,3),16)||0, g = parseInt(c.slice(3,5),16)||0, b = parseInt(c.slice(5,7),16)||0;
      c = `rgba(${r},${g},${b},${a})`;
    }
    el.style.webkitTextStroke = sz + 'px ' + c;
    el.style.paintOrder = 'stroke fill';
  } else {
    el.style.webkitTextStroke = '';
  }
}

// === ライティング適用（applySettings・pending両方から呼ばれる） ===
function _applyLighting(lighting, avatarId) {
  const L = window.avatarLighting;
  if (!L) return;
  const b = lighting.brightness ?? 1.0;
  const c = lighting.contrast ?? 1.0;
  const temp = lighting.temperature ?? 0;  // -1(寒色)〜+1(暖色)
  const sat = lighting.saturation ?? 1.0;
  // 詳細ライト設定（直接指定がある場合はそちらを優先）
  if (lighting.ambient != null) L.setAmbient(lighting.ambient, avatarId);
  if (lighting.directional != null) L.setDirectional(lighting.directional, avatarId);
  if (lighting.ambient == null && lighting.directional == null) {
    L.setExposure(b, avatarId);
    L.setAmbient(Math.max(0.1, Math.min(2.0, L.BASE_AMBIENT * b / c)), avatarId);
    L.setDirectional(Math.max(0.2, Math.min(3.0, L.BASE_DIRECTIONAL * b * c)), avatarId);
  }
  // ライト方向
  if (lighting.lightX != null || lighting.lightY != null || lighting.lightZ != null) {
    L.setPosition(lighting.lightX, lighting.lightY, lighting.lightZ, avatarId);
  }
  // 色温度 → ライトの色（暖色=黄、寒色=青）
  const r = 1.0 + temp * 0.15;
  const g = 1.0;
  const bl = 1.0 - temp * 0.15;
  L.setColor(r, g, bl, avatarId);
  // 彩度 → CSSフィルター（アバター個別）
  const canvasSelector = avatarId === 'student' ? '#avatar-area-2 canvas'
    : avatarId === 'teacher' ? '#avatar-area-1 canvas'
    : '#avatar-area-1 canvas, #avatar-area-2 canvas';
  document.querySelectorAll(canvasSelector).forEach(c => {
    c.style.filter = sat !== 1.0 ? `saturate(${sat})` : '';
  });
}

// === 保存済み設定（表示時の再適用用、avatar-renderer.jsからも参照） ===
let _savedOverlaySettings = {};
window._savedOverlaySettings = _savedOverlaySettings;

// === 設定適用（%/vw単位） ===
function applySettings(s) {
  _savedOverlaySettings = { ..._savedOverlaySettings, ...s };
  window._savedOverlaySettings = _savedOverlaySettings;
  // === avatar1（先生） ===
  const avatarArea1 = document.getElementById('avatar-area-1');
  if (s.avatar1) {
    applyCommonStyle(avatarArea1, s.avatar1);
    if (s.avatar1.width != null) avatarArea1.style.width = s.avatar1.width + '%';
    if (s.avatar1.height != null) avatarArea1.style.height = s.avatar1.height + '%';
    if (s.avatar1.bodyAngle != null) {
      window.avatarInstances?.['teacher']?.setBodyAngle(s.avatar1.bodyAngle);
    }
    if (s.avatar1.headTilt != null) {
      window.avatarInstances?.['teacher']?.setHeadTilt(s.avatar1.headTilt);
    }
    const idleKeys1 = ['idleScale','breathScale','swayScale','headScale','gazeRange','armAngle','armScale','earFreq'];
    const idleParams1 = {};
    for (const k of idleKeys1) {
      if (s.avatar1[k] != null) idleParams1[k] = s.avatar1[k];
    }
    if (Object.keys(idleParams1).length > 0) {
      window.avatarInstances?.['teacher']?.setIdleParams(idleParams1);
    }
    if (window.dispatchEvent) window.dispatchEvent(new Event('resize'));
  }
  // === avatar2（生徒） ===
  const avatarArea2 = document.getElementById('avatar-area-2');
  if (s.avatar2) {
    applyCommonStyle(avatarArea2, s.avatar2);
    if (s.avatar2.width != null) avatarArea2.style.width = s.avatar2.width + '%';
    if (s.avatar2.height != null) avatarArea2.style.height = s.avatar2.height + '%';
    if (s.avatar2.bodyAngle != null) {
      window.avatarInstances?.['student']?.setBodyAngle(s.avatar2.bodyAngle);
    }
    if (s.avatar2.headTilt != null) {
      window.avatarInstances?.['student']?.setHeadTilt(s.avatar2.headTilt);
    }
    const idleKeys2 = ['idleScale','breathScale','swayScale','headScale','gazeRange','armAngle','armScale','earFreq'];
    const idleParams2 = {};
    for (const k of idleKeys2) {
      if (s.avatar2[k] != null) idleParams2[k] = s.avatar2[k];
    }
    if (Object.keys(idleParams2).length > 0) {
      window.avatarInstances?.['student']?.setIdleParams(idleParams2);
    }
  }
  // === lighting（アバター個別 or 共通） ===
  if (s.lighting_teacher) {
    if (window.avatarLighting) {
      _applyLighting(s.lighting_teacher, 'teacher');
    } else {
      if (!window._pendingLightingPerChar) window._pendingLightingPerChar = {};
      window._pendingLightingPerChar.teacher = s.lighting_teacher;
    }
  }
  if (s.lighting_student) {
    if (window.avatarLighting) {
      _applyLighting(s.lighting_student, 'student');
    } else {
      if (!window._pendingLightingPerChar) window._pendingLightingPerChar = {};
      window._pendingLightingPerChar.student = s.lighting_student;
    }
  }
  if (s.lighting && !s.lighting_teacher && !s.lighting_student) {
    if (window.avatarLighting) {
      _applyLighting(s.lighting, 'teacher');
      _applyLighting(s.lighting, 'student');
    } else {
      window._pendingLighting = s.lighting;
    }
  }
  // === subtitle (teacher + student) ===
  for (const [key, el] of [['subtitle', subtitleEl], ['subtitle2', subtitle2El]]) {
    if (s[key]) {
      applyCommonStyle(el, s[key]);
      // 字幕固有: bottom配置 + 中心基準（commonのtopをオーバーライド）
      if (s[key].bottom != null) el.style.bottom = s[key].bottom + '%';
      el.style.top = '';
      el.style.transform = 'translateX(-50%)';
      if (s[key].fontSize != null) el.querySelector('.speech').style.fontSize = s[key].fontSize + 'vw';
      if (s[key].maxWidth != null) el.style.maxWidth = s[key].maxWidth + '%';
      if (s[key].fadeDuration != null) el.dataset.fadeDuration = s[key].fadeDuration;
    }
  }
  // === todo ===
  if (s.todo) {
    applyCommonStyle(todoPanelEl, s.todo);
    todoSettings = Object.assign(todoSettings, s.todo);
    // todo固有: サイズ + maxHeight + transform
    if (s.todo.width != null) todoPanelEl.style.width = s.todo.width + '%';
    if (s.todo.height != null) {
      todoPanelEl.style.height = s.todo.height + '%';
      todoPanelEl.style.maxHeight = 'none';
      todoPanelEl.style.overflow = 'hidden';
    }
    if (s.todo.positionX != null) todoPanelEl.style.transform = 'none';
    if (s.todo.fontSize != null) {
      todoPanelEl.querySelectorAll('.todo-item').forEach(el => el.style.fontSize = s.todo.fontSize + 'vw');
    }
    if (s.todo.titleFontSize != null) todoPanelEl.querySelector('.todo-title').style.fontSize = s.todo.titleFontSize + 'vw';
    loadTodo();
  }
  // === lesson_title ===
  if (s.lesson_title) {
    const ltpanel = document.getElementById('lesson-title-panel');
    if (ltpanel) {
      applyCommonStyle(ltpanel, s.lesson_title);
      const lttext = document.getElementById('lesson-title-text');
      if (lttext && s.lesson_title.fontSize != null) {
        lttext.style.fontSize = s.lesson_title.fontSize + 'vw';
      }
    }
  }
  // === lesson_text ===
  if (s.lesson_text) {
    const ltp = document.getElementById('lesson-text-panel');
    if (ltp) {
      applyCommonStyle(ltp, s.lesson_text);
      if (s.lesson_text.width != null) ltp.style.width = s.lesson_text.width + '%';
      if (s.lesson_text.height != null) ltp.style.height = s.lesson_text.height + '%';
      if (s.lesson_text.maxHeight != null) ltp.style.maxHeight = s.lesson_text.maxHeight + '%';
      const ltc = document.getElementById('lesson-text-content');
      if (ltc) {
        if (s.lesson_text.fontSize != null) ltc.style.fontSize = s.lesson_text.fontSize + 'vw';
        if (s.lesson_text.lineHeight != null) ltc.style.lineHeight = s.lesson_text.lineHeight;
      }
    }
  }
  // === lesson_progress ===
  if (s.lesson_progress) {
    const lpp = document.getElementById('lesson-progress-panel');
    if (lpp) {
      applyCommonStyle(lpp, s.lesson_progress);
      if (s.lesson_progress.width != null) lpp.style.width = s.lesson_progress.width + '%';
      if (s.lesson_progress.maxHeight != null) lpp.style.maxHeight = s.lesson_progress.maxHeight + '%';
      // 文字サイズ: fontSize（共通）→ 全子要素に適用、titleFontSize/itemFontSize（固有）→ 個別に上書き
      const fs = s.lesson_progress.fontSize;
      const titleFs = s.lesson_progress.titleFontSize ?? (fs != null ? fs : null);
      const itemFs = s.lesson_progress.itemFontSize ?? (fs != null ? fs : null);
      if (titleFs != null) {
        const title = document.getElementById('lesson-progress-title');
        if (title) title.style.fontSize = titleFs + 'vw';
        lpp.dataset.titleFontSize = titleFs;
      }
      if (itemFs != null) {
        lpp.querySelectorAll('.lesson-progress-item').forEach(el =>
          el.style.fontSize = itemFs + 'vw'
        );
        lpp.dataset.itemFontSize = itemFs;
      }
      // タイトル文字スタイル
      const titleTextEl = lpp.querySelector('.lp-title-text');
      if (titleTextEl) {
        const lp = s.lesson_progress;
        if (lp.titleColor != null) titleTextEl.style.color = lp.titleColor;
        _applyStroke(titleTextEl, lp.titleStrokeSize, lp.titleStrokeColor, lp.titleStrokeOpacity);
      }
      // カウント文字スタイル
      const countEl = lpp.querySelector('.lp-title-count');
      if (countEl) {
        const lp = s.lesson_progress;
        if (lp.countFontSize != null) countEl.style.fontSize = lp.countFontSize + 'vw';
        if (lp.countColor != null) countEl.style.color = lp.countColor;
        _applyStroke(countEl, lp.countStrokeSize, lp.countStrokeColor, lp.countStrokeOpacity);
      }
      // dataset に保存（動的要素再生成時に復元用）
      const lp = s.lesson_progress;
      for (const k of ['titleColor','titleStrokeSize','titleStrokeColor','titleStrokeOpacity',
                        'countFontSize','countColor','countStrokeSize','countStrokeColor','countStrokeOpacity']) {
        if (lp[k] != null) lpp.dataset[k] = lp[k];
      }
    }
  }
  // === sync ===
  if (s.sync) {
    if (s.sync.lipsyncDelay != null) {
      _lipsyncDelay = s.sync.lipsyncDelay;
      try { window.chrome?.webview?.postMessage({_syncDelay: _lipsyncDelay}); } catch(e){}
    }
  }
}
