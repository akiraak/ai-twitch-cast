# プラン: アバターの体の向き設定＋自然な見回しモーション

## ステータス: 完了

## Context

TODOの「キャラクターの表示の角度を変えたい。左側ならやや内側に。右側ならやや左側に」を実装する。
現在VRMアバターはカメラ正面固定で表示されており、画面の左右に配置しても常に正面を向いている。
また、配信中のアバターが自然に左右を見回すモーションがなく、やや機械的に見える。

## やること

1. **体の向き設定（静的）**: 管理画面のアバター固有設定にスライダー追加。Y軸回転で体の向きを変更
2. **見回しモーション（動的）**: idle時に5〜15秒間隔でランダムな方向に頭を向ける自然なgaze system

## 前提バグ修正

`_get_item_type("avatar1")` が `"avatar1"` を返すため `_ITEM_SPECIFIC_SCHEMA["avatar"]` にマッチせず、
アバター固有設定（scaleなど）が管理画面に表示されていない。これを先に修正する。

## 実装ステップ

### Step 1: `_get_item_type` のバグ修正
**ファイル**: `scripts/routes/items.py:144-152`

`avatar1`/`avatar2` → `"avatar"` にマッピング追加:
```python
if item_id.startswith("avatar"):
    return "avatar"
```

### Step 2: avatarスキーマに `bodyAngle` 追加
**ファイル**: `scripts/routes/items.py:70-74`

```python
"avatar": [
    {"title": "固有設定", "fields": [
        {"key": "scale", "label": "スケール", "type": "slider", "min": 0.1, "max": 3, "step": 0.05, "default": 1.0},
        {"key": "bodyAngle", "label": "体の向き (°)", "type": "slider", "min": -45, "max": 45, "step": 1, "default": 0},
    ]},
],
```

### Step 3: `_OVERLAY_DEFAULTS` に `bodyAngle` 追加
**ファイル**: `scripts/routes/overlay.py:381-390`

avatar1/avatar2のデフォルトに `"bodyAngle": 0` を追加。起動時のsettings取得で値が返るようにする。

### Step 4: `AvatarInstance` にbodyAngle + gaze system追加
**ファイル**: `static/js/avatar-renderer.js`

#### 4a: コンストラクタにgaze状態変数追加
```javascript
this._bodyAngle = 0;
this._gazeTargetY = 0;
this._gazeCurrentY = 0;
this._gazeTargetX = 0;
this._gazeCurrentX = 0;
this._gazeNextChange = performance.now() / 1000 + 3 + Math.random() * 5;
this._gazeHoldUntil = 0;
```

#### 4b: `setBodyAngle(deg)` メソッド追加（`setIdleScale`の後）
```javascript
setBodyAngle(deg) {
  this._bodyAngle = deg;
  if (this.currentVRM) {
    this.currentVRM.scene.rotation.y = deg * Math.PI / 180;
  }
}
```
`vrm.scene.rotation.y` を直接回転。ボーン回転（idle/gesture）はローカル空間なので干渉しない。

#### 4c: VRM読み込み時にbodyAngle再適用
`loadVRM()` でモデル置き換え後に `this._bodyAngle` を適用。

#### 4d: `_animate()` に見回しシステム追加（`!gestureActive`ブロック内）
既存の頭の動き（headX/headZ/headY）の前に、`!gestureActive`ブロック内で:
- 5〜15秒間隔でランダムな目標角度を選択（Y: ±6°, X: ±3°）
  - ※ idle headYが±1.2°のため、gazeは±6°に抑える（大きすぎると不自然）
- 指数イージングで滑らかに補間: `current += (target - current) * min(1, delta * 2)`
- 2〜6秒ホールド後、次の方向へ

headY/headXに加算:
```javascript
const headX = (Math.sin(t * 0.7) * 1.2 + Math.sin(t * 1.3) * 0.6) * s + this._gazeCurrentX;
const headY = Math.sin(t * 0.4) * 1.2 * s + this._gazeCurrentY;
```
gazeはidleScaleとは独立（自然な行動のため常にアクティブ）。
ジェスチャー中はgaze更新をスキップ（gestureのhead animationと競合防止）。

#### 4e: `window.avatarVRM`互換シムに`setBodyAngle`追加
```javascript
setBodyAngle(deg) { teacherAvatar.setBodyAngle(deg); },
```

### Step 5: `applySettings()` でbodyAngle適用
**ファイル**: `static/js/broadcast/settings.js:61-75`

avatar1/avatar2の設定適用に追加:
```javascript
if (s.avatar1.bodyAngle != null) {
  window.avatarInstances?.['teacher']?.setBodyAngle(s.avatar1.bodyAngle);
}
```
avatar2も同様（`window.avatarInstances['student']`）。

### Step 6: 設定パネルの即時反映
**ファイル**: `static/js/broadcast/settings-panel.js`（`_scheduleSpSave`内）

スライダー操作時にWebSocket応答を待たず即座にsetBodyAngleを呼ぶ:
```javascript
if ((_spItemId === 'avatar1' || _spItemId === 'avatar2') && key === 'bodyAngle') {
  const id = _spItemId === 'avatar1' ? 'teacher' : 'student';
  window.avatarInstances?.[id]?.setBodyAngle(value);
}
```

## 変更ファイル一覧

| ファイル | 変更内容 |
|---------|---------|
| `scripts/routes/items.py` | `_get_item_type` バグ修正 + `bodyAngle`スキーマ追加 |
| `scripts/routes/overlay.py` | デフォルト値追加 |
| `static/js/avatar-renderer.js` | `setBodyAngle()` + gaze system |
| `static/js/broadcast/settings.js` | bodyAngle設定適用 |
| `static/js/broadcast/settings-panel.js` | スライダー即時反映 |

## 検証方法

1. `python3 -m pytest tests/ -q` — 既存テスト通過
2. サーバー再起動後、管理画面「配信画面」→「アバター（メイン）」の設定パネルに「体の向き」スライダーが表示される
3. スライダーを動かすとbroadcast.htmlのアバターがY軸回転する（左：マイナス、右：プラス）
4. アバターが数秒ごとに自然に左右を見回す動き（頭の向き変化）が確認できる
5. ジェスチャー再生中は見回しが一時停止し、終了後に再開する
