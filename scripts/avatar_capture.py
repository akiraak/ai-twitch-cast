"""
アバターキャプチャサーバー（Windows側で実行）

VSeeFaceウィンドウをキャプチャし、MJPEGストリームとして配信する。
WSL2側のbroadcast.htmlがこのストリームを<img>で表示する。

使い方（Windows PowerShell / cmd）:
  pip install mss Pillow
  python avatar_capture.py

環境変数:
  AVATAR_CAPTURE_PORT  - ポート番号（デフォルト: 9090）
  AVATAR_CAPTURE_FPS   - フレームレート（デフォルト: 15）
  AVATAR_CAPTURE_QUALITY - JPEG品質（デフォルト: 70）
"""

import io
import os
import sys
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

try:
    import mss
    from PIL import Image
except ImportError:
    print("=" * 50)
    print("このスクリプトはWindows上で実行してください。")
    print("WSL2のrequirements.txtとは別に、")
    print("Windows側のPython環境でインストールが必要です:")
    print()
    print("  pip install mss Pillow")
    print("=" * 50)
    sys.exit(1)

# Windows専用: ウィンドウキャプチャ
if sys.platform == "win32":
    import ctypes
    import ctypes.wintypes

    user32 = ctypes.windll.user32

    def find_window(class_name=None, window_name=None):
        """ウィンドウハンドルを検索"""
        return user32.FindWindowW(class_name, window_name)

    def find_window_by_title_keyword(keyword):
        """タイトルにキーワードを含むウィンドウを検索"""
        result = []

        def enum_callback(hwnd, _):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    if keyword.lower() in buf.value.lower():
                        result.append((hwnd, buf.value))
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(enum_callback), 0)
        return result

    def get_window_rect(hwnd):
        """ウィンドウの座標を取得"""
        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        return {
            "left": rect.left,
            "top": rect.top,
            "width": rect.right - rect.left,
            "height": rect.bottom - rect.top,
        }
else:
    # Linux/WSL: ダミー（テスト用）
    def find_window_by_title_keyword(keyword):
        return []

    def get_window_rect(hwnd):
        return {"left": 0, "top": 0, "width": 640, "height": 480}


PORT = int(os.environ.get("AVATAR_CAPTURE_PORT", "9090"))
FPS = int(os.environ.get("AVATAR_CAPTURE_FPS", "15"))
QUALITY = int(os.environ.get("AVATAR_CAPTURE_QUALITY", "70"))

# 最新フレーム（スレッド間共有）
_latest_frame = None
_frame_lock = threading.Lock()


def capture_loop(hwnd):
    """ウィンドウを定期キャプチャしてJPEGに変換"""
    global _latest_frame
    interval = 1.0 / FPS

    with mss.mss() as sct:
        while True:
            start = time.monotonic()
            try:
                rect = get_window_rect(hwnd)
                monitor = {
                    "left": rect["left"],
                    "top": rect["top"],
                    "width": rect["width"],
                    "height": rect["height"],
                }
                screenshot = sct.grab(monitor)
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=QUALITY)
                with _frame_lock:
                    _latest_frame = buf.getvalue()
            except Exception as e:
                print(f"キャプチャエラー: {e}")

            elapsed = time.monotonic() - start
            sleep_time = interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)


class MJPEGHandler(BaseHTTPRequestHandler):
    """MJPEGストリームを配信するHTTPハンドラ"""

    def do_GET(self):
        if self.path == "/stream":
            self.send_mjpeg_stream()
        elif self.path == "/snapshot":
            self.send_snapshot()
        elif self.path == "/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            has_frame = _latest_frame is not None
            self.wfile.write(f'{{"ok":true,"has_frame":{str(has_frame).lower()},"fps":{FPS}}}'.encode())
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"""<html><body style="background:#000;">
                <h2 style="color:#fff;">Avatar Capture Server</h2>
                <p style="color:#ccc;"><a href="/stream" style="color:#7c4dff;">MJPEG Stream</a> |
                <a href="/snapshot" style="color:#7c4dff;">Snapshot</a> |
                <a href="/status" style="color:#7c4dff;">Status</a></p>
                <img src="/stream" style="max-width:100%;">
                </body></html>""")

    def send_mjpeg_stream(self):
        """MJPEG形式で連続フレーム配信"""
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        interval = 1.0 / FPS
        try:
            while True:
                with _frame_lock:
                    frame = _latest_frame
                if frame:
                    self.wfile.write(b"--frame\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(frame)}\r\n".encode())
                    self.wfile.write(b"\r\n")
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
                time.sleep(interval)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def send_snapshot(self):
        """単一フレームを返す"""
        with _frame_lock:
            frame = _latest_frame
        if frame:
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(frame)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(frame)
        else:
            self.send_response(503)
            self.end_headers()

    def log_message(self, format, *args):
        """アクセスログを抑制（streamが大量に出るため）"""
        pass


def main():
    print(f"=== Avatar Capture Server ===")
    print(f"ポート: {PORT}, FPS: {FPS}, JPEG品質: {QUALITY}")
    print()

    # VSeeFaceウィンドウを探す
    windows = find_window_by_title_keyword("VSeeFace")
    if not windows:
        print("VSeeFaceウィンドウが見つかりません。")
        print("VSeeFaceを起動してから再実行してください。")
        if sys.platform != "win32":
            print("（注意: このスクリプトはWindows上で実行してください）")
        sys.exit(1)

    print("見つかったウィンドウ:")
    for i, (hwnd, title) in enumerate(windows):
        rect = get_window_rect(hwnd)
        print(f"  [{i}] {title} ({rect['width']}x{rect['height']})")

    # 最初のウィンドウを使用
    hwnd, title = windows[0]
    rect = get_window_rect(hwnd)
    print(f"\nキャプチャ対象: {title}")
    print(f"サイズ: {rect['width']}x{rect['height']}")

    # キャプチャスレッド開始
    capture_thread = threading.Thread(target=capture_loop, args=(hwnd,), daemon=True)
    capture_thread.start()
    print(f"\nキャプチャ開始 ({FPS}fps)")

    # HTTPサーバー開始
    server = HTTPServer(("0.0.0.0", PORT), MJPEGHandler)
    print(f"MJPEGサーバー起動: http://0.0.0.0:{PORT}/")
    print(f"  ストリーム: http://localhost:{PORT}/stream")
    print(f"  スナップショット: http://localhost:{PORT}/snapshot")
    print(f"\nWSL2からのアクセス:")
    print(f"  http://<WindowsのIP>:{PORT}/stream")
    print(f"\nCtrl+Cで終了")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n停止中...")
        server.shutdown()


if __name__ == "__main__":
    main()
