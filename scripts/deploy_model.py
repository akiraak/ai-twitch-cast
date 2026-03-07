"""Live2DモデルをVTube Studioにデプロイ/クリーンアップするスクリプト

使い方:
  python scripts/deploy_model.py                   # デプロイ
  python scripts/deploy_model.py --clean            # クリーンアップ
  python scripts/deploy_model.py --model <モデル名>  # 特定モデルのみ
"""

import argparse
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from src.wsl_path import to_windows_path

load_dotenv()

RESOURCES_DIR = Path(__file__).resolve().parent.parent / "resources" / "live2d"


def get_vts_models_dir() -> Path:
    """VTube StudioのモデルフォルダをWindowsパスで取得する"""
    vts_dir = os.environ.get("VTS_MODELS_DIR")
    if not vts_dir:
        print("エラー: .envにVTS_MODELS_DIRを設定してください。")
        print("例: VTS_MODELS_DIR=C:\\Program Files (x86)\\Steam\\steamapps\\common\\VTube Studio\\VTube Studio_Data\\StreamingAssets\\Live2DModels")
        sys.exit(1)

    # WindowsパスをWSLパスに変換
    result = os.popen(f'wslpath "{vts_dir}"').read().strip()
    if not result:
        print(f"エラー: パスの変換に失敗しました: {vts_dir}")
        sys.exit(1)

    path = Path(result)
    if not path.exists():
        print(f"エラー: VTube Studioのモデルフォルダが見つかりません: {vts_dir}")
        sys.exit(1)

    return path


def deploy(models_dir: Path, model_name: str = None):
    """モデルをVTube Studioにコピーする"""
    if not RESOURCES_DIR.exists():
        print(f"リソースフォルダがありません: {RESOURCES_DIR}")
        print("resources/live2d/ にモデルを配置してください。")
        return

    models = [RESOURCES_DIR / model_name] if model_name else list(RESOURCES_DIR.iterdir())
    models = [m for m in models if m.is_dir()]

    if not models:
        print("デプロイするモデルがありません。")
        return

    for model_path in models:
        dest = models_dir / model_path.name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(model_path, dest)
        print(f"デプロイ: {model_path.name} → {dest}")

    print(f"\n{len(models)}件のモデルをデプロイしました。VTube Studioを再起動してください。")


def clean(models_dir: Path, model_name: str = None):
    """VTube Studioからデプロイしたモデルを削除する"""
    if not RESOURCES_DIR.exists():
        return

    models = [RESOURCES_DIR / model_name] if model_name else list(RESOURCES_DIR.iterdir())
    models = [m for m in models if m.is_dir()]

    removed = 0
    for model_path in models:
        dest = models_dir / model_path.name
        if dest.exists():
            shutil.rmtree(dest)
            print(f"削除: {dest}")
            removed += 1

    if removed:
        print(f"\n{removed}件のモデルを削除しました。")
    else:
        print("削除対象のモデルはありませんでした。")


def main():
    parser = argparse.ArgumentParser(description="Live2DモデルをVTube Studioにデプロイ")
    parser.add_argument("--clean", action="store_true", help="モデルを削除する")
    parser.add_argument("--model", type=str, help="対象モデル名（省略時は全モデル）")
    args = parser.parse_args()

    models_dir = get_vts_models_dir()

    if args.clean:
        clean(models_dir, args.model)
    else:
        deploy(models_dir, args.model)


if __name__ == "__main__":
    main()
