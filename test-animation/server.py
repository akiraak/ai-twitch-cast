"""Test animation server with log endpoint."""
import http.server
import os

LOG_FILE = os.path.join(os.path.dirname(__file__), 'debug.log')

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/log':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            with open(LOG_FILE, 'a') as f:
                f.write(body)
            self.send_response(204)
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Suppress access logs
        pass

if __name__ == '__main__':
    import signal
    import subprocess

    PORT = 8888

    # Kill existing process on the port
    try:
        result = subprocess.run(['lsof', '-ti', f':{PORT}'], capture_output=True, text=True)
        for pid in result.stdout.strip().split('\n'):
            if pid:
                os.kill(int(pid), signal.SIGKILL)
                print(f'Killed existing process {pid} on port {PORT}')
        import time; time.sleep(0.3)
    except Exception:
        pass

    # Clear log on start
    with open(LOG_FILE, 'w') as f:
        f.write('')
    print(f'Serving on http://localhost:{PORT}  (log → {LOG_FILE})')
    server = http.server.HTTPServer(('', PORT), Handler)
    server.serve_forever()
