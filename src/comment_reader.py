"""コメント読み上げサービス（Twitchチャット → AI応答 → TTS → 再生 → 表情連動 → DB保存）"""

import asyncio
import logging
from collections import deque

logger = logging.getLogger(__name__)

from src import db
from src.ai_responder import (
    generate_event_response, generate_multi_event_response, generate_multi_response,
    generate_persona, generate_response, generate_self_note, generate_user_notes,
    get_character, get_character_id, get_chat_characters,
)
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
        self._segment_queue = deque()  # 長文分割の2文目以降/マルチキャラの後続エントリ
        self._process_task = None
        self._note_task = None
        self._running = False
        self._episode_id = None
        self._characters = None  # {"teacher": config, "student": config or None}

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
        # マルチキャラ設定を読み込み
        try:
            self._characters = await asyncio.to_thread(get_chat_characters)
            if self._characters.get("student"):
                logger.info("[multi-char] マルチキャラモード: teacher=%s, student=%s",
                            self._characters["teacher"].get("name"),
                            self._characters["student"].get("name"))
            else:
                logger.info("[multi-char] シングルキャラモード: teacher=%s",
                            self._characters["teacher"].get("name"))
        except Exception as e:
            logger.warning("[multi-char] キャラクター読み込み失敗、シングルモードで動作: %s", e)
            self._characters = None
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
        """分割された1セグメントを発話する（マルチキャラ対応）"""
        try:
            translation = seg.get("translation", "")
            avatar_id = seg.get("avatar_id", "teacher")
            voice = seg.get("voice")
            style = seg.get("style")
            char_name = seg.get("char_name", "ちょビ")
            char_config = seg.get("char_config")
            speaker = seg.get("speaker", "teacher")
            logger.info("[segment] セグメント発話: [%s/%s] %s", speaker, seg["emotion"], seg["content"])

            # キャラ間の間（前のセグメントと異なるspeakerの場合）
            if seg.get("inter_speaker_pause"):
                await asyncio.sleep(0.3)

            self._speech.apply_emotion(seg["emotion"], avatar_id=avatar_id, character_config=char_config)
            await self._speech.speak(seg["content"], subtitle={
                "author": char_name,
                "trigger_text": seg["content"],
                "result": {"speech": seg["content"], "emotion": seg["emotion"], "translation": translation},
            }, chat_result={"speech": seg["content"], "translation": translation},
                tts_text=seg.get("tts_text"), voice=voice, style=style, avatar_id=avatar_id,
                post_to_chat=self._post_to_chat)
            self._speech.apply_emotion("neutral", avatar_id=avatar_id, character_config=char_config)
            await self._speech.notify_overlay_end()
            # アバター発話をDBに保存
            await self._save_avatar_comment("segment", "[セグメント]", seg["content"], seg["emotion"], speaker=speaker)
        except Exception as e:
            logger.error("セグメント発話失敗: %s", e, exc_info=True)

    async def respond_webui(self, message):
        """WebUIからの会話に応答する（あキらのメッセージをTwitchチャットに投稿）"""
        author = "あキら"
        try:
            # あキらのメッセージをTwitchチャットに投稿
            try:
                await self._chat.send_message(f"[あキら] {message}")
            except Exception as e:
                logger.warning("GMメッセージのチャット投稿失敗: %s", e)
            user = await asyncio.to_thread(db.get_or_create_user, author)

            # マルチキャラモード
            if self._characters and self._characters.get("student"):
                responses = await self._generate_multi_ai_response(
                    author, message, user["comment_count"],
                )
                await self._save_multi_to_db(user, message, responses)
                await asyncio.to_thread(db.update_user_last_seen, user["id"])
                first = responses[0]
                first_cfg = self._characters.get(first["speaker"], self._characters["teacher"])
                se_info = None
                if first.get("se"):
                    from src.se_resolver import resolve_se
                    se_info = resolve_se(first["se"])
                self._speech.apply_emotion(first["emotion"], avatar_id=first["speaker"], character_config=first_cfg)
                await self._speech.speak(first["speech"], subtitle={
                    "author": first_cfg.get("name", author), "trigger_text": message, "result": first,
                }, tts_text=first.get("tts_text"), se=se_info,
                    voice=first_cfg.get("tts_voice"), style=first_cfg.get("tts_style"),
                    avatar_id=first["speaker"])
                self._speech.apply_emotion("neutral", avatar_id=first["speaker"], character_config=first_cfg)
                await self._speech.notify_overlay_end()
                # 2エントリ目以降
                for entry in responses[1:]:
                    cfg = self._characters.get(entry["speaker"], self._characters["teacher"])
                    await asyncio.sleep(0.3)
                    self._speech.apply_emotion(entry["emotion"], avatar_id=entry["speaker"], character_config=cfg)
                    await self._speech.speak(entry["speech"], subtitle={
                        "author": cfg.get("name", entry["speaker"]), "trigger_text": message, "result": entry,
                    }, tts_text=entry.get("tts_text"),
                        voice=cfg.get("tts_voice"), style=cfg.get("tts_style"),
                        avatar_id=entry["speaker"])
                    self._speech.apply_emotion("neutral", avatar_id=entry["speaker"], character_config=cfg)
                    await self._speech.notify_overlay_end()
                return first
            else:
                # シングルキャラモード（既存動作）
                result = await self._generate_ai_response(
                    author, message, user["comment_count"],
                )
                await self._save_to_db(user, message, result)
                await asyncio.to_thread(db.update_user_last_seen, user["id"])
                self._speech.apply_emotion(result["emotion"])
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
        """1件のコメントにAIで応答して読み上げる（マルチキャラ対応）"""
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

            # マルチキャラモード
            if self._characters and self._characters.get("student"):
                responses = await self._generate_multi_ai_response(
                    author, message, user["comment_count"], note,
                    already_greeted=already_greeted,
                )
                # 視聴者コメント + 全応答をDB保存
                await self._save_multi_to_db(user, message, responses)
                await asyncio.to_thread(db.update_user_last_seen, user["id"])

                first = responses[0]
                first_cfg = self._characters.get(first["speaker"], self._characters["teacher"])
                first_name = first_cfg.get("name", first["speaker"])

                # SE解決（1エントリ目のみ）
                se_info = None
                if first.get("se"):
                    from src.se_resolver import resolve_se
                    se_info = resolve_se(first["se"])
                    if se_info:
                        logger.info("[se] AI選択: category=%s → %s", first["se"], se_info["filename"])

                # 1エントリ目: SE・字幕・チャット投稿付きで即再生
                self._speech.apply_emotion(first["emotion"], avatar_id=first["speaker"], character_config=first_cfg)
                await self._speech.speak(first["speech"], subtitle={
                    "author": first_name, "trigger_text": message, "result": first,
                }, chat_result=first, tts_text=first.get("tts_text"),
                    voice=first_cfg.get("tts_voice"), style=first_cfg.get("tts_style"),
                    avatar_id=first["speaker"],
                    post_to_chat=self._post_to_chat, se=se_info)
                self._speech.apply_emotion("neutral", avatar_id=first["speaker"], character_config=first_cfg)
                await self._speech.notify_overlay_end()

                # 2エントリ目以降はセグメントキューに入れる（コメント到着でキャンセル）
                for entry in responses[1:]:
                    cfg = self._characters.get(entry["speaker"], self._characters["teacher"])
                    self._segment_queue.append({
                        "content": entry["speech"],
                        "emotion": entry["emotion"],
                        "tts_text": entry.get("tts_text"),
                        "translation": entry.get("translation", ""),
                        "speaker": entry["speaker"],
                        "avatar_id": entry["speaker"],
                        "voice": cfg.get("tts_voice"),
                        "style": cfg.get("tts_style"),
                        "char_name": cfg.get("name", entry["speaker"]),
                        "char_config": cfg,
                        "inter_speaker_pause": True,
                    })
            else:
                # シングルキャラモード（既存動作）
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

    async def _generate_multi_ai_response(self, author, message, comment_count, user_note="", already_greeted=False):
        """マルチキャラAI応答を生成する（両キャラのメモ・ペルソナを使用）"""
        logger.info("[ai] マルチキャラ応答生成中...")
        timeline = await asyncio.to_thread(db.get_recent_timeline, 10, 2)
        stream_context = await self._get_stream_context()

        # 先生のコンテキスト
        teacher_id = get_character_id()
        teacher_memory = await asyncio.to_thread(db.get_character_memory, teacher_id)
        self_note = teacher_memory.get("self_note") or None
        persona = teacher_memory.get("persona") or None

        # 生徒のコンテキスト（先生と同じフローで取得）
        student_self_note = None
        student_persona = None
        student_ctx = self._get_student_context()
        if student_ctx:
            student_memory = await asyncio.to_thread(db.get_character_memory, student_ctx["id"])
            student_self_note = student_memory.get("self_note") or None
            student_persona = student_memory.get("persona") or None

        responses = await asyncio.to_thread(
            generate_multi_response, author, message, self._characters,
            comment_count=comment_count, timeline=timeline,
            stream_context=stream_context, user_note=user_note or None,
            already_greeted=already_greeted, self_note=self_note, persona=persona,
            student_self_note=student_self_note, student_persona=student_persona,
        )
        for r in responses:
            logger.info("[ai] [%s/%s] %s", r["speaker"], r["emotion"], r["speech"])
        return responses

    async def _get_stream_context(self):
        """配信コンテキストを収集する（タイトル・トピック・TODO・授業情報）"""
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
        # 授業情報（LessonRunnerが実行中の場合）
        try:
            runner = self._lesson_runner
            if runner.state.value != "idle" and runner.lesson_id:
                lesson = await asyncio.to_thread(db.get_lesson, runner.lesson_id)
                if lesson:
                    lesson_ctx = {"lesson_name": lesson["name"]}
                    sections = runner._sections
                    idx = runner.current_index
                    if idx < len(sections):
                        current = sections[idx]
                        lesson_ctx["current_section"] = current.get("content", "")[:200]
                        lesson_ctx["section_type"] = current.get("section_type", "")
                    context["lesson"] = lesson_ctx
        except Exception as e:
            logger.debug("授業情報取得失敗: %s", e)
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

    async def _save_multi_to_db(self, user, message, responses):
        """マルチキャラ応答をDBに保存する"""
        if not self._episode_id:
            return
        # 視聴者コメントを保存
        await asyncio.to_thread(
            db.save_comment, self._episode_id, user["id"], message,
        )
        await asyncio.to_thread(db.increment_comment_count, user["id"])
        # 各キャラの応答を保存
        for entry in responses:
            await asyncio.to_thread(
                db.save_avatar_comment, self._episode_id, "comment",
                f"{user['name']}さんのコメント: {message}",
                entry["speech"], entry["emotion"], speaker=entry.get("speaker"),
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

    async def speak_event(self, event_type, detail, voice=None, style=None, avatar_id="teacher"):
        """イベントに対してアバターが発話する（コミット・作業開始等、マルチキャラ対応）"""
        try:
            logger.info("[event] %s: %s", event_type, detail)
            # 直前のイベント応答を取得（繰り返し防止）
            last_responses = None
            try:
                recent = await asyncio.to_thread(db.get_recent_avatar_comments, 5, 1, trigger_type="event")
                last_responses = [c["text"] for c in recent if c.get("text")]
            except Exception:
                pass

            # マルチキャラモード
            if self._characters and self._characters.get("student"):
                responses = await asyncio.to_thread(
                    generate_multi_event_response, event_type, detail,
                    self._characters, last_event_responses=last_responses,
                )
                for i, entry in enumerate(responses):
                    cfg = self._characters.get(entry["speaker"], self._characters["teacher"])
                    entry_name = cfg.get("name", entry["speaker"])
                    entry_voice = voice if i == 0 and voice else cfg.get("tts_voice")
                    entry_style = style if i == 0 and style else cfg.get("tts_style")
                    entry_avatar_id = entry["speaker"]
                    logger.info("[event] [%s/%s] %s", entry["speaker"], entry["emotion"], entry["speech"])

                    if i > 0:
                        await asyncio.sleep(0.3)

                    self._speech.apply_emotion(entry["emotion"], avatar_id=entry_avatar_id, character_config=cfg)
                    await self._speech.speak(entry["speech"], voice=entry_voice, style=entry_style,
                        avatar_id=entry_avatar_id, subtitle={
                        "author": entry_name,
                        "trigger_text": f"[{event_type}] {detail}",
                        "result": entry,
                    }, chat_result=entry if i == 0 else None,
                        tts_text=entry.get("tts_text"),
                        post_to_chat=self._post_to_chat if i == 0 else None)
                    self._speech.apply_emotion("neutral", avatar_id=entry_avatar_id, character_config=cfg)
                    await self._speech.notify_overlay_end()
                    await self._save_avatar_comment(
                        "event", f"[{event_type}] {detail}",
                        entry["speech"], entry["emotion"], speaker=entry["speaker"],
                    )
            else:
                # シングルキャラモード（既存動作）
                result = await asyncio.to_thread(generate_event_response, event_type, detail, last_event_responses=last_responses)
                logger.info("[event] [%s] %s", result["emotion"], result["speech"])
                self._speech.apply_emotion(result["emotion"], avatar_id=avatar_id)
                await self._speech.speak(result["speech"], voice=voice, style=style, avatar_id=avatar_id, subtitle={
                    "author": "システム",
                    "trigger_text": f"[{event_type}] {detail}",
                    "result": result,
                }, chat_result=result, tts_text=result.get("tts_text"),
                    post_to_chat=self._post_to_chat)
                self._speech.apply_emotion("neutral", avatar_id=avatar_id)
                await self._speech.notify_overlay_end()
                await self._save_avatar_comment("event", f"[{event_type}] {detail}", result["speech"], result["emotion"])
        except Exception as e:
            logger.error("イベント発話失敗: %s", e)

    def _get_student_context(self):
        """生徒キャラのコンテキスト{id, config}を返す（なければNone）"""
        if not self._characters or not self._characters.get("student"):
            return None
        student_cfg = self._characters["student"]
        from src.character_manager import get_channel_id
        row = db.get_character_by_role(get_channel_id(), "student")
        if not row:
            return None
        return {"id": row["id"], "config": student_cfg}

    async def _get_self_note(self):
        """先生キャラの記憶メモを取得する"""
        try:
            char_id = get_character_id()
            memory = await asyncio.to_thread(db.get_character_memory, char_id)
            return memory.get("self_note", "") or None
        except Exception as e:
            logger.debug("アバターメモ取得失敗: %s", e)
            return None

    # --- 共通メモ更新メソッド ---

    async def _update_character_self_note(self, char_id, char_config, char_name=None):
        """1キャラのセルフメモを更新する（共通処理）"""
        name = char_name or char_config.get("name", "?")
        try:
            memory = await asyncio.to_thread(db.get_character_memory, char_id)
            timeline = await asyncio.to_thread(db.get_recent_timeline, 50, 2)
            if not timeline:
                return
            new_note = await asyncio.to_thread(
                generate_self_note, timeline, char_config=char_config,
            )
            if new_note and new_note != memory.get("self_note", ""):
                await asyncio.to_thread(db.update_character_self_note, char_id, new_note)
                logger.info("[note] %sメモ更新: %s", name, new_note)
        except Exception as e:
            logger.warning("[note] %sメモ更新失敗: %s", name, e)

    async def _update_character_persona(self, char_id, char_config, speaker=None, char_name=None):
        """1キャラのペルソナを更新する（共通処理）"""
        name = char_name or char_config.get("name", "?")
        try:
            memory = await asyncio.to_thread(db.get_character_memory, char_id)
            current_persona = memory.get("persona", "")
            avatar_comments = await asyncio.to_thread(
                db.get_recent_avatar_comments, 50, 2, speaker=speaker,
            )
            if not avatar_comments:
                return
            persona = await asyncio.to_thread(
                generate_persona, avatar_comments, current_persona, char_config=char_config,
            )
            if persona:
                await asyncio.to_thread(db.update_character_persona, char_id, persona)
                logger.info("[persona] %sペルソナ更新: %s", name, persona[:80])
        except Exception as e:
            logger.warning("[persona] %sペルソナ更新失敗: %s", name, e)

    async def _update_self_note(self):
        """全キャラのセルフメモを更新する"""
        # 先生
        teacher_id = get_character_id()
        await self._update_character_self_note(teacher_id, get_character())
        # 生徒
        student_ctx = self._get_student_context()
        if student_ctx:
            await self._update_character_self_note(student_ctx["id"], student_ctx["config"])

    async def _update_persona(self):
        """全キャラのペルソナを更新する"""
        # 先生
        teacher_id = get_character_id()
        await self._update_character_persona(teacher_id, get_character())
        # 生徒
        student_ctx = self._get_student_context()
        if student_ctx:
            await self._update_character_persona(
                student_ctx["id"], student_ctx["config"], speaker="student",
            )

    async def _save_avatar_comment(self, trigger_type, trigger_text, text, emotion="neutral", speaker=None):
        """アバターのコメントをDBに保存する"""
        if not self._episode_id:
            logger.warning("[avatar-save] episode_id未設定のためスキップ: %s", trigger_text[:30])
            return
        try:
            await asyncio.to_thread(
                db.save_avatar_comment, self._episode_id, trigger_type, trigger_text, text, emotion,
                speaker=speaker,
            )
            logger.info("[avatar-save] 保存OK: ep=%s, type=%s, speaker=%s", self._episode_id, trigger_type, speaker)
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
