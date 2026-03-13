# アバター表示品質改善プラン — VSeeFace表示に近づける

## 調査結果サマリ

### VSeeFace のレンダリング環境
- **Unity Built-in RP** (Unity 2019.4.16f1)、Linear カラースペース
- **トーンマッピングなし**（MToonシェーダーもポストプロセスも適用しない）
- **UniVRM 0.89**（VRM 0.x のみ対応）
- **ライト構成**: 白色 Directional Light 1灯のみ、intensity=0.975、回転(16, -146, -7.8)
- 明示的な Ambient Light は無く、間接光は MToon 内で SH9（球面調和関数）として処理

### Shinano.vrm の構造
- VRM 0.x (specVersion 0.0)、Blender VRM Addon で出力
- 全5マテリアルが **VRM/MToon** シェーダー（設定は全マテリアル共通）
- `_ShadeToony: 1.0`（完全2値トゥーン）、`_ShadeShift: 0.0`
- `_ShadeColor: [0.95, 0.93, 0.96]`（ガンマ空間。three-vrm で gammaEOTF 適用後 → [0.897, 0.854, 0.916] リニア）
- `_OutlineWidth: 0.0` + `MTOON_OUTLINE_NONE: True`（**アウトラインなし**）
- `_ReceiveShadowRate: 0.0`、`_IndirectLightIntensity: 1.0`
- `_LightColorAttenuation: 0.0`

### three-vrm v3 の MToon 実装
- VRM 0.x → **V0CompatPlugin** が VRM 1.0 形式に変換 → **MToonMaterialLoaderPlugin** が MToonMaterial を生成
- MToonMaterial は **ShaderMaterial を継承**。フラグメントシェーダ末尾に `#include <tonemapping_fragment>` があり、**Three.js の toneMapping が適用される**
- `_ShadeColor` の色値には **gammaEOTF (pow 2.2)** が適用される（VRM 0.x → 1.0 変換時）
- `_IndirectLightIntensity` → `giEqualizationFactor = 1.0 - value` にマッピングされるが、**v3.3.3 のシェーダーでは giEqualizationFactor は実際には未使用**
- AmbientLight は **常に diffuseColor（明部色）のみ** に寄与。shadeColor には影響しない
- `shadeColorFactor`, `shadingShiftFactor`, `shadingToonyFactor` は **ランタイムで変更可能**（uniform 経由）

## 比較画像分析（tmp/chara2.png）

| 項目 | Electron（現状） | VSeeFace（目標） |
|------|------------------|------------------|
| **全体の色味** | 白飛び気味、彩度が低い | 自然な色味、テクスチャ本来の色が出ている |
| **肌の色** | 薄く白っぽい | 暖かみのある自然な肌色 |
| **髪の色** | グレーがかって平坦 | 白〜薄紫のグラデーションが鮮明 |
| **衣装の色** | コントラスト不足で平坦 | 白と黒の対比がはっきり |
| **陰影（トゥーン）** | ほぼ見えない（全体が均一に明るい） | 首元・髪下・衣装の折り目に柔らかい影がある |
| **目の表現** | 色が薄い | 瞳の色が鮮やかで深みがある |

※ VRMファイル自体にアウトライン設定がないため、VSeeFaceでもアウトラインは表示されていない。
比較画像でVSeeFaceの輪郭がくっきり見えるのは、色のコントラストが正しく出ているため。

## 原因分析（調査に基づく確定版）

### 原因1: ACESFilmicToneMapping（最大の要因）

```javascript
renderer.toneMapping = THREE.ACESFilmicToneMapping;  // ← 問題
```

three-vrm の MToonMaterial は `#include <tonemapping_fragment>` を含むため、**ACES が全マテリアルに適用される**ことが確認済み。

VSeeFace は **トーンマッピングなし**（MToon も Unity Built-in RP もポストプロセスを適用しない）。

ACES の影響:
- ハイライト圧縮 → 白い部分の色差が潰れる
- 高輝度部の彩度低下 → MToon が出力した色がくすむ
- S字カーブ → 中間色の分布が変わり、意図した色味からずれる

### 原因2: AmbientLight が強すぎ + VSeeFace と構造が違う

```javascript
const ambientLight = new THREE.AmbientLight(0xffffff, 2.0);   // ← 問題
const dirLight = new THREE.DirectionalLight(0xffffff, 1.5);
```

**VSeeFace のライト構成**: DirectionalLight 1灯（intensity 0.975）のみ。Ambient Light なし。

three-vrm の MToon における AmbientLight の挙動:
- AmbientLight は **diffuseColor（明部色）にのみ** 加算される（shadeColor には影響しない）
- つまり AmbientLight=2.0 は **影部には寄与せず、明部だけを過剰に明るくする**
- 結果: 明部が白飛びし、影との差も生まれない

VSeeFace での間接光:
- MToon は SH9（球面調和関数）を上下平均化した `toonedGI` を使う
- `_IndirectLightIntensity` のデフォルトは **0.1**（非常に弱い）
- 間接光は控えめで、ほぼ DirectionalLight だけで陰影が決まる

### 原因3: _ShadeColor の gammaEOTF 変換の影響

`fix_vrm_mtoon.py` で設定した値:
```python
"_ShadeColor": [0.95, 0.93, 0.96, 1.0]  # ガンマ空間
```

three-vrm V0CompatPlugin が **gammaEOTF（pow 2.2）** を適用:
- R: 0.95 → 0.897
- G: 0.93 → 0.854
- B: 0.96 → 0.916

リニア空間では [0.897, 0.854, 0.916] となり、ガンマ空間での見た目より暗い。
ただし AmbientLight が強すぎて明部が飽和しているため、この影色の差が現状では見えていない。
AmbientLight を下げれば、この影色が適切に見えるようになる。

### ~~原因4: アウトラインがない~~ → 修正不要

VRM ファイル自体に `_OutlineWidth: 0.0` + `MTOON_OUTLINE_NONE` が設定されており、
**VSeeFace でもアウトラインは描画されていない**。
比較画像でのエッジの見え方の差は、色のコントラスト（原因1+2）が原因。

## 修正プラン

### Step 1: トーンマッピングを無効化（効果: 大）

```javascript
// Before
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.0;

// After
renderer.toneMapping = THREE.NoToneMapping;
```

- MToonが出力する色がそのままフレームバッファに書き込まれる
- VSeeFace の Unity Built-in RP + MToon と同じ動作になる
- **根拠**: three-vrm MToonMaterial のフラグメントシェーダが `#include <tonemapping_fragment>` を含んでおり、NoToneMapping にすることでこのパスがスキップされる

### Step 2: ライティングをVSeeFace準拠に変更（効果: 大）

```javascript
// Before
const ambientLight = new THREE.AmbientLight(0xffffff, 2.0);
const dirLight = new THREE.DirectionalLight(0xffffff, 1.5);
dirLight.position.set(1, 2, 3);

// After
const ambientLight = new THREE.AmbientLight(0xffffff, 0.4);
const dirLight = new THREE.DirectionalLight(0xffffff, 1.0);
dirLight.position.set(-1, 1.5, -2);  // VSeeFaceのデフォルト回転(16,-146,-7.8)に近い方向
```

VSeeFace は DirectionalLight 0.975 + Ambient なし。
ただし Three.js には SH9 がないため、完全に Ambient=0 だと暗くなりすぎる。
AmbientLight=0.4 で SH9 の弱い間接光を近似する。

DirectionalLight の方向:
- VSeeFace デフォルト回転 (16, -146, -7.8) は、**左前上方から照らす** 構成
- Three.js の `position.set(-1, 1.5, -2)` で近似（正規化されて方向ベクトルになる）

**なぜこの値か**:
- MToon で AmbientLight は diffuseColor にのみ加算されるため、値を下げることで明部の白飛びが解消される
- DirectionalLight=1.0 は VSeeFace の 0.975 に近く、トゥーン陰影が自然に出る
- AmbientLight=0.4 は VSeeFace の SH9 toonedGI の近似（調整の余地あり）

### Step 3: 明るさ調整UIの修正（NoToneMapping対応）

`NoToneMapping` では `toneMappingExposure` が無効。ライト強度の倍率で代替する:

```javascript
const BASE_AMBIENT = 0.4;
const BASE_DIRECTIONAL = 1.0;

window.avatarLighting = {
  setAmbient(intensity) { ambientLight.intensity = intensity; },
  setDirectional(intensity) { dirLight.intensity = intensity; },
  setExposure(val) {
    // NoToneMapping: ライト強度の倍率で代替
    ambientLight.intensity = BASE_AMBIENT * val;
    dirLight.intensity = BASE_DIRECTIONAL * val;
  },
  setColor(r, g, b) {
    ambientLight.color.setRGB(r, g, b);
    dirLight.color.setRGB(r, g, b);
  },
};
```

`applySettings` のコントラスト計算式:
```javascript
L.setAmbient(Math.max(0.1, Math.min(2.0, BASE_AMBIENT / c)));
L.setDirectional(Math.max(0.2, Math.min(3.0, BASE_DIRECTIONAL * c)));
```

コントラストを上げると: Ambient↓ + Directional↑ → 明暗差が大きくなる（MToonのトゥーン陰影が強調）

### Step 4: overlay.py のデフォルト値更新

```python
# Before
"lighting": {"brightness": 1.0, "contrast": 1.0, "temperature": 0, "saturation": 1.0}

# After
"lighting": {"brightness": 1.0, "contrast": 1.0, "temperature": 0.1, "saturation": 1.0}
```

VSeeFace の表示はやや暖色寄りに見えるため、色温度を微調整。

### Step 5: MToonマテリアルのランタイム調整（効果: 中、オプション）

Step 1〜3 の効果を確認した上で、さらに調整が必要な場合のみ実施。

```javascript
function adjustMToonMaterials(vrm) {
  vrm.scene.traverse((node) => {
    if (!node.isMesh) return;
    const mats = Array.isArray(node.material) ? node.material : [node.material];
    mats.forEach(mat => {
      if (mat.uniforms?.shadeColorFactor) {
        // three-vrm v3 の MToonMaterial はランタイムで uniform 変更可能
        // 影色を調整する場合（リニア空間で指定）:
        // mat.shadeColorFactor.setRGB(0.85, 0.80, 0.87);

        // shadingShift を負にすると影領域が広がる:
        // mat.shadingShiftFactor = -0.1;
      }
    });
  });
}
```

**注意点**:
- `giEqualizationFactor` は three-vrm v3.3.3 のシェーダーで **未使用**（変更しても効果なし）
- `shadeColorFactor` はリニア空間で指定する（VRM 0.x のガンマ空間値とは異なる）
- テクスチャの追加/削除はシェーダー再コンパイルが必要なため非推奨。数値・色の変更は即反映

## 優先順位

| 順位 | Step | 変更箇所 | 期待効果 | 根拠 |
|:----:|:----:|----------|----------|------|
| 1 | Step 1 | broadcast.html | 彩度・色味の大幅改善 | VSeeFace=トーンマッピングなし。three-vrm MToon に ACES が適用されていることを確認済み |
| 2 | Step 2 | broadcast.html | トゥーン陰影が出て立体感改善 | VSeeFace=DirLight 0.975のみ。MToon の AmbientLight は明部にしか寄与しないことを確認済み |
| 3 | Step 3 | broadcast.html | UI操作が正常に動作 | Step 1 で toneMappingExposure が無効になるため必須 |
| 4 | Step 4 | overlay.py | 肌色が暖かく自然に | 微調整 |
| 5 | Step 5 | broadcast.html | さらなる微調整 | Step 1〜3 の効果を見て判断 |

Step 1〜3 が最も効果が大きく、この3つでVSeeFace表示にかなり近づく見込み。
~~旧 Step 6（アウトライン）は VRM ファイル自体にアウトラインがないため不要。~~

## 変更ファイル

- `static/broadcast.html` — レンダラー設定、ライティング、（オプション）MToon調整
- `scripts/routes/overlay.py` — デフォルト値

## 確認方法

1. `/broadcast` でアバター表示を確認
2. VSeeFace の `tmp/chara2.png` と並べて比較
3. Web UI のライティングスライダーで微調整
4. 特に確認すべき箇所: 肌色、髪のグラデーション、衣装の白黒コントラスト、瞳の色

## ステータス: 未着手
