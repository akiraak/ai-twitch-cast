# アイテム共通化バグ修正プラン

## ステータス: 計画中

## 問題の概要

1. **共通プロパティが配信画面に反映されない**: applyCommonStyleがCSS変数のみ設定し直接適用しないため、bgColor/border/textColor/textStroke/paddingが効かない
2. **WebUIのコントロール構造が混乱**: 既存の個別コントロール（bgOpacity, zIndex等）と「詳細設定」折りたたみ内の共通コントロールが分離し、重複と混乱を招いている
3. **足りないコントロール**: 文字縁取り色、文字縁取り透明度

## 修正方針

### WebUI: 共通UI → 固有UIの2段構成（折りたたみ廃止）

各fieldsetの構成を以下に統一:

```
┌─ アバター ─────────────────────────┐
│ [共通コントロール] ← JS生成、全パネル同じ │
│   表示ON/OFF                        │
│   X位置 / Y位置 / Z順序              │
│   背景色 / 背景透明度                 │
│   角丸                              │
│   ふち枠 ON/OFF / 色 / サイズ        │
│   文字色                            │
│   文字縁取り サイズ / 色 / 透明度      │
│   パディング                         │
│ ─── 固有パラメータ ──── ← 静的HTML    │
│   スケール                           │
└────────────────────────────────────┘
```

- `<details>` 折りたたみは削除
- bgOpacity、zIndexは共通コントロールに統一（既存の個別スライダーは削除）
- JS生成の共通コントロールがfieldset先頭に挿入される

### broadcast-main.js: 直接スタイル適用

applyCommonStyleをCSS変数のみ → **直接スタイル適用**に変更。

## 修正ステップ

### Step 1: applyCommonStyleを直接適用に変更

`broadcast-main.js`の`applyCommonStyle()`を修正:

```javascript
function applyCommonStyle(el, props) {
  if (!el || !props) return;
  // 表示
  if (props.visible != null) {
    if (!Number(props.visible)) el.style.display = 'none';
    else if (el.style.display === 'none') el.style.display = '';
  }
  // 配置
  if (props.positionX != null) el.style.left = props.positionX + '%';
  if (props.positionY != null) el.style.top = props.positionY + '%';
  if (props.zIndex != null) el.style.zIndex = props.zIndex;
  // 背景透明度
  if (props.bgOpacity != null) setBgOpacity(el, props.bgOpacity);
  // 角丸
  if (props.borderRadius != null) el.style.borderRadius = props.borderRadius + 'px';
  // ふち枠（borderEnabled=1のみ適用、0はスキップして既存CSS borderを維持）
  if (props.borderEnabled != null && Number(props.borderEnabled)) {
    const bc = props.borderColor || 'rgba(255,255,255,0.5)';
    const bs = props.borderSize || 1;
    el.style.border = bs + 'px solid ' + bc;
  }
  // 文字色
  if (props.textColor != null) el.style.color = props.textColor;
  // 文字縁取り
  if (props.textStrokeSize != null || props.textStrokeColor != null) {
    const size = Number(props.textStrokeSize) || 0;
    if (size > 0) {
      const color = props.textStrokeColor || 'rgba(0,0,0,0.8)';
      el.style.webkitTextStroke = size + 'px ' + color;
      el.style.paintOrder = 'stroke fill';
    } else {
      el.style.webkitTextStroke = '';
    }
  }
  // パディング
  if (props.padding != null) el.style.padding = props.padding + 'px';
  // CSS変数も並行設定（CSS参照アイテム用）
  if (props.borderRadius != null) el.style.setProperty('--item-border-radius', props.borderRadius + 'px');
  if (props.bgColor != null) el.style.setProperty('--item-bg-color', props.bgColor);
  if (props.textColor != null) el.style.setProperty('--item-text-color', props.textColor);
  if (props.fontSize != null) el.style.setProperty('--item-font-size', props.fontSize + 'vw');
  if (props.padding != null) el.style.setProperty('--item-padding', props.padding + 'px');
}
```

注意:
- `borderEnabled=0`の場合は`border:none`にしない（subtitle/todo/topicの既存CSS borderが消えてしまうため）
- `borderEnabled=1`の場合のみ直接適用

### Step 2: applySettings固有コードの重複削除

各アイテムの固有コードから、applyCommonStyleでカバー済みのプロパティ処理を削除:

| アイテム | 削除する重複処理 | 維持する固有処理 |
|---------|----------------|----------------|
| subtitle | bgOpacity, zIndex | bottom配置、fontSize→.response、maxWidth、fadeDuration |
| todo | bgOpacity, zIndex | width、height+maxHeight+overflow、transform、fontSize→.todo-item、titleFontSize |
| topic | bgOpacity, zIndex | maxWidth、titleFontSize |
| version | bgOpacity, zIndex | format、fontSize→#version-text、strokeSize/strokeOpacity |
| dev_activity | （なし） | （なし） |

### Step 3: WebUI構造の全面刷新

#### index.html: 既存の共通コントロールを削除

各fieldsetから以下のstatic HTMLを削除（JS生成に移行するため）:
- X位置（`data-key="*.positionX"`）スライダー — 全アイテム（subtitleはbottomのみなので除く）
- Y位置（`data-key="*.positionY"`）スライダー — 全アイテム（subtitleはbottomのみなので除く）
- 背景透明度（`data-key="*.bgOpacity"`）スライダー — 全アイテム
- Z順序（`data-key="*.zIndex"`）スライダー — 全アイテム
- バージョン表示トグル（`id="lv-version-visible"`） — version固有→共通visible

#### index-app.js: _commonPropsHTML を更新

`<details>` を廃止し、全コントロールをフラットに表示:

```javascript
function _commonPropsHTML(s) {
  return `
    ${row('表示', toggle(s, 'visible'))}
    ${row('X位置 (%)', slider(s, 'positionX', 0, 100, 0.5))}
    ${row('Y位置 (%)', slider(s, 'positionY', 0, 100, 0.5))}
    ${row('Z順序', slider(s, 'zIndex', 0, 100, 1))}
    ${row('背景色', color(s, 'bgColor'))}
    ${row('背景透明度', slider(s, 'bgOpacity', 0, 1, 0.05))}
    ${row('角丸 (px)', slider(s, 'borderRadius', 0, 30, 1))}
    ${row('ふち枠', toggle(s, 'borderEnabled'))}
    ${row('枠色', color(s, 'borderColor'))}
    ${row('枠サイズ', slider(s, 'borderSize', 0, 10, 0.5))}
    ${row('文字色', color(s, 'textColor'))}
    ${row('文字縁取り', slider(s, 'textStrokeSize', 0, 10, 0.5))}
    ${row('縁取り色', color(s, 'textStrokeColor'))}
    ${row('縁取り透明度', slider(s, 'textStrokeOpacity', 0, 1, 0.05))}
    ${row('パディング (px)', slider(s, 'padding', 0, 30, 1))}
  `;
}
```

#### initCommonProps: 挿入位置をfieldset先頭に変更

```javascript
function initCommonProps() {
  for (const s of sections) {
    const fs = document.querySelector(`fieldset[data-section="${s}"]`);
    if (!fs) continue;
    // legendの直後（先頭）に共通コントロールを挿入
    const legend = fs.querySelector('legend');
    if (legend) legend.insertAdjacentHTML('afterend', _commonPropsHTML(s));
    else fs.insertAdjacentHTML('afterbegin', _commonPropsHTML(s));
    // 区切り線を追加（共通と固有の境界）
    // 固有パラメータが存在する場合のみ
    const specificRows = fs.querySelectorAll('.layout-row:not(.common-row)');
    if (specificRows.length > 0) {
      specificRows[0].insertAdjacentHTML('beforebegin',
        '<div style="border-top:1px solid #e0d0f0; margin:8px 0; font-size:0.7rem; color:#9a88b5;">固有パラメータ</div>');
    }
  }
}
```

### Step 4: バージョン固有の表示トグル処理を共通化

現在バージョンだけ専用の `onVersionToggle()` + `_updateVersionToggleStyle()` がある。これを共通の `onLayoutToggle()` に統合:

- `onVersionToggle()` のトグルスタイル更新ロジック → `onLayoutToggle()` に統合済み
- `id="lv-version-visible"` の専用処理 → 共通の `.layout-toggle[data-key="version.visible"]` に移行
- `onVersionToggle` / `_updateVersionToggleStyle` を削除

### Step 5: テスト更新

- `test_broadcast_patterns.py`:
  - applyCommonStyleが `el.style.borderRadius` 等の直接適用を含むことを検証
  - `_commonPropsHTML` が `<details>` を含まないことを検証
  - `_commonPropsHTML` が bgOpacity, zIndex, textStrokeColor, textStrokeOpacity を含むことを検証

## 全アイテムの最終コントロール配置

### 共通（JS生成、全パネル同一、15コントロール）
| コントロール | data-key | 入力タイプ |
|------------|----------|-----------|
| 表示 | `{s}.visible` | トグル |
| X位置 | `{s}.positionX` | スライダー 0-100 |
| Y位置 | `{s}.positionY` | スライダー 0-100 |
| Z順序 | `{s}.zIndex` | スライダー 0-100 |
| 背景色 | `{s}.bgColor` | カラーピッカー |
| 背景透明度 | `{s}.bgOpacity` | スライダー 0-1 |
| 角丸 | `{s}.borderRadius` | スライダー 0-30 |
| ふち枠 | `{s}.borderEnabled` | トグル |
| 枠色 | `{s}.borderColor` | カラーピッカー |
| 枠サイズ | `{s}.borderSize` | スライダー 0-10 |
| 文字色 | `{s}.textColor` | カラーピッカー |
| 文字縁取り | `{s}.textStrokeSize` | スライダー 0-10 |
| 縁取り色 | `{s}.textStrokeColor` | カラーピッカー |
| 縁取り透明度 | `{s}.textStrokeOpacity` | スライダー 0-1 |
| パディング | `{s}.padding` | スライダー 0-30 |

### 固有（静的HTML、パネルごとに異なる）
| パネル | 固有コントロール |
|-------|----------------|
| アバター | スケール |
| 字幕 | 下端, 文字サイズ, 最大幅, フェード, [テスト表示ボタン] |
| TODO | 幅, 高さ, 文字サイズ, タイトル文字サイズ |
| トピック | 最大幅, タイトル文字サイズ |
| バージョン | フォーマット, 文字サイズ, 縁取りサイズ, 縁取り濃さ |
| 開発アクティビティ | 文字サイズ |

## 変更ファイル

| ファイル | 変更内容 |
|---------|---------|
| `static/js/broadcast-main.js` | applyCommonStyle直接適用化、applySettings重複削除 |
| `static/js/index-app.js` | _commonPropsHTML全面刷新（details廃止、bgOpacity/zIndex/textStroke色透明度追加）、initCommonProps挿入位置変更、onVersionToggle統合 |
| `static/index.html` | 各fieldsetからbgOpacity/zIndexスライダー削除、version表示トグル削除 |
| `tests/test_broadcast_patterns.py` | 直接適用検証、details不在検証 |

## リスク

1. **padding直接適用**: subtitle/todoのCSS paddingがvw単位。直接適用はpx単位で上書きする → DB未設定時はapplyCommonStyleが呼ばれないのでCSS値が維持される。ユーザーがWebUIで変更した場合のみpxに切り替わる（意図的な変更なのでOK）
2. **borderEnabled=0**: 既存CSS borderを消さないようにスキップする。ユーザーがborderEnabled=1にして→0に戻した場合、手動で設定したborderが残る → 許容（ページリロードでCSS値に戻る）
3. **onVersionToggle削除**: バージョントグルの視覚的フィードバック（ノブ移動）が共通トグルの仕組みに統合される。見た目は同等
