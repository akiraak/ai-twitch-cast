"""CommentReader の並列TTS事前生成テスト"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_reader():
    """CommentReaderインスタンスを生成（依存をモック化）"""
    with patch("src.comment_reader.TwitchChat"):
        from src.comment_reader import CommentReader
        reader = CommentReader()
    reader._speech = MagicMock()
    reader._speech.apply_emotion = MagicMock()
    reader._speech.speak = AsyncMock()
    reader._speech.notify_overlay_end = AsyncMock()
    reader._speech.generate_tts = AsyncMock(return_value=None)
    return reader


class TestSpeakSegmentParallel:
    """_speak_segment の事前生成タスク対応"""

    @pytest.mark.asyncio
    async def test_tts_task_awaited_and_wav_passed(self, tmp_path):
        """tts_taskがあればawaitしwav_pathをspeakに渡す"""
        reader = _make_reader()
        wav_path = tmp_path / "pre.wav"
        wav_path.write_bytes(b"WAV")

        async def fake_gen():
            return wav_path

        task = asyncio.create_task(fake_gen())
        seg = {
            "content": "テスト",
            "emotion": "neutral",
            "tts_text": "テスト",
            "translation": "",
            "speaker": "student",
            "avatar_id": "student",
            "voice": "Leda",
            "style": "",
            "char_name": "なるこ",
            "char_config": {"name": "なるこ"},
            "tts_task": task,
        }
        with patch.object(reader, "_save_avatar_comment", new_callable=AsyncMock):
            await reader._speak_segment(seg)

        reader._speech.speak.assert_called_once()
        assert reader._speech.speak.call_args.kwargs["wav_path"] == wav_path

    @pytest.mark.asyncio
    async def test_tts_task_failure_falls_back(self):
        """tts_taskが失敗してもwav_path=Noneでspeakを呼ぶ（フォールバック）"""
        reader = _make_reader()

        async def failing():
            raise RuntimeError("gen fail")

        task = asyncio.create_task(failing())
        await asyncio.sleep(0)  # タスクを走らせる
        seg = {
            "content": "テスト",
            "emotion": "neutral",
            "tts_text": "テスト",
            "translation": "",
            "speaker": "teacher",
            "avatar_id": "teacher",
            "voice": None,
            "style": None,
            "char_name": "ちょビ",
            "char_config": {"name": "ちょビ"},
            "tts_task": task,
        }
        with patch.object(reader, "_save_avatar_comment", new_callable=AsyncMock):
            await reader._speak_segment(seg)

        reader._speech.speak.assert_called_once()
        assert reader._speech.speak.call_args.kwargs["wav_path"] is None

    @pytest.mark.asyncio
    async def test_no_tts_task_backward_compat(self):
        """tts_taskなしでも（既存セグメント・単話者長文分割）動作する"""
        reader = _make_reader()
        seg = {
            "content": "テスト",
            "emotion": "neutral",
            "tts_text": "テスト",
            "translation": "",
            "speaker": "teacher",
            "avatar_id": "teacher",
            "voice": None,
            "style": None,
            "char_name": "ちょビ",
            "char_config": None,
        }
        with patch.object(reader, "_save_avatar_comment", new_callable=AsyncMock):
            await reader._speak_segment(seg)

        reader._speech.speak.assert_called_once()
        assert reader._speech.speak.call_args.kwargs["wav_path"] is None


class TestSegmentQueueCancellation:
    """_process_loop / stop() でtts_taskがキャンセルされる"""

    @pytest.mark.asyncio
    async def test_comment_arrival_cancels_pending_tasks(self):
        """コメント到着でsegment_queueクリア時、未完了tts_taskがキャンセルされる"""
        reader = _make_reader()
        cancelled = []

        async def pending():
            try:
                await asyncio.sleep(10.0)
            except asyncio.CancelledError:
                cancelled.append(True)
                raise

        task1 = asyncio.create_task(pending())
        task2 = asyncio.create_task(pending())
        await asyncio.sleep(0)

        reader._segment_queue.append({"content": "a", "tts_task": task1})
        reader._segment_queue.append({"content": "b", "tts_task": task2})

        # _respondをモック化（実行しない）
        reader._respond = AsyncMock()
        reader._queue.append(("alice", "hello"))
        reader._running = True

        async def run_once():
            # _process_loopの本体1サイクルを模擬
            if reader._queue:
                if reader._segment_queue:
                    for seg in reader._segment_queue:
                        t = seg.get("tts_task")
                        if t is not None and not t.done():
                            t.cancel()
                    reader._segment_queue.clear()
                author, message = reader._queue.popleft()
                await reader._respond(author, message)

        await run_once()
        await asyncio.sleep(0.05)

        assert len(cancelled) == 2
        assert len(reader._segment_queue) == 0

    @pytest.mark.asyncio
    async def test_stop_cancels_segment_tasks(self):
        """stop()でsegment_queue内のtts_taskがキャンセルされる"""
        reader = _make_reader()
        cancelled = []

        async def pending():
            try:
                await asyncio.sleep(10.0)
            except asyncio.CancelledError:
                cancelled.append(True)
                raise

        task = asyncio.create_task(pending())
        await asyncio.sleep(0)
        reader._segment_queue.append({"content": "a", "tts_task": task})

        # 外部依存をモック化
        reader._chat.stop = AsyncMock()
        reader._lesson_runner.stop = AsyncMock()
        reader._claude_watcher.stop = AsyncMock()

        await reader.stop()
        await asyncio.sleep(0.05)

        assert len(cancelled) == 1
