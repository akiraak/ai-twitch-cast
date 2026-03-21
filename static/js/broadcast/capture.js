// ウィンドウキャプチャ・アバターストリーム

// === アバターストリーム ===
function setAvatarStream(url) {
  avatarImg.src = url;
  avatarImg.style.display = '';
  avatarImg.onerror = () => {
    // ストリーム切断時は非表示
    avatarImg.style.display = 'none';
  };
}

function stopAvatarStream() {
  avatarImg.src = '';
  avatarImg.style.display = 'none';
}

// === snapshotポーリング（プレビュー用フォールバック） ===
function startSnapshotPolling(host) {
  if (snapshotHost === host && snapshotTimer) return;
  snapshotHost = host;
  if (snapshotTimer) clearInterval(snapshotTimer);
  console.log(`[Capture] snapshotポーリング開始: ${host}`);
  snapshotTimer = setInterval(() => {
    for (const [id, img] of Object.entries(captureImgMap)) {
      const url = `http://${snapshotHost}/snapshot/${id}?t=${Date.now()}`;
      img.src = url;
    }
  }, SNAPSHOT_INTERVAL);
}

function stopSnapshotPolling() {
  if (snapshotTimer) { clearInterval(snapshotTimer); snapshotTimer = null; }
}

// === キャプチャレイヤー管理 ===
function addCaptureLayer(id, streamUrl, label, layout) {
  console.log(`[Capture] addCaptureLayer: id=${id}, streamUrl=${streamUrl}, useDirectCapture=${useDirectCapture}`, layout);
  if (captureLayers[id]) removeCaptureLayer(id);
  const div = document.createElement('div');
  div.className = 'capture-layer';
  div.dataset.editable = `capture:${id}`;
  div.dataset.captureId = id;
  applyLayoutToEl(div, layout);

  const labelEl = document.createElement('div');
  labelEl.className = 'edit-label';
  labelEl.textContent = label || id;
  div.appendChild(labelEl);

  const img = document.createElement('img');
  img.alt = label || id;
  div.appendChild(img);

  captureContainer.appendChild(div);
  captureLayers[id] = div;
  captureImgMap[id] = img;

  if (!useDirectCapture && streamUrl) {
    // snapshotポーリングでフレーム受信
    try {
      const httpUrl = new URL(streamUrl);
      startSnapshotPolling(httpUrl.host);
    } catch (e) {}
  }

  setupEditable(div);
}

function removeCaptureLayer(id) {
  const el = captureLayers[id];
  if (el) {
    const img = captureImgMap[id];
    el.remove();
    delete captureLayers[id];
    delete captureImgMap[id];
  }
}

function updateCaptureLayout(id, layout) {
  const el = captureLayers[id];
  if (el) applyLayoutToEl(el, layout);
}
