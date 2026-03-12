/**
 * Preload script - メインプロセスとレンダラー間のIPC bridge
 */

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('captureAPI', {
  onStartCapture(callback) {
    ipcRenderer.on('start-capture', (event, config) => callback(config));
  },
  sendFrame(id, jpegArrayBuffer) {
    ipcRenderer.send('capture-frame', { id, jpeg: jpegArrayBuffer });
  },
  sendError(id, error) {
    ipcRenderer.send('capture-error', { id, error });
  },
});
