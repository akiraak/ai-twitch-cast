"""授業再生エンジン — セクションを順次再生する"""

import asyncio
import logging
from enum import Enum

from src import db
from src.speech_pipeline import SpeechPipeline

logger = logging.getLogger(__name__)


class LessonState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"


class LessonRunner:
    """授業セクションを順次再生するエンジン

    CommentReaderのSpeechPipelineを共有し、授業セクションを順次発話する。
    一時停止/再開/停止の制御が可能。
    """

    def __init__(self, speech: SpeechPipeline, on_overlay=None):
        self._speech = speech
        self._on_overlay = on_overlay
        self._state = LessonState.IDLE
        self._lesson_id: int | None = None
        self._sections: list[dict] = []
        self._current_index: int = 0
        self._task: asyncio.Task | None = None
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # 初期状態は非一時停止
        self._episode_id: int | None = None

    @property
    def state(self) -> LessonState:
        return self._state

    @property
    def lesson_id(self) -> int | None:
        return self._lesson_id

    @property
    def current_index(self) -> int:
        return self._current_index

    @property
    def total_sections(self) -> int:
        return len(self._sections)

    def set_episode(self, episode_id: int | None):
        self._episode_id = episode_id

    async def start(self, lesson_id: int):
        """授業を開始する"""
        if self._state == LessonState.RUNNING:
            await self.stop()

        lesson = db.get_lesson(lesson_id)
        if not lesson:
            raise ValueError("コンテンツが見つかりません")

        sections = db.get_lesson_sections(lesson_id)
        if not sections:
            raise ValueError("スクリプトがありません。先にスクリプトを生成してください。")

        self._lesson_id = lesson_id
        self._sections = sections
        self._current_index = 0
        self._state = LessonState.RUNNING
        self._pause_event.set()

        logger.info("授業開始: lesson=%d (%s), sections=%d",
                     lesson_id, lesson["name"], len(sections))

        # ステータス通知
        await self._notify_status()

        self._task = asyncio.create_task(self._run_loop())

    async def pause(self):
        """授業を一時停止する"""
        if self._state != LessonState.RUNNING:
            return
        self._state = LessonState.PAUSED
        self._pause_event.clear()
        logger.info("授業一時停止: lesson=%d, section=%d/%d",
                     self._lesson_id, self._current_index + 1, len(self._sections))
        await self._notify_status()

    async def resume(self):
        """授業を再開する"""
        if self._state != LessonState.PAUSED:
            return
        self._state = LessonState.RUNNING
        self._pause_event.set()
        logger.info("授業再開: lesson=%d, section=%d/%d",
                     self._lesson_id, self._current_index + 1, len(self._sections))
        await self._notify_status()

    async def stop(self):
        """授業を停止する"""
        if self._state == LessonState.IDLE:
            return
        self._state = LessonState.IDLE
        self._pause_event.set()  # pause中のawaitを解除
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        self._lesson_id = None
        self._sections = []
        self._current_index = 0
        logger.info("授業停止")
        await self._hide_lesson_text()
        await self._notify_status()

    async def _run_loop(self):
        """セクションを順次再生する"""
        try:
            while self._current_index < len(self._sections) and self._state != LessonState.IDLE:
                # 一時停止中は待機
                await self._pause_event.wait()
                if self._state == LessonState.IDLE:
                    break

                section = self._sections[self._current_index]
                await self._play_section(section)
                self._current_index += 1
                await self._notify_status()

                # セクション間の間（wait_seconds × pace_scale）
                if self._current_index < len(self._sections):
                    wait = section.get("wait_seconds", 2)
                    # questionセクションの間は _handle_question で処理済みなのでスキップ
                    if section.get("section_type") == "question" and section.get("question"):
                        wait = 1  # question後は短い間だけ
                    scaled_wait = wait * self._get_pace_scale()
                    if scaled_wait > 0:
                        await self._pause_aware_sleep(scaled_wait)

            # 全セクション完了
            if self._state != LessonState.IDLE:
                logger.info("授業完了: lesson=%d", self._lesson_id)
                self._state = LessonState.IDLE
                await self._hide_lesson_text()
                await self._notify_status()
                self._lesson_id = None
                self._sections = []
                self._current_index = 0

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("授業再生エラー: %s", e, exc_info=True)
            self._state = LessonState.IDLE
            await self._hide_lesson_text()
            await self._notify_status()

    async def _play_section(self, section: dict):
        """1セクションを再生する"""
        section_type = section["section_type"]
        content = section["content"]
        tts_text = section.get("tts_text") or content
        display_text = section.get("display_text", "")
        emotion = section.get("emotion", "neutral")

        logger.info("[lesson] セクション %d/%d [%s] %s",
                     self._current_index + 1, len(self._sections),
                     emotion, section_type)
        logger.info("[lesson]   content=%s", repr(content[:200]))
        logger.info("[lesson]   tts_text=%s", repr(tts_text[:200]))
        logger.info("[lesson]   display_text=%s", repr(display_text[:200]) if display_text else "（なし）")
        # content==tts_textの場合は警告
        if content == tts_text:
            logger.warning("[lesson]   ⚠ content と tts_text が同一（分離されていない）")
        # SSMLタグやlangタグの混入チェック
        import re as _re
        _ssml_pat = _re.compile(r'<lang\b|</?lang>|\[lang:', _re.IGNORECASE)
        if _ssml_pat.search(content):
            logger.warning("[lesson]   ⚠ content に言語タグが混入: %s", _ssml_pat.findall(content))
        if display_text and _ssml_pat.search(display_text):
            logger.warning("[lesson]   ⚠ display_text に言語タグが混入: %s", _ssml_pat.findall(display_text))

        # 画面テキスト表示
        if display_text:
            await self._show_lesson_text(display_text)

        # 感情適用 → TTS → リセット
        self._speech.apply_emotion(emotion)

        # 発話をSpeechPipelineで行う
        # 長文は文分割して順次再生
        content_parts = SpeechPipeline.split_sentences(content)
        tts_parts = SpeechPipeline.split_sentences(tts_text)

        for i, part in enumerate(content_parts):
            if self._state == LessonState.IDLE:
                break
            part_tts = tts_parts[i] if i < len(tts_parts) else part
            logger.info("[lesson]   part[%d] subtitle=%s", i, repr(part[:100]))
            logger.info("[lesson]   part[%d] tts=%s", i, repr(part_tts[:100]))
            await self._speech.speak(part, subtitle={
                "author": "ちょビ",
                "trigger_text": f"[授業] {section_type}",
                "result": {"speech": part, "emotion": emotion, "translation": ""},
            }, tts_text=part_tts)
            await self._speech.notify_overlay_end()

        self._speech.apply_emotion("neutral")

        # questionセクションの場合: 問いかけ → 待ち → 回答
        if section_type == "question" and section.get("question"):
            await self._handle_question(section)

        # 画面テキスト非表示
        if display_text:
            await asyncio.sleep(0.5)
            await self._hide_lesson_text()

        # アバター発話をDB保存
        if self._episode_id:
            try:
                await asyncio.to_thread(
                    db.save_avatar_comment, self._episode_id,
                    "lesson", f"[授業:{section_type}]", content, emotion,
                )
            except Exception as e:
                logger.warning("授業コメントDB保存失敗: %s", e)

    def _get_pace_scale(self) -> float:
        """settings DBから間のスケールを取得する（デフォルト1.0）"""
        try:
            val = db.get_setting("lesson.pace_scale")
            if val is not None:
                return max(0.1, min(3.0, float(val)))
        except Exception:
            pass
        return 1.0

    async def _pause_aware_sleep(self, seconds: float):
        """一時停止に対応したsleep"""
        steps = max(1, int(seconds * 2))
        interval = seconds / steps
        for _ in range(steps):
            await self._pause_event.wait()
            if self._state == LessonState.IDLE:
                return
            await asyncio.sleep(interval)

    async def _handle_question(self, section: dict):
        """問いかけセクションの処理"""
        wait = section.get("wait_seconds", 8)
        answer = section.get("answer", "")

        if wait > 0:
            scaled_wait = wait * self._get_pace_scale()
            logger.info("[lesson] 問いかけ: %.1f秒待ち (base=%d, scale=%.1f)", scaled_wait, wait, self._get_pace_scale())
            await self._pause_aware_sleep(scaled_wait)

        # 回答
        if answer and self._state != LessonState.IDLE:
            emotion = section.get("emotion", "neutral")
            self._speech.apply_emotion(emotion)
            await self._speech.speak(answer, subtitle={
                "author": "ちょビ",
                "trigger_text": "[授業] 回答",
                "result": {"speech": answer, "emotion": emotion, "translation": ""},
            }, tts_text=answer)
            await self._speech.notify_overlay_end()
            self._speech.apply_emotion("neutral")

    async def _show_lesson_text(self, text: str):
        """配信画面にテキストを表示する"""
        if self._on_overlay:
            await self._on_overlay({
                "type": "lesson_text_show",
                "text": text,
            })

    async def _hide_lesson_text(self):
        """配信画面のテキストを非表示にする"""
        if self._on_overlay:
            await self._on_overlay({
                "type": "lesson_text_hide",
            })

    async def _notify_status(self):
        """授業ステータスを配信画面に通知する"""
        if self._on_overlay:
            await self._on_overlay({
                "type": "lesson_status",
                "state": self._state.value,
                "lesson_id": self._lesson_id,
                "current_index": self._current_index,
                "total_sections": len(self._sections),
            })

    def get_status(self) -> dict:
        """現在のステータスを取得する"""
        return {
            "state": self._state.value,
            "lesson_id": self._lesson_id,
            "current_index": self._current_index,
            "total_sections": len(self._sections),
        }
