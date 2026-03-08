"""コメント読み上げサービス（Twitchチャット → AI応答 → TTS → 再生 → 表情連動 → DB保存）"""

import asyncio
import tempfile
from collections import deque
from pathlib import Path

from src import db
from src.ai_responder import generate_response, get_character
from src.tts import synthesize
from src.twitch_chat import TwitchChat


class CommentReader:
    """Twitchコメントを読み上げるサービス"""

    def __init__(self, vsf=None, on_overlay=None):
        self._chat = TwitchChat()
        self._vsf = vsf
        self._on_overlay = on_overlay
        self._queue = deque()
        self._process_task = None
        self._running = False
        self._episode_id = None

    def set_episode(self, episode_id):
        """現在のエピソードIDを設定する"""
        self._episode_id = episode_id

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
        self._episode_id = None
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
                    await self._respond(author, message)
                else:
                    await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass

    async def _respond(self, author, message):
        """1件のコメントにAIで応答して読み上げる"""
        try:
            # ユーザー取得・コメント数
            user = await asyncio.to_thread(db.get_or_create_user, author)
            comment_count = user["comment_count"]

            # AI応答生成
            print(f"[ai] 応答生成中...")
            result = await asyncio.to_thread(
                generate_response, author, message, comment_count
            )
            response_text = result["response"]
            emotion = result["emotion"]
            print(f"[ai] [{emotion}] {response_text}")

            # DB保存
            if self._episode_id:
                await asyncio.to_thread(
                    db.save_comment,
                    self._episode_id, user["id"], message, response_text, emotion,
                )
                await asyncio.to_thread(db.increment_comment_count, user["id"])

            # オーバーレイに送信
            if self._on_overlay:
                await self._on_overlay({
                    "type": "comment",
                    "author": author,
                    "message": message,
                    "response": response_text,
                    "english": result.get("english", ""),
                    "emotion": emotion,
                })

            # 表情を設定
            self._apply_emotion(emotion)

            # TTS生成・再生
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                wav_path = f.name

            print(f"[tts] 生成中...")
            await asyncio.to_thread(synthesize, response_text, wav_path)

            proc = await asyncio.create_subprocess_exec(
                "ffplay", "-nodisp", "-autoexit", "-loglevel", "error", wav_path,
            )
            await proc.wait()

            Path(wav_path).unlink(missing_ok=True)

            # 表情をニュートラルに戻す
            self._apply_emotion("neutral")

            # オーバーレイに発話終了を通知
            if self._on_overlay:
                await self._on_overlay({"type": "speaking_end"})

        except Exception as e:
            print(f"[error] 応答失敗: {e}")

    def _apply_emotion(self, emotion):
        """感情に対応するBlendShapeを適用する"""
        if not self._vsf:
            return
        char = get_character()
        blendshapes = char.get("emotion_blendshapes", {}).get(emotion, {})
        if blendshapes:
            self._vsf.set_blendshapes(blendshapes)
        else:
            # ニュートラル: 表情リセット
            all_emotions = set()
            for bs in char.get("emotion_blendshapes", {}).values():
                all_emotions.update(bs.keys())
            if all_emotions:
                self._vsf.set_blendshapes({k: 0.0 for k in all_emotions})
