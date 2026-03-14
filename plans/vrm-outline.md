# VRMキャラ描画にアウトラインを入れる

## 背景

- TODOにある「キャラ描画にアウトラインを入れる（髪や服の線も強調）」の実装プラン
- 現在の配信画面のVRMアバターは `@pixiv/three-vrm@3.3.3` + Three.js r0.169.0 でレンダリング
- MToon材質は使用されているが、`fix_vrm_mtoon.py` でアウトラインは明示的に無効化されている（`_OutlineWidth: 0.0`, `MTOON_OUTLINE_NONE: True`）

## アプローチ比較

### A. ランタイムアウトライン（broadcast.html側JS）⭐推奨

VRM読み込み後、MToonMaterialの `outlineWidthMode` / `outlineWidthFactor` / `outlineColorFactor` を設定する。

**メリット:**
- リアルタイムで太さ・色を調整可能
- Web UIからパラメータ制御できる
- VRMファイル自体を変更しなくてよい
- three-vrm v3のMToonMaterial組み込み機能なので追加ライブラリ不要

**デメリット:**
- VRMモデルがMToonMaterial以外（StandardMaterialなど）の場合は効かない
- three-vrm v3のMToonMaterial実装にアウトライン描画が含まれていない可能性がある（v3ではアウトラインはMultiPassで別描画が必要な場合あり）

### B. ポストプロセッシング（Three.js EffectComposer + エッジ検出）

法線・深度バッファからエッジを検出してアウトライン描画。

**メリット:**
- マテリアルに依存しない（どんなVRMでも動く）
- 髪・服の内部線もピクセル精度で検出可能

**デメリット:**
- 追加ライブラリのインポートが必要（EffectComposer, RenderPass, ShaderPass）
- パフォーマンスコスト（追加レンダリングパス）
- 背景が透過の場合、深度/法線の扱いに工夫が必要

### C. 反転ハル法（Inverted Hull / Back-Face Outline）

メッシュを複製 → 法線反転 → 少し拡大 → 黒色で裏面のみ描画。

**メリット:**
- 古典的で安定した手法
- アニメ調に最もマッチ

**デメリット:**
- メッシュ複製でメモリ2倍
- ボーンアニメーション（idle/lipsync）に追従させる必要がある
- 実装量が多い

## 推奨: アプローチA（ランタイムMToonアウトライン）

three-vrm v3のMToonMaterialにはアウトラインプロパティが存在する。まずこれを試し、効果が不十分なら B に移行。

## 実装ステップ

### Step 1: loadVRM後にアウトラインを有効化

`broadcast.html` の `loadVRM()` 関数内、VRM追加後にメッシュを走査してMToonMaterialのアウトラインを設定：

```javascript
// VRM読み込み完了後
vrm.scene.traverse((node) => {
  if (node.isMesh && node.material) {
    const mats = Array.isArray(node.material) ? node.material : [node.material];
    mats.forEach(mat => {
      if (mat.isShaderMaterial || mat.isMToonMaterial) {
        // MToonMaterialのアウトラインプロパティ
        if ('outlineWidthMode' in mat) {
          mat.outlineWidthMode = 1; // screenCoordinates
          mat.outlineWidthFactor = 0.005; // 画面高さの0.5%
          mat.outlineColorFactor = new THREE.Color(0, 0, 0);
          mat.outlineLightingMixFactor = 0.0; // ライティングの影響なし（純黒）
        }
      }
    });
  }
});
```

### Step 2: Web UIにアウトライン調整パラメータ追加

`index.html` のキャラクタータブに以下を追加：
- **太さ** (outlineWidthFactor): スライダー 0.001 〜 0.02（デフォルト 0.005）
- **色** (outlineColorFactor): カラーピッカー（デフォルト #000000）
- **有効/無効** トグル

### Step 3: API経由でbroadcast.htmlに反映

WebSocketで `outline_settings` イベントを送信 → broadcast.htmlで受信してリアルタイム更新。

### Step 4: scenes.json / DBに設定を永続化

`scenes.json` の avatar セクション or DB に保存：

```json
{
  "avatar": {
    "outline": {
      "enabled": true,
      "width": 0.005,
      "color": [0, 0, 0]
    }
  }
}
```

## フォールバック: アプローチB（ポストプロセス）

MToonのアウトラインが効かない場合（MaterialがMToonでない、またはプロパティが存在しない場合）：

```javascript
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { ShaderPass } from 'three/addons/postprocessing/ShaderPass.js';

// Sobelエッジ検出シェーダで法線ベースのアウトライン
const edgeShader = {
  uniforms: {
    tDiffuse: { value: null },
    tNormal: { value: null },
    resolution: { value: new THREE.Vector2() },
    outlineWidth: { value: 1.0 },
    outlineColor: { value: new THREE.Color(0, 0, 0) },
  },
  // ...フラグメントシェーダでSobelフィルタ
};
```

## リスク

- **three-vrm v3のMToon実装**: アウトラインが別パス（MultiPass）で描画される場合、VRMLoaderPluginの設定が必要な可能性あり
- **パフォーマンス**: アウトライン描画は追加の描画コスト。配信のFPSに影響する可能性
- **VRMモデル依存**: モデルによってマテリアル構成が異なるため、全マテリアルで効くとは限らない

## 作業見積もり

- Step 1（コア実装）: MToonプロパティの確認と設定
- Step 2-4（UI/永続化）: 既存パターン（ライティングプリセット等）の踏襲

## ステータス: 完了（アプローチA+C混合: MeshBasicMaterial+onBeforeCompile反転ハル法）
