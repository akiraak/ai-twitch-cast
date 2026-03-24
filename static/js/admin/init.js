// 初期化・WebSocket接続

const _initHash = location.hash.slice(1);
const [_initTab, _initParam] = _initHash.split(':');
if (_initTab === 'chat' && _initParam) {
  const pg = Math.max(1, parseInt(_initParam) || 1);
  _chatOffset = (pg - 1) * _chatLimit;
}
{ if (TAB_NAMES.includes(_initTab)) switchTab(_initTab);
}

// スキーマ取得後に共通コントロールを注入（スキーマAPIベース）
_loadCommonSchema().then(() => {
  initCommonProps();
  // 固定パネルに子パネル管理UIを注入
  ['avatar1', 'avatar2', 'subtitle', 'todo'].forEach(panelId => {
    const body = document.querySelector(`[data-section="${panelId}"] .panel-body`);
    if (body) injectChildPanelSection(body, panelId);
  });
  // キャプチャ・カスタムテキスト・背景をロード（パネル生成+共通コントロール注入）
  captureRefreshSources();
  loadCustomTexts();
  loadCategoryFiles('background');
  // VRMファイルはキャラクタータブで管理（_loadCharVrmFiles）
  _loadCharVrmFiles();
  // 全パネルの値を読み込み
  loadVolumes();
  loadLayout().then(() => {
    // ライティングdata-keyをteacher用に初期化し値をロード
    if (typeof _loadCharLighting === 'function') _loadCharLighting();
  });
  loadCharacter();
  loadLightingPresets();
  loadBgmTracks();
  refreshStatus();
});
setInterval(refreshStatus, 30000);
setInterval(captureRefreshSources, 30000);
setInterval(syncBgmVolumes, 30000);

// --- WebSocket接続（プレビュー→WebUIリアルタイム同期） ---
(function connectLayoutWS() {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(`${protocol}//${location.host}/ws/broadcast`);
  ws.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      // サーバー再起動通知
      if (data.type === 'server_restart') {
        showUpdateDialog();
        return;
      }
      // チャットメッセージをリアルタイム表示（先頭に追加）
      if (data.type === 'comment') {
        prependChatMessage(data);
        return;
      }
      if (data.type !== 'settings_update') return;
      // レイアウトスライダーをリアルタイム更新（自身の変更中は除く）
      if (_layoutTimer) return;
      for (const [section, props] of Object.entries(data)) {
        if (section === 'type') continue;
        if (typeof props !== 'object') continue;
        for (const [prop, val] of Object.entries(props)) {
          const key = `${section}.${prop}`;
          // layoutSettingsを更新
          if (!layoutSettings[section]) layoutSettings[section] = {};
          layoutSettings[section][prop] = val;
          // UIのスライダー・数値入力を更新
          const numEl = document.getElementById('lv-' + key.replace('.', '-'));
          if (numEl) {
            numEl.value = val;
            const slider = numEl.closest('.layout-row')?.querySelector('.layout-slider');
            if (slider) slider.value = val;
          }
          // カラーピッカー
          const colorEl = document.querySelector(`.layout-color[data-key="${key}"]`);
          if (colorEl) colorEl.value = cssColorToHex(String(val));
          // トグル
          const toggleEl = document.querySelector(`.layout-toggle[data-key="${key}"]`);
          if (toggleEl) {
            toggleEl.checked = !!Number(val);
            const track = toggleEl.nextElementSibling;
            const knob = track?.nextElementSibling;
            if (track) track.style.background = toggleEl.checked ? '#7b1fa2' : '#ccc';
            if (knob) knob.style.left = toggleEl.checked ? '16px' : '2px';
          }
        }
      }
    } catch (err) {}
  };
  ws.onclose = () => setTimeout(connectLayoutWS, 3000);
  ws.onerror = () => ws.close();
})();
