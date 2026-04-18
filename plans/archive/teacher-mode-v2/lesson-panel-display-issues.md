# 授業パネル表示問題 - 調査報告

## ステータス: 未修正

## 問題の概要

授業テキストパネル（`#lesson-text-panel`）と授業進捗パネル（`#lesson-progress-panel`）の表示位置・背景・サイズが意図通りに反映されない。

## 発見された問題

### 1. 保存済み設定がCSS固定位置を上書き（致命的）

位置・サイズはCSS固定（ドラッグ不可）に変更済みだが、**過去にドラッグで保存された不正な値がDBに残っている**。

- `lesson_text`: `positionX: 0.0, positionY: 0.0`（CSS中央配置と矛盾）
- `lesson_progress`: `positionX: 4.63, positionY: 23.91`（CSS左上配置と矛盾）

`applyCommonStyle`で`positionX/Y`を除外しているが、**`width`と`height`は除外されていない**ため、保存済みの`height: 46.25%`等がCSSの`max-height: 70%`を上書きしている。

### 2. 背景透明度のインラインスタイル競合

CSSでは`var(--bg-opacity)`で背景色を計算しているが、`applyCommonStyle`が以下の順で処理:
1. `bgColor`設定時: `el.style.background = _hexToRgba(bgColor, alpha)` でインラインスタイルを直接設定
2. `bgOpacity`設定時: `--bg-opacity`変数を更新 + インラインbackgroundも再計算

**問題**: `bgColor`が`rgba(...)`形式で保存されている場合、CSSのgradient背景が単色RGBAに置き換わる。

### 3. `visible`プロパティの干渉

`showLessonText()`で`display: block`を設定した直後に`applySettings()`を呼ぶが、保存設定に`visible: 1`があるため`applyCommonStyle`が再度`display`を操作。現在は問題ないが、`visible: 0`が保存されていると表示されない。

## 修正方針

### A. 保存済み不正値のクリーンアップ
- DBから`lesson_text`と`lesson_progress`の`positionX/Y/width/height`を削除
- `_OVERLAY_DEFAULTS`から位置・サイズのデフォルト値を削除

### B. applySettingsでの除外を厳密化
- `lesson_text`と`lesson_progress`のapplyCommonStyle呼び出しで`width`, `height`, `zIndex`も除外

### C. 背景スタイルの統一
- `bgOpacity`変更時のインラインbackground再計算を改善（現在のrgba形式対応で部分修正済み）

## 変更対象ファイル

| ファイル | 変更内容 |
|---------|---------|
| `scripts/routes/overlay.py` | `_OVERLAY_DEFAULTS`からlesson系の位置・サイズ削除 |
| `static/js/broadcast/settings.js` | applyCommonStyleに渡す前にwidth/height/zIndexも除外 |
| DB | 保存済みの不正な位置・サイズ値をクリーンアップ |
