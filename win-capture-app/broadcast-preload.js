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
  // メインプロセスに音声URLを通知（ブラウザAudioContextバイパス）
  notifyPlayAudio: (url) => {
    ipcRenderer.send('audio-play-url', { type: 'tts', url });
  },
  notifyPlayBgm: (url) => {
    ipcRenderer.send('audio-play-url', { type: 'bgm', url });
  },
  notifyStopBgm: () => {
    ipcRenderer.send('audio-stop-bgm');
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
  // broadcast.html側でリスナ登録完了後に呼ぶ → main.jsが既存キャプチャ一覧を送信
  notifyReady() {
    ipcRenderer.send('capture-receiver-ready');
  },
});
