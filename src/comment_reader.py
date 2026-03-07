"""コメント読み上げサービス（Twitchチャット → TTS → 再生）"""

import asyncio
import tempfile
from collections import deque
from pathlib import Path

from src.tts import synthesize
from src.twitch_chat import TwitchChat


class CommentReader:
    """Twitchコメントを読み上げるサービス"""

    def __init__(self):
        self._chat = TwitchChat()
        self._queue = deque()
        self._process_task = None
        self._running = False

    async def start(self):
        """読み上げを開始する"""
        if self._running:
            return
        self._running = True
        await self._chat.start(self._on_message)
        self._process_task = asyncio.create_task(self._process_loop())
        print("コメント読み上げを開始しました")

    async def stop(self):
        """読み上げを停止する"""
        self._running = False
        await self._chat.stop()
        if self._process_task:
            self._process_task.cancel()
            try:
                await self._process_task
            except (asyncio.CancelledError, Exception):
                pass
            self._process_task = None
        self._queue.clear()
        print("コメント読み上げを停止しました")

    @property
    def is_running(self):
        return self._running

    @property
    def queue_size(self):
        return len(self._queue)

    async def _on_message(self, author, message):
        """チャットメッセージ受信時"""
        print(f"[chat] {author}: {message}")
        self._queue.append((author, message))

    async def _process_loop(self):
        """キューの読み上げを順次処理する"""
        try:
            while self._running:
                if self._queue:
                    author, message = self._queue.popleft()
                    await self._speak(author, message)
                else:
                    await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass

    async def _speak(self, author, message):
        """1件のコメントを読み上げる"""
        text = f"{author}さん。{message}"
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                wav_path = f.name

            print(f"[tts] 生成中: {text}")
            await asyncio.to_thread(synthesize, text, wav_path)

            proc = await asyncio.create_subprocess_exec(
                "ffplay", "-nodisp", "-autoexit", "-loglevel", "error", wav_path,
            )
            await proc.wait()

            Path(wav_path).unlink(missing_ok=True)
        except Exception as e:
            print(f"[error] 読み上げ失敗: {e}")
