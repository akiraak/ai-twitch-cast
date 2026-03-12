/**
 * AI Twitch Cast - Window Capture Server (Electron Main Process)
 *
 * Windowsウィンドウをキャプチャし、MJPEGストリームとして配信する。
 * WSL2側のbroadcast.htmlがこのストリームを<img>で表示する。
 */

const { app, BrowserWindow, Menu, desktopCapturer, ipcMain } = require('electron');
const express = require('express');
const path = require('path');

const PORT = parseInt(process.env.WIN_CAPTURE_PORT || '9090');
const DEFAULT_FPS = parseInt(process.env.WIN_CAPTURE_FPS || '15');
const DEFAULT_QUALITY = parseFloat(process.env.WIN_CAPTURE_QUALITY || '0.7');

// キャプチャセッション管理
const captures = new Map(); // id -> CaptureSession
let nextId = 0;

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

  // 全MJPEGクライアントにプッシュ
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
});

ipcMain.on('capture-error', (event, { id, error }) => {
  console.error(`[${id}] キャプチャエラー:`, error);
});

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
      const sources = await desktopCapturer.getSources({
        types: ['window'],
        thumbnailSize: { width: 320, height: 240 },
      });
      const windows = sources
        .filter(s => s.name && s.name.trim() !== '')
        .map(s => ({
          sourceId: s.id,
          name: s.name,
          thumbnailDataUrl: s.thumbnail.toDataURL(),
        }));
      res.json(windows);
    } catch (e) {
      res.status(500).json({ error: e.message });
    }
  });

  // POST /capture - キャプチャ開始
  server.post('/capture', async (req, res) => {
    const { sourceId, id: customId, fps, quality } = req.body;
    if (!sourceId) {
      return res.status(400).json({ ok: false, error: 'sourceId is required' });
    }

    // ソース名を取得
    let sourceName = 'Unknown';
    try {
      const sources = await desktopCapturer.getSources({ types: ['window'], thumbnailSize: { width: 1, height: 1 } });
      const found = sources.find(s => s.id === sourceId);
      if (found) sourceName = found.name;
    } catch (e) {}

    const captureId = customId || `cap_${nextId++}`;

    // 既存セッションがあれば停止
    if (captures.has(captureId)) {
      stopCapture(captureId);
    }

    // 非表示BrowserWindowを作成
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

    win.loadFile('capture.html');
    win.webContents.on('did-finish-load', () => {
      win.webContents.send('start-capture', {
        id: captureId,
        sourceId,
        fps: session.fps,
        quality: quality || DEFAULT_QUALITY,
      });
    });

    res.json({
      ok: true,
      id: captureId,
      name: sourceName,
      stream_url: `/stream/${captureId}`,
    });
  });

  // DELETE /capture/:id - キャプチャ停止
  server.delete('/capture/:id', (req, res) => {
    const ok = stopCapture(req.params.id);
    res.json({ ok });
  });

  // GET /captures - アクティブキャプチャ一覧
  server.get('/captures', (req, res) => {
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
    res.json(list);
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
    const { serverUrl } = req.body;
    if (!serverUrl) {
      return res.status(400).json({ error: 'serverUrl required' });
    }

    try {
      // WSLサーバーからbroadcastトークンを取得
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
          webPreferences: {
            contextIsolation: true,
            nodeIntegration: false,
          },
        });
        previewWindow.setMenu(null);
        previewWindow.setMenuBarVisibility(false);
        previewWindow.loadURL(previewUrl);
        previewWindow.on('closed', () => { previewWindow = null; });
      }

      res.json({ ok: true });
    } catch (e) {
      res.status(500).json({ error: e.message });
    }
  });

  // POST /preview/close - プレビューウィンドウを閉じる
  server.post('/preview/close', (req, res) => {
    if (previewWindow && !previewWindow.isDestroyed()) {
      previewWindow.close();
    }
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

  server.listen(PORT, '0.0.0.0', () => {
    console.log(`=== Window Capture Server ===`);
    console.log(`ポート: ${PORT}`);
    console.log(`http://localhost:${PORT}/`);
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
