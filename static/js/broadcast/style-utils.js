// 共通スタイルユーティリティ（applyCommonStyle, applyLayoutToEl等）

// === 背景透明度の適用（CSS変数で制御） ===
function setBgOpacity(el, opacity) {
  el.style.setProperty('--bg-opacity', opacity);
}

// === hex色をrgbaに変換 ===
function _hexToRgba(hex, alpha) {
  const r = parseInt(hex.slice(1,3), 16) || 0;
  const g = parseInt(hex.slice(3,5), 16) || 0;
  const b = parseInt(hex.slice(5,7), 16) || 0;
  return `rgba(${r},${g},${b},${alpha})`;
}

// === Google Fonts動的読み込み ===
const _loadedGoogleFonts = new Set();
const _GOOGLE_FONT_NAMES = ['M PLUS Rounded 1c', 'Kosugi Maru'];
function _loadGoogleFont(name) {
  if (!name || _loadedGoogleFonts.has(name) || !_GOOGLE_FONT_NAMES.includes(name)) return;
  _loadedGoogleFonts.add(name);
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = `https://fonts.googleapis.com/css2?family=${encodeURIComponent(name)}&display=swap`;
  document.head.appendChild(link);
}

// === 共通スタイル適用（直接適用 + CSS変数並行設定） ===
function applyCommonStyle(el, props) {
  if (!el || !props) return;
  // 表示（CSS display:none を持つアイテムにも対応するため、block を明示指定）
  if (props.visible != null) {
    el.style.display = Number(props.visible) ? 'block' : 'none';
  }
  // 配置
  if (props.positionX != null) el.style.left = props.positionX + '%';
  if (props.positionY != null) el.style.top = props.positionY + '%';
  if (props.zIndex != null) el.style.zIndex = props.zIndex;
  // 背景色（hex色 → rgbaに変換してbackground直接適用）
  if (props.bgColor != null) {
    el.style.setProperty('--item-bg-color', props.bgColor);
    if (props.bgColor.startsWith('#')) {
      const a = parseFloat(el.style.getPropertyValue('--bg-opacity')) || 0.85;
      el.style.background = _hexToRgba(props.bgColor, a);
    }
  }
  // 背景透明度
  if (props.bgOpacity != null) {
    setBgOpacity(el, props.bgOpacity);
    // backgroundを再計算（インラインスタイルがvar()を上書きしている場合があるため）
    let bgColor = el.style.getPropertyValue('--item-bg-color');
    if (bgColor) {
      if (bgColor.startsWith('#')) {
        el.style.background = _hexToRgba(bgColor, props.bgOpacity);
      } else {
        // rgba形式 → alpha値を差し替え
        const m = bgColor.match(/rgba?\(\s*(\d+),\s*(\d+),\s*(\d+)/);
        if (m) el.style.background = `rgba(${m[1]},${m[2]},${m[3]},${props.bgOpacity})`;
      }
    } else {
      // bgColorが未設定 → computedStyleからRGB値を取得してalphaを適用
      const cs = getComputedStyle(el);
      const m = cs.backgroundColor?.match(/rgba?\(\s*(\d+),\s*(\d+),\s*(\d+)/);
      if (m) el.style.background = `rgba(${m[1]},${m[2]},${m[3]},${props.bgOpacity})`;
    }
  }
  // 背景ぼかし（backdrop-filter: blur）
  // bgOpacity=0なら強制無効、それ以外はbackdropBlur値で制御
  if (props.backdropBlur != null) el.style.setProperty('--item-backdrop-blur', String(props.backdropBlur));
  if (props.bgOpacity != null || props.backdropBlur != null) {
    const opacity = parseFloat(props.bgOpacity ?? el.style.getPropertyValue('--bg-opacity') ?? 0.85);
    const bv = parseFloat(props.backdropBlur ?? el.style.getPropertyValue('--item-backdrop-blur') ?? 6);
    const filter = (opacity > 0 && bv > 0) ? `blur(${bv}px)` : 'none';
    el.style.backdropFilter = filter;
    el.style.webkitBackdropFilter = filter;
  }
  // 角丸
  if (props.borderRadius != null) {
    el.style.borderRadius = props.borderRadius + 'px';
    el.style.setProperty('--item-border-radius', props.borderRadius + 'px');
  }
  // ふち枠（borderSize=0で非表示、>0で表示、borderOpacityで透明度制御）
  if (props.borderColor != null) el.style.setProperty('--item-border-color', props.borderColor);
  if (props.borderSize != null) el.style.setProperty('--item-border-size', String(props.borderSize));
  if (props.borderOpacity != null) el.style.setProperty('--item-border-opacity', String(props.borderOpacity));
  if (props.borderColor != null || props.borderSize != null || props.borderOpacity != null) {
    const bs = parseFloat(props.borderSize ?? el.style.getPropertyValue('--item-border-size')) || 0;
    if (bs > 0) {
      let bc = props.borderColor || el.style.getPropertyValue('--item-border-color') || 'rgba(255,255,255,0.5)';
      const bo = parseFloat(props.borderOpacity ?? el.style.getPropertyValue('--item-border-opacity') ?? 1);
      // 色に透明度を適用（hex → rgba変換、またはrgba のalpha値を差し替え）
      if (bc.startsWith('#')) {
        bc = _hexToRgba(bc, bo);
      } else {
        const m = bc.match(/rgba?\(\s*(\d+),\s*(\d+),\s*(\d+)/);
        if (m) bc = `rgba(${m[1]},${m[2]},${m[3]},${bo})`;
      }
      el.style.border = bs + 'px solid ' + bc;
    } else {
      el.style.border = 'none';
    }
  }
  // 文字色（親要素 + custom-text-colorクラスで子要素にも伝播）
  if (props.textColor != null) {
    el.style.color = props.textColor;
    el.style.setProperty('--item-text-color', props.textColor);
    el.classList.add('custom-text-color');
  }
  // 文字縁取り（CSS変数に保存 + 全プロパティを読み出して適用）
  if (props.textStrokeSize != null) el.style.setProperty('--item-text-stroke-size', String(props.textStrokeSize));
  if (props.textStrokeColor != null) el.style.setProperty('--item-text-stroke-color', props.textStrokeColor);
  if (props.textStrokeOpacity != null) el.style.setProperty('--item-text-stroke-opacity', String(props.textStrokeOpacity));
  if (props.textStrokeSize != null || props.textStrokeColor != null || props.textStrokeOpacity != null) {
    const size = Number(props.textStrokeSize ?? el.style.getPropertyValue('--item-text-stroke-size')) || 0;
    if (size > 0) {
      let color = props.textStrokeColor || el.style.getPropertyValue('--item-text-stroke-color') || 'rgba(0,0,0,0.8)';
      const opacity = parseFloat(props.textStrokeOpacity ?? el.style.getPropertyValue('--item-text-stroke-opacity') ?? 0.8);
      // 色に透明度を適用（hex → rgba変換、またはrgba のalpha値を差し替え）
      if (color.startsWith('#')) {
        color = _hexToRgba(color, opacity);
      } else {
        const m = color.match(/rgba?\(\s*(\d+),\s*(\d+),\s*(\d+)/);
        if (m) color = `rgba(${m[1]},${m[2]},${m[3]},${opacity})`;
      }
      el.style.webkitTextStroke = size + 'px ' + color;
      el.style.paintOrder = 'stroke fill';
    } else {
      el.style.webkitTextStroke = '';
    }
  }
  // 文字サイズ
  if (props.fontSize != null) {
    el.style.fontSize = props.fontSize + 'vw';
    el.style.setProperty('--item-font-size', props.fontSize + 'vw');
  }
  // パディング
  if (props.padding != null) {
    el.style.padding = props.padding + 'px';
    el.style.setProperty('--item-padding', props.padding + 'px');
  }
  // 文字揃え（水平）
  if (props.textAlign != null) {
    const ct = el.querySelector('.custom-text-content, .child-text-content') || el;
    ct.style.textAlign = props.textAlign;
  }
  // 文字揃え（垂直）
  if (props.verticalAlign != null) {
    const ct = el.querySelector('.custom-text-content, .child-text-content') || el;
    ct.style.justifyContent = props.verticalAlign === 'center' ? 'center' : props.verticalAlign === 'bottom' ? 'flex-end' : 'flex-start';
  }
  // フォント
  if (props.fontFamily != null) {
    const ct = el.querySelector('.custom-text-content, .child-text-content') || el;
    ct.style.fontFamily = props.fontFamily || '';
    _loadGoogleFont(props.fontFamily);
  }
}

// === レイアウト適用（キャプチャ・カスタムテキスト共用） ===
function applyLayoutToEl(el, layout) {
  if (layout.x != null) el.style.left = layout.x + '%';
  if (layout.y != null) el.style.top = layout.y + '%';
  if (layout.width != null) el.style.width = layout.width + '%';
  if (layout.height != null) el.style.height = layout.height + '%';
  if (layout.zIndex != null) el.style.zIndex = layout.zIndex;
  if (layout.visible === false) el.style.display = 'none';
  else el.style.display = '';
}
