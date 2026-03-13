"""テスト共通設定 - 未インストール外部モジュールのスタブ"""

import sys
from unittest.mock import MagicMock

# twitchio等の外部モジュールがインストールされていない環境でも
# scripts.state → src.comment_reader → src.twitch_chat のインポートチェーンが通るようにする
_STUB_MODULES = [
    "twitchio",
    "aiohttp",
]

for mod_name in _STUB_MODULES:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()
