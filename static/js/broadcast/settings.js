// 設定適用（applySettings, _applyLighting）

// === ライティング適用（applySettings・pending両方から呼ばれる） ===
function _applyLighting(lighting) {
  const L = window.avatarLighting;
  if (!L) return;
  const b = lighting.brightness ?? 1.0;
  const c = lighting.contrast ?? 1.0;
  const temp = lighting.temperature ?? 0;  // -1(寒色)〜+1(暖色)
  const sat = lighting.saturation ?? 1.0;
  // 詳細ライト設定（直接指定がある場合はそちらを優先）
  if (lighting.ambient != null) L.setAmbient(lighting.ambient);
  if (lighting.directional != null) L.setDirectional(lighting.directional);
  if (lighting.ambient == null && lighting.directional == null) {
    // 明るさ・コントラストからの自動計算（詳細設定がない場合のみ）
    L.setExposure(b);
    L.setAmbient(Math.max(0.1, Math.min(2.0, L.BASE_AMBIENT * b / c)));
    L.setDirectional(Math.max(0.2, Math.min(3.0, L.BASE_DIRECTIONAL * b * c)));
  }
  // ライト方向
  if (lighting.lightX != null || lighting.lightY != null || lighting.lightZ != null) {
    L.setPosition(lighting.lightX, lighting.lightY, lighting.lightZ);
  }
  // 色温度 → ライトの色（暖色=黄、寒色=青）
  const r = 1.0 + temp * 0.15;
  const g = 1.0;
  const bl = 1.0 - temp * 0.15;
  L.setColor(r, g, bl);
  // 彩度 → CSSフィルター
  document.getElementById('avatar-canvas').style.filter = sat !== 1.0 ? `saturate(${sat})` : '';
}

// === 設定適用（%/vw単位） ===
function applySettings(s) {
  // === avatar ===
  const avatarArea = document.getElementById('avatar-area');
  if (s.avatar) {
    applyCommonStyle(avatarArea, s.avatar);
    // avatar固有: サイズ + キャンバスリサイズ
    if (s.avatar.width != null) avatarArea.style.width = s.avatar.width + '%';
    if (s.avatar.height != null) avatarArea.style.height = s.avatar.height + '%';
    if (window.dispatchEvent) window.dispatchEvent(new Event('resize'));
  }
  // === lighting ===
  if (s.lighting) {
    if (window.avatarLighting) {
      _applyLighting(s.lighting);
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
  // === topic ===
  if (s.topic) {
    applyCommonStyle(topicPanelEl, s.topic);
    if (s.topic.maxWidth != null) topicPanelEl.style.maxWidth = s.topic.maxWidth + '%';
    if (s.topic.titleFontSize != null) {
      document.getElementById('topic-title-text').style.fontSize = s.topic.titleFontSize + 'vw';
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
