"""授業再生エンジン — セクションを順次再生する（クライアント主導型）

Phase 3: PythonはTTS+リップシンクのバンドルを生成してC#に送信し、
C#が再生を主導する。完了はlesson_section_completeイベントで通知される。
"""

import asyncio
import base64
import json as _json
import logging
import shutil
import wave
from enum import Enum
from pathlib import Path

from src import db
from src.lesson_generator import get_lesson_characters
from src.lipsync import analyze_amplitude
from src.speech_pipeline import SpeechPipeline

PLAYBACK_SETTING_KEY = "lesson.playback"

PROJECT_DIR = Path(__file__).resolve().parent.parent
LESSON_AUDIO_DIR = PROJECT_DIR / "resources" / "audio" / "lessons"

logger = logging.getLogger(__name__)


class LessonState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"


def _cache_path(lesson_id: int, order_index: int, part_index: int, lang: str = "ja", generator: str = "gemini", version_number: int = 1) -> Path:
    """TTSキャッシュファイルのパスを返す（バージョン別サブディレクトリ、旧パス互換あり）

    パス解決順序:
    1. 新パス: {lesson_id}/{lang}/{generator}/v{N}/section_*.wav
    2. バージョニング前互換: {lesson_id}/{lang}/{generator}/section_*.wav（v1のみ）
    3. generator導入前互換: {lesson_id}/{lang}/section_*.wav（v1+geminiのみ）
    """
    filename = f"section_{order_index:02d}_part_{part_index:02d}.wav"
    new_path = LESSON_AUDIO_DIR / str(lesson_id) / lang / generator / f"v{version_number}" / filename
    if new_path.exists():
        return new_path
    # 旧パス互換（バージョニング導入前: generator直下、v1のみ）
    if version_number == 1:
        pre_ver = LESSON_AUDIO_DIR / str(lesson_id) / lang / generator / filename
        if pre_ver.exists():
            return pre_ver
        # generator導入前互換（lang直下、geminiのみ）
        if generator == "gemini":
            legacy = LESSON_AUDIO_DIR / str(lesson_id) / lang / filename
            if legacy.exists():
                return legacy
    return new_path


def _dlg_cache_path(lesson_id: int, order_index: int, dlg_index: int, lang: str = "ja", generator: str = "gemini", version_number: int = 1) -> Path:
    """dialogue用TTSキャッシュファイルのパスを返す（バージョン別サブディレクトリ、旧パス互換あり）"""
    filename = f"section_{order_index:02d}_dlg_{dlg_index:02d}.wav"
    new_path = LESSON_AUDIO_DIR / str(lesson_id) / lang / generator / f"v{version_number}" / filename
    if new_path.exists():
        return new_path
    if version_number == 1:
        pre_ver = LESSON_AUDIO_DIR / str(lesson_id) / lang / generator / filename
        if pre_ver.exists():
            return pre_ver
        if generator == "gemini":
            legacy = LESSON_AUDIO_DIR / str(lesson_id) / lang / filename
            if legacy.exists():
                return legacy
    return new_path


def clear_tts_cache(lesson_id: int, order_index: int | None = None, lang: str | None = None,
                    generator: str | None = None, version_number: int | None = None):
    """TTSキャッシュを削除する

    Args:
        lesson_id: レッスンID
        order_index: 指定時はそのセクションのみ、Noneなら全セクション
        lang: 指定時はその言語のみ、Noneなら全言語
        generator: 指定時はそのジェネレータのキャッシュのみ、Noneなら全ジェネレータ
        version_number: 指定時はそのバージョンのみ、Noneなら全バージョン
    """

    def _delete_files_in_dir(d: Path, oi: int | None):
        """ディレクトリ内のセクションファイルを削除"""
        if not d.exists():
            return
        if oi is not None:
            for f in d.glob(f"section_{oi:02d}_*.wav"):
                f.unlink(missing_ok=True)
        else:
            shutil.rmtree(d, ignore_errors=True)

    def _clear_gen_dir(gen_dir: Path, oi: int | None, vn: int | None):
        """generator ディレクトリ配下のキャッシュ削除"""
        if not gen_dir.exists():
            return
        if vn is not None:
            # 特定バージョンのみ
            _delete_files_in_dir(gen_dir / f"v{vn}", oi)
            # v1 の場合はgenerator直下のレガシーファイルも削除
            if vn == 1:
                _delete_files_in_dir(gen_dir, oi) if oi is not None else None
                if oi is not None:
                    for f in gen_dir.glob(f"section_{oi:02d}_*.wav"):
                        f.unlink(missing_ok=True)
                else:
                    # generator直下のwavファイルのみ削除（v*サブディレクトリは残す）
                    for f in gen_dir.glob("section_*.wav"):
                        f.unlink(missing_ok=True)
        else:
            # 全バージョン（generator配下ごと削除）
            if oi is not None:
                # generator直下のファイル
                for f in gen_dir.glob(f"section_{oi:02d}_*.wav"):
                    f.unlink(missing_ok=True)
                # v*サブディレクトリ内のファイル
                for sub in gen_dir.iterdir():
                    if sub.is_dir() and sub.name.startswith("v"):
                        for f in sub.glob(f"section_{oi:02d}_*.wav"):
                            f.unlink(missing_ok=True)
            else:
                shutil.rmtree(gen_dir, ignore_errors=True)

    if generator is not None:
        # 特定generatorのキャッシュのみ削除
        if lang:
            gen_dir = LESSON_AUDIO_DIR / str(lesson_id) / lang / generator
            _clear_gen_dir(gen_dir, order_index, version_number)
            # v1+gemini: lang直下のレガシーファイルも削除
            if version_number in (None, 1) and generator == "gemini":
                lang_dir = LESSON_AUDIO_DIR / str(lesson_id) / lang
                if lang_dir.exists() and order_index is not None:
                    for f in lang_dir.glob(f"section_{order_index:02d}_*.wav"):
                        f.unlink(missing_ok=True)
                elif lang_dir.exists():
                    for f in lang_dir.glob("section_*.wav"):
                        f.unlink(missing_ok=True)
        else:
            lesson_dir = LESSON_AUDIO_DIR / str(lesson_id)
            if not lesson_dir.exists():
                return
            for lang_dir in lesson_dir.iterdir():
                if lang_dir.is_dir():
                    gen_dir = lang_dir / generator
                    _clear_gen_dir(gen_dir, order_index, version_number)
        return

    # generator=None → 全ジェネレータ削除
    if version_number is not None:
        # 特定バージョンだけ削除（全generator内のv{N}を削除）
        if lang:
            lang_dir = LESSON_AUDIO_DIR / str(lesson_id) / lang
        else:
            lang_dir = LESSON_AUDIO_DIR / str(lesson_id)
        if not lang_dir.exists():
            return
        if lang:
            # lang直下のレガシーファイル（v1のみ）
            if version_number == 1 and order_index is not None:
                for f in lang_dir.glob(f"section_{order_index:02d}_part_*.wav"):
                    f.unlink(missing_ok=True)
            elif version_number == 1:
                for f in lang_dir.glob("section_*_part_*.wav"):
                    f.unlink(missing_ok=True)
            # 各generator内のv{N}
            for sub in lang_dir.iterdir():
                if sub.is_dir() and not sub.name.startswith("v"):
                    _clear_gen_dir(sub, order_index, version_number)
        else:
            for ld in lang_dir.iterdir():
                if ld.is_dir():
                    if version_number == 1 and order_index is not None:
                        for f in ld.glob(f"section_{order_index:02d}_part_*.wav"):
                            f.unlink(missing_ok=True)
                    for sub in ld.iterdir():
                        if sub.is_dir() and not sub.name.startswith("v"):
                            _clear_gen_dir(sub, order_index, version_number)
        return

    # version_number=None, generator=None → 既存動作（全削除）
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
                    _clear_gen_dir(sub, order_index, None)
    else:
        shutil.rmtree(lesson_dir, ignore_errors=True)


def get_tts_cache_info(lesson_id: int, lang: str = "ja", generator: str = "gemini",
                       version_number: int = 1) -> list[dict]:
    """TTSキャッシュの状況を返す（part形式 + dlg形式の両方を検索）

    Args:
        lesson_id: レッスンID
        lang: 言語
        generator: ジェネレータ
        version_number: バージョン番号
    """
    sections_map: dict[int, list[dict]] = {}
    seen: set[tuple[int, str, int]] = set()  # (order_index, type, index) 重複排除

    # スキャン対象ディレクトリ（優先順: 新パス → バージョニング前 → generator導入前）
    scan_dirs: list[Path] = []
    ver_dir = LESSON_AUDIO_DIR / str(lesson_id) / lang / generator / f"v{version_number}"
    if ver_dir.exists():
        scan_dirs.append(ver_dir)
    if version_number == 1:
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
    db_sections = db.get_lesson_sections(lesson_id, lang=lang, generator=generator,
                                          version_number=version_number)
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
        self._version_number: int = 1
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

    async def restore(self) -> bool:
        """DBから授業再生状態を読み取り、サーバー再起動後に授業を復旧する

        Returns:
            True: 復旧に成功（授業を再開）
            False: 復旧対象なし or 復旧失敗
        """
        playback = self.get_playback_state()
        if not playback:
            return False

        lesson_id = playback.get("lesson_id")
        if not lesson_id:
            self._clear_playback_state()
            return False

        lesson = db.get_lesson(lesson_id)
        if not lesson:
            logger.warning("[lesson restore] lesson_id=%d が存在しません、永続化データをクリア", lesson_id)
            self._clear_playback_state()
            return False

        lang = playback.get("lang", "ja")
        generator = playback.get("generator", "gemini")
        version_number = playback.get("version_number", 1)
        saved_index = playback.get("section_index", 0)
        episode_id = playback.get("episode_id")

        sections = db.get_lesson_sections(lesson_id, lang=lang, generator=generator,
                                          version_number=version_number)
        if not sections:
            logger.warning("[lesson restore] セクションが見つかりません、永続化データをクリア")
            self._clear_playback_state()
            return False

        # C#の授業再生状態を問い合わせる
        csharp_state = None
        try:
            from scripts.services.capture_client import ws_request
            csharp_state = await asyncio.wait_for(
                ws_request("lesson_status", timeout=3.0), timeout=5.0
            )
        except Exception as e:
            logger.info("[lesson restore] C#状態取得失敗（未接続）: %s", type(e).__name__)

        # 復旧開始インデックスを決定
        resume_index = saved_index
        if csharp_state:
            cs_status = csharp_state.get("status") or csharp_state.get("state", "no_lesson")
            if cs_status == "idle":
                # C#はセクション再生完了 → 次のセクションから
                resume_index = saved_index + 1
                logger.info("[lesson restore] C# idle → section %d から再開", resume_index)
            elif cs_status == "playing":
                # C#が再生中 → 全セクション完了を待つ（新方式ではC#が単独で完走する）
                logger.info("[lesson restore] C# playing → lesson_complete 待ち")
                saved_total = playback.get("total_duration", 300)
                try:
                    from scripts.services.capture_client import (
                        get_lesson_complete_event,
                        get_lesson_section_complete_event,
                    )
                    lesson_evt = get_lesson_complete_event()
                    lesson_evt.clear()
                    sec_evt = get_lesson_section_complete_event()
                    sec_evt.clear()
                    # どちらのイベントが来ても進む
                    done, _pending = await asyncio.wait(
                        [
                            asyncio.create_task(lesson_evt.wait()),
                            asyncio.create_task(sec_evt.wait()),
                        ],
                        timeout=saved_total * 1.5 + 60,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for t in _pending:
                        t.cancel()
                    if not done:
                        logger.warning("[lesson restore] 完了イベントタイムアウト")
                except Exception as e:
                    logger.warning("[lesson restore] 完了待ち失敗: %s", e)
                # 新方式: C#が単独で全完走する → 以降のセクションは不要
                if lesson_evt.is_set():
                    self._clear_playback_state()
                    return False
                resume_index = saved_index + 1
            else:
                # no_lesson → 保存されたインデックスからやり直し
                logger.info("[lesson restore] C# %s → section %d からやり直し", cs_status, saved_index)
        else:
            # C#未接続 → 保存されたインデックスからやり直し
            logger.info("[lesson restore] C#未接続 → section %d からやり直し", saved_index)

        # 全セクション完了済みチェック
        if resume_index >= len(sections):
            logger.info("[lesson restore] 全セクション完了済み、永続化データをクリア")
            self._clear_playback_state()
            return False

        # 状態をセットアップして再開
        self._lesson_id = lesson_id
        self._lesson_name = lesson["name"]
        self._lang = lang
        self._generator = generator
        self._version_number = version_number
        self._sections = sections
        self._current_index = resume_index
        self._state = LessonState.RUNNING
        self._pause_event.set()
        if episode_id:
            self._episode_id = episode_id

        # キャラクター設定を取得
        try:
            characters = await asyncio.to_thread(get_lesson_characters)
            self._teacher_cfg = characters.get("teacher")
            self._student_cfg = characters.get("student")
        except Exception as e:
            logger.warning("キャラクター設定取得失敗: %s", e)
            self._teacher_cfg = None
            self._student_cfg = None

        logger.info("授業復旧: lesson=%d (%s), section=%d/%d から再開",
                     lesson_id, lesson["name"], resume_index + 1, len(sections))

        await self._notify_status()
        self._task = asyncio.create_task(self._run_loop())
        return True

    async def start(self, lesson_id: int, lang: str = "ja", generator: str = "gemini",
                    version_number: int | None = None):
        """授業を開始する

        version_number: 再生するバージョン。省略時は全セクション（後方互換）。
        """
        if self._state == LessonState.RUNNING:
            await self.stop()

        lesson = db.get_lesson(lesson_id)
        if not lesson:
            raise ValueError("コンテンツが見つかりません")

        sections = db.get_lesson_sections(lesson_id, lang=lang, generator=generator,
                                          version_number=version_number)
        if not sections:
            raise ValueError("スクリプトがありません。先にスクリプトを生成してください。")

        self._lesson_id = lesson_id
        self._lesson_name = lesson["name"]
        self._lang = lang
        self._generator = generator
        self._version_number = version_number or 1
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

        logger.info("授業開始: lesson=%d (%s), sections=%d, teacher=%s, student=%s",
                     lesson_id, lesson["name"], len(sections),
                     "有" if self._teacher_cfg else "無",
                     "有" if self._student_cfg else "無")

        # ステータス通知
        await self._notify_status()

        self._task = asyncio.create_task(self._run_loop())

    async def pause(self):
        """授業を一時停止する（C#にも転送）"""
        if self._state != LessonState.RUNNING:
            return
        self._state = LessonState.PAUSED
        self._pause_event.clear()
        try:
            from scripts.services.capture_client import ws_request
            await ws_request("lesson_pause")
        except Exception as e:
            logger.warning("[lesson] pause送信失敗: %s", e)
        logger.info("授業一時停止: lesson=%d, section=%d/%d",
                     self._lesson_id, self._current_index + 1, len(self._sections))
        await self._notify_status()

    async def resume(self):
        """授業を再開する（C#にも転送）"""
        if self._state != LessonState.PAUSED:
            return
        self._state = LessonState.RUNNING
        self._pause_event.set()
        try:
            from scripts.services.capture_client import ws_request
            await ws_request("lesson_resume")
        except Exception as e:
            logger.warning("[lesson] resume送信失敗: %s", e)
        logger.info("授業再開: lesson=%d, section=%d/%d",
                     self._lesson_id, self._current_index + 1, len(self._sections))
        await self._notify_status()

    async def stop(self):
        """授業を停止する（C#にも転送）"""
        if self._state == LessonState.IDLE:
            return
        self._state = LessonState.IDLE
        self._pause_event.set()  # pause中のawaitを解除

        # DB永続化をクリア
        self._clear_playback_state()

        # C#に停止指示
        try:
            from scripts.services.capture_client import ws_request
            await ws_request("lesson_stop")
        except Exception as e:
            logger.warning("[lesson] stop送信失敗: %s", e)

        # 完了イベントをsetして待機中のタスクを解除（旧: section、新: lesson）
        try:
            from scripts.services.capture_client import (
                get_lesson_complete_event,
                get_lesson_section_complete_event,
            )
            get_lesson_section_complete_event().set()
            get_lesson_complete_event().set()
        except Exception:
            pass

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
        self._version_number = 1
        self._teacher_cfg = None
        self._student_cfg = None
        logger.info("授業停止")
        await self._hide_lesson_text()
        await self._notify_status()

    async def _run_loop(self):
        """全セクション一括バンドル生成→C#送信→lesson_complete 待機"""
        try:
            await self._send_all_and_play()

            # 全セクション完了（stopでIDLEになっていない場合）
            if self._state != LessonState.IDLE:
                logger.info("授業完了: lesson=%d", self._lesson_id)
                self._state = LessonState.IDLE
                self._clear_playback_state()
                await self._notify_status()
                self._lesson_id = None
                self._sections = []
                self._current_index = 0
                self._generator = "gemini"
                self._version_number = 1
                self._teacher_cfg = None
                self._student_cfg = None

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("授業再生エラー: %s", e, exc_info=True)
            self._state = LessonState.IDLE
            await self._hide_lesson_text()
            await self._notify_status()

    async def _send_all_and_play(self):
        """全セクションのバンドルを事前生成→一括送信→再生→完了待機"""
        from scripts.services.capture_client import (
            get_lesson_complete_event,
            ws_request,
        )

        # 1. 全セクションのバンドルを事前生成（self._current_index から）
        all_sections: list[dict] = []
        total_duration = 0.0
        pace_scale = self._get_pace_scale()
        start_index = self._current_index

        for i in range(start_index, len(self._sections)):
            if self._state == LessonState.IDLE:
                return  # stopが呼ばれた

            # 一時停止中はここでも待機（セクション生成単位の中断点）
            await self._pause_event.wait()
            if self._state == LessonState.IDLE:
                return

            section = self._sections[i]
            self._current_index = i
            await self._notify_tts_progress(i, len(self._sections))

            bundle = await self._build_section_bundle(section, i)
            if bundle is None:
                logger.warning("[lesson] セクション %d: バンドル生成失敗、スキップ", i)
                continue
            all_sections.append(bundle)
            total_duration += self._calc_section_duration(bundle, pace_scale)
            logger.info("[lesson] セクション %d/%d TTS生成完了 (duration=%.1fs)",
                         i + 1, len(self._sections), total_duration)

        if self._state == LessonState.IDLE:
            return
        if not all_sections:
            logger.warning("[lesson] 送信可能なセクションがありません")
            return

        # 2. 一括送信
        logger.info("[lesson] 全セクションをC#に送信: sections=%d, total_duration=%.1fs",
                     len(all_sections), total_duration)
        try:
            load_result = await ws_request(
                "lesson_load", timeout=30.0,
                lesson_id=self._lesson_id,
                total_sections=len(all_sections),
                pace_scale=pace_scale,
                sections=all_sections,
            )
            logger.info("[lesson]   lesson_load: %s", "ok" if load_result.get("ok") else load_result)
        except Exception as e:
            logger.error("[lesson] lesson_load 送信失敗: %s", e)
            return

        # 3. 再生開始（完了イベントはクリアしてから play を送る）
        evt = get_lesson_complete_event()
        evt.clear()

        try:
            play_result = await ws_request("lesson_play", timeout=5.0)
            logger.info("[lesson]   lesson_play: %s", "ok" if play_result.get("ok") else play_result)
        except Exception as e:
            logger.error("[lesson] lesson_play 送信失敗: %s", e)
            return

        # DB永続化（total_duration も保存）
        self._save_playback_state(total_duration=total_duration)

        # 4. 授業全体の完了を待つ
        await self._wait_lesson_complete(evt, total_duration)

        # 5. DB保存: 授業全体のアバター発話
        if self._episode_id:
            for section in self._sections:
                content = section.get("content", "")
                emotion = section.get("emotion", "neutral")
                section_type = section.get("section_type", "")
                try:
                    await asyncio.to_thread(
                        db.save_avatar_comment, self._episode_id,
                        "lesson", f"[授業:{section_type}]", content, emotion,
                    )
                except Exception as e:
                    logger.warning("授業コメントDB保存失敗: %s", e)

    async def _build_section_bundle(self, section: dict, section_index: int) -> dict | None:
        """単一セクションのバンドル（lesson_load.sections[]に入れる辞書）を組み立てる"""
        section_type = section["section_type"]
        display_text = section.get("display_text", "")
        order_index = section.get("order_index", section_index)

        # display_properties をパース
        display_props = self._parse_display_properties(section)

        # dialogues を統一フォーマットで取得
        dialogues, is_single_speaker = self._get_unified_dialogues(section)

        # バンドル生成（TTS + lipsync + wav_b64）
        dlg_bundle = await self._build_dialogue_bundle(dialogues, order_index, is_single_speaker)

        if not dlg_bundle:
            logger.warning("[lesson] セクション %d: dialogueバンドルが空", section_index)
            return None

        # questionセクション
        question_data = None
        if section_type == "question" and section.get("question"):
            question_data = await self._build_question_data(section, order_index)

        return {
            "lesson_id": self._lesson_id,
            "section_index": section_index,
            "total_sections": len(self._sections),
            "section_type": section_type,
            "display_text": display_text,
            "display_properties": display_props,
            "dialogues": dlg_bundle,
            "question": question_data,
            "wait_seconds": section.get("wait_seconds", 2),
        }

    @staticmethod
    def _calc_section_duration(section_bundle: dict, pace_scale: float) -> float:
        """セクションバンドルの合計再生時間（秒）を算出する"""
        total = sum(d.get("duration", 0) for d in section_bundle.get("dialogues", []))
        q = section_bundle.get("question")
        if q:
            total += q.get("wait_seconds", 0) * pace_scale
            total += sum(d.get("duration", 0) for d in q.get("answer_dialogues", []))
        total += section_bundle.get("wait_seconds", 0) * pace_scale
        return total

    async def _wait_lesson_complete(self, evt: asyncio.Event, total_duration: float):
        """lesson_complete を待つ。イベントロスト時はポーリングでC#状態を確認する。

        - Phase 1: 音声再生時間+30秒をイベント待ち
        - Phase 2: idle検知で完了扱い、最大 total_duration*1.5+60 秒まで
        """
        from scripts.services.capture_client import ws_request as _ws_request

        phase1_timeout = total_duration + 30
        max_timeout = total_duration * 1.5 + 60
        poll_interval = 5.0

        # Phase 1: 音声再生中は完了イベントだけを待つ
        try:
            await asyncio.wait_for(evt.wait(), timeout=phase1_timeout)
            logger.info("[lesson] 授業完了イベント受信")
            return
        except asyncio.TimeoutError:
            pass

        # Phase 2: C# statusをポーリング
        elapsed = phase1_timeout
        while elapsed < max_timeout and self._state != LessonState.IDLE:
            try:
                status = await _ws_request("lesson_status", timeout=3.0)
                cs_state = status.get("state", "unknown") if status else "unknown"
                cs_sec = status.get("section_index", -1) if status else -1
                cs_total = status.get("total_sections", 0) if status else 0
                logger.info("[lesson]   C# status: state=%s, section=%d/%d",
                             cs_state, cs_sec + 1, cs_total)

                if cs_state == "idle":
                    logger.info("[lesson]   C# idle検知 → 授業完了扱い（イベントロスト）")
                    return
            except Exception as e:
                logger.warning("[lesson]   C# status取得失敗: %s", type(e).__name__)

            wait_time = min(poll_interval, max_timeout - elapsed)
            try:
                await asyncio.wait_for(evt.wait(), timeout=wait_time)
                return
            except asyncio.TimeoutError:
                elapsed += wait_time

        logger.warning("[lesson] 授業完了タイムアウト (%.0f秒)", max_timeout)

    async def _notify_tts_progress(self, current: int, total: int):
        """TTS生成中の進捗を配信画面に通知する"""
        if self._on_overlay:
            await self._on_overlay({
                "type": "lesson_status",
                "state": self._state.value,
                "lesson_id": self._lesson_id,
                "lesson_name": self._lesson_name,
                "current_index": current,
                "total_sections": total,
                "phase": "tts_generating",
                "tts_progress": {"current": current + 1, "total": total},
            })

    async def _prepare_and_send_section(self, section: dict):
        """セクションバンドルを生成してC#に送信し、完了イベントを待つ"""
        section_type = section["section_type"]
        display_text = section.get("display_text", "")
        order_index = section.get("order_index", self._current_index)

        logger.info("[lesson] セクション %d/%d [%s]",
                     self._current_index + 1, len(self._sections), section_type)

        # display_properties をパース
        display_props = self._parse_display_properties(section)

        # dialoguesを統一フォーマットで取得（単話者→dialogues変換含む）
        dialogues, is_single_speaker = self._get_unified_dialogues(section)

        # バンドル生成（TTS + lipsync + wav_b64）
        bundle = await self._build_dialogue_bundle(dialogues, order_index, is_single_speaker)

        if not bundle:
            logger.warning("[lesson] セクション %d: バンドルが空（TTS生成失敗）", self._current_index)
            return

        # questionセクションの処理
        question_data = None
        if section_type == "question" and section.get("question"):
            question_data = await self._build_question_data(section, order_index)

        # C#にセクションデータを送信
        from scripts.services.capture_client import get_lesson_section_complete_event, ws_request

        section_data = {
            "lesson_id": self._lesson_id,
            "section_index": self._current_index,
            "total_sections": len(self._sections),
            "section_type": section_type,
            "display_text": display_text,
            "display_properties": display_props,
            "dialogues": bundle,
            "question": question_data,
            "wait_seconds": section.get("wait_seconds", 2),
            "pace_scale": self._get_pace_scale(),
        }

        load_result = await ws_request("lesson_section_load", timeout=30.0, section_data=section_data)
        logger.info("[lesson]   section_load: %s", "ok" if load_result.get("ok") else load_result)

        # 完了イベントをクリア（再生開始前にクリアしないとrace condition）
        evt = get_lesson_section_complete_event()
        evt.clear()

        # 再生開始
        play_result = await ws_request("lesson_section_play", timeout=5.0)
        logger.info("[lesson]   section_play: %s", "ok" if play_result.get("ok") else play_result)

        # 進捗をDBに永続化（再生開始後に保存）
        self._save_playback_state()

        # C#からの完了通知を待つ（ポーリング付き）
        total_duration = sum(d["duration"] for d in bundle)
        timeout = total_duration + 30
        wait_secs = section.get("wait_seconds", 2) * self._get_pace_scale()
        timeout += wait_secs
        if question_data:
            timeout += question_data.get("wait_seconds", 8) * self._get_pace_scale()
            timeout += sum(d.get("duration", 0) for d in question_data.get("answer_dialogues", []))

        await self._wait_section_complete(evt, timeout, total_duration)

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

    @staticmethod
    def _parse_dialogues(section: dict) -> list[dict] | None:
        """セクションからdialogueリストをパースする"""
        dialogues_raw = section.get("dialogues", "")
        if not dialogues_raw:
            return None
        try:
            parsed = _json.loads(dialogues_raw) if isinstance(dialogues_raw, str) else dialogues_raw
            # v4: {dialogues: [...], review: {...}} 形式に対応
            if isinstance(parsed, dict) and "dialogues" in parsed:
                dialogues = parsed["dialogues"]
            else:
                dialogues = parsed
            if not isinstance(dialogues, list) or len(dialogues) == 0:
                return None
            return dialogues
        except (_json.JSONDecodeError, TypeError):
            return None

    @staticmethod
    def _parse_display_properties(section: dict) -> dict:
        """セクションからdisplay_propertiesをパースする"""
        display_props_raw = section.get("display_properties", "{}")
        if not display_props_raw:
            return {}
        try:
            props = _json.loads(display_props_raw) if isinstance(display_props_raw, str) else display_props_raw
            return props if isinstance(props, dict) else {}
        except (_json.JSONDecodeError, TypeError):
            return {}

    def _get_unified_dialogues(self, section: dict) -> tuple[list[dict], bool]:
        """セクションのdialoguesを統一フォーマットで返す

        Returns:
            (dialogues, is_single_speaker): dialoguesリストと単話者フラグ
        """
        dialogues = self._parse_dialogues(section)
        if dialogues:
            return dialogues, False

        # 単話者モード → dialogues配列に変換
        content = section.get("content", "")
        tts_text = section.get("tts_text") or content
        emotion = section.get("emotion", "neutral")

        content_parts = SpeechPipeline.split_sentences(content)
        tts_parts = SpeechPipeline.split_sentences(tts_text)

        return [
            {
                "speaker": "teacher",
                "content": part,
                "tts_text": tts_parts[i] if i < len(tts_parts) else part,
                "emotion": emotion,
            }
            for i, part in enumerate(content_parts)
        ], True

    async def _generate_dlg_tts(self, dlg: dict, index: int, order_index: int) -> Path | None:
        """対話モードのTTS生成（キャッシュ対応、キャラクター別voice/style）"""
        speaker = dlg.get("speaker", "teacher")
        cfg = (self._teacher_cfg or {}) if speaker == "teacher" else (self._student_cfg or {})
        voice = cfg.get("tts_voice")
        style = cfg.get("tts_style")
        tts_text = dlg.get("tts_text", dlg.get("content", ""))

        cached = _dlg_cache_path(self._lesson_id, order_index, index,
                                  lang=self._lang, generator=self._generator,
                                  version_number=self._version_number)
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

    async def _generate_single_tts(self, tts_text: str, index: int, order_index: int) -> Path | None:
        """単話者モードのTTS生成（キャッシュ対応、デフォルトvoice/style）"""
        cached = _cache_path(self._lesson_id, order_index, index,
                              lang=self._lang, generator=self._generator,
                              version_number=self._version_number)
        if cached.exists():
            return cached

        logger.info("[lesson]   generating part[%d] tts=%s", index, repr(tts_text[:100]))
        wav = await self._speech.generate_tts(tts_text, tts_text=tts_text)
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

    async def _wav_to_bundle_entry(self, wav_path: Path, dlg: dict, index: int) -> dict | None:
        """WAVファイルからバンドルエントリを生成する"""
        if not wav_path or not wav_path.exists():
            return None

        try:
            lipsync_frames = await asyncio.to_thread(analyze_amplitude, wav_path)
        except Exception as e:
            logger.warning("[lesson] リップシンク解析失敗: %s", e)
            lipsync_frames = []

        with wave.open(str(wav_path), "rb") as wf:
            duration = wf.getnframes() / wf.getframerate()

        wav_b64 = base64.b64encode(wav_path.read_bytes()).decode()

        return {
            "index": index,
            "speaker": dlg.get("speaker", "teacher"),
            "avatar_id": dlg.get("speaker", "teacher"),
            "content": dlg.get("content", ""),
            "emotion": dlg.get("emotion", "neutral"),
            "gesture": SpeechPipeline.EMOTION_GESTURES.get(dlg.get("emotion", "neutral")),
            "lipsync_frames": lipsync_frames,
            "duration": duration,
            "wav_b64": wav_b64,
        }

    async def _build_dialogue_bundle(self, dialogues: list[dict], order_index: int,
                                      is_single_speaker: bool = False) -> list[dict]:
        """dialogueリストからバンドルを組み立てる（TTS+lipsync+wav_b64）"""
        bundle = []
        cache_hits = 0
        for i, dlg in enumerate(dialogues):
            if self._state == LessonState.IDLE:
                break

            # TTS生成（キャッシュ対応）
            if is_single_speaker:
                tts_text = dlg.get("tts_text", dlg.get("content", ""))
                wav_path = await self._generate_single_tts(tts_text, i, order_index)
            else:
                wav_path = await self._generate_dlg_tts(dlg, i, order_index)

            if not wav_path or not wav_path.exists():
                logger.warning("[lesson]   TTS生成失敗 [%d]: %s",
                               i, repr(dlg.get("content", "")[:100]))
                continue

            # キャッシュヒット判定（generate前にファイルが存在していた場合）
            # generate_*_tts がキャッシュを返した場合も含む
            entry = await self._wav_to_bundle_entry(wav_path, dlg, i)
            if entry:
                bundle.append(entry)

        logger.info("[lesson]   バンドル生成完了: %d/%d エントリ", len(bundle), len(dialogues))
        return bundle

    async def _build_question_data(self, section: dict, order_index: int) -> dict:
        """questionセクションのデータを生成する"""
        question_wait = section.get("wait_seconds", 8)
        answer = section.get("answer", "")

        answer_dialogues = []
        if answer and self._state != LessonState.IDLE:
            emotion = section.get("emotion", "neutral")
            answer_dlg = {
                "speaker": "teacher",
                "content": answer,
                "tts_text": answer,
                "emotion": emotion,
            }
            # TTS生成（キャッシュなし — 一時ファイル）
            wav_path = await self._speech.generate_tts(answer, tts_text=answer)
            entry = await self._wav_to_bundle_entry(wav_path, answer_dlg, 0)
            if entry:
                answer_dialogues.append(entry)
            # クリーンアップ
            if wav_path and wav_path.exists():
                wav_path.unlink(missing_ok=True)
                try:
                    wav_path.parent.rmdir()
                except OSError:
                    pass

        return {
            "wait_seconds": question_wait,
            "answer_dialogues": answer_dialogues,
        }

    async def _wait_section_complete(self, evt: asyncio.Event, timeout: float, total_duration: float):
        """完了イベントを待つ。ポーリングでC#状態を確認し、idle検知時は即座に完了扱いにする。

        C#が lesson_section_complete を送れない場合（WebSocket断絶・C#エラー等）でも、
        C# lesson_status がidle（再生完了）なら即座に次のセクションに進める。
        """
        from scripts.services.capture_client import ws_request as _ws_request

        poll_interval = 5.0  # ポーリング間隔（秒）
        # 音声再生が終わるまでの推定時間はポーリングしない（C#が再生中なのは確実）
        initial_wait = min(total_duration + 5, timeout)
        elapsed = 0.0

        # フェーズ1: 音声再生中は完了イベントだけを待つ
        try:
            await asyncio.wait_for(evt.wait(), timeout=initial_wait)
            return  # 正常完了
        except asyncio.TimeoutError:
            elapsed = initial_wait

        # フェーズ2: 音声再生時間を過ぎたらC# statusをポーリング
        remaining = timeout - elapsed
        while remaining > 0 and self._state != LessonState.IDLE:
            # C#のlesson_statusを確認
            try:
                status = await _ws_request("lesson_status", timeout=3.0)
                cs_state = status.get("state", "unknown") if status else "unknown"
                cs_dlg = status.get("dialogue_index", -1) if status else -1
                cs_total = status.get("total_dialogues", 0) if status else 0
                logger.info("[lesson]   C# status: state=%s, dialogue=%d/%d", cs_state, cs_dlg + 1, cs_total)

                if cs_state == "idle":
                    # C#は再生完了しているがイベントが届かなかった
                    logger.info("[lesson]   C# idle検知 → セクション完了扱い（イベントロスト）")
                    return
            except Exception as e:
                logger.warning("[lesson]   C# status取得失敗: %s", type(e).__name__)

            # 次のポーリングまでイベント待ち
            wait_time = min(poll_interval, remaining)
            try:
                await asyncio.wait_for(evt.wait(), timeout=wait_time)
                return  # 正常完了
            except asyncio.TimeoutError:
                remaining -= wait_time

        logger.warning("[lesson] セクション完了タイムアウト (%.0f秒)", timeout)

    def _get_pace_scale(self) -> float:
        """settings DBから間のスケールを取得する（デフォルト1.0）"""
        try:
            val = db.get_setting("lesson.pace_scale")
            if val is not None:
                return max(0.1, min(3.0, float(val)))
        except Exception:
            pass
        return 1.0

    async def _show_lesson_text(self, text: str, display_properties: dict | None = None):
        """配信画面にテキストを表示する"""
        if self._on_overlay:
            event = {
                "type": "lesson_text_show",
                "text": text,
            }
            if display_properties:
                event["display_properties"] = display_properties
            await self._on_overlay(event)

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

    def _save_playback_state(self, total_duration: float | None = None):
        """授業再生状態をDBに永続化する

        total_duration: 復旧時の lesson_complete 待機タイムアウト算出に使う
        """
        data = {
            "lesson_id": self._lesson_id,
            "section_index": self._current_index,
            "state": self._state.value,
            "lang": self._lang,
            "generator": self._generator,
            "version_number": self._version_number,
            "episode_id": self._episode_id,
        }
        if total_duration is not None:
            data["total_duration"] = total_duration
        db.set_setting(PLAYBACK_SETTING_KEY, _json.dumps(data))

    @staticmethod
    def _clear_playback_state():
        """授業再生状態をDBから削除する"""
        db.delete_setting(PLAYBACK_SETTING_KEY)

    @staticmethod
    def get_playback_state() -> dict | None:
        """DBから授業再生状態を読み取る"""
        raw = db.get_setting(PLAYBACK_SETTING_KEY)
        if not raw:
            return None
        try:
            return _json.loads(raw)
        except (_json.JSONDecodeError, TypeError):
            return None

    def get_status(self) -> dict:
        """現在のステータスを取得する"""
        return {
            "state": self._state.value,
            "lesson_id": self._lesson_id,
            "lang": self._lang,
            "generator": self._generator,
            "version_number": self._version_number,
            "current_index": self._current_index,
            "total_sections": len(self._sections),
        }
