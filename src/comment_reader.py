"""コメント読み上げサービス（Twitchチャット → AI応答 → TTS → 再生 → 表情連動 → DB保存）"""

import asyncio
import logging
import tempfile
import time
import wave
from collections import deque
from pathlib import Path

logger = logging.getLogger(__name__)

from src import db
from src.ai_responder import generate_event_response, generate_response, generate_self_note, generate_user_notes, get_character
from src.lipsync import analyze_amplitude
from src.tts import synthesize
from src.twitch_chat import TwitchChat


class CommentReader:
    """Twitchコメントを読み上げるサービス"""

    def __init__(self, on_overlay=None, topic_talker=None):
        self._chat = TwitchChat()
        self._on_overlay = on_overlay
        self._topic_talker = topic_talker
        self._queue = deque()
        self._process_task = None
        self._note_task = None
        self._running = False
        self._episode_id = None
        self._idle_since = None  # キューが空になった時刻

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
        self._note_task = asyncio.create_task(self._note_update_loop())
        logger.info("コメント読み上げを開始しました")

    async def stop(self):
        """読み上げを停止する"""
        self._running = False
        await self._chat.stop()
        for task in [self._process_task, self._note_task]:
            if task:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
        self._process_task = None
        self._note_task = None
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
                    self._idle_since = None
                    author, message = self._queue.popleft()
                    await self._respond(author, message)
                elif self._topic_talker and self._should_auto_speak():
                    await self._auto_speak()
                    # 発話後にidleタイマーをリセット（即座に連続発話しないように）
                    self._idle_since = time.monotonic()
                else:
                    if self._idle_since is None:
                        self._idle_since = time.monotonic()
                    await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            pass

    def _should_auto_speak(self):
        """自発的発話すべきかを判定する"""
        if self._idle_since is None:
            return False
        idle_seconds = time.monotonic() - self._idle_since
        return self._topic_talker.should_speak(idle_seconds)

    async def _auto_speak(self):
        """トピックに基づいて自発的に発話する"""
        try:
            # トピック自動生成・ローテーションチェック
            stream_context = await self._get_stream_context()
            self_note = await self._get_self_note()
            new_topic = await self._topic_talker.maybe_rotate_topic(
                stream_context=stream_context, self_note=self_note,
            )
            if new_topic:
                logger.info("[topic] トピック自動変更: %s", new_topic["title"])

            script = await self._topic_talker.get_next()
            if not script:
                return
            english = script.get("english", "")
            logger.info("[topic] 自発的発話: [%s] %s", script["emotion"], script["content"])
            self._apply_emotion(script["emotion"])
            await self._speak(script["content"], subtitle={
                "author": "ちょビ",
                "message": script["content"],
                "result": {"response": script["content"], "emotion": script["emotion"], "english": english},
            }, chat_result={"response": script["content"], "english": english},
                tts_text=script.get("tts_text"))
            self._apply_emotion("neutral")
            await self._notify_overlay_end()
            # アバター発話をDBに保存
            logger.info("[topic] DB保存呼び出し: episode=%s", self._episode_id)
            await self._save_avatar_speech("[トピック]", script["content"], script["emotion"])
        except Exception as e:
            logger.error("自発的発話失敗: %s", e, exc_info=True)

    async def _respond(self, author, message):
        """1件のコメントにAIで応答して読み上げる"""
        try:
            user = await asyncio.to_thread(db.get_or_create_user, author)
            already_greeted = False
            if self._episode_id:
                ep_count = await asyncio.to_thread(
                    db.count_user_comments_in_episode, self._episode_id, user["id"],
                )
                already_greeted = ep_count > 0
            # メモは初回挨拶時のみ渡す（過剰な言及を防ぐ）
            note = user.get("note", "") if not already_greeted else ""
            result = await self._generate_ai_response(
                author, message, user["comment_count"], note,
                already_greeted=already_greeted,
            )
            await self._save_to_db(user, message, result)
            await asyncio.to_thread(db.update_user_last_seen, user["id"])
            self._apply_emotion(result["emotion"])
            # 字幕・チャット投稿・音声を同時に送信（TTS生成後に全て発火）
            await self._speak(result["response"], subtitle={
                "author": author, "message": message, "result": result,
            }, chat_result=result, tts_text=result.get("tts_text"))
            self._apply_emotion("neutral")
            await self._notify_overlay_end()
            if self._topic_talker:
                self._topic_talker.mark_spoken()
        except Exception as e:
            logger.error("応答失敗: %s", e)

    async def _generate_ai_response(self, author, message, comment_count, user_note="", already_greeted=False):
        """AI応答を生成する（会話履歴・配信コンテキスト付き）"""
        logger.info("[ai] 応答生成中...")
        history = await asyncio.to_thread(db.get_recent_comments, 5, 2)
        stream_context = await self._get_stream_context()
        # アバター自身のメモを取得
        self_note = await self._get_self_note()
        result = await asyncio.to_thread(
            generate_response, author, message, comment_count,
            history=history, stream_context=stream_context,
            user_note=user_note or None, already_greeted=already_greeted,
            self_note=self_note,
        )
        logger.info("[ai] [%s] %s", result["emotion"], result["response"])
        return result

    async def _get_stream_context(self):
        """配信コンテキストを収集する（タイトル・トピック・TODO）"""
        context = {}
        # 配信タイトル
        try:
            from src.twitch_api import TwitchAPI
            api = TwitchAPI()
            info = await api.get_channel_info()
            if info.get("title"):
                context["title"] = info["title"]
        except Exception:
            pass
        # 現在のトピック
        if self._topic_talker:
            status = self._topic_talker.get_status()
            if status.get("active") and status.get("topic"):
                context["topic"] = status["topic"]["title"]
        # TODO（作業中タスク）
        try:
            from pathlib import Path
            todo_path = Path(__file__).resolve().parent.parent / "TODO.md"
            if todo_path.exists():
                import re
                items = []
                for line in todo_path.read_text(encoding="utf-8").splitlines():
                    m = re.match(r"\s*-\s*\[>\]\s*(.*)", line)
                    if m:
                        items.append(m.group(1).strip())
                if items:
                    context["todo_items"] = items
        except Exception:
            pass
        return context if context else None

    async def _save_to_db(self, user, message, result):
        """コメントと応答をDBに保存する"""
        if not self._episode_id:
            return
        await asyncio.to_thread(
            db.save_comment,
            self._episode_id, user["id"], message, result["response"], result["emotion"],
        )
        await asyncio.to_thread(db.increment_comment_count, user["id"])

    @staticmethod
    def _strip_lang_tags(text):
        """テキストから [lang:xx]...[/lang] タグを除去する"""
        import re
        return re.sub(r'\[/?lang(?::\w+)?\]', '', text)

    async def _post_to_chat(self, result):
        """AI応答をTwitchチャットに投稿する"""
        try:
            text = self._strip_lang_tags(result["response"])
            english = result.get("english", "")
            if english:
                text = f"{text} ({english})"
            await self._chat.send_message(text)
        except Exception as e:
            logger.error("チャット投稿失敗: %s", e)

    async def _notify_overlay(self, author, message, result):
        """オーバーレイにコメント情報を送信する"""
        if not self._on_overlay:
            return
        await self._on_overlay({
            "type": "comment",
            "author": author,
            "message": message,
            "response": self._strip_lang_tags(result["response"]),
            "english": result.get("english", ""),
            "emotion": result["emotion"],
        })

    async def _notify_overlay_end(self):
        """オーバーレイに発話終了を通知する"""
        if self._on_overlay:
            await self._on_overlay({"type": "speaking_end"})

    async def _speak(self, text, voice=None, subtitle=None, chat_result=None, tts_text=None):
        """TTS生成・ブラウザソース経由で再生する

        Args:
            subtitle: 字幕データ {author, message, result}。指定時はTTS生成後に字幕と音声を同時送信
            chat_result: チャット投稿データ。指定時はTTS生成後に投稿
            tts_text: TTS用テキスト（言語タグ付き）。指定時はこちらをTTSに送信
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

                # === 同時発火（字幕+リップシンク+音声を一斉送信） ===
                t_fire = time.monotonic()

                if subtitle:
                    await self._notify_overlay(
                        subtitle["author"], subtitle["message"], subtitle["result"],
                    )
                if lipsync_frames:
                    await self._on_overlay({
                        "type": "lipsync",
                        "frames": lipsync_frames,
                        "autostart": True,
                    })
                # C#アプリにTTS送信（配信中→FFmpegパイプ、非配信→ローカル再生）
                await self._send_tts_to_native_app(wav_path)

                logger.info("[tts] 同時発火完了: %.0fms", (time.monotonic() - t_fire) * 1000)

                # チャット投稿（音声再生の2秒後）
                if chat_result:
                    async def _delayed_chat(result):
                        await asyncio.sleep(2.0)
                        await self._post_to_chat(result)
                    asyncio.create_task(_delayed_chat(chat_result))

                # 音声の長さ分だけ待機
                await asyncio.sleep(duration + 0.5)

                # リップシンク停止
                if lipsync_frames:
                    await self._on_overlay({"type": "lipsync_stop"})
            else:
                # TTS失敗時: チャット投稿してテキスト表示のみ（数秒待つ）
                if chat_result:
                    await self._post_to_chat(chat_result)
                await asyncio.sleep(5.0)

        # クリーンアップ（参照クリア→ファイル削除の順でrace condition防止）
        self._current_audio = None
        wav_path.unlink(missing_ok=True)
        wav_path.parent.rmdir()

    async def _send_tts_to_native_app(self, wav_path):
        """TTS WAVをC#アプリに送信する。C#側で配信中→FFmpegパイプ、非配信→ローカル再生。"""
        t0 = time.monotonic()
        try:
            from scripts.routes.stream_control import _get_volume
            from scripts.services.capture_client import ws_request

            import base64
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

    async def speak_event(self, event_type, detail, voice=None):
        """イベントに対してアバターが発話する（コミット・作業開始等）"""
        try:
            logger.info("[event] %s: %s", event_type, detail)
            result = await asyncio.to_thread(generate_event_response, event_type, detail)
            logger.info("[event] [%s] %s", result["emotion"], result["response"])
            self._apply_emotion(result["emotion"])
            # 字幕・チャット投稿・音声を同時に送信（TTS生成後に全て発火）
            await self._speak(result["response"], voice=voice, subtitle={
                "author": "システム",
                "message": f"[{event_type}] {detail}",
                "result": result,
            }, chat_result=result, tts_text=result.get("tts_text"))
            self._apply_emotion("neutral")
            await self._notify_overlay_end()
            if self._topic_talker:
                self._topic_talker.mark_spoken()
            # アバター発話をDBに保存
            await self._save_avatar_speech(f"[{event_type}] {detail}", result["response"], result["emotion"])
        except Exception as e:
            logger.error("イベント発話失敗: %s", e)

    async def _get_self_note(self):
        """アバター自身の記憶メモを取得する"""
        try:
            char_name = get_character().get("name", "ちょビ")
            user = await asyncio.to_thread(db.get_or_create_user, char_name)
            return user.get("note", "") or None
        except Exception:
            return None

    async def _update_self_note(self):
        """アバター自身の記憶メモを更新する"""
        try:
            char_name = get_character().get("name", "ちょビ")
            user = await asyncio.to_thread(db.get_or_create_user, char_name)
            recent = await asyncio.to_thread(db.get_recent_comments, 20, 2)
            if not recent:
                return
            current_note = user.get("note", "")
            new_note = await asyncio.to_thread(
                generate_self_note, recent, current_note,
            )
            if new_note and new_note != current_note:
                await asyncio.to_thread(db.update_user_note, user["id"], new_note)
                logger.info("[note] アバターメモ更新: %s", new_note)
        except Exception as e:
            logger.warning("[note] アバターメモ更新失敗: %s", e)

    async def _save_avatar_speech(self, message, response, emotion="neutral"):
        """アバターの発話をDBに保存する（会話履歴に含めるため）"""
        if not self._episode_id:
            logger.warning("[avatar-save] episode_id未設定のためスキップ: %s", message[:30])
            return
        try:
            char_name = get_character().get("name", "ちょビ")
            user = await asyncio.to_thread(db.get_or_create_user, char_name)
            await asyncio.to_thread(
                db.save_comment, self._episode_id, user["id"], message, response, emotion,
            )
            await asyncio.to_thread(db.increment_comment_count, user["id"])
            logger.info("[avatar-save] 保存OK: ep=%s, msg=%s", self._episode_id, message[:30])
        except Exception as e:
            logger.warning("アバター発話DB保存失敗: %s", e)

    async def _note_update_loop(self):
        """15分ごとにユーザーメモをバッチ更新する"""
        from datetime import datetime, timedelta, timezone
        NOTE_INTERVAL = 15 * 60  # 15分
        try:
            last_run = datetime.now(timezone.utc)
            while self._running:
                await asyncio.sleep(NOTE_INTERVAL)
                if not self._running:
                    break
                try:
                    since = last_run.isoformat()
                    last_run = datetime.now(timezone.utc)
                    users = await asyncio.to_thread(db.get_users_commented_since, since)
                    if not users:
                        continue
                    # 各ユーザーの直近コメントを取得
                    users_data = []
                    for u in users:
                        comments = await asyncio.to_thread(
                            db.get_user_recent_comments, u["name"], 10, 2,
                        )
                        if comments:
                            users_data.append({
                                "name": u["name"],
                                "note": u.get("note", ""),
                                "comments": comments,
                            })
                    if not users_data:
                        continue
                    logger.info("[note] ユーザーメモ更新中... (%d人)", len(users_data))
                    notes = await asyncio.to_thread(generate_user_notes, users_data)
                    for u in users:
                        if u["name"] in notes and notes[u["name"]]:
                            await asyncio.to_thread(
                                db.update_user_note, u["id"], notes[u["name"]],
                            )
                    logger.info("[note] ユーザーメモ更新完了: %s", notes)
                    # アバター自身のメモも更新
                    await self._update_self_note()
                except Exception as e:
                    logger.error("[note] ユーザーメモ更新失敗: %s", e)
        except asyncio.CancelledError:
            pass

    def _apply_emotion(self, emotion):
        """感情に対応するBlendShapeを適用する"""
        char = get_character()
        blendshapes = char.get("emotion_blendshapes", {}).get(emotion, {})
        if not blendshapes:
            # ニュートラル: 表情リセット
            all_emotions = set()
            for bs in char.get("emotion_blendshapes", {}).values():
                all_emotions.update(bs.keys())
            blendshapes = {k: 0.0 for k in all_emotions} if all_emotions else {}

        # broadcast.html VRMアバターにWebSocket送信
        if self._on_overlay and blendshapes:
            asyncio.create_task(self._on_overlay({
                "type": "blendshape",
                "shapes": blendshapes,
            }))
