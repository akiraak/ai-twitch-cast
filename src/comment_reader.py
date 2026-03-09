"""コメント読み上げサービス（Twitchチャット → AI応答 → TTS → 再生 → 表情連動 → DB保存）"""

import asyncio
import logging
import tempfile
from collections import deque
from pathlib import Path

logger = logging.getLogger(__name__)

from src import db
from src.ai_responder import generate_event_response, generate_response, get_character
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
        logger.info("コメント読み上げを開始しました")

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
        logger.info("コメント読み上げを停止しました")

    @property
    def is_running(self):
        return self._running

    @property
    def queue_size(self):
        return len(self._queue)

    async def _on_message(self, author, message):
        """チャットメッセージ受信時"""
        logger.info("[chat] %s: %s", author, message)
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
            user = await asyncio.to_thread(db.get_or_create_user, author)
            result = await self._generate_ai_response(author, message, user["comment_count"])
            await self._save_to_db(user, message, result)
            await self._notify_overlay(author, message, result)
            self._apply_emotion(result["emotion"])
            await self._speak(result["response"])
            self._apply_emotion("neutral")
            await self._notify_overlay_end()
        except Exception as e:
            logger.error("応答失敗: %s", e)

    async def _generate_ai_response(self, author, message, comment_count):
        """AI応答を生成する"""
        logger.info("[ai] 応答生成中...")
        result = await asyncio.to_thread(
            generate_response, author, message, comment_count
        )
        logger.info("[ai] [%s] %s", result["emotion"], result["response"])
        return result

    async def _save_to_db(self, user, message, result):
        """コメントと応答をDBに保存する"""
        if not self._episode_id:
            return
        await asyncio.to_thread(
            db.save_comment,
            self._episode_id, user["id"], message, result["response"], result["emotion"],
        )
        await asyncio.to_thread(db.increment_comment_count, user["id"])

    async def _notify_overlay(self, author, message, result):
        """オーバーレイにコメント情報を送信する"""
        if not self._on_overlay:
            return
        await self._on_overlay({
            "type": "comment",
            "author": author,
            "message": message,
            "response": result["response"],
            "english": result.get("english", ""),
            "emotion": result["emotion"],
        })

    async def _notify_overlay_end(self):
        """オーバーレイに発話終了を通知する"""
        if self._on_overlay:
            await self._on_overlay({"type": "speaking_end"})

    async def _speak(self, text):
        """TTS生成・再生する"""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav_path = f.name
        logger.info("[tts] 生成中...")
        await asyncio.to_thread(synthesize, text, wav_path)
        proc = await asyncio.create_subprocess_exec(
            "ffplay", "-nodisp", "-autoexit", "-loglevel", "error", wav_path,
        )
        await proc.wait()
        Path(wav_path).unlink(missing_ok=True)

    async def speak_event(self, event_type, detail):
        """イベントに対してアバターが発話する（コミット・作業開始等）"""
        try:
            logger.info("[event] %s: %s", event_type, detail)
            result = await asyncio.to_thread(generate_event_response, event_type, detail)
            logger.info("[event] [%s] %s", result["emotion"], result["response"])
            await self._notify_overlay("システム", f"[{event_type}] {detail}", result)
            self._apply_emotion(result["emotion"])
            await self._speak(result["response"])
            self._apply_emotion("neutral")
            await self._notify_overlay_end()
        except Exception as e:
            logger.error("イベント発話失敗: %s", e)

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
