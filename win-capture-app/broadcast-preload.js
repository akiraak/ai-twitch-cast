/**
 * broadcast.html用プリロードスクリプト
 * オフスクリーン配信ウィンドウで音声キャプチャAPIを公開する
 */
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('audioCapture', {
  isAvailable: true,
  sendPCM: (buffer) => {
    ipcRenderer.send('audio-pcm', Buffer.from(buffer));
  },
});
