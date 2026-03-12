/**
 * AI Twitch Cast - Window Capture Server (Electron Main Process)
 *
 * Windowsウィンドウをキャプチャし、MJPEGストリームとして配信する。
 * WSL2側のbroadcast.htmlがこのストリームを<img>で表示する。
 */

const { app, BrowserWindow, Menu, desktopCapturer, ipcMain } = require('electron');
const express = require('express');
const path = require('path');
const WebSocket = require('ws');

const PORT = parseInt(process.env.WIN_CAPTURE_PORT || '9090');
const DEFAULT_FPS = parseInt(process.env.WIN_CAPTURE_FPS || '15');
const DEFAULT_QUALITY = parseFloat(process.env.WIN_CAPTURE_QUALITY || '0.7');
const WS_BACKPRESSURE_LIMIT = 1024 * 1024; // 1MB: これ以上バッファが溜まったらフレームを間引く

// キャプチャセッション管理
const captures = new Map(); // id -> CaptureSession
let nextId = 0;

// WebSocket: キャプチャインデックス管理
const captureIndexMap = new Map(); // id -> index (0-255)
let nextCaptureIndex = 0;
let wss = null; // WebSocket.Server

// プレビューウィンドウ
let previewWindow = null;

/**
 * @typedef {Object} CaptureSession
 * @property {string} id
 * @property {string} sourceId - desktopCapturer source ID
 * @property {string} name - ウィンドウ名
 * @property {BrowserWindow} window - 非表示レンダラーウィンドウ
 * @property {Buffer|null} latestFrame - 最新JPEGフレーム
 * @property {Set} clients - MJPEG接続中のHTTPレスポンス
 * @property {number} fps
 */

// === IPC: レンダラーからフレーム受信 ===
ipcMain.on('capture-frame', (event, { id, jpeg }) => {
  const session = captures.get(id);
  if (!session) return;

  const buf = Buffer.from(jpeg);
  session.latestFrame = buf;

  // 全MJPEGクライアントにプッシュ（互換性維持）
  const dead = [];
  for (const res of session.clients) {
    try {
      res.write(`--frame\r\nContent-Type: image/jpeg\r\nContent-Length: ${buf.length}\r\n\r\n`);
      res.write(buf);
      res.write('\r\n');
    } catch (e) {
      dead.push(res);
    }
  }
  for (const res of dead) {
    session.clients.delete(res);
  }

  // WebSocketクライアントにバイナリ送信（1byte index + JPEG）
  const captureIdx = captureIndexMap.get(id);
  if (captureIdx !== undefined && wss) {
    const header = Buffer.alloc(1);
    header[0] = captureIdx;
    const frame = Buffer.concat([header, buf]);
    wss.clients.forEach(client => {
      if (client.readyState === WebSocket.OPEN && client.bufferedAmount < WS_BACKPRESSURE_LIMIT) {
        client.send(frame);
      }
    });
  }
});

ipcMain.on('capture-error', (event, { id, error }) => {
  console.error(`[${id}] キャプチャエラー:`, error);
});

// === コア機能（HTTP/WebSocket共用） ===

async function getWindowsList() {
  const sources = await desktopCapturer.getSources({
    types: ['window'],
    thumbnailSize: { width: 320, height: 240 },
  });
  return sources
    .filter(s => s.name && s.name.trim() !== '')
    .map(s => ({
      sourceId: s.id,
      name: s.name,
      thumbnailDataUrl: s.thumbnail.toDataURL(),
    }));
}

async function startCaptureSession({ sourceId, id: customId, fps, quality }) {
  if (!sourceId) throw new Error('sourceId is required');

  let sourceName = 'Unknown';
  try {
    const sources = await desktopCapturer.getSources({ types: ['window'], thumbnailSize: { width: 1, height: 1 } });
    const found = sources.find(s => s.id === sourceId);
    if (found) sourceName = found.name;
  } catch (e) {}

  const captureId = customId || `cap_${nextId++}`;

  if (captures.has(captureId)) stopCapture(captureId);

  const win = new BrowserWindow({
    show: false,
    width: 1920,
    height: 1080,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  const session = {
    id: captureId,
    sourceId,
    name: sourceName,
    window: win,
    latestFrame: null,
    clients: new Set(),
    fps: fps || DEFAULT_FPS,
  };

  captures.set(captureId, session);

  captureIndexMap.set(captureId, nextCaptureIndex++);

  if (wss) {
    const msg = JSON.stringify({
      type: 'capture_add',
      id: captureId,
      index: captureIndexMap.get(captureId),
      name: sourceName,
    });
    wss.clients.forEach(client => {
      if (client.readyState === WebSocket.OPEN) client.send(msg);
    });
  }

  win.loadFile('capture.html');
  win.webContents.on('did-finish-load', () => {
    win.webContents.send('start-capture', {
      id: captureId,
      sourceId,
      fps: session.fps,
      quality: quality || DEFAULT_QUALITY,
    });
  });

  return { ok: true, id: captureId, name: sourceName, stream_url: `/stream/${captureId}` };
}

function getCapturesList() {
  const list = [];
  for (const [id, session] of captures) {
    list.push({
      id,
      sourceId: session.sourceId,
      name: session.name,
      fps: session.fps,
      has_frame: session.latestFrame !== null,
      clients: session.clients.size,
    });
  }
  return list;
}

async function openPreview(serverUrl) {
  if (!serverUrl) throw new Error('serverUrl required');
  const tokenResp = await fetch(`${serverUrl}/api/broadcast/token`);
  const { token } = await tokenResp.json();
  const previewUrl = `${serverUrl}/preview?token=${token}`;

  if (previewWindow && !previewWindow.isDestroyed()) {
    previewWindow.loadURL(previewUrl);
    previewWindow.focus();
  } else {
    previewWindow = new BrowserWindow({
      width: 1580,
      height: 720,
      title: 'AI Twitch Cast - Preview',
      autoHideMenuBar: true,
      webPreferences: { contextIsolation: true, nodeIntegration: false },
    });
    previewWindow.setMenu(null);
    previewWindow.setMenuBarVisibility(false);
    previewWindow.loadURL(previewUrl);
    previewWindow.on('closed', () => { previewWindow = null; });
  }
  return { ok: true };
}

// === Express HTTPサーバー ===
function startServer() {
  const server = express();

  // CORS
  server.use((req, res, next) => {
    res.header('Access-Control-Allow-Origin', '*');
    res.header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS');
    res.header('Access-Control-Allow-Headers', 'Content-Type');
    if (req.method === 'OPTIONS') return res.sendStatus(204);
    next();
  });

  server.use(express.json());

  // GET /status
  server.get('/status', (req, res) => {
    res.json({ ok: true, captures: captures.size });
  });

  // GET /windows - ウィンドウ一覧
  server.get('/windows', async (req, res) => {
    try {
      res.json(await getWindowsList());
    } catch (e) {
      res.status(500).json({ error: e.message });
    }
  });

  // POST /capture - キャプチャ開始
  server.post('/capture', async (req, res) => {
    try {
      res.json(await startCaptureSession(req.body));
    } catch (e) {
      res.status(400).json({ ok: false, error: e.message });
    }
  });

  // DELETE /capture/:id - キャプチャ停止
  server.delete('/capture/:id', (req, res) => {
    const ok = stopCapture(req.params.id);
    res.json({ ok });
  });

  // GET /captures - アクティブキャプチャ一覧
  server.get('/captures', (req, res) => {
    res.json(getCapturesList());
  });

  // GET /stream/:id - MJPEGストリーム
  server.get('/stream/:id', (req, res) => {
    const session = captures.get(req.params.id);
    if (!session) {
      return res.status(404).json({ error: `capture '${req.params.id}' not found` });
    }

    res.writeHead(200, {
      'Content-Type': 'multipart/x-mixed-replace; boundary=frame',
      'Cache-Control': 'no-cache, no-store, must-revalidate',
      'Connection': 'keep-alive',
      'Access-Control-Allow-Origin': '*',
    });

    session.clients.add(res);
    req.on('close', () => session.clients.delete(res));
  });

  // GET /snapshot/:id - 単一フレーム
  server.get('/snapshot/:id', (req, res) => {
    const session = captures.get(req.params.id);
    if (!session) {
      return res.status(404).json({ error: `capture '${req.params.id}' not found` });
    }
    if (!session.latestFrame) {
      return res.status(503).json({ error: 'no frame yet' });
    }
    res.writeHead(200, {
      'Content-Type': 'image/jpeg',
      'Content-Length': session.latestFrame.length,
      'Access-Control-Allow-Origin': '*',
    });
    res.end(session.latestFrame);
  });

  // GET / - インデックス
  server.get('/', (req, res) => {
    const captureList = [];
    for (const [id, session] of captures) {
      captureList.push(`<div>
        <h3>${id}: ${session.name}</h3>
        <img src="/stream/${id}" style="max-width:480px;">
      </div>`);
    }
    res.send(`<!DOCTYPE html>
<html><body style="background:#1a1a2e;color:#eee;font-family:sans-serif;padding:20px;">
<h1>Window Capture Server</h1>
<p>Port: ${PORT} | Captures: ${captures.size}</p>
<h2>API</h2>
<ul>
<li><a href="/windows" style="color:#b388ff;">GET /windows</a></li>
<li><a href="/captures" style="color:#b388ff;">GET /captures</a></li>
<li>POST /capture - {sourceId, id?, fps?, quality?}</li>
<li>DELETE /capture/:id</li>
<li>GET /stream/:id</li>
<li>GET /snapshot/:id</li>
</ul>
<h2>Active Captures</h2>
${captureList.join('') || '<p>なし</p>'}
</body></html>`);
  });

  // === プレビューウィンドウ管理 ===

  // POST /preview/open - プレビューウィンドウを開く
  server.post('/preview/open', async (req, res) => {
    try {
      res.json(await openPreview(req.body.serverUrl));
    } catch (e) {
      res.status(500).json({ error: e.message });
    }
  });

  // POST /preview/close - プレビューウィンドウを閉じる
  server.post('/preview/close', (req, res) => {
    if (previewWindow && !previewWindow.isDestroyed()) previewWindow.close();
    res.json({ ok: true });
  });

  // GET /preview/status - プレビュー状態
  server.get('/preview/status', (req, res) => {
    res.json({ open: previewWindow !== null && !previewWindow.isDestroyed() });
  });

  // POST /quit - アプリ終了（asar更新後の再起動用）
  server.post('/quit', (req, res) => {
    res.json({ ok: true });
    setTimeout(() => app.quit(), 500);
  });

  const httpServer = server.listen(PORT, '0.0.0.0', () => {
    console.log(`=== Window Capture Server ===`);
    console.log(`ポート: ${PORT}`);
    console.log(`http://localhost:${PORT}/`);
  });

  // WebSocketサーバー（キャプチャフレーム配信用）
  wss = new WebSocket.Server({ server: httpServer, path: '/ws/capture' });

  wss.on('connection', (ws) => {
    console.log(`WebSocketクライアント接続 (計${wss.clients.size})`);
    // 現在のキャプチャ一覧を送信
    ws.send(JSON.stringify({
      type: 'captures',
      list: Array.from(captures.entries()).map(([id, session]) => ({
        id,
        index: captureIndexMap.get(id),
        name: session.name,
      })),
    }));
    ws.on('close', () => {
      console.log(`WebSocketクライアント切断 (残${wss.clients.size})`);
    });
  });

  // WebSocket制御サーバー（WSL2↔Electron コマンド制御用）
  const controlWss = new WebSocket.Server({ server: httpServer, path: '/ws/control' });

  controlWss.on('connection', (ws) => {
    console.log('制御WebSocket接続');

    ws.on('message', async (raw) => {
      let msg;
      try {
        msg = JSON.parse(raw);
      } catch (e) {
        return;
      }
      const { requestId, action } = msg;

      try {
        let result;
        switch (action) {
          case 'status':
            result = { ok: true, captures: captures.size };
            break;
          case 'windows':
            result = await getWindowsList();
            break;
          case 'start_capture':
            result = await startCaptureSession(msg);
            break;
          case 'stop_capture':
            result = { ok: stopCapture(msg.id) };
            break;
          case 'captures':
            result = getCapturesList();
            break;
          case 'preview_open':
            result = await openPreview(msg.serverUrl);
            break;
          case 'preview_close':
            if (previewWindow && !previewWindow.isDestroyed()) previewWindow.close();
            result = { ok: true };
            break;
          case 'preview_status':
            result = { open: previewWindow !== null && !previewWindow.isDestroyed() };
            break;
          case 'quit':
            result = { ok: true };
            setTimeout(() => app.quit(), 500);
            break;
          default:
            result = { ok: false, error: `unknown action: ${action}` };
        }
        ws.send(JSON.stringify({ requestId, ...(Array.isArray(result) ? { data: result } : result) }));
      } catch (e) {
        ws.send(JSON.stringify({ requestId, ok: false, error: e.message }));
      }
    });

    ws.on('close', () => console.log('制御WebSocket切断'));
  });
}

function stopCapture(id) {
  const session = captures.get(id);
  if (!session) return false;

  // MJPEGクライアントを閉じる
  for (const res of session.clients) {
    try { res.end(); } catch (e) {}
  }

  // BrowserWindowを閉じる
  try {
    if (!session.window.isDestroyed()) {
      session.window.close();
    }
  } catch (e) {}

  captures.delete(id);
  captureIndexMap.delete(id);

  // WebSocketクライアントにキャプチャ削除を通知
  if (wss) {
    const msg = JSON.stringify({ type: 'capture_remove', id });
    wss.clients.forEach(client => {
      if (client.readyState === WebSocket.OPEN) client.send(msg);
    });
  }

  console.log(`キャプチャ停止: ${id} (${session.name})`);
  return true;
}

// === Electron App Lifecycle ===
// UNCパス（\\wsl.localhost\...）から起動時のみGPUを無効化
if (app.getPath('exe').startsWith('\\\\')) {
  app.commandLine.appendSwitch('disable-gpu');
  app.commandLine.appendSwitch('disable-software-rasterizer');
}

app.whenReady().then(() => {
  Menu.setApplicationMenu(null);
  startServer();
});

app.on('window-all-closed', (e) => {
  // ウィンドウが全て閉じてもアプリを終了しない（サーバーとして動作）
  e.preventDefault();
});
