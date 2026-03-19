/**
 * テキスト変数の共通定義（カスタムテキスト・子パネル共用）
 * 変数の追加・変更はここだけで行う
 */

const TEXT_VARIABLES = [
  { key: 'version' },
  { key: 'date' },
  { key: 'year' },
  { key: 'month' },
  { key: 'day' },
];

// UI表示用ヒント文字列
const TEXT_VARIABLE_HINT = '変数: ' + TEXT_VARIABLES.map(v => `{${v.key}}`).join(' ');

/**
 * テキスト内の {variable} を実際の値に置換
 * @param {string} text - 置換対象テキスト
 * @returns {string} 置換後テキスト
 */
function replaceTextVariables(text) {
  const info = window._versionInfo;
  if (!info) return text;
  const d = info.updated_at ? new Date(info.updated_at) : null;
  const values = {
    version: info.version || '',
    year:  d ? String(d.getFullYear()) : '',
    month: d ? String(d.getMonth() + 1).padStart(2, '0') : '',
    day:   d ? String(d.getDate()).padStart(2, '0') : '',
  };
  values.date = d ? `${values.year}-${values.month}-${values.day}` : '';

  let result = text;
  for (const v of TEXT_VARIABLES) {
    result = result.replace(new RegExp(`\\{${v.key}}`, 'g'), values[v.key] || '');
  }
  return result;
}
