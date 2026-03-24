// 設定適用（applySettings, _applyLighting）

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

// === 保存済み設定（表示時の再適用用） ===
let _savedOverlaySettings = {};

// === 設定適用（%/vw単位） ===
function applySettings(s) {
  _savedOverlaySettings = { ..._savedOverlaySettings, ...s };
  // === avatar1（先生） ===
  const avatarArea1 = document.getElementById('avatar-area-1');
  if (s.avatar1) {
    applyCommonStyle(avatarArea1, s.avatar1);
    if (s.avatar1.width != null) avatarArea1.style.width = s.avatar1.width + '%';
    if (s.avatar1.height != null) avatarArea1.style.height = s.avatar1.height + '%';
    if (window.dispatchEvent) window.dispatchEvent(new Event('resize'));
  }
  // === avatar2（生徒） ===
  const avatarArea2 = document.getElementById('avatar-area-2');
  if (s.avatar2) {
    applyCommonStyle(avatarArea2, s.avatar2);
    if (s.avatar2.width != null) avatarArea2.style.width = s.avatar2.width + '%';
    if (s.avatar2.height != null) avatarArea2.style.height = s.avatar2.height + '%';
  }
  // === lighting（アバター個別 or 共通） ===
  if (s.lighting_teacher) {
    if (window.avatarLighting) _applyLighting(s.lighting_teacher, 'teacher');
  }
  if (s.lighting_student) {
    if (window.avatarLighting) _applyLighting(s.lighting_student, 'student');
  }
  if (s.lighting) {
    if (window.avatarLighting) {
      _applyLighting(s.lighting, 'teacher');
      _applyLighting(s.lighting, 'student');
    } else {
      window._pendingLighting = s.lighting;
    }
  }
  // === subtitle ===
  if (s.subtitle) {
    applyCommonStyle(subtitleEl, s.subtitle);
    // 字幕固有: 常に水平中央配置 + bottom配置（commonのtop/leftをオーバーライド）
    if (s.subtitle.bottom != null) subtitleEl.style.bottom = s.subtitle.bottom + '%';
    subtitleEl.style.top = '';
    subtitleEl.style.left = '50%';
    subtitleEl.style.transform = 'translateX(-50%)';
    if (s.subtitle.fontSize != null) subtitleEl.querySelector('.speech').style.fontSize = s.subtitle.fontSize + 'vw';
    if (s.subtitle.maxWidth != null) subtitleEl.style.maxWidth = s.subtitle.maxWidth + '%';
    if (s.subtitle.fadeDuration != null) subtitleEl.dataset.fadeDuration = s.subtitle.fadeDuration;
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
  // === lesson_text（data-fixed-layoutでレイアウトはCSS固定） ===
  if (s.lesson_text) {
    const ltp = document.getElementById('lesson-text-panel');
    if (ltp) {
      applyCommonStyle(ltp, s.lesson_text);
      // 固有プロパティ
      if (s.lesson_text.maxHeight != null) ltp.style.maxHeight = s.lesson_text.maxHeight + '%';
      const ltc = document.getElementById('lesson-text-content');
      if (ltc) {
        if (s.lesson_text.fontSize != null) ltc.style.fontSize = s.lesson_text.fontSize + 'vw';
        if (s.lesson_text.lineHeight != null) ltc.style.lineHeight = s.lesson_text.lineHeight;
      }
    }
  }
  // === lesson_progress（data-fixed-layoutでレイアウトはCSS固定） ===
  if (s.lesson_progress) {
    const lpp = document.getElementById('lesson-progress-panel');
    if (lpp) {
      applyCommonStyle(lpp, s.lesson_progress);
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
