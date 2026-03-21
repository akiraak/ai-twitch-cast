"""SE（効果音）解決モジュール — AIが選択したカテゴリからSEファイルを解決する"""

import random

from src import db


def resolve_se(category: str | None) -> dict | None:
    """AIが指定したSEカテゴリからファイルを解決する

    Args:
        category: SEカテゴリ名（Noneなら不要）

    Returns:
        {"filename": str, "volume": float, "duration": float, "url": str} or None
    """
    if not category:
        return None
    tracks = db.get_se_tracks_by_category(category)
    if not tracks:
        return None
    track = random.choice(tracks)
    return {
        "filename": track["filename"],
        "volume": track["volume"],
        "duration": track["duration"],
        "url": f"/se/{track['filename']}",
    }


def get_available_categories() -> list[dict]:
    """利用可能なSEカテゴリ一覧を返す（重複なし）

    Returns:
        [{"name": str, "description": str}, ...]
    """
    all_tracks = db.get_all_se_tracks()
    categories = {}
    for info in all_tracks.values():
        cat = info["category"]
        if cat and cat not in categories:
            categories[cat] = info.get("description", "")
    return [{"name": k, "description": v} for k, v in sorted(categories.items())]
