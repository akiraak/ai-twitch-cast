/**
 * AI Twitch Cast - Window Capture & Streaming Server (Electron Main Process)
 *
 * 1. Windowsウィンドウをキャプチャし、MJPEGストリームとして配信する
 * 2. broadcast.htmlをオフスクリーンレンダリングし、FFmpegでTwitchに直接配信する
 *    (xvfb/PulseAudioなしでWindows上で配信パイプラインを完結)
 */

const { app, BrowserWindow, Menu, desktopCapturer, ipcMain } = require('electron');
const { spawn, execSync } = require('child_process');
const express = require('express');
const fs = require('fs');
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

// === 配信ストリーミング状態 ===
let broadcastWindow = null;    // オフスクリーンBrowserWindow（broadcast.html）
let ffmpegProcess = null;      // FFmpeg child_process
let streamStartTime = null;    // 配信開始時刻（ms）
let streamConfig = null;       // 現在の配信設定
let frameCount = 0;            // 送信フレーム数
let frameDropCount = 0;        // ドロップフレーム数
let ffmpegLastLog = [];        // FFmpeg stderrの最後のログ（診断用）

// === 音声ストリーミング（HTTP経由でFFmpegに送信） ===
let audioSilenceTimer = null;   // サイレンスハートビート
let lastAudioPcmTime = 0;      // 最後にPCMデータを受信した時刻
let audioStreamRes = null;      // FFmpegへのHTTPレスポンス（PCMストリーム）

const STREAM_DEFAULTS = {
  resolution: '1920x1080',
  framerate: 30,
  videoBitrate: '3500k',
  audioBitrate: '128k',
  preset: 'ultrafast',
};

function getFfmpegPath() {
  // 1. ビルド済みアプリ: resources/ffmpeg/ffmpeg.exe
  const bundled = path.join(process.resourcesPath, 'ffmpeg', 'ffmpeg.exe');
  if (fs.existsSync(bundled)) return bundled;

  // 2. exe横のffmpegディレクトリ（デプロイ先で自動ダウンロードした場合）
  const exeDir = app.isPackaged
    ? path.dirname(process.execPath)
    : __dirname;
  const exeSibling = path.join(exeDir, 'ffmpeg', 'ffmpeg.exe');
  if (fs.existsSync(exeSibling)) return exeSibling;

  // 3. 開発時: ./ffmpeg/ffmpeg.exe（exeSiblingと同じになる場合あり）
  const dev = path.join(__dirname, 'ffmpeg', 'ffmpeg.exe');
  if (dev !== exeSibling && fs.existsSync(dev)) return dev;

  // 4. PATHにffmpegがあるかチェック（Windows: where, Unix: which）
  try {
    const cmd = process.platform === 'win32' ? 'where ffmpeg' : 'which ffmpeg';
    const result = execSync(cmd, { encoding: 'utf-8', timeout: 5000 }).trim();
    if (result) return result.split('\n')[0].trim();
  } catch (_) {
    // PATHにない
  }

  // 5. フォールバック: ダウンロード先パス（まだ存在しないが、downloadFfmpegで配置される）
  return exeSibling;
}

/**
 * FFmpegをダウンロードして配置する（Windows専用）
 * BtbN FFmpeg Builds (GPL版) を使用
 */
async function downloadFfmpeg() {
  // asar内は書き込み不可なので、exeと同階層 or userDataに配置
  const exeDir = app.isPackaged
    ? path.dirname(process.execPath)
    : __dirname;
  const targetDir = path.join(exeDir, 'ffmpeg');
  const targetExe = path.join(targetDir, 'ffmpeg.exe');
  if (fs.existsSync(targetExe)) return targetExe;

  console.log('FFmpegが見つかりません。自動ダウンロードを開始します...');

  if (!fs.existsSync(targetDir)) {
    fs.mkdirSync(targetDir, { recursive: true });
  }

  // PowerShellでダウンロード＋展開（Windows環境前提）
  const zipPath = path.join(targetDir, 'ffmpeg-temp.zip');
  const extractDir = path.join(targetDir, 'temp-extract');

  const psScript = `
$ProgressPreference = 'SilentlyContinue'
$url = 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip'
Write-Host "Downloading FFmpeg..."
Invoke-WebRequest -Uri $url -OutFile '${zipPath.replace(/\\/g, '\\\\')}'
Write-Host "Extracting..."
Expand-Archive -Path '${zipPath.replace(/\\/g, '\\\\')}' -DestinationPath '${extractDir.replace(/\\/g, '\\\\')}' -Force
$ffmpegExe = Get-ChildItem -Path '${extractDir.replace(/\\/g, '\\\\')}' -Filter ffmpeg.exe -Recurse | Where-Object { $_.Directory.Name -eq 'bin' } | Select-Object -First 1
if ($ffmpegExe) {
  Copy-Item $ffmpegExe.FullName '${targetExe.replace(/\\/g, '\\\\')}'
  Write-Host "OK"
} else {
  Write-Host "ERROR: ffmpeg.exe not found in archive"
  exit 1
}
`;

  return new Promise((resolve, reject) => {
    const ps = spawn('powershell', ['-NoProfile', '-Command', psScript], {
      stdio: ['ignore', 'pipe', 'pipe'],
    });

    let stdout = '';
    let stderr = '';
    ps.stdout.on('data', (d) => { stdout += d; console.log('[FFmpegDL]', d.toString().trim()); });
    ps.stderr.on('data', (d) => { stderr += d; });

    ps.on('close', (code) => {
      // クリーンアップ
      try { fs.rmSync(zipPath, { force: true }); } catch (_) {}
      try { fs.rmSync(extractDir, { recursive: true, force: true }); } catch (_) {}

      if (code === 0 && fs.existsSync(targetExe)) {
        const size = fs.statSync(targetExe).size;
        console.log(`FFmpegダウンロード完了: ${(size / 1024 / 1024).toFixed(1)} MB`);
        resolve(targetExe);
      } else {
        reject(new Error(`FFmpegダウンロード失敗 (code: ${code}): ${stderr || stdout}`));
      }
    });

    ps.on('error', (err) => {
      reject(new Error(`FFmpegダウンロード失敗: ${err.message}`));
    });
  });
}

function stopAudioSilenceTimer() {
  if (audioSilenceTimer) {
    clearInterval(audioSilenceTimer);
    audioSilenceTimer = null;
  }
}

// IPC: broadcast.htmlのcaptureReceiver準備完了 → 既存キャプチャ一覧を送信
ipcMain.on('capture-receiver-ready', () => {
  if (!broadcastWindow || broadcastWindow.isDestroyed()) return;
  console.log(`[DirectCapture] 準備完了、既存キャプチャ${captures.size}件を送信`);
  for (const [id, session] of captures) {
    broadcastWindow.webContents.send('capture-add-to-broadcast', {
      id,
      index: captureIndexMap.get(id),
      name: session.name,
    });
  }
});

// IPC: broadcast.htmlからPCM音声データ受信 → HTTP経由でFFmpegに送信
ipcMain.on('audio-pcm', (event, buffer) => {
  if (audioStreamRes && !audioStreamRes.destroyed) {
    try {
      lastAudioPcmTime = Date.now();
      audioStreamRes.write(Buffer.from(buffer));
    } catch (e) {}
  }
});

// ウィンドウ位置の永続化
const BOUNDS_FILE = path.join(app.getPath('userData'), 'preview-bounds.json');
let _saveBoundsTimer = null;

function saveBounds() {
  if (!previewWindow || previewWindow.isDestroyed()) return;
  const bounds = previewWindow.getBounds();
  try {
    fs.writeFileSync(BOUNDS_FILE, JSON.stringify(bounds));
  } catch (e) {}
}

function loadBounds() {
  try {
    return JSON.parse(fs.readFileSync(BOUNDS_FILE, 'utf-8'));
  } catch (e) {
    return null;
  }
}

function debouncedSaveBounds() {
  if (_saveBoundsTimer) clearTimeout(_saveBoundsTimer);
  _saveBoundsTimer = setTimeout(saveBounds, 300);
}

/**
 * @typedef {Object} CaptureSession
 * @property {string} id
 * @property {string} sourceId - desktopCapturer source ID
 * @property {string} name - ウィンドウ名
 * @property {BrowserWindow} window - 非表示レンダラーウィンドウ
 * @property {Buffer|null} latestFrame - 最新JPEGフレーム
 * @property {number} fps
 */

// === IPC: レンダラーからフレーム受信 ===
ipcMain.on('capture-frame', (event, { id, jpeg }) => {
  const session = captures.get(id);
  if (!session) return;

  const buf = Buffer.from(jpeg);
  session.latestFrame = buf;

  // broadcastWindowへIPC直接送信（Phase 6: MJPEG/WebSocket不要の高速パス）
  if (broadcastWindow && !broadcastWindow.isDestroyed()) {
    broadcastWindow.webContents.send('capture-frame-to-broadcast', { id, jpeg });
  }

  // WebSocketクライアントにバイナリ送信（プレビューウィンドウ用）
  const captureIdx = captureIndexMap.get(id);
  if (captureIdx !== undefined && wss && wss.clients.size > 0) {
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

  // broadcastWindowへキャプチャ追加を通知（IPC直接受信用）
  if (broadcastWindow && !broadcastWindow.isDestroyed()) {
    broadcastWindow.webContents.send('capture-add-to-broadcast', {
      id: captureId,
      index: captureIndexMap.get(captureId),
      name: sourceName,
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
    const saved = loadBounds();
    previewWindow = new BrowserWindow({
      width: saved?.width || 1580,
      height: saved?.height || 720,
      x: saved?.x,
      y: saved?.y,
      title: 'AI Twitch Cast - Preview',
      autoHideMenuBar: true,
      webPreferences: { contextIsolation: true, nodeIntegration: false },
    });
    previewWindow.setMenu(null);
    previewWindow.setMenuBarVisibility(false);
    previewWindow.loadURL(previewUrl);
    previewWindow.on('move', debouncedSaveBounds);
    previewWindow.on('resize', debouncedSaveBounds);
    previewWindow.on('closed', () => { previewWindow = null; });
  }
  return { ok: true };
}

// === 配信ストリーミング（Electron→FFmpeg→Twitch） ===

async function openBroadcastWindow(serverUrl) {
  if (broadcastWindow && !broadcastWindow.isDestroyed()) {
    return { ok: true, already_open: true };
  }

  const tokenResp = await fetch(`${serverUrl}/api/broadcast/token`);
  const { token } = await tokenResp.json();
  const broadcastUrl = `${serverUrl}/broadcast?token=${token}`;

  const cfg = streamConfig || STREAM_DEFAULTS;
  const [width, height] = cfg.resolution.split('x').map(Number);

  broadcastWindow = new BrowserWindow({
    width,
    height,
    show: false,
    webPreferences: {
      offscreen: true,
      backgroundThrottling: false,  // 音声処理が停止されないようにする
      preload: path.join(__dirname, 'broadcast-preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  broadcastWindow.webContents.setAudioMuted(false);  // 明示的に音声ミュート解除
  broadcastWindow.webContents.setFrameRate(cfg.framerate);
  // broadcast.htmlのconsole出力をメインプロセスに転送（音声デバッグ用）
  broadcastWindow.webContents.on('console-message', (_e, level, msg) => {
    console.log(`[Broadcast] ${msg}`);
  });
  broadcastWindow.loadURL(broadcastUrl);
  broadcastWindow.on('closed', () => {
    broadcastWindow = null;
    // 配信中にウィンドウが閉じたら配信も停止
    if (ffmpegProcess) {
      console.log('配信ウィンドウが閉じたため配信停止');
      stopStream();
    }
  });

  console.log(`配信ウィンドウ作成: ${width}x${height} @ ${cfg.framerate}fps`);
  return { ok: true };
}

function closeBroadcastWindow() {
  if (broadcastWindow && !broadcastWindow.isDestroyed()) {
    broadcastWindow.close();
  }
  broadcastWindow = null;
  return { ok: true };
}

function onBroadcastPaint(event, dirty, image) {
  if (!ffmpegProcess || !ffmpegProcess.stdin || !ffmpegProcess.stdin.writable) return;

  // バックプレッシャー: バッファが溜まっている場合はフレームをスキップ（2フレーム分≒16MB）
  if (ffmpegProcess.stdin.writableLength > 1024 * 1024 * 16) {
    frameDropCount++;
    return;
  }

  try {
    const bitmap = image.toBitmap();
    ffmpegProcess.stdin.write(bitmap);
    frameCount++;
  } catch (e) {
    // FFmpegのstdinが閉じている場合は無視
    frameDropCount++;
  }
}

async function startStream(config) {
  if (ffmpegProcess) {
    return { ok: false, error: '既に配信中です' };
  }

  const streamKey = config.streamKey;
  if (!streamKey) {
    return { ok: false, error: 'streamKey が必要です' };
  }

  // 設定をマージ
  streamConfig = { ...STREAM_DEFAULTS };
  if (config.resolution) streamConfig.resolution = config.resolution;
  if (config.framerate) streamConfig.framerate = parseInt(config.framerate);
  if (config.videoBitrate) streamConfig.videoBitrate = config.videoBitrate;
  if (config.audioBitrate) streamConfig.audioBitrate = config.audioBitrate;
  if (config.preset) streamConfig.preset = config.preset;

  const { resolution, framerate, videoBitrate, audioBitrate, preset } = streamConfig;

  // 配信ウィンドウを開く（未オープンの場合）
  if (!broadcastWindow || broadcastWindow.isDestroyed()) {
    if (!config.serverUrl) {
      return { ok: false, error: 'serverUrl が必要です（配信ウィンドウ未オープン）' };
    }
    await openBroadcastWindow(config.serverUrl);
    // ページ読み込み完了を待つ
    await new Promise(resolve => setTimeout(resolve, 3000));
  }

  const rtmpUrl = `rtmp://live-tyo.twitch.tv/app/${streamKey}`;

  // FFmpegコマンド: rawvideo(pipe:0) + 音声(HTTP PCMストリーム) → H.264+AAC → RTMP
  const ffmpegArgs = [
    // 映像入力: パイプからBGRA rawvideo
    '-thread_queue_size', '512',
    '-f', 'rawvideo',
    '-pixel_format', 'bgra',
    '-video_size', resolution,
    '-framerate', String(framerate),
    '-i', 'pipe:0',
    // 音声入力: ローカルHTTP経由でbroadcast.htmlのPCM音声を受け取る
    '-probesize', '32',
    '-analyzeduration', '0',
    '-thread_queue_size', '4096',
    '-f', 's16le',
    '-ar', '44100',
    '-ac', '2',
    '-i', `http://127.0.0.1:${PORT}/audio-pcm-stream`,
  ];

  ffmpegArgs.push(
    // 映像エンコード
    '-c:v', 'libx264',
    '-preset', preset,
    '-tune', 'zerolatency',
    '-b:v', videoBitrate,
    '-maxrate', videoBitrate,
    '-bufsize', videoBitrate,
    '-pix_fmt', 'yuv420p',
    '-g', String(framerate * 2),
    // 音声エンコード
    '-c:a', 'aac',
    '-b:a', audioBitrate,
    '-ar', '44100',
    // 出力
    '-f', 'flv',
    rtmpUrl,
  );

  let ffmpegBin = getFfmpegPath();

  // FFmpegが見つからない場合、自動ダウンロードを試みる
  if (!fs.existsSync(ffmpegBin)) {
    if (process.platform === 'win32') {
      console.log('FFmpegが見つかりません。自動ダウンロードを試みます...');
      try {
        ffmpegBin = await downloadFfmpeg();
      } catch (e) {
        return { ok: false, error: `FFmpegの自動ダウンロードに失敗しました: ${e.message}` };
      }
    } else {
      return { ok: false, error: `FFmpegが見つかりません（検索パス: ${ffmpegBin}）` };
    }
  }

  console.log('FFmpeg起動:', ffmpegBin, ffmpegArgs.join(' '));

  try {
    ffmpegProcess = spawn(ffmpegBin, ffmpegArgs, {
      stdio: ['pipe', 'pipe', 'pipe'],
    });
  } catch (e) {
    return { ok: false, error: `FFmpeg起動失敗: ${e.message}（パス: ${ffmpegBin}）` };
  }

  // spawnは非同期なので、プロセスが即座に失敗するケースを検出する
  const spawnResult = await new Promise((resolve) => {
    let settled = false;
    const onError = (err) => {
      if (!settled) {
        settled = true;
        resolve({ ok: false, error: `FFmpeg起動失敗: ${err.message}（パス: ${ffmpegBin}）` });
      }
    };
    const onClose = (code) => {
      if (!settled) {
        settled = true;
        resolve({ ok: false, error: `FFmpegが即座に終了しました (code: ${code})。ffmpegがPATHに存在するか確認してください（検索パス: ${ffmpegBin}）` });
      }
    };
    ffmpegProcess.on('error', onError);
    ffmpegProcess.on('close', onClose);
    // 500ms待って生存確認
    setTimeout(() => {
      if (!settled) {
        settled = true;
        ffmpegProcess.removeListener('error', onError);
        ffmpegProcess.removeListener('close', onClose);
        resolve({ ok: true });
      }
    }, 500);
  });

  if (!spawnResult.ok) {
    stopAudioSilenceTimer();
    ffmpegProcess = null;
    streamStartTime = null;
    return spawnResult;
  }

  // stdinのエラーハンドラ（パイプ破損でクラッシュしないように）
  ffmpegProcess.stdin.on('error', (err) => {
    console.warn('FFmpeg stdin エラー（無視）:', err.message);
  });

  // サイレンスハートビート: PCMデータが来ない場合にサイレンスを送り続ける
  // （AudioContextがsuspendの場合や、broadcast.html未読み込み時の対策）
  lastAudioPcmTime = Date.now();
  stopAudioSilenceTimer();
  audioSilenceTimer = setInterval(() => {
    if (!audioStreamRes || audioStreamRes.destroyed) {
      return;
    }
    if (Date.now() - lastAudioPcmTime > 300) {
      try {
        // 300ms分のサイレンス（s16le, 44100Hz, stereo）
        audioStreamRes.write(Buffer.alloc(Math.floor(44100 * 2 * 2 * 0.3)));
      } catch (e) {}
    }
  }, 300);

  ffmpegLastLog = [];
  ffmpegProcess.stderr.on('data', (data) => {
    const line = data.toString().trim();
    if (line) {
      console.log('[FFmpeg]', line);
      ffmpegLastLog.push(line);
      // 最後の20行だけ保持
      if (ffmpegLastLog.length > 20) ffmpegLastLog.shift();
    }
  });

  ffmpegProcess.on('close', (code) => {
    console.log(`FFmpeg終了 (code: ${code})`);
    // paintリスナーを解除
    if (broadcastWindow && !broadcastWindow.isDestroyed()) {
      broadcastWindow.webContents.removeListener('paint', onBroadcastPaint);
    }
    stopAudioSilenceTimer();
    ffmpegProcess = null;
    streamStartTime = null;
  });

  ffmpegProcess.on('error', (err) => {
    console.error('FFmpegプロセスエラー:', err.message);
    // paintリスナーを解除
    if (broadcastWindow && !broadcastWindow.isDestroyed()) {
      broadcastWindow.webContents.removeListener('paint', onBroadcastPaint);
    }
    stopAudioSilenceTimer();
    ffmpegProcess = null;
    streamStartTime = null;
  });

  // フレーム送信開始
  frameCount = 0;
  frameDropCount = 0;
  broadcastWindow.webContents.on('paint', onBroadcastPaint);

  streamStartTime = Date.now();
  console.log(`配信開始: ${resolution} @ ${framerate}fps → Twitch`);

  return { ok: true };
}

function stopStream() {
  if (!ffmpegProcess) {
    return { ok: false, error: '配信中ではありません' };
  }

  // paintリスナーを解除
  if (broadcastWindow && !broadcastWindow.isDestroyed()) {
    broadcastWindow.webContents.removeListener('paint', onBroadcastPaint);
  }

  const result = {
    ok: true,
    uptime_seconds: streamStartTime ? Math.floor((Date.now() - streamStartTime) / 1000) : 0,
    frames_sent: frameCount,
    frames_dropped: frameDropCount,
  };

  // FFmpegを安全に停止: stdin閉じる → SIGTERM → SIGKILL
  const proc = ffmpegProcess;
  try {
    proc.stdin.end();
  } catch (e) {}

  setTimeout(() => {
    if (proc && proc.exitCode === null) {
      try { proc.kill('SIGTERM'); } catch (e) {}
      setTimeout(() => {
        if (proc && proc.exitCode === null) {
          try { proc.kill('SIGKILL'); } catch (e) {}
        }
      }, 5000);
    }
  }, 2000);

  // 音声HTTPストリームを閉じる
  if (audioStreamRes && !audioStreamRes.destroyed) {
    try { audioStreamRes.end(); } catch (e) {}
    audioStreamRes = null;
  }
  stopAudioSilenceTimer();

  console.log(`配信停止: ${result.uptime_seconds}秒, ${frameCount}フレーム送信, ${frameDropCount}フレームドロップ`);

  return result;
}

function getStreamStatus() {
  const ffmpegBin = getFfmpegPath();
  const ffmpegExists = fs.existsSync(ffmpegBin);
  return {
    streaming: ffmpegProcess !== null && ffmpegProcess.exitCode === null,
    broadcast_window_open: broadcastWindow !== null && !broadcastWindow.isDestroyed(),
    uptime_seconds: streamStartTime ? Math.floor((Date.now() - streamStartTime) / 1000) : null,
    frames_sent: frameCount,
    frames_dropped: frameDropCount,
    config: streamConfig,
    ffmpeg_path: ffmpegBin,
    ffmpeg_exists: ffmpegExists,
    ffmpeg_log: ffmpegLastLog.slice(-5),
    audio_stream_connected: audioStreamRes !== null && !audioStreamRes.destroyed,
    audio_receiving_pcm: lastAudioPcmTime > 0 && (Date.now() - lastAudioPcmTime) < 1000,
  };
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

  // GET /audio-pcm-stream - FFmpegが音声PCMを読み取るHTTPストリーム
  server.get('/audio-pcm-stream', (req, res) => {
    res.writeHead(200, {
      'Content-Type': 'application/octet-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
    });
    // 初期サイレンス送信（FFmpegの入力初期化ブロックを防止）
    res.write(Buffer.alloc(44100 * 2 * 2));  // 1秒分 s16le stereo
    audioStreamRes = res;
    console.log('[AudioStream] FFmpeg音声ストリーム接続');
    req.on('close', () => {
      console.log('[AudioStream] FFmpeg音声ストリーム切断');
      audioStreamRes = null;
    });
  });

  // GET /status
  server.get('/status', (req, res) => {
    res.json({
      ok: true,
      captures: captures.size,
      streaming: ffmpegProcess !== null && ffmpegProcess.exitCode === null,
      broadcast_window: broadcastWindow !== null && !broadcastWindow.isDestroyed(),
    });
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

  // GET /stream/:id - MJPEGストリーム（廃止: snapshotにリダイレクト）
  server.get('/stream/:id', (req, res) => {
    res.redirect(`/snapshot/${req.params.id}`);
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
        <img src="/snapshot/${id}" style="max-width:480px;">
      </div>`);
    }
    const streamStatus = getStreamStatus();
    res.send(`<!DOCTYPE html>
<html><body style="background:#1a1a2e;color:#eee;font-family:sans-serif;padding:20px;">
<h1>Window Capture & Streaming Server</h1>
<p>Port: ${PORT} | Captures: ${captures.size} | Streaming: ${streamStatus.streaming ? '配信中' : '停止'}</p>
<h2>Capture API</h2>
<ul>
<li><a href="/windows" style="color:#b388ff;">GET /windows</a></li>
<li><a href="/captures" style="color:#b388ff;">GET /captures</a></li>
<li>POST /capture - {sourceId, id?, fps?, quality?}</li>
<li>DELETE /capture/:id</li>
<li>GET /stream/:id</li>
<li>GET /snapshot/:id</li>
</ul>
<h2>Streaming API</h2>
<ul>
<li>POST /stream/start - {streamKey, serverUrl, resolution?, framerate?, videoBitrate?}</li>
<li>POST /stream/stop</li>
<li><a href="/stream/status" style="color:#b388ff;">GET /stream/status</a></li>
<li>POST /broadcast/open - {serverUrl}</li>
<li>POST /broadcast/close</li>
<li><a href="/broadcast/status" style="color:#b388ff;">GET /broadcast/status</a></li>
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

  // === 配信ストリーミング ===

  // POST /stream/start - 配信開始
  server.post('/stream/start', async (req, res) => {
    try {
      res.json(await startStream(req.body));
    } catch (e) {
      res.status(500).json({ ok: false, error: e.message });
    }
  });

  // POST /stream/stop - 配信停止
  server.post('/stream/stop', (req, res) => {
    res.json(stopStream());
  });

  // GET /stream/status - 配信状態
  server.get('/stream/status', (req, res) => {
    res.json(getStreamStatus());
  });

  // POST /broadcast/open - 配信ウィンドウ（オフスクリーン）を開く
  server.post('/broadcast/open', async (req, res) => {
    try {
      res.json(await openBroadcastWindow(req.body.serverUrl));
    } catch (e) {
      res.status(500).json({ ok: false, error: e.message });
    }
  });

  // POST /broadcast/close - 配信ウィンドウを閉じる
  server.post('/broadcast/close', (req, res) => {
    res.json(closeBroadcastWindow());
  });

  // GET /broadcast/status - 配信ウィンドウ状態
  server.get('/broadcast/status', (req, res) => {
    res.json({
      open: broadcastWindow !== null && !broadcastWindow.isDestroyed(),
      streaming: ffmpegProcess !== null && ffmpegProcess.exitCode === null,
    });
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

  // WebSocketサーバー（noServerモードで手動振り分け）
  wss = new WebSocket.Server({ noServer: true, perMessageDeflate: false });
  const controlWss = new WebSocket.Server({ noServer: true, perMessageDeflate: false });

  httpServer.on('upgrade', (request, socket, head) => {
    const { pathname } = new URL(request.url, `http://${request.headers.host}`);
    if (pathname === '/ws/capture') {
      wss.handleUpgrade(request, socket, head, (ws) => wss.emit('connection', ws, request));
    } else if (pathname === '/ws/control') {
      controlWss.handleUpgrade(request, socket, head, (ws) => controlWss.emit('connection', ws, request));
    } else {
      socket.destroy();
    }
  });

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
            result = {
              ok: true,
              captures: captures.size,
              streaming: ffmpegProcess !== null && ffmpegProcess.exitCode === null,
              broadcast_window: broadcastWindow !== null && !broadcastWindow.isDestroyed(),
            };
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
          case 'broadcast_open':
            result = await openBroadcastWindow(msg.serverUrl);
            break;
          case 'broadcast_close':
            result = closeBroadcastWindow();
            break;
          case 'start_stream':
            result = await startStream(msg);
            break;
          case 'stop_stream':
            result = stopStream();
            break;
          case 'stream_status':
            result = getStreamStatus();
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

  // BrowserWindowを閉じる
  try {
    if (!session.window.isDestroyed()) {
      session.window.close();
    }
  } catch (e) {}

  captures.delete(id);
  captureIndexMap.delete(id);

  // broadcastWindowへキャプチャ削除を通知（IPC直接受信用）
  if (broadcastWindow && !broadcastWindow.isDestroyed()) {
    broadcastWindow.webContents.send('capture-remove-to-broadcast', { id });
  }

  // WebSocketクライアントにキャプチャ削除を通知（プレビュー用）
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
// DPIスケーリングを1に固定（オフスクリーンレンダリングのサイズを正確にする）
app.commandLine.appendSwitch('force-device-scale-factor', '1');
// オフスクリーンでAudioContextが動作するようにする（ユーザージェスチャー不要）
app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required');

// UNCパス（\\wsl.localhost\...）から起動時のみGPUを無効化
if (app.getPath('exe').startsWith('\\\\')) {
  app.commandLine.appendSwitch('disable-gpu');
  app.commandLine.appendSwitch('disable-software-rasterizer');
}

// 未処理例外でクラッシュしないようにする
process.on('uncaughtException', (err) => {
  console.error('未処理例外（クラッシュ防止）:', err.message, err.stack);
});
process.on('unhandledRejection', (reason) => {
  console.error('未処理Promise拒否:', reason);
});

app.whenReady().then(() => {
  Menu.setApplicationMenu(null);
  startServer();
});

app.on('window-all-closed', (e) => {
  // ウィンドウが全て閉じてもアプリを終了しない（サーバーとして動作）
  e.preventDefault();
});

app.on('before-quit', () => {
  // 配信中ならFFmpegを停止
  if (ffmpegProcess) {
    console.log('アプリ終了: 配信停止');
    stopStream();
  }
  if (broadcastWindow && !broadcastWindow.isDestroyed()) {
    broadcastWindow.close();
  }
});
