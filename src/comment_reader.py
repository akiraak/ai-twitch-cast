"""コメント読み上げサービス（Twitchチャット → AI応答 → TTS → 再生 → 表情連動 → DB保存）"""

import asyncio
import logging
from collections import deque

logger = logging.getLogger(__name__)

from src import db
from src.ai_responder import generate_event_response, generate_persona, generate_response, generate_self_note, generate_user_notes, get_character, get_character_id
from src.lesson_runner import LessonRunner
from src.speech_pipeline import SpeechPipeline
from src.twitch_chat import TwitchChat


class CommentReader:
    """Twitchコメントを読み上げるサービス"""

    def __init__(self, on_overlay=None):
        self._chat = TwitchChat()
        self._on_overlay = on_overlay
        self._speech = SpeechPipeline(on_overlay=on_overlay)
        self._lesson_runner = LessonRunner(speech=self._speech, on_overlay=on_overlay)
        self._queue = deque()
        self._segment_queue = deque()  # 長文分割の2文目以降
        self._process_task = None
        self._note_task = None
        self._running = False
        self._episode_id = None

    @property
    def lesson_runner(self) -> LessonRunner:
        return self._lesson_runner

    def set_episode(self, episode_id):
        """現在のエピソードIDを設定する"""
        self._episode_id = episode_id
        self._lesson_runner.set_episode(episode_id)

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
        # 授業実行中なら停止
        await self._lesson_runner.stop()
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
        self._segment_queue.clear()
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
                    # コメント最優先 → 残りセグメントはキャンセル
                    if self._segment_queue:
                        logger.info("[segment] コメント到着 → 残り%dセグメントをキャンセル", len(self._segment_queue))
                        self._segment_queue.clear()
                    author, message = self._queue.popleft()
                    await self._respond(author, message)
                elif self._segment_queue:
                    # 長文分割の続きセグメント
                    seg = self._segment_queue.popleft()
                    await self._speak_segment(seg)
                else:
                    await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            pass

    async def _speak_segment(self, seg):
        """分割された1セグメントを発話する"""
        try:
            translation = seg.get("translation", "")
            logger.info("[segment] セグメント発話: [%s] %s", seg["emotion"], seg["content"])
            self._speech.apply_emotion(seg["emotion"])
            await self._speech.speak(seg["content"], subtitle={
                "author": "ちょビ",
                "trigger_text": seg["content"],
                "result": {"speech": seg["content"], "emotion": seg["emotion"], "translation": translation},
            }, chat_result={"speech": seg["content"], "translation": translation},
                tts_text=seg.get("tts_text"), post_to_chat=self._post_to_chat)
            self._speech.apply_emotion("neutral")
            await self._speech.notify_overlay_end()
            # アバター発話をDBに保存
            await self._save_avatar_comment("segment", "[セグメント]", seg["content"], seg["emotion"])
        except Exception as e:
            logger.error("セグメント発話失敗: %s", e, exc_info=True)

    async def respond_webui(self, message):
        """WebUIからの会話に応答する（GMのメッセージをTwitchチャットに投稿）"""
        author = "GM"
        try:
            # GMのメッセージをTwitchチャットに投稿
            try:
                await self._chat.send_message(f"[GM] {message}")
            except Exception as e:
                logger.warning("GMメッセージのチャット投稿失敗: %s", e)
            user = await asyncio.to_thread(db.get_or_create_user, author)
            result = await self._generate_ai_response(
                author, message, user["comment_count"],
            )
            await self._save_to_db(user, message, result)
            await asyncio.to_thread(db.update_user_last_seen, user["id"])
            self._speech.apply_emotion(result["emotion"])
            # SE解決
            se_info = None
            if result.get("se"):
                from src.se_resolver import resolve_se
                se_info = resolve_se(result["se"])
            await self._speech.speak(result["speech"], subtitle={
                "author": author, "trigger_text": message, "result": result,
            }, tts_text=result.get("tts_text"), se=se_info)
            self._speech.apply_emotion("neutral")
            await self._speech.notify_overlay_end()
            return result
        except Exception as e:
            logger.error("WebUI応答失敗: %s", e)
            return {"speech": "", "emotion": "neutral", "translation": ""}

    async def _respond(self, author, message):
        """1件のコメントにAIで応答して読み上げる（長文は分割して順次再生）"""
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

            # 句読点で分割
            from src.speech_pipeline import SpeechPipeline
            content_parts = SpeechPipeline.split_sentences(result["speech"])
            tts_parts = SpeechPipeline.split_sentences(result.get("tts_text", result["speech"]))

            # SE解決（1文目のみ）
            se_info = None
            if result.get("se"):
                from src.se_resolver import resolve_se
                se_info = resolve_se(result["se"])
                if se_info:
                    logger.info("[se] AI選択: category=%s → %s", result["se"], se_info["filename"])

            # 1文目: SE・字幕・チャット投稿付きで即再生
            first_tts = tts_parts[0] if tts_parts else content_parts[0]
            first_result = {**result, "speech": content_parts[0]}
            self._speech.apply_emotion(result["emotion"])
            await self._speech.speak(content_parts[0], subtitle={
                "author": author, "trigger_text": message, "result": first_result,
            }, chat_result=result, tts_text=first_tts,
                post_to_chat=self._post_to_chat, se=se_info)
            self._speech.apply_emotion("neutral")
            await self._speech.notify_overlay_end()

            # 2文目以降はキューに入れる（コメント到着でキャンセル）
            for i in range(1, len(content_parts)):
                tts_text = tts_parts[i] if i < len(tts_parts) else content_parts[i]
                self._segment_queue.append({
                    "content": content_parts[i],
                    "emotion": result["emotion"],
                    "tts_text": tts_text,
                    "translation": "",
                })
        except Exception as e:
            logger.error("応答失敗: %s", e)

    async def _generate_ai_response(self, author, message, comment_count, user_note="", already_greeted=False):
        """AI応答を生成する（会話履歴・配信コンテキスト付き）"""
        logger.info("[ai] 応答生成中...")
        timeline = await asyncio.to_thread(db.get_recent_timeline, 10, 2)
        stream_context = await self._get_stream_context()
        # アバター自身のメモを取得
        self_note = await self._get_self_note()
        # ペルソナ（性格特徴）を取得
        char_id = get_character_id()
        memory = await asyncio.to_thread(db.get_character_memory, char_id)
        persona = memory.get("persona") or None
        result = await asyncio.to_thread(
            generate_response, author, message, comment_count,
            timeline=timeline, stream_context=stream_context,
            user_note=user_note or None, already_greeted=already_greeted,
            self_note=self_note, persona=persona,
        )
        logger.info("[ai] [%s] %s", result["emotion"], result["speech"])
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
        except Exception as e:
            logger.debug("配信タイトル取得失敗: %s", e)
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
        except Exception as e:
            logger.debug("TODO取得失敗: %s", e)
        return context if context else None

    async def _save_to_db(self, user, message, result):
        """コメントと応答をDBに保存する"""
        if not self._episode_id:
            return
        # 視聴者コメントを保存
        await asyncio.to_thread(
            db.save_comment, self._episode_id, user["id"], message,
        )
        await asyncio.to_thread(db.increment_comment_count, user["id"])
        # アバターの応答を保存
        await asyncio.to_thread(
            db.save_avatar_comment, self._episode_id, "comment",
            f"{user['name']}さんのコメント: {message}",
            result["speech"], result["emotion"],
        )

    async def _post_to_chat(self, result):
        """AI応答をTwitchチャットに投稿する"""
        try:
            text = SpeechPipeline.strip_lang_tags(result["speech"])
            translation = result.get("translation", "")
            if translation:
                text = f"{text} ({translation})"
            await self._chat.send_message(text)
        except Exception as e:
            logger.error("チャット投稿失敗: %s", e)

    async def speak_event(self, event_type, detail, voice=None):
        """イベントに対してアバターが発話する（コミット・作業開始等）"""
        try:
            logger.info("[event] %s: %s", event_type, detail)
            # 直前のイベント応答を取得（繰り返し防止）
            last_responses = None
            try:
                recent = await asyncio.to_thread(db.get_recent_avatar_comments, 5, 1, trigger_type="event")
                last_responses = [c["text"] for c in recent if c.get("text")]
            except Exception:
                pass
            result = await asyncio.to_thread(generate_event_response, event_type, detail, last_event_responses=last_responses)
            logger.info("[event] [%s] %s", result["emotion"], result["speech"])
            self._speech.apply_emotion(result["emotion"])
            # 字幕・チャット投稿・音声を同時に送信（TTS生成後に全て発火）
            await self._speech.speak(result["speech"], voice=voice, subtitle={
                "author": "システム",
                "trigger_text": f"[{event_type}] {detail}",
                "result": result,
            }, chat_result=result, tts_text=result.get("tts_text"),
                post_to_chat=self._post_to_chat)
            self._speech.apply_emotion("neutral")
            await self._speech.notify_overlay_end()
            # アバター発話をDBに保存
            await self._save_avatar_comment("event", f"[{event_type}] {detail}", result["speech"], result["emotion"])
        except Exception as e:
            logger.error("イベント発話失敗: %s", e)

    async def _get_self_note(self):
        """アバター自身の記憶メモを取得する"""
        try:
            char_id = get_character_id()
            memory = await asyncio.to_thread(db.get_character_memory, char_id)
            return memory.get("self_note", "") or None
        except Exception as e:
            logger.debug("アバターメモ取得失敗: %s", e)
            return None

    async def _update_self_note(self):
        """アバター自身の記憶メモを更新する"""
        try:
            from datetime import datetime, timedelta, timezone
            char_id = get_character_id()
            memory = await asyncio.to_thread(db.get_character_memory, char_id)
            timeline = await asyncio.to_thread(db.get_recent_timeline, 50, 2)
            if not timeline:
                return
            new_note = await asyncio.to_thread(
                generate_self_note, timeline,
            )
            if new_note and new_note != memory.get("self_note", ""):
                await asyncio.to_thread(db.update_character_self_note, char_id, new_note)
                logger.info("[note] アバターメモ更新: %s", new_note)
        except Exception as e:
            logger.warning("[note] アバターメモ更新失敗: %s", e)

    async def _update_persona(self):
        """ペルソナ（性格特徴）を応答パターンから更新する"""
        try:
            char_id = get_character_id()
            memory = await asyncio.to_thread(db.get_character_memory, char_id)
            current_persona = memory.get("persona", "")
            avatar_comments = await asyncio.to_thread(db.get_recent_avatar_comments, 50, 2)
            if not avatar_comments:
                return
            persona = await asyncio.to_thread(generate_persona, avatar_comments, current_persona)
            if persona:
                await asyncio.to_thread(db.update_character_persona, char_id, persona)
                logger.info("[persona] ペルソナ更新: %s", persona[:80])
        except Exception as e:
            logger.warning("[persona] ペルソナ更新失敗: %s", e)

    async def _save_avatar_comment(self, trigger_type, trigger_text, text, emotion="neutral"):
        """アバターのコメントをDBに保存する"""
        if not self._episode_id:
            logger.warning("[avatar-save] episode_id未設定のためスキップ: %s", trigger_text[:30])
            return
        try:
            await asyncio.to_thread(
                db.save_avatar_comment, self._episode_id, trigger_type, trigger_text, text, emotion,
            )
            logger.info("[avatar-save] 保存OK: ep=%s, type=%s", self._episode_id, trigger_type)
        except Exception as e:
            logger.warning("アバターコメントDB保存失敗: %s", e)

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
                    # ユーザーメモ更新（直近15分にコメントがあった場合のみ）
                    users = await asyncio.to_thread(db.get_users_commented_since, since)
                    if users:
                        users_data = []
                        for u in users:
                            comments = await asyncio.to_thread(
                                db.get_user_recent_comments, u["name"], 20, 2,
                            )
                            if comments:
                                users_data.append({
                                    "name": u["name"],
                                    "note": u.get("note", ""),
                                    "comments": comments,
                                })
                        if users_data:
                            logger.info("[note] ユーザーメモ更新中... (%d人)", len(users_data))
                            notes = await asyncio.to_thread(generate_user_notes, users_data)
                            for u in users:
                                if u["name"] in notes and notes[u["name"]]:
                                    await asyncio.to_thread(
                                        db.update_user_note, u["id"], notes[u["name"]],
                                    )
                            logger.info("[note] ユーザーメモ更新完了: %s", notes)
                    # アバター自身のメモ・ペルソナは常に更新（直近コメントの有無に依存しない）
                    await self._update_self_note()
                    await self._update_persona()
                except Exception as e:
                    logger.error("[note] ユーザーメモ更新失敗: %s", e)
        except asyncio.CancelledError:
            pass
