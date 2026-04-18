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
    reader._speech.speak_batch = AsyncMock()
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


class TestSpeakEventMultiBatch:
    """speak_event マルチキャラ経路が speak_batch を使うこと（Claude Code実況ギャップ縮小）"""

    @pytest.mark.asyncio
    async def test_multi_calls_speak_batch_once(self, tmp_path):
        """マルチキャラ分岐は speak_batch を1回だけ呼び、speak は呼ばれない"""
        reader = _make_reader()
        reader._characters = {
            "teacher": {"name": "ちょビ", "tts_voice": "Despina", "tts_style": ""},
            "student": {"name": "なるこ", "tts_voice": "Kore", "tts_style": ""},
        }
        wav_path = tmp_path / "fake.wav"
        wav_path.write_bytes(b"WAV")
        reader._speech.generate_tts = AsyncMock(return_value=wav_path)

        responses = [
            {"speaker": "teacher", "speech": "1番目", "emotion": "neutral"},
            {"speaker": "student", "speech": "2番目", "emotion": "joy"},
        ]

        with patch("src.comment_reader.generate_multi_event_response", return_value=responses), \
             patch("src.comment_reader.db.get_recent_avatar_comments", return_value=[]), \
             patch.object(reader, "_save_avatar_comment", new_callable=AsyncMock), \
             patch.object(reader, "_post_to_chat", new_callable=AsyncMock):
            await reader.speak_event("claude_work", "テスト")

        assert reader._speech.speak_batch.call_count == 1
        assert reader._speech.speak.call_count == 0

        entries = reader._speech.speak_batch.call_args.args[0]
        assert len(entries) == 2
        assert entries[0]["avatar_id"] == "teacher"
        assert entries[1]["avatar_id"] == "student"
        assert entries[0]["subtitle"]["author"] == "ちょビ"
        assert entries[1]["subtitle"]["author"] == "なるこ"
        assert entries[0]["emotion"] == "neutral"
        assert entries[1]["emotion"] == "joy"
        assert entries[0]["wav_path"] == wav_path
        # 内部用キーは batch エントリに残さない
        assert "_entry" not in entries[0]

    @pytest.mark.asyncio
    async def test_multi_saves_all_to_db(self, tmp_path):
        """全エントリがDB保存される（バッチ送信前にまとめて）"""
        reader = _make_reader()
        reader._characters = {
            "teacher": {"name": "ちょビ"},
            "student": {"name": "なるこ"},
        }
        wav_path = tmp_path / "fake.wav"
        wav_path.write_bytes(b"WAV")
        reader._speech.generate_tts = AsyncMock(return_value=wav_path)

        responses = [
            {"speaker": "teacher", "speech": "報告1", "emotion": "joy"},
            {"speaker": "student", "speech": "ほんと？", "emotion": "surprise"},
        ]
        with patch("src.comment_reader.generate_multi_event_response", return_value=responses), \
             patch("src.comment_reader.db.get_recent_avatar_comments", return_value=[]), \
             patch.object(reader, "_save_avatar_comment", new_callable=AsyncMock) as mock_save, \
             patch.object(reader, "_post_to_chat", new_callable=AsyncMock):
            await reader.speak_event("commit", "テスト")

        assert mock_save.call_count == 2
        first = mock_save.call_args_list[0]
        assert first.args[0] == "event"
        assert first.args[2] == "報告1"
        assert first.args[3] == "joy"
        assert first.kwargs["speaker"] == "teacher"

    @pytest.mark.asyncio
    async def test_multi_skips_when_all_tts_fail(self):
        """全TTS生成失敗時は speak_batch を呼ばず、DB保存も走らない"""
        reader = _make_reader()
        reader._characters = {
            "teacher": {"name": "ちょビ"},
            "student": {"name": "なるこ"},
        }
        reader._speech.generate_tts = AsyncMock(return_value=None)

        responses = [
            {"speaker": "teacher", "speech": "1", "emotion": "neutral"},
            {"speaker": "student", "speech": "2", "emotion": "joy"},
        ]
        with patch("src.comment_reader.generate_multi_event_response", return_value=responses), \
             patch("src.comment_reader.db.get_recent_avatar_comments", return_value=[]), \
             patch.object(reader, "_save_avatar_comment", new_callable=AsyncMock) as mock_save, \
             patch.object(reader, "_post_to_chat", new_callable=AsyncMock):
            await reader.speak_event("claude_work", "テスト")

        assert reader._speech.speak_batch.call_count == 0
        assert reader._speech.speak.call_count == 0
        assert mock_save.call_count == 0

    @pytest.mark.asyncio
    async def test_multi_posts_first_entry_to_chat(self, tmp_path):
        """最初のエントリだけチャット投稿される（遅延バックグラウンド実行）"""
        reader = _make_reader()
        reader._characters = {
            "teacher": {"name": "ちょビ"},
            "student": {"name": "なるこ"},
        }
        wav_path = tmp_path / "fake.wav"
        wav_path.write_bytes(b"WAV")
        reader._speech.generate_tts = AsyncMock(return_value=wav_path)

        responses = [
            {"speaker": "teacher", "speech": "最初", "emotion": "neutral"},
            {"speaker": "student", "speech": "二番目", "emotion": "joy"},
        ]

        # asyncio.sleep を短縮（2秒遅延を即座に終わらせる）
        original_sleep = asyncio.sleep

        async def fast_sleep(sec, *args, **kwargs):
            if sec >= 1.5:
                return await original_sleep(0)
            return await original_sleep(sec)

        post_mock = AsyncMock()

        with patch("src.comment_reader.generate_multi_event_response", return_value=responses), \
             patch("src.comment_reader.db.get_recent_avatar_comments", return_value=[]), \
             patch.object(reader, "_save_avatar_comment", new_callable=AsyncMock), \
             patch.object(reader, "_post_to_chat", post_mock), \
             patch("src.comment_reader.asyncio.sleep", side_effect=fast_sleep):
            await reader.speak_event("claude_work", "テスト")
            # 遅延タスクが走り切るまで待つ
            await original_sleep(0.05)

        assert post_mock.call_count == 1
        assert post_mock.call_args.args[0]["speech"] == "最初"
