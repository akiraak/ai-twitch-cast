# プラン: 待機モーションパラメータ調整UI

## ステータス: Step 3完了、Step 4〜6未着手

## Context

現在VRMアバターの待機モーション（呼吸・体の揺れ・頭の動き・腕の揺れ・見回し・まばたき・耳ぴくぴく）のパラメータはすべてハードコードされている。管理画面から調整できるようにして、キャラクターごとに最適な動きを設定したい。

既存の `idleScale` は全体の振幅倍率だが、個別パラメータの調整はできない。

## 現在のハードコード値（avatar-renderer.js）

| カテゴリ | パラメータ | 現在の値 | 説明 |
|---------|-----------|---------|------|
| 呼吸 | 周期 | `t * 1.6`（~4秒） | sin波の速度 |
| 呼吸 | 振幅 | `0.8` | chest回転角度(°) |
| 体の揺れ | 周期 | `t * 0.9` + `t * 0.37` | 2つのsin波合成（~7秒） |
| 体の揺れ | 振幅 | `1.0` + `0.4` | spine Z軸回転(°) |
| 頭の動き | X振幅 | `1.2` + `0.6` | 上下うなずき(°) |
| 頭の動き | Y振幅 | `1.2` | 左右首振り(°) |
| 頭の動き | Z振幅 | `1.6` + `0.6` | 首かしげ(°) |
| 見回し | Y範囲 | `±6°` | 左右見回し |
| 見回し | X範囲 | `±3°` | 上下見回し |
| 見回し | ホールド | `2〜6秒` | 一方向を見つめる時間 |
| 見回し | 間隔 | `3〜10秒` | 次の見回しまで |
| 腕 | ベース角度 | `±70°` | upperArm Z軸 |
| 腕 | 揺れ幅 | `0.8°` | 揺れの振幅 |
| 前腕 | ベース角度 | `±20°` | lowerArm Y軸 |
| 前腕 | 揺れ幅 | `0.6°` | 揺れの振幅 |
| まばたき | 間隔 | `2〜6秒` | ランダム |
| まばたき | 持続 | `0.08秒` | 閉じている時間 |
| 耳ぴくぴく | 間隔 | `3〜10秒` | ランダム |

## 方針

全パラメータを出すと複雑すぎるので、**直感的なグループスライダー**にまとめる。

### UIに出すスライダー（avatar固有設定に追加）

| key | label | min | max | step | default | 影響範囲 |
|-----|-------|-----|-----|------|---------|---------|
| `idleScale` | 動きの大きさ | 0 | 2 | 0.05 | 1.0 | 全体の振幅倍率（既存） |
| `breathScale` | 呼吸の大きさ | 0 | 3 | 0.1 | 1.0 | 呼吸振幅の倍率 |
| `swayScale` | 体の揺れ | 0 | 3 | 0.1 | 1.0 | spine揺れの倍率 |
| `headScale` | 頭の動き | 0 | 3 | 0.1 | 1.0 | 頭のうなずき・首振り・かしげの倍率 |
| `gazeRange` | 見回し範囲 | 0 | 3 | 0.1 | 1.0 | gaze Y/Xの倍率（0=見回しなし） |
| `armAngle` | 腕の角度 | 30 | 90 | 1 | 70 | upperArmのベース角度(°) |
| `armScale` | 腕の揺れ | 0 | 3 | 0.1 | 1.0 | 腕揺れの倍率 |
| `earFreq` | 耳ぴくぴく頻度 | 0 | 3 | 0.1 | 1.0 | 耳ぴくぴく間隔の倍率（0=無効、大=頻繁） |

※ `idleScale` は既存だがUI未公開。今回スライダーとして出す。
※ `earFreq` は間隔の逆数的に作用: 倍率が大きいほど間隔が短くなる。0で完全無効。

## 実装ステップ

### Step 1: avatarスキーマに待機モーションスライダー追加
**ファイル**: `scripts/routes/items.py`

`_ITEM_SPECIFIC_SCHEMA["avatar"]` に「待機モーション」グループを追加:
```python
{"title": "待機モーション", "fields": [
    {"key": "idleScale", "label": "動きの大きさ", "type": "slider", "min": 0, "max": 2, "step": 0.05, "default": 1.0},
    {"key": "breathScale", "label": "呼吸の大きさ", "type": "slider", "min": 0, "max": 3, "step": 0.1, "default": 1.0},
    {"key": "swayScale", "label": "体の揺れ", "type": "slider", "min": 0, "max": 3, "step": 0.1, "default": 1.0},
    {"key": "headScale", "label": "頭の動き", "type": "slider", "min": 0, "max": 3, "step": 0.1, "default": 1.0},
    {"key": "gazeRange", "label": "見回し範囲", "type": "slider", "min": 0, "max": 3, "step": 0.1, "default": 1.0},
    {"key": "armAngle", "label": "腕の角度 (°)", "type": "slider", "min": 30, "max": 90, "step": 1, "default": 70},
    {"key": "armScale", "label": "腕の揺れ", "type": "slider", "min": 0, "max": 3, "step": 0.1, "default": 1.0},
    {"key": "earFreq", "label": "耳ぴくぴく頻度", "type": "slider", "min": 0, "max": 3, "step": 0.1, "default": 1.0},
]},
```

### Step 2: AvatarInstanceにパラメータ変数＋setterを追加
**ファイル**: `static/js/avatar-renderer.js`

コンストラクタに追加:
```javascript
this.breathScale = 1.0;
this.swayScale = 1.0;
this.headScale = 1.0;
this.gazeRange = 1.0;
this.armAngle = 70;
this.armScale = 1.0;
this.earFreq = 1.0;
```

setter メソッド（一括設定用）:
```javascript
setIdleParams(params) {
  if (params.idleScale != null) this.idleScale = params.idleScale;
  if (params.breathScale != null) this.breathScale = params.breathScale;
  if (params.swayScale != null) this.swayScale = params.swayScale;
  if (params.headScale != null) this.headScale = params.headScale;
  if (params.gazeRange != null) this.gazeRange = params.gazeRange;
  if (params.armAngle != null) this.armAngle = params.armAngle;
  if (params.armScale != null) this.armScale = params.armScale;
  if (params.earFreq != null) this.earFreq = params.earFreq;
}
```

### Step 3: animate()でパラメータを参照
**ファイル**: `static/js/avatar-renderer.js`

ハードコード値をインスタンス変数に置き換え:
```javascript
// 呼吸
const breath = Math.sin(t * 1.6) * 0.8 * s * this.breathScale;

// 体の揺れ
const sway = (Math.sin(t * 0.9) * 1.0 + Math.sin(t * 0.37) * 0.4) * s * this.swayScale;

// 頭の動き
const headX = (Math.sin(t * 0.7) * 1.2 + Math.sin(t * 1.3) * 0.6) * s * this.headScale + this._gazeCurrentX;
const headZ = (Math.sin(t * 0.5) * 1.6 + Math.sin(t * 1.1) * 0.6) * s * this.headScale;
const headY = Math.sin(t * 0.4) * 1.2 * s * this.headScale + this._gazeCurrentY;

// 見回し
this._gazeTargetY = (Math.random() - 0.5) * 12 * this.gazeRange;
this._gazeTargetX = (Math.random() - 0.5) * 6 * this.gazeRange;

// 腕
const aa = this.armAngle;
const rArmSway = Math.sin(t * 0.6 + 1.0) * 0.8 * s * this.armScale;
const lArmSway = Math.sin(t * 0.6 + 2.5) * 0.8 * s * this.armScale;
setBoneRotation(this.currentVRM, 'rightUpperArm', quatFromAxisAngle(0, 0, 1, -aa + rArmSway));
setBoneRotation(this.currentVRM, 'leftUpperArm', quatFromAxisAngle(0, 0, 1, aa + lArmSway));

// 耳ぴくぴく（earFreq=0で無効、大きいほど頻繁）
// 間隔計算: earFreq > 0 のとき nextEarTwitch = now + (3 + random*7) / earFreq
// earFreq === 0 のとき earTwitch判定をスキップ
```

### Step 4: applySettings()で待機パラメータ適用
**ファイル**: `static/js/broadcast/settings.js`

avatar1/avatar2ブロック内に追加:
```javascript
const idleKeys = ['idleScale','breathScale','swayScale','headScale','gazeRange','armAngle','armScale','earFreq'];
const idleParams = {};
for (const k of idleKeys) {
  if (s.avatar1[k] != null) idleParams[k] = s.avatar1[k];
}
if (Object.keys(idleParams).length > 0) {
  window.avatarInstances?.['teacher']?.setIdleParams(idleParams);
}
```

### Step 5: 設定パネル即時反映
**ファイル**: `static/js/broadcast/settings-panel.js`

`_scheduleSpSave` 内に追加:
```javascript
const _idleKeys = ['idleScale','breathScale','swayScale','headScale','gazeRange','armAngle','armScale','earFreq'];
if ((_spItemId === 'avatar1' || _spItemId === 'avatar2') && _idleKeys.includes(key)) {
  const id = _spItemId === 'avatar1' ? 'teacher' : 'student';
  window.avatarInstances?.[id]?.setIdleParams({[key]: value});
}
```

### Step 6: VRMロード後の再適用
**ファイル**: `static/js/avatar-renderer.js`（`initAvatar`末尾）

既存のbodyAngle再適用の隣に追加:
```javascript
const idleKeys = ['idleScale','breathScale','swayScale','headScale','gazeRange','armAngle','armScale','earFreq'];
const teacherIdle = {};
for (const k of idleKeys) {
  if (saved.avatar1?.[k] != null) teacherIdle[k] = saved.avatar1[k];
}
if (Object.keys(teacherIdle).length > 0) teacherAvatar.setIdleParams(teacherIdle);
// student側も同様
```

## 変更ファイル一覧

| ファイル | 変更内容 |
|---------|---------|
| `scripts/routes/items.py` | 待機モーションスキーマ追加 |
| `static/js/avatar-renderer.js` | パラメータ変数・setter・animate参照 |
| `static/js/broadcast/settings.js` | applySettingsで待機パラメータ適用 |
| `static/js/broadcast/settings-panel.js` | スライダー即時反映 |

## 検証方法

1. `python3 -m pytest tests/ -q` — 既存テスト通過
2. 管理画面「配信画面」→「アバター（メイン）」に「待機モーション」セクション表示
3. broadcast.htmlの右クリック設定パネルにも同セクション表示
4. 各スライダー操作でアバターの動きが即座に変化:
   - 動きの大きさ 0 → ほぼ静止
   - 呼吸 0 → 胸の動きなし
   - 体の揺れ 3 → 大きく左右に揺れる
   - 腕の角度 30 → 腕が下がる、90 → 腕が水平
   - 耳ぴくぴく頻度 0 → 耳が動かない、3 → 頻繁にぴくぴく
5. 設定がDBに保存され、ページリロード後も維持される
