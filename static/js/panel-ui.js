/**
 * パネル描画共通関数（index.html 管理画面用）
 * 依存: text-variables.js (TEXT_VARIABLE_HINT), index-app.js (escHtml, loadChildPanels)
 */

/**
 * テキスト編集UI（ラベル+テキストエリア+変数ヒント）のHTMLを生成
 * @param {object} opts
 * @param {string} opts.label - 現在のラベル値
 * @param {string} opts.content - 現在のコンテンツ値
 * @param {string} opts.onLabelChange - ラベル変更時のJS式
 * @param {string} opts.onContentChange - コンテンツ変更時のJS式
 * @returns {string} HTML文字列
 */
function renderTextEditUI(opts) {
  return `
    <div style="display:flex; align-items:center; gap:8px; margin-bottom:6px;">
      <input type="text" value="${escHtml(opts.label)}" placeholder="ラベル"
        style="flex:1; padding:2px 6px; font-size:0.85rem; border:1px solid #ccc; border-radius:4px;"
        onchange="${opts.onLabelChange}">
    </div>
    <textarea rows="2" style="width:100%; box-sizing:border-box; padding:4px 6px; font-size:0.8rem; border:1px solid #ccc; border-radius:4px; resize:vertical;"
      onchange="${opts.onContentChange}">${escHtml(opts.content)}</textarea>
    <div style="font-size:0.7rem; color:#9a88b5; margin-top:2px;">${TEXT_VARIABLE_HINT}</div>`;
}

/**
 * 子パネル管理UIをパネルに注入する
 * @param {HTMLElement} panelBody - 注入先の.panel-body要素
 * @param {string} parentId - 親パネルのID
 */
function injectChildPanelSection(panelBody, parentId) {
  const container = document.createElement('div');
  container.style.cssText = 'margin-top:8px; border-top:1px solid #eee; padding-top:8px;';
  container.innerHTML = `
    <div style="font-size:0.8rem; font-weight:bold; margin-bottom:4px;">子パネル</div>
    <div data-children-for="${parentId}"></div>
    <button onclick="addChildPanel('${parentId}')"
      style="margin-top:4px; padding:3px 10px; background:#5c6bc0; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:0.75rem;">
      + 子テキスト追加</button>`;
  panelBody.appendChild(container);
  loadChildPanels(parentId, container.querySelector(`[data-children-for="${parentId}"]`));
}
