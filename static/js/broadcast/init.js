// broadcast.html 初期化

async function init() {
  // 背景画像（APIから選択済み背景を取得）
  try {
    const res = await fetch('/api/files/background/list');
    const data = await res.json();
    if (data.ok && data.active) {
      document.getElementById('background').src = '/resources/images/backgrounds/' + data.active;
    }
  } catch (e) {}

  // オーバーレイ設定読み込み
  try {
    const res = await fetch('/api/overlay/settings');
    const s = await res.json();
    applySettings(s);
  } catch (e) {
    console.log('設定読み込みスキップ:', e.message);
  }

  // 音量設定読み込み
  try {
    const res = await fetch('/api/broadcast/volumes');
    const v = await res.json();
    if (v.master != null) volumes.master = v.master;
    if (v.tts != null) volumes.tts = v.tts;
    if (v.bgm != null) volumes.bgm = v.bgm;
    applyVolume();
  } catch (e) {
    console.log('音量設定読み込みスキップ:', e.message);
  }

  // 配信状態を取得（リップシンク遅延切替用）
  try {
    const res = await fetch('/api/broadcast/status');
    const st = await res.json();
    _isStreaming = !!st.streaming;
    console.log('[Sync] init streaming:', _isStreaming);
  } catch (e) {}

  // アバターストリーム復元
  try {
    const res = await fetch('/api/broadcast/avatar');
    const av = await res.json();
    if (av.url) setAvatarStream(av.url);
  } catch (e) {}

  // キャプチャソース読み込み
  try {
    const res = await fetch('/api/capture/sources');
    const sources = await res.json();
    for (const s of sources) {
      addCaptureLayer(s.id, s.stream_url, s.label || s.name || s.id, s.layout);
    }
  } catch (e) { console.log('キャプチャ読み込みスキップ:', e.message); }

  // カスタムテキスト読み込み
  try {
    const res = await fetch('/api/overlay/custom-texts');
    const items = await res.json();
    for (const item of items) {
      addCustomTextLayer(item.id, item.label, item.content, item.layout);
    }
  } catch (e) { console.log('カスタムテキスト読み込みスキップ:', e.message); }

  // broadcast_itemsから共通プロパティをカスタムテキスト・キャプチャに適用 + 子パネル読み込み
  try {
    const allItems = await (await fetch('/api/items')).json();
    for (const bi of allItems) {
      if (bi.type === 'custom_text' && bi.id.startsWith('customtext:')) {
        const numId = parseInt(bi.id.split(':')[1]);
        const el = customTextLayers[numId];
        if (el) applyCommonStyle(el, bi);
      } else if (bi.type === 'capture' && bi.id.startsWith('capture:')) {
        // captureはIDがセッション固有のためwindow_name経由では適用困難→スキップ
      }
      // 子パネルの読み込み
      if (bi.children) {
        for (const child of bi.children) {
          addChildPanel(bi.id, child);
        }
      }
    }
  } catch (e) {}

  // バージョン情報取得 → カスタムテキストの変数を再展開
  try {
    const res = await fetch('/api/status');
    const st = await res.json();
    window._versionInfo = st;
    document.querySelectorAll('.custom-text-content[data-raw-content], .child-text-content[data-raw-content]').forEach(el => {
      el.textContent = replaceTextVariables(el.dataset.rawContent);
    });
  } catch (e) {}

  await loadTodo();
  // TODOはWebSocket pushで更新されるためポーリング不要
  connectWS();

  initEditMode();
}

init();
