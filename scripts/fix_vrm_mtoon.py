"""VRM 0.xファイルのマテリアルをMToonシェーダに書き換え、サムネイルを埋め込む

VRM Addon for BlenderはMToon 1.0でエクスポートするが、
VSeeFaceはVRM 0.xのMToon（VRM/MToon）しか認識しない。
このスクリプトでVRMファイルのJSONを直接書き換える。

使い方:
    python scripts/fix_vrm_mtoon.py resources/vrm/Shinano.vrm [--thumbnail image.png]
"""

import argparse
import json
import struct
import sys
import os


def read_vrm(path):
    """VRMファイルを読み込み、JSONとバイナリチャンクを返す"""
    with open(path, "rb") as f:
        magic = f.read(4)  # glTF
        version = struct.unpack("<I", f.read(4))[0]
        total_length = struct.unpack("<I", f.read(4))[0]

        # JSON chunk
        json_length = struct.unpack("<I", f.read(4))[0]
        json_type = f.read(4)  # JSON
        json_bytes = f.read(json_length)
        json_data = json.loads(json_bytes)

        # Binary chunk (残り全部)
        bin_data = f.read()

    return json_data, bin_data, version


def write_vrm(path, json_data, bin_chunk, version):
    """VRMファイルを書き出す"""
    json_bytes = json.dumps(json_data, ensure_ascii=False).encode("utf-8")
    # glTFはJSONチャンクを4バイトアラインメント（スペースでパディング）
    while len(json_bytes) % 4 != 0:
        json_bytes += b" "

    json_length = len(json_bytes)
    total_length = 12 + 8 + json_length + len(bin_chunk)

    with open(path, "wb") as f:
        f.write(b"glTF")
        f.write(struct.pack("<I", version))
        f.write(struct.pack("<I", total_length))
        # JSON chunk
        f.write(struct.pack("<I", json_length))
        f.write(b"JSON")
        f.write(json_bytes)
        # Binary chunk (そのまま)
        f.write(bin_chunk)


def add_thumbnail(json_data, bin_data, thumbnail_path):
    """サムネイル画像をVRMに埋め込む

    glTFバイナリバッファに画像を追加し、VRMメタデータのtextureとして参照する。
    bin_dataはバイナリチャンク全体（ヘッダ含む）。
    """
    with open(thumbnail_path, "rb") as f:
        thumb_bytes = f.read()

    # バイナリチャンクからヘッダ（8バイト）とボディを分離
    bin_body_length = struct.unpack("<I", bin_data[:4])[0]
    bin_body = bin_data[8:8 + bin_body_length]

    # サムネイル画像をバッファ末尾に追加
    thumb_offset = len(bin_body)
    thumb_length = len(thumb_bytes)

    # 4バイトアラインメント
    padding = (4 - (thumb_length % 4)) % 4
    new_bin_body = bin_body + thumb_bytes + (b"\x00" * padding)

    # バッファサイズを更新
    buffers = json_data.get("buffers", [])
    if buffers:
        buffers[0]["byteLength"] = len(new_bin_body)

    # bufferViewを追加
    buffer_views = json_data.get("bufferViews", [])
    thumb_bv_index = len(buffer_views)
    buffer_views.append({
        "buffer": 0,
        "byteOffset": thumb_offset,
        "byteLength": thumb_length,
    })

    # imageを追加
    images = json_data.get("images", [])
    thumb_img_index = len(images)
    images.append({
        "name": "thumbnail",
        "mimeType": "image/png",
        "bufferView": thumb_bv_index,
    })

    # textureを追加
    textures = json_data.get("textures", [])
    thumb_tex_index = len(textures)
    textures.append({
        "source": thumb_img_index,
        "sampler": 0,
    })

    # VRMメタデータにサムネイルを設定
    vrm_ext = json_data.get("extensions", {}).get("VRM", {})
    meta = vrm_ext.get("meta", {})
    meta["texture"] = thumb_tex_index

    # 新しいバイナリチャンクを組み立て（ヘッダ + ボディ）
    new_bin_chunk = struct.pack("<I", len(new_bin_body)) + b"BIN\x00" + new_bin_body

    print(f"  サムネイル追加: {thumbnail_path} ({thumb_length} bytes, tex={thumb_tex_index})")
    return json_data, new_bin_chunk


def fix_materials(json_data):
    """materialPropertiesをVRM/MToonシェーダに書き換える"""
    vrm_ext = json_data.get("extensions", {}).get("VRM", {})
    mat_props = vrm_ext.get("materialProperties", [])
    gltf_mats = json_data.get("materials", [])

    for i, mp in enumerate(mat_props):
        name = mp.get("name", f"mat_{i}")

        # glTFマテリアルからテクスチャインデックスを取得
        tex_index = None
        if i < len(gltf_mats):
            pbr = gltf_mats[i].get("pbrMetallicRoughness", {})
            base_tex = pbr.get("baseColorTexture", {})
            tex_index = base_tex.get("index")

        # MToonシェーダに設定
        mp["shader"] = "VRM/MToon"
        mp["renderQueue"] = 2000

        # MToon float プロパティ（明るいアニメ調）
        mp["floatProperties"] = {
            "_Cutoff": 0.5,
            "_BlendMode": 0,          # Opaque
            "_CullMode": 2,           # Back
            "_OutlineCullMode": 1,    # Front
            "_SrcBlend": 1,
            "_DstBlend": 0,
            "_ZWrite": 1,
            "_ShadeToony": 1.0,       # 完全トゥーン
            "_ShadeShift": 0.0,       # 影のシフトなし
            "_ReceiveShadowRate": 0.0, # 影を受けない
            "_ShadingGradeRate": 1.0,
            "_LightColorAttenuation": 0.0,  # ライト色の影響なし
            "_IndirectLightIntensity": 1.0,  # 間接光を最大に
            "_RimLightingMix": 0.0,
            "_RimFresnelPower": 1.0,
            "_RimLift": 0.0,
            "_OutlineWidth": 0.0,     # アウトラインなし
            "_OutlineScaledMaxDistance": 1.0,
            "_OutlineLightingMix": 1.0,
            "_BumpScale": 1.0,
        }

        # MToon vector/color プロパティ
        mp["vectorProperties"] = {
            "_Color": [1.0, 1.0, 1.0, 1.0],           # Lit Color = 白（テクスチャ色そのまま）
            "_ShadeColor": [0.95, 0.93, 0.96, 1.0],    # 影色 = ほぼ白（とても明るい影）
            "_EmissionColor": [0.0, 0.0, 0.0, 1.0],
            "_RimColor": [0.0, 0.0, 0.0, 1.0],
            "_OutlineColor": [0.0, 0.0, 0.0, 1.0],
            "_MainTex": [0.0, 0.0, 1.0, 1.0],          # UV offset/scale
            "_ShadeTexture": [0.0, 0.0, 1.0, 1.0],
        }

        # テクスチャプロパティ
        tex_props = {}
        if tex_index is not None:
            tex_props["_MainTex"] = tex_index
            tex_props["_ShadeTexture"] = tex_index  # 影にも同じテクスチャ
        mp["textureProperties"] = tex_props

        # face_alpha用の透過設定
        if "alpha" in name.lower():
            mp["floatProperties"]["_BlendMode"] = 1  # Cutout
            mp["renderQueue"] = 2450

        # タグ
        mp["keywordMap"] = {
            "_NORMALMAP": False,
            "MTOON_OUTLINE_NONE": True,
        }
        mp["tagMap"] = {
            "RenderType": "Opaque" if "alpha" not in name.lower() else "TransparentCutout",
        }

        print(f"  MToon設定: {name} (tex={tex_index})")

    return json_data


def main():
    parser = argparse.ArgumentParser(description="VRM 0.x MToonシェーダ修正・サムネイル埋め込み")
    parser.add_argument("input", help="入力VRMファイル")
    parser.add_argument("-o", "--output", help="出力VRMファイル（省略時は上書き）")
    parser.add_argument("-t", "--thumbnail", help="サムネイル画像（PNG）")
    args = parser.parse_args()

    output_path = args.output or args.input

    print(f"入力: {args.input}")
    json_data, bin_data, version = read_vrm(args.input)
    json_data = fix_materials(json_data)

    if args.thumbnail:
        json_data, bin_data = add_thumbnail(json_data, bin_data, args.thumbnail)

    write_vrm(output_path, json_data, bin_data, version)

    size_mb = os.path.getsize(output_path) / 1024 / 1024
    print(f"出力: {output_path} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
