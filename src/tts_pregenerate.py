"""TTS事前生成モジュール

授業コンテンツのTTS音声をバックグラウンドで事前生成する。
LessonRunnerと同じキャッシュパス構造を使い、再生時にキャッシュヒットさせる。
"""

import asyncio
import json
import logging
import shutil
import tempfile
from pathlib import Path

from src.lesson_runner import _cache_path, _dlg_cache_path
from src.speech_pipeline import SpeechPipeline
from src.tts import synthesize
from src.lesson_generator.utils import get_lesson_characters
from src import db

logger = logging.getLogger(__name__)


async def _generate_one(text: str, cache: Path, voice=None, style=None) -> bool:
    """1つのTTS音声を生成してキャッシュに保存する。

    Returns: True=新規生成, False=失敗
    """
    tmp_path = Path(tempfile.mkdtemp()) / "speech.wav"
    try:
        await asyncio.to_thread(synthesize, text, str(tmp_path), voice=voice, style=style)
        cache.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(tmp_path, cache)
        return True
    except Exception as e:
        logger.warning("[tts-pregen] 生成失敗: %s", e)
        return False
    finally:
        tmp_path.unlink(missing_ok=True)
        try:
            tmp_path.parent.rmdir()
        except OSError:
            pass


def _parse_dialogues(section: dict, student_cfg: dict | None) -> list[dict] | None:
    """セクションからdialogueリストをパースする（lesson_runner._play_sectionと同じロジック）"""
    dialogues_raw = section.get("dialogues", "")
    if not dialogues_raw or not student_cfg:
        return None
    try:
        parsed = json.loads(dialogues_raw) if isinstance(dialogues_raw, str) else dialogues_raw
        if isinstance(parsed, dict) and "dialogues" in parsed:
            dialogues = parsed["dialogues"]
        else:
            dialogues = parsed
        if not isinstance(dialogues, list) or len(dialogues) == 0:
            return None
        return dialogues
    except (json.JSONDecodeError, TypeError):
        return None


async def pregenerate_section_tts(
    lesson_id: int,
    section: dict,
    order_index: int,
    lang: str,
    generator: str,
    version_number: int,
    teacher_cfg: dict | None,
    student_cfg: dict | None,
    cancel_event: asyncio.Event | None = None,
) -> dict:
    """1セクション分のTTSを事前生成する。

    Returns: {"generated": int, "cached": int, "failed": int}
    """
    result = {"generated": 0, "cached": 0, "failed": 0}

    dialogues = _parse_dialogues(section, student_cfg)

    if dialogues:
        # 対話モード
        for i, dlg in enumerate(dialogues):
            if cancel_event and cancel_event.is_set():
                return result

            cached = _dlg_cache_path(lesson_id, order_index, i,
                                     lang=lang, generator=generator,
                                     version_number=version_number)
            if cached.exists():
                result["cached"] += 1
                continue

            speaker = dlg.get("speaker", "teacher")
            cfg = teacher_cfg if speaker == "teacher" else student_cfg
            cfg = cfg or {}
            voice = cfg.get("tts_voice")
            style = cfg.get("tts_style")
            tts_text = dlg.get("tts_text", dlg.get("content", ""))

            # 1回リトライ
            ok = await _generate_one(tts_text, cached, voice=voice, style=style)
            if not ok:
                await asyncio.sleep(1)
                ok = await _generate_one(tts_text, cached, voice=voice, style=style)

            if ok:
                result["generated"] += 1
            else:
                result["failed"] += 1

            await asyncio.sleep(0.1)
    else:
        # 単話者モード
        content = section.get("content", "")
        tts_text = section.get("tts_text") or content
        if not content:
            return result

        content_parts = SpeechPipeline.split_sentences(content)
        tts_parts = SpeechPipeline.split_sentences(tts_text)

        for i, _part in enumerate(content_parts):
            if cancel_event and cancel_event.is_set():
                return result

            cached = _cache_path(lesson_id, order_index, i,
                                 lang=lang, generator=generator,
                                 version_number=version_number)
            if cached.exists():
                result["cached"] += 1
                continue

            part_tts = tts_parts[i] if i < len(tts_parts) else content_parts[i]

            # voice/style渡さない → synthesize()内のget_tts_config()に委ねる
            ok = await _generate_one(part_tts, cached)
            if not ok:
                await asyncio.sleep(1)
                ok = await _generate_one(part_tts, cached)

            if ok:
                result["generated"] += 1
            else:
                result["failed"] += 1

            await asyncio.sleep(0.1)

    return result


async def pregenerate_lesson_tts(
    lesson_id: int,
    lang: str,
    generator: str,
    version_number: int,
    cancel_event: asyncio.Event | None = None,
    on_progress=None,
) -> dict:
    """レッスン全セクションのTTSを事前生成する。

    Args:
        lesson_id: レッスンID
        lang: 言語コード
        generator: 生成器名
        version_number: バージョン番号
        cancel_event: キャンセル用イベント
        on_progress: 進捗コールバック (completed, total, section_result)

    Returns: {"total": int, "generated": int, "cached": int, "failed": int, "cancelled": bool}
    """
    sections = await asyncio.to_thread(
        db.get_lesson_sections, lesson_id,
        lang=lang, generator=generator, version_number=version_number,
    )

    total = len(sections)
    result = {"total": total, "generated": 0, "cached": 0, "failed": 0, "cancelled": False}

    if total == 0:
        if on_progress:
            on_progress(0, 0, result)
        return result

    # キャラクター設定を取得
    try:
        characters = await asyncio.to_thread(get_lesson_characters)
        teacher_cfg = characters.get("teacher")
        student_cfg = characters.get("student")
    except Exception as e:
        logger.warning("[tts-pregen] キャラクター設定取得失敗: %s", e)
        teacher_cfg = None
        student_cfg = None

    for i, section in enumerate(sections):
        if cancel_event and cancel_event.is_set():
            result["cancelled"] = True
            logger.info("[tts-pregen] キャンセルされました (%d/%d)", i, total)
            break

        order_index = section.get("order_index", i)
        logger.info("[tts-pregen] セクション %d/%d [%s]",
                     i + 1, total, section.get("section_type", "?"))

        sec_result = await pregenerate_section_tts(
            lesson_id, section, order_index, lang, generator, version_number,
            teacher_cfg, student_cfg, cancel_event,
        )

        result["generated"] += sec_result["generated"]
        result["cached"] += sec_result["cached"]
        result["failed"] += sec_result["failed"]

        if on_progress:
            on_progress(i + 1, total, result)

    logger.info("[tts-pregen] 完了: total=%d, generated=%d, cached=%d, failed=%d, cancelled=%s",
                 total, result["generated"], result["cached"], result["failed"], result["cancelled"])
    return result
