/**
 * Capture Renderer - ウィンドウキャプチャ + JPEG書き出し
 *
 * 非表示BrowserWindow内で動作。
 * getUserMediaでウィンドウのMediaStreamを取得し、
 * canvasでフレームを描画→JPEG変換→メインプロセスへIPC送信。
 */

const video = document.getElementById('video');
const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');

let captureId = null;
let intervalId = null;

window.captureAPI.onStartCapture(async (config) => {
  captureId = config.id;
  const fps = config.fps || 15;
  const quality = config.quality || 0.7;

  try {
    // getUserMediaでウィンドウストリーム取得
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: {
        mandatory: {
          chromeMediaSource: 'desktop',
          chromeMediaSourceId: config.sourceId,
        },
      },
    });

    video.srcObject = stream;
    await video.play();

    // canvasサイズをビデオに合わせる
    canvas.width = video.videoWidth || 1920;
    canvas.height = video.videoHeight || 1080;

    // ビデオサイズが確定したらリサイズ
    video.addEventListener('resize', () => {
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
    });

    // フレームキャプチャループ
    const interval = 1000 / fps;
    intervalId = setInterval(() => {
      if (video.readyState < 2) return; // HAVE_CURRENT_DATA以上

      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

      canvas.toBlob((blob) => {
        if (!blob) return;
        blob.arrayBuffer().then((ab) => {
          window.captureAPI.sendFrame(captureId, ab);
        });
      }, 'image/jpeg', quality);
    }, interval);

    console.log(`キャプチャ開始: ${captureId} (${fps}fps, quality=${quality})`);
  } catch (e) {
    console.error('キャプチャ開始失敗:', e);
    window.captureAPI.sendError(captureId, e.message);
  }
});
