# レイアウトエディタ仕様

## ステータス: 実装済み（改善予定あり）

## 概要

broadcast.htmlに組み込まれた配信画面のレイアウト編集機能。
Electronプレビューウィンドウ（preview.html）のiframe内、またはブラウザで`/broadcast`に直接アクセスして使用する。

## 現在の実装

### 編集対象パーツ

各パーツは`data-editable`属性で識別される。

| パーツ | data-editable | デフォルト位置 | デフォルトz-index |
|--------|---------------|---------------|-------------------|
| アバター | `avatar` | left:73.25% top:62.15% | 5 |
| 字幕 | `subtitle` | bottom:7.4% left:50% | 20 |
| TODOパネル | `todo` | left:50% top:16% | 20 |
| トピックパネル | `topic` | left:1.04% top:1.85% | 20 |
| キャプチャレイヤー | `capture:{id}` | 動的 | 10 |

### 編集モード

- **常時有効**（`?edit`パラメータは廃止済み）
- embedded時（iframe内）はツールバーを非表示にするが、編集機能自体は有効

### パーツの状態遷移

```
[通常] → クリック → [アクティブ(editing)] → 空白クリック → [通常]
                                            → 他パーツ上クリック → [他パーツがアクティブ]
```

#### 通常状態
- カーソル: `pointer`
- ホバー時: 薄紫の枠線（`rgba(124, 77, 255, 0.4)`）+ ラベル表示
- ドラッグ・リサイズ不可

#### アクティブ状態（`.editing`クラス）
- カーソル: `move`
- 枠線: 緑の実線（`#4caf50`）
- ラベル表示 + 四隅にリサイズハンドル表示
- ドラッグ移動・リサイズ可能
- z-indexを9000に一時引き上げ（他パーツの上で操作可能にする）
- 他パーツに`.edit-inactive`クラスを付与（`pointer-events: none !important`でイベント透過）

#### ドラッグ中（`.dragging`クラス）
- 枠線: ピンク実線（`#ff4081`）、opacity: 0.85

### 操作

#### パーツ選択
- クリックでアクティブ化（そのままドラッグも可）
- 右クリックでコンテキストメニュー（Z順序変更）
- 空白部分クリックでアクティブ解除 → その位置に他パーツがあれば自動選択（z-index最大のもの）+ドラッグ開始
- 他パーツが`edit-inactive`でも、document-levelハンドラがBoundingRect判定で検出し切り替え+ドラッグ可能

#### 移動（`startDrag()`）
- アクティブ状態でマウスドラッグ
- 位置は`%`単位で計算（`offsetLeft / window.innerWidth * 100`）
- ドラッグ中は`transform: none`に設定（`translateX(-50%)`等を解除）
- setupEditableのmousedownとdocument-levelハンドラの両方から呼び出し可能

#### リサイズ
- 四隅のハンドル（SE/SW/NE/NW）でリサイズ
- サイズは`%`単位
- 左・上方向のリサイズ時は位置も連動して変更

#### Z順序変更
- 右クリック → 「Z順序を変更...」
- ▲▼ボタンで±1、数値直接入力、最背面(0)/最前面(100)ボタン

### 重なり処理の仕組み

パーツが重なっている場合の操作を可能にするため、以下の3つの機構が連携する:

1. **z-index引き上げ**: アクティブパーツのz-indexを9000に設定（視覚的に最前面）
2. **edit-inactiveクラス**: 他パーツに`pointer-events: none !important`を付与（イベント透過）
   - CSSの`[data-editable] { pointer-events: auto !important }`を`.edit-inactive`で上書きするため、
     `.edit-inactive`の詳細度を`[data-editable].edit-inactive`にしている
3. **document-level座標判定**: `edit-inactive`でクリック不能なパーツも、BoundingRectで検出して選択+ドラッグ開始

### 保存

#### 自動保存（`scheduleSave` → `editSave`）
- ドラッグ・リサイズ完了後500msのデバウンスで自動保存
- 手動保存ボタンもツールバーにあり

#### 保存先
- オーバーレイ設定: `POST /api/overlay/settings` → SQLite DB（`overlay.{section}.{prop}`キー）
- キャプチャレイアウト: `POST /api/capture/{id}/layout`

#### 保存時の注意
- 編集中のz-index=9000は保存しない（`getRealZIndex()`で元の値を取得）
- 保存後のWebSocket `settings_update`ブロードキャストは`_saving`フラグで無視（位置リセット防止）

### ツールバー（`.edit-toolbar`）

- ウィンドウキャプチャ追加（セレクト + 追加ボタン）
- 保存ボタン
- embedded時（iframe内）は非表示
- Go Live等の配信制御はpreview.htmlのコントロールパネルに集約

### アバター固有

- Three.js VRMレンダリング（`<canvas>`）
- `ResizeObserver`でアバターエリアのリサイズを監視し、canvasサイズとカメラアスペクト比を自動更新

## 未実装・改善予定

- [ ] 補助線（スナップガイド）: 中央揃え、他パーツの端に合わせる
- [ ] ウィンドウサイズ変更時にアスペクト比を保つ
