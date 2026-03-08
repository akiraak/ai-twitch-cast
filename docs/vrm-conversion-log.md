# VRM変換 作業ログ

FBXモデル（Shinano）をVRM形式に変換する作業の記録。

---

## モデル情報

- **モデル名**: Shinano ver1.02
- **元形式**: FBX (Kaydara FBX 7400)
- **ライセンス**: VN3ライセンス
- **ファイル**: `tmp/3d-model/Shinano_ver1.02/`
- **公式**: [BOOTH](https://ponderogen.booth.pm/items/6106863)

## 変換パイプライン

2段階のパイプラインで変換する:

1. **Blender** (`convert_to_vrm.py`): FBXインポート → テクスチャ設定 → MToonシェーダ変換 → VRM 0.xエクスポート
2. **Python** (`fix_vrm_mtoon.py`): VRMファイルのJSON内materialPropertiesを `VRM/MToon` に書き換え

### なぜ2段階か

Blender VRM AddonはMToon 1.0形式でエクスポートするが、VRM 0.xの `materialProperties` には
`VRM_USE_GLTFSHADER`（glTF標準シェーダ）として書き出される。VSeeFaceはVRM 0.xの `VRM/MToon`
シェーダのみ認識するため、エクスポート後にJSONを直接書き換える必要がある。

```
FBX → [Blender + VRM Addon] → VRM 0.x (shader=VRM_USE_GLTFSHADER)
                                  ↓
                          [fix_vrm_mtoon.py]
                                  ↓
                          VRM 0.x (shader=VRM/MToon) ← VSeeFaceで正常表示
```

## FBX構造の分析

### ボーン構成

ヒューマノイドボーンが揃っており、VRMマッピングが可能:

| VRM Required Bone | FBXボーン名 |
|---|---|
| hips | Hips |
| spine | Spine |
| chest | Chest |
| neck | Neck |
| head | Head |
| leftShoulder | Shoulder.L |
| leftUpperArm | Upper_arm.L |
| leftLowerArm | Lower_arm.L |
| leftHand | Hand.L |
| rightShoulder | Shoulder.R |
| rightUpperArm | Upper_arm.R |
| rightLowerArm | Lower_arm.R |
| rightHand | Hand.R |
| leftUpperLeg | Upper_leg.L |
| leftLowerLeg | Lower_leg.L |
| leftFoot | Foot.L |
| leftToes | Toe.L |
| rightUpperLeg | Upper_leg.R |
| rightLowerLeg | Lower_leg.R |
| rightFoot | Foot.R |
| rightToes | Toe.R |
| leftEye | LeftEye |
| rightEye | RightEye |

### 指ボーン

全指のProximal/Intermediate/Distalが揃っている（VRM Full対応可能）。

### メッシュ構成

| メッシュ | 頂点数 | マテリアル |
|---|---|---|
| Body（顔） | 9,485 | Shinano_face, Shinano_face_alpha |
| Body_base（体） | 13,700 | Shinano_body |
| Cloth_sweater | 13,678 | Shinano_costume |
| Hair_back / Hair_bang / Hair_side / Hair_base | 計12,668 | Shinano_hair |
| Cloth_skirt | 5,816 | Shinano_costume |
| Cloth_tights | 3,655 | Shinano_costume |
| Cloth_boots | 2,946 | Shinano_costume |
| 他（下着・ドレス・尻尾・耳） | - | - |

### BlendShape（ShapeKey）

非常に豊富。主要カテゴリ:

- **VRChatリップシンク**: `vrc.v_aa`, `vrc.v_ih`, `vrc.v_ou`, `vrc.v_e`, `vrc.v_oh` 等15種
- **目**: `eye_close`, `eye_joy`, `eye_angry`, `eye_sad`, `eye_surprise`, `eye_happy` 等
- **口**: `mouth_a1`, `mouth_i1`, `mouth_u1`, `mouth_e1`, `mouth_o1`, `mouth_smile`, `mouth_sad` 等
- **眉**: `eyebrow_joy`, `eyebrow_angry1`, `eyebrow_sad1`, `eyebrow_surprised` 等
- **その他**: `other_cheek_1`（照れ）, `other_tear_1`（涙）, `other_pout`（ほっぺ膨らみ）
- **MMD互換**: `まばたき`, `笑い`, `あ`, `い`, `う`, `え`, `お` 等

### VRM BlendShapeGroup マッピング

VRM 0.x のプリセット名で設定:

| VRM Preset | 使用するShapeKey |
|---|---|
| joy | eye_joy + mouth_smile + eyebrow_joy |
| angry | eye_angry + mouth_straight + eyebrow_angry1 |
| sorrow | eye_sad + mouth_sad + eyebrow_sad1 |
| fun | eye_nagomi1 + mouth_smile(50%) |
| blink | eye_close |
| blink_l | eye_close_L |
| blink_r | eye_close_R |
| a | mouth_a1 |
| i | mouth_i1 |
| u | mouth_u1 |
| e | mouth_e1 |
| o | mouth_o1 |

## 変換手順

### Step 1: 環境準備

```bash
sudo apt install -y blender python3-numpy
# VRM Addon ダウンロード
curl -sL -o /tmp/vrm_addon.zip \
    "https://github.com/saturday06/VRM-Addon-for-Blender/releases/download/v3.21.1/VRM_Addon_for_Blender-3_21_1.zip"
# VRM Addon インストール
blender --background --python-expr "
import bpy
bpy.ops.preferences.addon_install(filepath='/tmp/vrm_addon.zip')
bpy.ops.preferences.addon_enable(module='VRM_Addon_for_Blender-release')
bpy.ops.wm.save_userpref()
"
```

### Step 2: FBXインポート + VRMエクスポート

```bash
blender --background --python scripts/convert_to_vrm.py -- \
    tmp/3d-model/Shinano_ver1.02/Shinano_ver1.02/FBX/Shinano.fbx \
    resources/vrm/Shinano.vrm
```

`convert_to_vrm.py` が行うこと:

1. FBXインポート
2. PNG/ディレクトリからテクスチャを読み込み、Principled BSDFに設定・パック
3. Principled BSDF → MToon 1.0 シェーダ変換（テクスチャ自動引き継ぎ）
4. MToonトゥーンパラメータ調整
5. 不要オブジェクト（Camera, Light, Cube）の削除
6. VRM 0.x ヒューマノイドボーンマッピング（53ボーン）
7. メタデータ設定
8. BlendShapeGroup設定（12プリセット）
9. VRM 0.x 形式でエクスポート

### Step 3: MToonシェーダ修正

```bash
python scripts/fix_vrm_mtoon.py resources/vrm/Shinano.vrm
```

`fix_vrm_mtoon.py` が行うこと:

1. VRMファイル（glTF）のJSONチャンクを読み取り
2. `materialProperties` のシェーダを `VRM_USE_GLTFSHADER` → `VRM/MToon` に書き換え
3. MToon floatProperties（トゥーン・影・ライト設定）を設定
4. MToon vectorProperties（Lit Color・Shade Color）を設定
5. テクスチャプロパティ（_MainTex, _ShadeTexture）をglTFマテリアルから引き継ぎ
6. VRMファイルを上書き保存

### MToon パラメータ設定値

| プロパティ | 値 | 説明 |
|---|---|---|
| `_ShadeToony` | 1.0 | 完全トゥーン（影の境界くっきり） |
| `_ShadeShift` | 0.0 | 影のシフトなし |
| `_ReceiveShadowRate` | 0.0 | 影を受けない |
| `_IndirectLightIntensity` | 1.0 | 間接光を最大に |
| `_LightColorAttenuation` | 0.0 | ライト色の影響なし |
| `_Color` | (1.0, 1.0, 1.0) | Lit Color = 白（テクスチャ色そのまま） |
| `_ShadeColor` | (0.95, 0.93, 0.96) | 影色 = ほぼ白（明るい影） |

### Step 4: 出力ファイル配置

```
resources/vrm/Shinano.vrm
```

### Step 5: 動作確認

```bash
# .envを設定
AVATAR_APP=vsf

# VSeeFaceでモデル読み込み → コンソールで制御テスト
python scripts/console.py
> vsf connect
> vsf demo
```

## 変換結果

- **出力**: `resources/vrm/Shinano.vrm` (178.4 MB)
- **VRM形式**: 0.x（VSeeFace互換）
- **シェーダ**: VRM/MToon（アニメ調トゥーンシェーディング）
- **ボーンマッピング**: 53/53 成功（全指含む）
- **BlendShapeGroup**: 12プリセット設定済み
  - 表情: joy, angry, sorrow, fun
  - まばたき: blink, blink_l, blink_r
  - リップシンク: a, i, u, e, o
- **テクスチャ**: 4枚埋め込み済み（face, body, costume, hair）
- **マテリアル**: 5つ（face, face_alpha, body, costume, hair）

### 使用ツール

| ツール | バージョン |
|---|---|
| Blender | 4.0.2 |
| VRM Addon for Blender | v3.21.1 |
| numpy | 1.26.4 |
| Python | 3.12 |

## トラブルシューティング

### VRM.NotVrm0Exception

VSeeFaceはVRM 0.x のみ対応。`spec_version = "1.0"` で出力するとこのエラーになる。
スクリプトでは `vrm_ext.spec_version = "0.0"` を指定して回避。

### テクスチャが表示されない

FBXが参照するテクスチャパス（`画像/`）が実際のディレクトリ構造と一致しないため、
FBXインポート時にテクスチャが読み込まれない。

**解決**: `PNG/` ディレクトリから手動で画像を読み込み、Principled BSDFのBase Colorに
接続・パックしてからMToon変換する。順番が重要で、**テクスチャ設定 → MToon変換** の順でないと
テクスチャが引き継がれない。

### モデルが暗い（VRM_USE_GLTFSHADER問題）

Blender VRM AddonでVRM 0.xエクスポートすると、BlenderでMToon 1.0を設定しても
`materialProperties` には `shader: "VRM_USE_GLTFSHADER"` と書き出される。
VSeeFaceはこれをglTF標準シェーダとして解釈し、MToonのトゥーン表示にならない。

**解決**: `fix_vrm_mtoon.py` でVRMファイルのJSONを直接書き換え、
`shader: "VRM/MToon"` と適切なfloat/vector/textureプロパティを設定する。

### VRM Addon のモジュール名

`VRM_Addon_for_Blender` ではなく `VRM_Addon_for_Blender-release` が正しいモジュール名。
`~/.config/blender/4.0/scripts/addons/` にインストールされたディレクトリ名で確認可能。

### VRM Addon の属性名（VRM 0.x vs 1.0）

- **VRM 0.x**: camelCase（`leftUpperArm`）。`vrm0.humanoid.human_bones` コレクションの各要素の `.bone` で参照。
- **VRM 1.0**: snake_case（`left_upper_arm`）。`vrm1.humanoid.human_bones` の属性名で直接アクセス。

## 備考

- 元モデルはlilToonシェーダ前提で作られている（Unity向け）
- VRM 0.xではMToonシェーダが標準。lilToonの明るいフラットな見た目を再現するため、影を最小限に設定
- 髪・服・尻尾のSpring Bone（揺れ物）は未設定（VSeeFace側で物理演算を適用する運用）
- テクスチャ埋め込みのためファイルサイズが大きい（178.4 MB）
- 一部メッシュで4を超えるジョイント影響があるが、上位4つに自動正規化される（動作に支障なし）
