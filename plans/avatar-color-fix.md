# アバター白飛び修正プラン

## 現状の問題

アバター（VRM/MToonシェーダー）が白飛びしている。色が薄く、全体的に明るすぎる。

## 原因分析

### 1. ライティングが強すぎる
- **Ambient Light: 2.0** — 非常に高い。全方向から均一に照らすため、影がなく平坦になる
- **Directional Light: 1.5** — これも高め
- **合計光量 3.5** が MToon マテリアルに当たっている

### 2. MToonマテリアルが「常時最大輝度」設計
- `_ReceiveShadowRate = 0.0` → 影を受けない（常に明るい）
- `_ShadeColor = (0.95, 0.93, 0.96)` → 影部分でも95%の明るさ
- `_LightColorAttenuation = 0.0` → ライト色の影響なし
- `_IndirectLightIntensity = 1.0` → 間接光も最大

### 3. ACESFilmicToneMapping + 高光量 = 白飛び
- ACES は HDR → LDR 変換で白飛び**軽減**はするが、入力が明るすぎれば飽和する
- exposure=1.0 でも ambient=2.0 + dir=1.5 だと MToon の明るいマテリアルでは白くなる

## 修正方針

**ライティングの強度を下げる** のが最もシンプルかつ効果的。

MToonマテリアルのプロパティ変更は VRM ファイル自体の再生成が必要で大変なので、ランタイムのライティング調整で対応する。

## 実装ステップ

### Step 1: デフォルトライティングを調整（broadcast.html）

```javascript
// Before
const ambientLight = new THREE.AmbientLight(0xffffff, 2.0);
const dirLight = new THREE.DirectionalLight(0xffffff, 1.5);

// After — 光量を大幅に下げる
const ambientLight = new THREE.AmbientLight(0xffffff, 0.7);
const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
```

- Ambient: 2.0 → 0.7（控えめな環境光で平坦さを軽減）
- Directional: 1.5 → 0.8（メインライトも抑える）
- 合計光量: 3.5 → 1.5（半分以下）

### Step 2: コントラスト計算式も調整（broadcast.html）

ライティング設定からの計算式もデフォルト値に合わせる：
```javascript
// Before
L.setAmbient(Math.max(0.5, Math.min(4.0, 2.0 / c)));
L.setDirectional(Math.max(0.3, Math.min(4.0, 1.5 * c)));

// After
L.setAmbient(Math.max(0.2, Math.min(2.0, 0.7 / c)));
L.setDirectional(Math.max(0.2, Math.min(2.0, 0.8 * c)));
```

### Step 3: トーンマッピング露出もやや下げる

```javascript
// Before
renderer.toneMappingExposure = 1.0;

// After
renderer.toneMappingExposure = 0.85;
```

ACES の S カーブでハイライトが圧縮されるので、0.85程度で自然な色味になる。

### Step 4: overlay.py のデフォルト値更新

```python
# Before
"lighting": {"brightness": 1.0, "contrast": 1.0, "temperature": 0, "saturation": 1.0}

# After
"lighting": {"brightness": 0.85, "contrast": 1.0, "temperature": 0, "saturation": 1.0}
```

## 影響範囲

- `static/broadcast.html` — レンダラー＋ライティング設定
- `scripts/routes/overlay.py` — デフォルト値

## 確認方法

- ブラウザで `/broadcast?token=xxx` を開いてアバターの色を確認
- Web UI の配信画面タブ → 明るさ/コントラストスライダーで微調整可能

## ステータス: 未着手
