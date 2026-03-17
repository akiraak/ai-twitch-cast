/**
 * 共通 fetch ラッパー
 *
 * @param {string} method - HTTP メソッド (GET, POST, PUT, DELETE)
 * @param {string} url - リクエスト URL
 * @param {object} [body] - リクエストボディ (JSON)
 * @param {object} [opts] - オプション
 * @param {function} [opts.onError] - エラー時コールバック (message) => void
 * @param {function} [opts.onLog] - ログコールバック (message) => void
 * @returns {Promise<object|null>} レスポンス JSON または null
 */
async function api(method, url, body, opts = {}) {
  const { onError, onLog } = opts;
  try {
    const fetchOpts = { method };
    if (body) {
      fetchOpts.headers = { 'Content-Type': 'application/json' };
      fetchOpts.body = JSON.stringify(body);
    }
    const r = await fetch(url, fetchOpts);
    const data = await r.json();
    if (!r.ok) {
      const msg = data.detail || JSON.stringify(data);
      if (onLog) onLog(`ERROR ${url}: ${msg}`);
      if (onError) onError(msg);
      return null;
    }
    if (onLog) onLog(`OK ${url}`);
    return data;
  } catch (e) {
    if (onLog) onLog(`ERROR ${url}: ${e.message}`);
    if (onError) onError(e.message);
    return null;
  }
}
