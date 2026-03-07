"""Twitchコメント読み上げスクリプト（単体実行用）"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from src.comment_reader import CommentReader


async def main():
    cr = CommentReader()

    if not cr._chat.token or not cr._chat.channel:
        print("エラー: TWITCH_TOKEN と TWITCH_CHANNEL を .env に設定してください")
        print("  TWITCH_TOKEN: https://twitchtokengenerator.com/ で取得")
        print("  TWITCH_CHANNEL: 読み上げたいチャンネル名")
        sys.exit(1)

    print(f"チャンネル '{cr._chat.channel}' のコメント読み上げを開始します...")
    print("Ctrl+C で終了\n")

    await cr.start()

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        await cr.stop()


if __name__ == "__main__":
    asyncio.run(main())
