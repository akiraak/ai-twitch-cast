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
        self._speak_lock = asyncio.Lock()

    @staticmethod
    def strip_lang_tags(text):
        """テキストから言語タグを除去する（[lang:xx] 形式 + SSML <lang> 形式の両方）"""
        # [lang:xx]...[/lang] 形式
        text = re.sub(r'\[/?lang(?::\w+)?\]', '', text)
        # SSML <lang xml:lang="xx">...</lang> 形式
        text = re.sub(r'<lang\b[^>]*>', '', text)
        text = re.sub(r'</lang>', '', text)
        return text

    @staticmethod
    def split_sentences(text):
        """テキストを日本語の句読点で分割してセグメントのリストを返す。

        全角の「。」「！」「？」でのみ分割する（英語のピリオド等では分割しない）。
        短い文（30文字以下）は分割しない。

        Returns:
            list[str]: 分割されたテキストのリスト（最低1要素）
        """
        if len(text) <= 30:
            return [text]

        # 全角句読点の後で分割（句読点は前のセグメントに含める）
        parts = re.split(r'(?<=[。！？])', text)
        # 空文字を除去してstrip
        segments = [p.strip() for p in parts if p.strip()]

        return segments if segments else [text]

    async def notify_overlay(self, author, trigger_text, result, avatar_id="teacher", duration=None):
        """オーバーレイにコメント情報を送信する"""
        if not self._on_overlay:
            return
        raw_speech = result["speech"]
        stripped_speech = self.strip_lang_tags(raw_speech)
        if raw_speech != stripped_speech:
            logger.info("[overlay] strip_lang_tags が除去: %s → %s", repr(raw_speech[:100]), repr(stripped_speech[:100]))
        # SSMLタグの残存チェック
        if '<lang' in stripped_speech or '</lang>' in stripped_speech:
            logger.warning("[overlay] ⚠ strip後もSSMLタグが残存: %s", repr(stripped_speech[:200]))
        payload = {
            "type": "comment",
            "author": author,
            "trigger_text": trigger_text,
            "speech": stripped_speech,
            "translation": result.get("translation", ""),
            "emotion": result["emotion"],
            "avatar_id": avatar_id,
        }
        if duration is not None:
            payload["duration"] = duration
        await self._on_overlay(payload)

    async def notify_overlay_end(self):
        """オーバーレイに発話終了を通知する"""
        if self._on_overlay:
            await self._on_overlay({"type": "speaking_end"})

    async def generate_tts(self, text, voice=None, style=None, tts_text=None):
        """TTS音声を事前生成する（再生はしない）

        Returns:
            Path | None: 生成されたWAVファイルのパス。失敗時はNone。
            キャンセル時は CancelledError を再送出する（テンポラリは削除済み）。
        """
        tmp_dir = Path(tempfile.mkdtemp())
        wav_path = tmp_dir / "speech.wav"
        t_start = time.monotonic()
        preview = (text or "")[:20].replace("\n", " ")
        logger.info("[tts] 事前生成開始: voice=%s, text='%s...'", voice, preview)
        try:
            await asyncio.to_thread(synthesize, tts_text or text, str(wav_path), voice=voice, style=style)
            logger.info("[tts] 事前生成完了: %.0fms text='%s...'", (time.monotonic() - t_start) * 1000, preview)
            return wav_path
        except asyncio.CancelledError:
            wav_path.unlink(missing_ok=True)
            try:
                tmp_dir.rmdir()
            except OSError:
                pass
            raise
        except Exception as e:
            logger.warning("[tts] 事前生成失敗: %s", e)
            wav_path.unlink(missing_ok=True)
            try:
                tmp_dir.rmdir()
            except OSError:
                pass
            return None

    async def speak(self, text, voice=None, style=None, subtitle=None, chat_result=None,
                    tts_text=None, post_to_chat=None, se=None, wav_path=None,
                    avatar_id="teacher"):
        """TTS生成・ブラウザソース経由で再生する（排他制御付き）

        Args:
            text: 読み上げるテキスト
            voice: TTS音声名
            style: TTSスタイル指示
            subtitle: 字幕データ {author, trigger_text, result}
            chat_result: チャット投稿データ
            tts_text: TTS用テキスト（言語タグ付き）
            post_to_chat: チャット投稿コールバック（async関数）
            se: SE情報 {filename, volume, duration, url} or None
            wav_path: 事前生成済みWAVパス（指定時はTTS生成をスキップ）
            avatar_id: アバター識別子（"teacher" or "student"）
        """
        async with self._speak_lock:
            await self._speak_impl(text, voice=voice, style=style, subtitle=subtitle,
                                   chat_result=chat_result, tts_text=tts_text,
                                   post_to_chat=post_to_chat, se=se,
                                   wav_path=wav_path, avatar_id=avatar_id)

    async def _speak_impl(self, text, voice=None, style=None, subtitle=None, chat_result=None,
                          tts_text=None, post_to_chat=None, se=None, wav_path=None,
                          avatar_id="teacher"):
        """speak()の実体（ロック取得済み前提）"""
        # === SE再生（TTS前） ===
        if se:
            await self.send_se_to_native_app(se)
            se_duration = se.get("duration", 1.0)
            await asyncio.sleep(se_duration + 0.3)

        pregenerated = wav_path is not None
        if not pregenerated:
            wav_path = Path(tempfile.mkdtemp()) / "speech.wav"
        tts_ok = pregenerated and wav_path.exists()
        t_start = time.monotonic()
        if not pregenerated:
            try:
                logger.info("[tts] 生成中...")
                await asyncio.to_thread(synthesize, tts_text or text, str(wav_path), voice=voice, style=style)
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
                        subtitle["author"], subtitle["trigger_text"], subtitle["result"],
                        avatar_id=avatar_id,
                        duration=duration,
                    )
                if lipsync_frames:
                    await self._on_overlay({
                        "type": "lipsync",
                        "frames": lipsync_frames,
                        "autostart": True,
                        "avatar_id": avatar_id,
                    })

                logger.info("[tts] 字幕・口パク発火完了: %.0fms（音声投入から）",
                            (time.monotonic() - t_fire) * 1000)

                # チャット投稿（音声再生の2秒後）
                if chat_result and post_to_chat:
                    async def _delayed_chat(result, fn):
                        await asyncio.sleep(2.0)
                        await fn(result)
                    asyncio.create_task(_delayed_chat(chat_result, post_to_chat))

                # 音声の長さ分だけ待機（余白は最小限にして自然なテンポを保つ）
                await asyncio.sleep(duration + 0.1)

                # C# 側の再生完了を確認（まだ再生中なら追加で待つ）
                await self._wait_tts_complete(max_extra=duration * 0.5)

                # リップシンク停止
                if lipsync_frames:
                    await self._on_overlay({"type": "lipsync_stop", "avatar_id": avatar_id})
            else:
                # TTS失敗時: チャット投稿してテキスト表示のみ（数秒待つ）
                if chat_result and post_to_chat:
                    await post_to_chat(chat_result)
                await asyncio.sleep(5.0)

        # クリーンアップ（参照クリア→ファイル削除の順でrace condition防止）
        # キャッシュ済みWAV（resources/audio/lessons/配下）は削除しない
        self._current_audio = None
        is_cached = "resources/audio/" in str(wav_path)
        if not is_cached:
            wav_path.unlink(missing_ok=True)
            try:
                wav_path.parent.rmdir()
            except OSError:
                pass

    async def _wait_tts_complete(self, max_extra: float = 5.0):
        """C# 側の TTS 再生が完了するまでポーリングで待機する

        Args:
            max_extra: 追加で待つ最大秒数（無限待ち防止）
        """
        try:
            from scripts.services.capture_client import ws_request
            elapsed = 0.0
            interval = 0.2
            while elapsed < max_extra:
                result = await ws_request("tts_status", timeout=2.0)
                if not (result and result.get("active")):
                    break
                await asyncio.sleep(interval)
                elapsed += interval
            if elapsed > 0.1:
                logger.info("[tts] TTS完了待ち: %.1f秒追加", elapsed)
        except Exception:
            pass  # C# 未接続時は静かにスキップ

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

            result = await ws_request("tts_audio", timeout=10.0, data=wav_b64, volume=volume)
            t3 = time.monotonic()
            logger.info(
                "[tts] C#アプリにTTS直接送信完了: %d bytes, vol=%.2f, "
                "status=%.0fms b64=%.0fms send=%.0fms total=%.0fms, response=%s",
                len(wav_data), volume,
                (t1 - t0) * 1000, (t2 - t1) * 1000,
                (t3 - t2) * 1000, (t3 - t0) * 1000, result,
            )
        except Exception as e:
            elapsed = (time.monotonic() - t0) * 1000
            # クールダウン中の場合、リセットして1回リトライ
            if "クールダウン中" in str(e):
                logger.info("[tts] C#アプリ接続クールダウンをリセットしてリトライ")
                try:
                    from scripts.services import capture_client
                    capture_client._ws_connect_cooldown_until = 0
                    result = await ws_request("tts_audio", timeout=10.0, data=wav_b64, volume=volume)
                    t3 = time.monotonic()
                    logger.info(
                        "[tts] C#アプリにTTS直接送信完了(リトライ): %d bytes, vol=%.2f, total=%.0fms",
                        len(wav_data), volume, (t3 - t0) * 1000,
                    )
                    return
                except Exception as e2:
                    elapsed = (time.monotonic() - t0) * 1000
                    logger.warning("[tts] C#アプリへのTTS送信失敗(リトライ後) (%.0fms): %s", elapsed, e2)
                    return
            logger.warning("[tts] C#アプリへのTTS送信失敗 (%.0fms): %s", elapsed, e)

    async def send_se_to_native_app(self, se):
        """SE音声をC#アプリに送信する"""
        t0 = time.monotonic()
        try:
            from scripts.routes.stream_control import _get_volume
            from scripts.services.capture_client import ws_request

            master = _get_volume("master")
            se_vol = _get_volume("se")
            track_vol = se.get("volume", 1.0)
            volume = min(1.0, se_vol * se_vol) * (master * master) * track_vol

            await ws_request("se_play", timeout=5.0, url=se["url"], volume=volume)
            logger.info(
                "[se] C#アプリにSE送信完了: url=%s vol=%.2f (%.0fms)",
                se["url"], volume, (time.monotonic() - t0) * 1000,
            )
        except Exception as e:
            elapsed = (time.monotonic() - t0) * 1000
            logger.warning("[se] C#アプリへのSE送信失敗 (%.0fms): %s", elapsed, e)

    # 感情→ジェスチャーのデフォルトマッピング
    EMOTION_GESTURES = {
        "joy": "nod",
        "surprise": "surprise",
        "thinking": "head_tilt",
        "excited": "happy_bounce",
        "sad": "sad_droop",
        "grateful": "bow",
    }

    def apply_emotion(self, emotion, gesture=None, avatar_id="teacher", character_config=None):
        """感情に対応するBlendShape + ジェスチャーを適用する"""
        char = character_config or get_character()
        blendshapes = char.get("emotion_blendshapes", {}).get(emotion, {})
        logger.info("[emotion] %s → blendshapes=%s (avatar=%s)", emotion, blendshapes, avatar_id)
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
                "avatar_id": avatar_id,
            }
            if gesture:
                event["gesture"] = gesture
            asyncio.create_task(self._on_overlay(event))
