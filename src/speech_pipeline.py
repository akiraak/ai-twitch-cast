"""音声パイプライン — TTS生成・リップシンク解析・音声送信のオーケストレーション"""

import asyncio
import base64
import logging
import re
import tempfile
import time
import wave
from pathlib import Path

from src.ai_responder import get_character
from src.lipsync import analyze_amplitude
from src.tts import synthesize

logger = logging.getLogger(__name__)


class SpeechPipeline:
    """TTS生成→リップシンク→WebSocket送信のオーケストレーション"""

    def __init__(self, on_overlay=None):
        self._on_overlay = on_overlay
        self._current_audio = None

    @staticmethod
    def strip_lang_tags(text):
        """テキストから [lang:xx]...[/lang] タグを除去する"""
        return re.sub(r'\[/?lang(?::\w+)?\]', '', text)

    async def notify_overlay(self, author, message, result):
        """オーバーレイにコメント情報を送信する"""
        if not self._on_overlay:
            return
        await self._on_overlay({
            "type": "comment",
            "author": author,
            "message": message,
            "response": self.strip_lang_tags(result["response"]),
            "english": result.get("english", ""),
            "emotion": result["emotion"],
        })

    async def notify_overlay_end(self):
        """オーバーレイに発話終了を通知する"""
        if self._on_overlay:
            await self._on_overlay({"type": "speaking_end"})

    async def speak(self, text, voice=None, subtitle=None, chat_result=None,
                    tts_text=None, post_to_chat=None):
        """TTS生成・ブラウザソース経由で再生する

        Args:
            text: 読み上げるテキスト
            voice: TTS音声名
            subtitle: 字幕データ {author, message, result}
            chat_result: チャット投稿データ
            tts_text: TTS用テキスト（言語タグ付き）
            post_to_chat: チャット投稿コールバック（async関数）
        """
        wav_path = Path(tempfile.mkdtemp()) / "speech.wav"
        tts_ok = False
        t_start = time.monotonic()
        try:
            logger.info("[tts] 生成中...")
            await asyncio.to_thread(synthesize, tts_text or text, str(wav_path), voice=voice)
            tts_ok = True
            logger.info("[tts] 生成完了: %.0fms", (time.monotonic() - t_start) * 1000)
        except Exception as e:
            logger.warning("[tts] 音声生成失敗、テキストのみ表示: %s", e)

        if self._on_overlay:
            if tts_ok:
                self._current_audio = wav_path

                # === 素材準備フェーズ（全て揃えてから発火） ===
                t_prep = time.monotonic()

                # リップシンク用振幅解析
                lipsync_frames = None
                try:
                    lipsync_frames = await asyncio.to_thread(analyze_amplitude, wav_path)
                    logger.info("[lipsync] 振幅解析完了: %dフレーム (%.0fms)",
                                len(lipsync_frames), (time.monotonic() - t_prep) * 1000)
                except Exception as e:
                    logger.warning("リップシンク解析失敗: %s", e)

                # 音声の長さを取得
                with wave.open(str(wav_path), "rb") as wf:
                    duration = wf.getnframes() / wf.getframerate()

                logger.info("[tts] 素材準備完了: %.0fms (TTS生成から%.0fms)",
                            (time.monotonic() - t_prep) * 1000,
                            (time.monotonic() - t_start) * 1000)

                # === 音声先行送信 → 字幕・口パク発火 ===
                # C#アプリにTTS送信し、デコード+FFmpegキュー投入完了を待つ
                t_fire = time.monotonic()
                await self.send_tts_to_native_app(wav_path)
                logger.info("[tts] C#音声投入完了: %.0fms", (time.monotonic() - t_fire) * 1000)

                # 音声がFFmpegに投入されたので、字幕・口パクを発火
                if subtitle:
                    await self.notify_overlay(
                        subtitle["author"], subtitle["message"], subtitle["result"],
                    )
                if lipsync_frames:
                    await self._on_overlay({
                        "type": "lipsync",
                        "frames": lipsync_frames,
                        "autostart": True,
                    })

                logger.info("[tts] 字幕・口パク発火完了: %.0fms（音声投入から）",
                            (time.monotonic() - t_fire) * 1000)

                # チャット投稿（音声再生の2秒後）
                if chat_result and post_to_chat:
                    async def _delayed_chat(result, fn):
                        await asyncio.sleep(2.0)
                        await fn(result)
                    asyncio.create_task(_delayed_chat(chat_result, post_to_chat))

                # 音声の長さ分だけ待機
                await asyncio.sleep(duration + 0.5)

                # リップシンク停止
                if lipsync_frames:
                    await self._on_overlay({"type": "lipsync_stop"})
            else:
                # TTS失敗時: チャット投稿してテキスト表示のみ（数秒待つ）
                if chat_result and post_to_chat:
                    await post_to_chat(chat_result)
                await asyncio.sleep(5.0)

        # クリーンアップ（参照クリア→ファイル削除の順でrace condition防止）
        self._current_audio = None
        wav_path.unlink(missing_ok=True)
        wav_path.parent.rmdir()

    async def send_tts_to_native_app(self, wav_path):
        """TTS WAVをC#アプリに送信する。C#側で配信中→FFmpegパイプ、非配信→ローカル再生。"""
        t0 = time.monotonic()
        try:
            from scripts.routes.stream_control import _get_volume
            from scripts.services.capture_client import ws_request

            wav_data = wav_path.read_bytes()
            t1 = time.monotonic()
            wav_b64 = base64.b64encode(wav_data).decode("ascii")
            t2 = time.monotonic()

            # ブラウザと同じ知覚的音量計算: min(1.0, tts²) × master²
            master = _get_volume("master")
            tts_vol = _get_volume("tts")
            volume = min(1.0, tts_vol * tts_vol) * (master * master)

            await ws_request("tts_audio", timeout=10.0, data=wav_b64, volume=volume)
            t3 = time.monotonic()
            logger.info(
                "[tts] C#アプリにTTS直接送信完了: %d bytes, vol=%.2f, "
                "status=%.0fms b64=%.0fms send=%.0fms total=%.0fms",
                len(wav_data), volume,
                (t1 - t0) * 1000, (t2 - t1) * 1000,
                (t3 - t2) * 1000, (t3 - t0) * 1000,
            )
        except Exception as e:
            elapsed = (time.monotonic() - t0) * 1000
            logger.warning("[tts] C#アプリへのTTS送信失敗 (%.0fms): %s", elapsed, e)

    # 感情→ジェスチャーのデフォルトマッピング
    EMOTION_GESTURES = {
        "joy": "nod",
        "surprise": "surprise",
        "thinking": "head_tilt",
        "excited": "happy_bounce",
        "sad": "sad_droop",
        "grateful": "bow",
    }

    def apply_emotion(self, emotion, gesture=None):
        """感情に対応するBlendShape + ジェスチャーを適用する"""
        char = get_character()
        blendshapes = char.get("emotion_blendshapes", {}).get(emotion, {})
        logger.info("[emotion] %s → blendshapes=%s", emotion, blendshapes)
        if not blendshapes:
            # ニュートラル: 表情リセット
            all_emotions = set()
            for bs in char.get("emotion_blendshapes", {}).values():
                all_emotions.update(bs.keys())
            blendshapes = {k: 0.0 for k in all_emotions} if all_emotions else {}

        # gestureが未指定の場合、感情からデフォルトマッピング
        if gesture is None:
            gesture = self.EMOTION_GESTURES.get(emotion)

        # broadcast.html VRMアバターにWebSocket送信
        if self._on_overlay and blendshapes:
            event = {
                "type": "blendshape",
                "shapes": blendshapes,
            }
            if gesture:
                event["gesture"] = gesture
            asyncio.create_task(self._on_overlay(event))
