/**
 * broadcast.html用プリロードスクリプト
 * オフスクリーン配信ウィンドウで音声キャプチャ・キャプチャ受信APIを公開する
 */
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('audioCapture', {
  isAvailable: true,
  sendPCM: (buffer) => {
    ipcRenderer.send('audio-pcm', Buffer.from(buffer));
  },
});

// Phase 6: キャプチャフレームIPC直接受信（MJPEG/WebSocket不要）
contextBridge.exposeInMainWorld('captureReceiver', {
  isAvailable: true,
  onFrame(callback) {
    ipcRenderer.on('capture-frame-to-broadcast', (_event, { id, jpeg }) => {
      callback(id, jpeg);
    });
  },
  onCaptureAdd(callback) {
    ipcRenderer.on('capture-add-to-broadcast', (_event, data) => callback(data));
  },
  onCaptureRemove(callback) {
    ipcRenderer.on('capture-remove-to-broadcast', (_event, data) => callback(data));
  },
});
