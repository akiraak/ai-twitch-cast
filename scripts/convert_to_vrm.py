"""FBXモデルをVRM 0.x形式に変換するBlenderスクリプト

使い方:
    blender --background --python scripts/convert_to_vrm.py -- <input.fbx> <output.vrm>

例:
    blender --background --python scripts/convert_to_vrm.py -- \
        tmp/3d-model/Shinano_ver1.02/Shinano_ver1.02/FBX/Shinano.fbx \
        resources/vrm/Shinano.vrm

注意:
    VRM 0.x形式で出力する。
"""

import sys
import os

import bpy

# --- 引数パース ---
argv = sys.argv
if "--" in argv:
    args = argv[argv.index("--") + 1:]
else:
    print("使い方: blender --background --python convert_to_vrm.py -- <input.fbx> <output.vrm>")
    sys.exit(1)

if len(args) < 2:
    print("引数が不足しています。<input.fbx> <output.vrm> を指定してください。")
    sys.exit(1)

input_fbx = os.path.abspath(args[0])
output_vrm = os.path.abspath(args[1])

print(f"入力: {input_fbx}")
print(f"出力: {output_vrm}")

os.makedirs(os.path.dirname(output_vrm), exist_ok=True)

# --- シーンをクリア ---
bpy.ops.wm.read_factory_settings(use_empty=True)

# VRM Addonを有効化
bpy.ops.preferences.addon_enable(module="VRM_Addon_for_Blender-release")

# --- FBXインポート ---
print("FBXをインポート中...")
bpy.ops.import_scene.fbx(filepath=input_fbx)

# --- テクスチャをPrincipled BSDFに割り当て ---
# MToon変換時にBaseColorテクスチャが自動で引き継がれるため、先に設定する
texture_dir = os.path.join(os.path.dirname(os.path.dirname(input_fbx)), "PNG")
print(f"テクスチャディレクトリ: {texture_dir}")

TEXTURE_MAP = {
    "Shinano_face": "Shinano_face.png",
    "Shinano_face_alpha": "Shinano_face.png",
    "Shinano_body": "Shinano_body.png",
    "Shinano_costume": "Shinano_costume.png",
    "Shinano_hair": "Shinano_hair.png",
}

for mat_name, tex_file in TEXTURE_MAP.items():
    mat = bpy.data.materials.get(mat_name)
    if mat is None:
        continue

    tex_path = os.path.join(texture_dir, tex_file)
    if not os.path.exists(tex_path):
        print(f"  警告: テクスチャ '{tex_path}' が見つかりません")
        continue

    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    # Principled BSDFを探す
    bsdf = None
    for node in nodes:
        if node.type == "BSDF_PRINCIPLED":
            bsdf = node
            break
    if bsdf is None:
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")

    # テクスチャをBase Colorに設定
    tex_node = nodes.new("ShaderNodeTexImage")
    img = bpy.data.images.load(tex_path)
    img.pack()
    tex_node.image = img
    links.new(tex_node.outputs["Color"], bsdf.inputs["Base Color"])

    if mat_name == "Shinano_face_alpha":
        mat.blend_method = "CLIP"
        links.new(tex_node.outputs["Alpha"], bsdf.inputs["Alpha"])

    print(f"  テクスチャ設定: {mat_name} <- {tex_file}")

# --- MToonシェーダに変換 ---
# Principled BSDFのBaseColorテクスチャがMToonに自動引き継ぎされる
print("MToonシェーダに変換中...")
for mat_name in TEXTURE_MAP:
    mat = bpy.data.materials.get(mat_name)
    if mat is None:
        continue

    bpy.ops.vrm.convert_material_to_mtoon1(material_name=mat_name)

    # MToon Outputノードのトゥーンパラメータを調整
    # lilToon風の明るいフラットなアニメ調を再現
    nodes = mat.node_tree.nodes
    for node in nodes:
        if node.type == "GROUP" and node.node_tree and "MToon 1.0 Output" in node.node_tree.name:
            node.inputs["Shading Toony"].default_value = 1.0    # 完全にトゥーン（影の境界くっきり）
            node.inputs["Shading Shift"].default_value = 0.8    # 影をほぼ出さない（正面光で明るく）
            node.inputs["GI Equalization Factor"].default_value = 1.0  # 環境光を最大に
            node.inputs["Shade Color"].default_value = (0.90, 0.88, 0.92, 1.0)  # 影色を明るく
            break

    # ShadeMultiplyにもBaseColorと同じテクスチャを設定（影にもテクスチャが乗る）
    base_node = nodes.get("Mtoon1BaseColorTexture.Image")
    shade_node = nodes.get("Mtoon1ShadeMultiplyTexture.Image")
    if base_node and base_node.image and shade_node:
        shade_node.image = base_node.image

    print(f"  MToon適用: {mat_name}")

# --- 不要オブジェクトを削除 ---
for obj in list(bpy.data.objects):
    if obj.type in ("CAMERA", "LIGHT") or obj.name == "Cube":
        bpy.data.objects.remove(obj, do_unlink=True)

# --- Armatureを取得 ---
armature = None
for obj in bpy.data.objects:
    if obj.type == "ARMATURE":
        armature = obj
        break

if armature is None:
    print("エラー: Armatureが見つかりません")
    sys.exit(1)

print(f"Armature: {armature.name} ({len(armature.data.bones)} bones)")

# Armatureを選択してアクティブに
bpy.context.view_layer.objects.active = armature
armature.select_set(True)

# --- VRM 0.x を指定 ---
vrm_ext = armature.data.vrm_addon_extension
vrm_ext.spec_version = "0.0"
vrm0 = vrm_ext.vrm0

# --- ヒューマノイドボーンマッピング ---
# VRM 0.x のbone名(camelCase) → FBXボーン名
BONE_MAPPING = {
    "hips": "Hips",
    "spine": "Spine",
    "chest": "Chest",
    "neck": "Neck",
    "head": "Head",
    "leftEye": "LeftEye",
    "rightEye": "RightEye",
    "leftShoulder": "Shoulder.L",
    "leftUpperArm": "Upper_arm.L",
    "leftLowerArm": "Lower_arm.L",
    "leftHand": "Hand.L",
    "rightShoulder": "Shoulder.R",
    "rightUpperArm": "Upper_arm.R",
    "rightLowerArm": "Lower_arm.R",
    "rightHand": "Hand.R",
    "leftUpperLeg": "Upper_leg.L",
    "leftLowerLeg": "Lower_leg.L",
    "leftFoot": "Foot.L",
    "leftToes": "Toe.L",
    "rightUpperLeg": "Upper_leg.R",
    "rightLowerLeg": "Lower_leg.R",
    "rightFoot": "Foot.R",
    "rightToes": "Toe.R",
    # 左手指
    "leftThumbProximal": "Thumb Proximal.L",
    "leftThumbIntermediate": "Thumb Intermediate.L",
    "leftThumbDistal": "Thumb Distal.L",
    "leftIndexProximal": "Index Proximal.L",
    "leftIndexIntermediate": "Index Intermediate.L",
    "leftIndexDistal": "Index Distal.L",
    "leftMiddleProximal": "Middle Proximal.L",
    "leftMiddleIntermediate": "Middle Intermediate.L",
    "leftMiddleDistal": "Middle Distal.L",
    "leftRingProximal": "Ring Proximal.L",
    "leftRingIntermediate": "Ring Intermediate.L",
    "leftRingDistal": "Ring Distal.L",
    "leftLittleProximal": "Little Proximal.L",
    "leftLittleIntermediate": "Little Intermediate.L",
    "leftLittleDistal": "Little Distal.L",
    # 右手指
    "rightThumbProximal": "Thumb Proximal.R",
    "rightThumbIntermediate": "Thumb Intermediate.R",
    "rightThumbDistal": "Thumb Distal.R",
    "rightIndexProximal": "Index Proximal.R",
    "rightIndexIntermediate": "Index Intermediate.R",
    "rightIndexDistal": "Index Distal.R",
    "rightMiddleProximal": "Middle Proximal.R",
    "rightMiddleIntermediate": "Middle Intermediate.R",
    "rightMiddleDistal": "Middle Distal.R",
    "rightRingProximal": "Ring Proximal.R",
    "rightRingIntermediate": "Ring Intermediate.R",
    "rightRingDistal": "Ring Distal.R",
    "rightLittleProximal": "Little Proximal.R",
    "rightLittleIntermediate": "Little Intermediate.R",
    "rightLittleDistal": "Little Distal.R",
}

# VRM 0.xはhuman_bonesコレクション（55エントリ）にbone名でアクセス
human_bones = vrm0.humanoid.human_bones
mapped = 0
for hb in human_bones:
    fbx_bone = BONE_MAPPING.get(hb.bone)
    if fbx_bone is None:
        continue
    if fbx_bone not in armature.data.bones:
        print(f"  警告: FBXボーン '{fbx_bone}' が見つかりません")
        continue
    hb.node.bone_name = fbx_bone
    mapped += 1

print(f"ボーンマッピング完了: {mapped}/{len(BONE_MAPPING)}")

# --- VRM 0.x メタデータ ---
meta = vrm0.meta
meta.title = "Shinano"
meta.author = "shinano_vrm"
meta.violent_ussage_name = "Disallow"
meta.sexual_ussage_name = "Disallow"
meta.commercial_ussage_name = "Disallow"
meta.license_name = "Other"

# --- VRM 0.x BlendShapeGroups ---
face_mesh_name = "Body"

# VRM 0.x preset名 → [(shape_key_name, weight 0-100), ...]
BLEND_SHAPE_PRESETS = {
    "joy": [
        ("eye_joy", 100),
        ("mouth_smile", 100),
        ("eyebrow_joy", 100),
    ],
    "angry": [
        ("eye_angry", 100),
        ("mouth_straight", 100),
        ("eyebrow_angry1", 100),
    ],
    "sorrow": [
        ("eye_sad", 100),
        ("mouth_sad", 100),
        ("eyebrow_sad1", 100),
    ],
    "fun": [
        ("eye_nagomi1", 100),
        ("mouth_smile", 50),
    ],
    "blink": [
        ("eye_close", 100),
    ],
    "blink_l": [
        ("eye_close_L", 100),
    ],
    "blink_r": [
        ("eye_close_R", 100),
    ],
    "a": [
        ("mouth_a1", 100),
    ],
    "i": [
        ("mouth_i1", 100),
    ],
    "u": [
        ("mouth_u1", 100),
    ],
    "e": [
        ("mouth_e1", 100),
    ],
    "o": [
        ("mouth_o1", 100),
    ],
}

bsg = vrm0.blend_shape_master.blend_shape_groups
for preset_name, shape_keys in BLEND_SHAPE_PRESETS.items():
    group = bsg.add()
    group.preset_name = preset_name
    group.name = preset_name

    for sk_name, weight in shape_keys:
        bind = group.binds.add()
        bind.mesh.mesh_object_name = face_mesh_name
        bind.index = sk_name
        bind.weight = weight

    print(f"  BlendShape: {preset_name} ({len(shape_keys)} binds)")

# --- VRMエクスポート ---
print(f"\nVRMをエクスポート中: {output_vrm}")
bpy.ops.export_scene.vrm(filepath=output_vrm)

if os.path.exists(output_vrm):
    size_mb = os.path.getsize(output_vrm) / 1024 / 1024
    print(f"\n変換完了: {output_vrm} ({size_mb:.1f} MB)")
else:
    print("\nエラー: VRMファイルが生成されませんでした。ログを確認してください。")
    sys.exit(1)
