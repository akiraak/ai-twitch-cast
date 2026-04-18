// ブラウザの console.log/warn/error と uncaught error をサーバーに転送する。
// サーバー側で jslog.txt に追記され、Claude Codeから tail/grep で確認できる。
// このファイルは index.html / broadcast.html の最初の <script> として読み込むこと。
(function() {
  const _buf = [];
  const _orig = console.log;
  const _origWarn = console.warn;
  const _origErr = console.error;
  const _path = location.pathname;
  const _page = _path === '/' ? 'admin'
              : _path.startsWith('/broadcast') ? 'broadcast'
              : _path.replace(/^\//, '');

  function capture(level, args) {
    const ts = new Date().toISOString().substr(11, 12);
    const body = Array.from(args).map(a => {
      try { return typeof a === 'object' ? JSON.stringify(a) : String(a); } catch(e) { return String(a); }
    }).join(' ');
    _buf.push(`${ts} [${_page}] [${level}] ${body}`);
  }

  console.log   = function() { capture('LOG',  arguments); _orig.apply(console, arguments); };
  console.warn  = function() { capture('WARN', arguments); _origWarn.apply(console, arguments); };
  console.error = function() { capture('ERR',  arguments); _origErr.apply(console, arguments); };

  window.addEventListener('error', function(e) {
    capture('UNCAUGHT', [`${e.message} at ${e.filename}:${e.lineno}:${e.colno}`]);
  });
  window.addEventListener('unhandledrejection', function(e) {
    capture('UNHANDLED_REJECTION', [String(e.reason && (e.reason.stack || e.reason.message || e.reason))]);
  });

  function flush() {
    if (_buf.length === 0) return;
    const lines = _buf.splice(0, 200);
    fetch('/api/debug/jslog', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({lines}),
      keepalive: true,
    }).catch(function(){});
  }
  setInterval(flush, 2000);
  // ページ離脱時に未送信ログを送る
  window.addEventListener('beforeunload', flush);
})();
