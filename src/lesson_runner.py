"""授業再生エンジン — セクションを順次再生する"""

import asyncio
import json as _json
import logging
import shutil
from enum import Enum
from pathlib import Path

from src import db
from src.lesson_generator import get_lesson_characters
from src.speech_pipeline import SpeechPipeline

PROJECT_DIR = Path(__file__).resolve().parent.parent
LESSON_AUDIO_DIR = PROJECT_DIR / "resources" / "audio" / "lessons"

logger = logging.getLogger(__name__)


class LessonState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"


def _cache_path(lesson_id: int, order_index: int, part_index: int, lang: str = "ja", generator: str = "gemini") -> Path:
    """TTSキャッシュファイルのパスを返す（generator別サブディレクトリ、旧パス互換あり）"""
    filename = f"section_{order_index:02d}_part_{part_index:02d}.wav"
    new_path = LESSON_AUDIO_DIR / str(lesson_id) / lang / generator / filename
    if new_path.exists():
        return new_path
    # 旧パス互換（generator導入前のキャッシュ）
    if generator == "gemini":
        legacy = LESSON_AUDIO_DIR / str(lesson_id) / lang / filename
        if legacy.exists():
            return legacy
    return new_path


def _dlg_cache_path(lesson_id: int, order_index: int, dlg_index: int, lang: str = "ja", generator: str = "gemini") -> Path:
    """dialogue用TTSキャッシュファイルのパスを返す（generator別サブディレクトリ、旧パス互換あり）"""
    filename = f"section_{order_index:02d}_dlg_{dlg_index:02d}.wav"
    new_path = LESSON_AUDIO_DIR / str(lesson_id) / lang / generator / filename
    if new_path.exists():
        return new_path
    # 旧パス互換（generator導入前のキャッシュ）
    if generator == "gemini":
        legacy = LESSON_AUDIO_DIR / str(lesson_id) / lang / filename
        if legacy.exists():
            return legacy
    return new_path


def clear_tts_cache(lesson_id: int, order_index: int | None = None, lang: str | None = None, generator: str | None = None):
    """TTSキャッシュを削除する

    Args:
        lesson_id: レッスンID
        order_index: 指定時はそのセクションのみ、Noneなら全セクション
        lang: 指定時はその言語のみ、Noneなら全言語
        generator: 指定時はそのジェネレータのキャッシュのみ、Noneなら全ジェネレータ
    """
    if generator is not None:
        # 特定generatorのキャッシュのみ削除
        if lang:
            gen_dir = LESSON_AUDIO_DIR / str(lesson_id) / lang / generator
            if not gen_dir.exists():
                return
            if order_index is not None:
                for f in gen_dir.glob(f"section_{order_index:02d}_*.wav"):
                    f.unlink(missing_ok=True)
            else:
                shutil.rmtree(gen_dir, ignore_errors=True)
        else:
            lesson_dir = LESSON_AUDIO_DIR / str(lesson_id)
            if not lesson_dir.exists():
                return
            for lang_dir in lesson_dir.iterdir():
                if lang_dir.is_dir():
                    gen_dir = lang_dir / generator
                    if gen_dir.exists():
                        if order_index is not None:
                            for f in gen_dir.glob(f"section_{order_index:02d}_*.wav"):
                                f.unlink(missing_ok=True)
                        else:
                            shutil.rmtree(gen_dir, ignore_errors=True)
        return

    # generator=None → 既存動作（全ジェネレータ削除）
    if lang:
        lesson_dir = LESSON_AUDIO_DIR / str(lesson_id) / lang
    else:
        lesson_dir = LESSON_AUDIO_DIR / str(lesson_id)
    if not lesson_dir.exists():
        return
    if order_index is not None:
        # レガシーファイル（lang直下）
        for f in lesson_dir.glob(f"section_{order_index:02d}_part_*.wav"):
            f.unlink(missing_ok=True)
        # generatorサブディレクトリ内のファイル
        if lang:
            for sub in lesson_dir.iterdir():
                if sub.is_dir():
                    for f in sub.glob(f"section_{order_index:02d}_*.wav"):
                        f.unlink(missing_ok=True)
    else:
        shutil.rmtree(lesson_dir, ignore_errors=True)


def get_tts_cache_info(lesson_id: int, lang: str = "ja", generator: str = "gemini") -> list[dict]:
    """TTSキャッシュの状況を返す（part形式 + dlg形式の両方を検索）

    Args:
        lesson_id: レッスンID
        lang: 言語
        generator: ジェネレータ（新パス構造のサブディレクトリ、geminiの場合は旧パスもスキャン）
    """
    sections_map: dict[int, list[dict]] = {}
    seen: set[tuple[int, str, int]] = set()  # (order_index, type, index) 重複排除

    # スキャン対象ディレクトリ: 新パス + レガシーパス（geminiのみ）
    scan_dirs: list[Path] = []
    gen_dir = LESSON_AUDIO_DIR / str(lesson_id) / lang / generator
    if gen_dir.exists():
        scan_dirs.append(gen_dir)
    if generator == "gemini":
        legacy_dir = LESSON_AUDIO_DIR / str(lesson_id) / lang
        if legacy_dir.exists():
            scan_dirs.append(legacy_dir)

    for scan_dir in scan_dirs:
        # part形式: section_00_part_00.wav
        for f in sorted(scan_dir.glob("section_*_part_*.wav")):
            parts = f.stem.split("_")  # section_00_part_00
            oi = int(parts[1])
            pi = int(parts[3])
            key = (oi, "part", pi)
            if key not in seen:
                seen.add(key)
                sections_map.setdefault(oi, []).append({
                    "part_index": pi,
                    "path": str(f.relative_to(PROJECT_DIR)),
                    "size": f.stat().st_size,
                })
        # dlg形式: section_00_dlg_00.wav
        for f in sorted(scan_dir.glob("section_*_dlg_*.wav")):
            parts = f.stem.split("_")  # section_00_dlg_00
            oi = int(parts[1])
            di = int(parts[3])
            key = (oi, "dlg", di)
            if key not in seen:
                seen.add(key)
                sections_map.setdefault(oi, []).append({
                    "part_index": di,
                    "path": str(f.relative_to(PROJECT_DIR)),
                    "size": f.stat().st_size,
                })

    # DB上のセクション数に合わせて返す
    db_sections = db.get_lesson_sections(lesson_id, lang=lang, generator=generator)
    result = []
    for i, sec in enumerate(db_sections):
        result.append({
            "order_index": sec["order_index"],
            "section_id": sec["id"],
            "parts": sections_map.get(sec["order_index"], []),
        })
    return result


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
        self._lesson_name: str = ""
        self._lang: str = "ja"
        self._sections: list[dict] = []
        self._current_index: int = 0
        self._task: asyncio.Task | None = None
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # 初期状態は非一時停止
        self._generator: str = "gemini"
        self._episode_id: int | None = None
        self._teacher_cfg: dict | None = None
        self._student_cfg: dict | None = None

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

    async def start(self, lesson_id: int, lang: str = "ja", generator: str = "gemini"):
        """授業を開始する"""
        if self._state == LessonState.RUNNING:
            await self.stop()

        lesson = db.get_lesson(lesson_id)
        if not lesson:
            raise ValueError("コンテンツが見つかりません")

        sections = db.get_lesson_sections(lesson_id, lang=lang, generator=generator)
        if not sections:
            raise ValueError("スクリプトがありません。先にスクリプトを生成してください。")

        self._lesson_id = lesson_id
        self._lesson_name = lesson["name"]
        self._lang = lang
        self._generator = generator
        self._sections = sections
        self._current_index = 0
        self._state = LessonState.RUNNING
        self._pause_event.set()

        # キャラクター設定を取得
        try:
            characters = await asyncio.to_thread(get_lesson_characters)
            self._teacher_cfg = characters.get("teacher")
            self._student_cfg = characters.get("student")
        except Exception as e:
            logger.warning("キャラクター設定取得失敗: %s", e)
            self._teacher_cfg = None
            self._student_cfg = None

        logger.info("授業開始: lesson=%d (%s), sections=%d, dialogue=%s",
                     lesson_id, lesson["name"], len(sections),
                     "有" if self._student_cfg else "無")

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
        self._generator = "gemini"
        self._teacher_cfg = None
        self._student_cfg = None
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
                self._generator = "gemini"
                self._teacher_cfg = None
                self._student_cfg = None

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("授業再生エラー: %s", e, exc_info=True)
            self._state = LessonState.IDLE
            await self._hide_lesson_text()
            await self._notify_status()

    async def _play_section(self, section: dict):
        """1セクションを再生する（dialoguesがあれば対話再生）"""
        section_type = section["section_type"]
        display_text = section.get("display_text", "")

        logger.info("[lesson] セクション %d/%d [%s]",
                     self._current_index + 1, len(self._sections), section_type)

        # 画面テキスト: あれば更新、なければ非表示
        if display_text:
            await self._show_lesson_text(display_text)
        else:
            await self._hide_lesson_text()

        # dialoguesがあれば対話再生、なければ従来の単話者再生
        dialogues_raw = section.get("dialogues", "")
        dialogues = None
        if dialogues_raw and self._student_cfg:
            try:
                parsed = _json.loads(dialogues_raw) if isinstance(dialogues_raw, str) else dialogues_raw
                # v4: {dialogues: [...], review: {...}} 形式に対応
                if isinstance(parsed, dict) and "dialogues" in parsed:
                    dialogues = parsed["dialogues"]
                else:
                    dialogues = parsed
                if not isinstance(dialogues, list) or len(dialogues) == 0:
                    dialogues = None
            except (_json.JSONDecodeError, TypeError):
                dialogues = None

        if dialogues:
            await self._play_dialogues(section, dialogues)
        else:
            await self._play_single_speaker(section)

        # questionセクションの場合: 問いかけ → 待ち → 回答
        if section_type == "question" and section.get("question"):
            await self._handle_question(section)

        # アバター発話をDB保存
        content = section["content"]
        emotion = section.get("emotion", "neutral")
        if self._episode_id:
            try:
                await asyncio.to_thread(
                    db.save_avatar_comment, self._episode_id,
                    "lesson", f"[授業:{section_type}]", content, emotion,
                )
            except Exception as e:
                logger.warning("授業コメントDB保存失敗: %s", e)

    async def _play_single_speaker(self, section: dict):
        """従来の単話者再生（先生のみ）"""
        content = section["content"]
        tts_text = section.get("tts_text") or content
        emotion = section.get("emotion", "neutral")
        section_type = section["section_type"]
        teacher_name = (self._teacher_cfg or {}).get("name", "ちょビ")

        logger.info("[lesson]   単話者モード: content=%s", repr(content[:200]))

        self._speech.apply_emotion(emotion, avatar_id="teacher")

        content_parts = SpeechPipeline.split_sentences(content)
        tts_parts = SpeechPipeline.split_sentences(tts_text)

        # 全パートのTTSを事前生成（キャッシュ対応）
        order_index = section.get("order_index", self._current_index)
        wav_paths = []
        cache_hits = 0
        for i, part in enumerate(content_parts):
            if self._state == LessonState.IDLE:
                break
            part_tts = tts_parts[i] if i < len(tts_parts) else part

            cached = _cache_path(self._lesson_id, order_index, i, lang=self._lang, generator=self._generator)
            if cached.exists():
                wav_paths.append(cached)
                cache_hits += 1
                continue

            logger.info("[lesson]   generating part[%d] tts=%s", i, repr(part_tts[:100]))
            wav = await self._speech.generate_tts(part, tts_text=part_tts)
            if wav and wav.exists():
                cached.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(wav, cached)
                wav.unlink(missing_ok=True)
                try:
                    wav.parent.rmdir()
                except OSError:
                    pass
                wav_paths.append(cached)
            else:
                wav_paths.append(wav)
        logger.info("[lesson]   TTS事前生成完了: %d/%d パート (cache hit: %d)",
                     len(wav_paths), len(content_parts), cache_hits)

        for i, part in enumerate(content_parts):
            if self._state == LessonState.IDLE:
                break
            await self._speech.speak(part, subtitle={
                "author": teacher_name,
                "trigger_text": f"[授業] {section_type}",
                "result": {"speech": part, "emotion": emotion, "translation": ""},
            }, tts_text=tts_parts[i] if i < len(tts_parts) else part,
               wav_path=wav_paths[i] if i < len(wav_paths) else None,
               avatar_id="teacher")
            await self._speech.notify_overlay_end()

        self._speech.apply_emotion("neutral", avatar_id="teacher")

    async def _generate_dlg_tts(self, dlg: dict, index: int, order_index: int) -> Path | None:
        """1つのdialogue発話のTTSを生成（キャッシュ対応）"""
        speaker = dlg.get("speaker", "teacher")
        cfg = (self._teacher_cfg or {}) if speaker == "teacher" else (self._student_cfg or {})
        voice = cfg.get("tts_voice")
        style = cfg.get("tts_style")
        tts_text = dlg.get("tts_text", dlg.get("content", ""))

        cached = _dlg_cache_path(self._lesson_id, order_index, index, lang=self._lang, generator=self._generator)
        if cached.exists():
            return cached

        logger.info("[lesson]   generating dlg[%d] speaker=%s tts=%s",
                     index, speaker, repr(tts_text[:100]))
        wav = await self._speech.generate_tts(tts_text, voice=voice, style=style,
                                               tts_text=tts_text)
        if wav and wav.exists():
            cached.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(wav, cached)
            wav.unlink(missing_ok=True)
            try:
                wav.parent.rmdir()
            except OSError:
                pass
            return cached
        return wav

    async def _play_dialogues(self, section: dict, dialogues: list[dict]):
        """対話再生 — 生成と再生をパイプライン化して初回の待ち時間を最小化"""
        section_type = section["section_type"]
        order_index = section.get("order_index", self._current_index)
        teacher_cfg = self._teacher_cfg or {}
        student_cfg = self._student_cfg or {}
        teacher_name = teacher_cfg.get("name", "ちょビ")
        student_name = student_cfg.get("name", "なるこ")

        logger.info("[lesson]   対話モード: %d発話", len(dialogues))

        # パイプライン: 現在の発話を再生しながら次の発話のTTSを生成
        next_wav_task = None
        for i, dlg in enumerate(dialogues):
            if self._state == LessonState.IDLE:
                break

            # 現在の発話のwavを取得
            if next_wav_task is not None:
                wav_path = await next_wav_task
                next_wav_task = None
            else:
                wav_path = await self._generate_dlg_tts(dlg, i, order_index)

            # 次の発話のTTS生成をバックグラウンドで開始
            if i + 1 < len(dialogues) and self._state != LessonState.IDLE:
                next_wav_task = asyncio.create_task(
                    self._generate_dlg_tts(dialogues[i + 1], i + 1, order_index)
                )

            # 現在の発話を再生
            speaker = dlg.get("speaker", "teacher")
            avatar_id = speaker
            cfg = teacher_cfg if speaker == "teacher" else student_cfg
            voice = cfg.get("tts_voice")
            style = cfg.get("tts_style")
            content = dlg.get("content", "")
            tts_text = dlg.get("tts_text", content)
            emotion = dlg.get("emotion", "neutral")
            name = teacher_name if speaker == "teacher" else student_name

            self._speech.apply_emotion(emotion, avatar_id=avatar_id)
            await self._speech.speak(
                content, voice=voice, style=style, avatar_id=avatar_id,
                tts_text=tts_text,
                wav_path=wav_path,
                subtitle={
                    "author": name,
                    "trigger_text": f"[授業] {section_type}",
                    "result": {"speech": content, "emotion": emotion, "translation": ""},
                },
            )
            self._speech.apply_emotion("neutral", avatar_id=avatar_id)
            await self._speech.notify_overlay_end()

            # 発話間に短い間
            if i < len(dialogues) - 1 and self._state != LessonState.IDLE:
                await asyncio.sleep(0.3)

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
            event = {
                "type": "lesson_status",
                "state": self._state.value,
                "lesson_id": self._lesson_id,
                "lesson_name": self._lesson_name,
                "current_index": self._current_index,
                "total_sections": len(self._sections),
            }
            # running/paused時はセクション概要を含める
            if self._state != LessonState.IDLE and self._sections:
                event["sections"] = [
                    {
                        "type": s["section_type"],
                        "summary": (s.get("title") or (s.get("content") or "")[:40])[:20],
                    }
                    for s in self._sections
                ]
            await self._on_overlay(event)

    def get_status(self) -> dict:
        """現在のステータスを取得する"""
        return {
            "state": self._state.value,
            "lesson_id": self._lesson_id,
            "lang": self._lang,
            "generator": self._generator,
            "current_index": self._current_index,
            "total_sections": len(self._sections),
        }
