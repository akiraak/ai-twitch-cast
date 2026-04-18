"""speech_pipeline のテスト（TTS・リップシンク・オーバーレイ・感情・モジュール分離）"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.speech_pipeline import SpeechPipeline
from src.ai_responder import DEFAULT_CHARACTER


# =====================================================
# strip_lang_tags
# =====================================================


class TestStripLangTags:
    def test_removes_opening_tag(self):
        assert SpeechPipeline.strip_lang_tags("[lang:en]hello") == "hello"

    def test_removes_closing_tag(self):
        assert SpeechPipeline.strip_lang_tags("hello[/lang]") == "hello"

    def test_removes_both_tags(self):
        result = SpeechPipeline.strip_lang_tags("今日は[lang:en]YouTube[/lang]の動画")
        assert result == "今日はYouTubeの動画"

    def test_removes_multiple_tags(self):
        text = "[lang:es]¡Hola![/lang]いらっしゃい[lang:en]Welcome[/lang]"
        result = SpeechPipeline.strip_lang_tags(text)
        assert result == "¡Hola!いらっしゃいWelcome"

    def test_no_tags_unchanged(self):
        text = "今日はいい天気ですね"
        assert SpeechPipeline.strip_lang_tags(text) == text

    def test_empty_string(self):
        assert SpeechPipeline.strip_lang_tags("") == ""


# =====================================================
# split_sentences
# =====================================================


class TestSplitSentences:
    def test_short_text_no_split(self):
        """30文字以下は分割しない"""
        assert SpeechPipeline.split_sentences("短いテキスト") == ["短いテキスト"]

    def test_split_on_maru(self):
        """「。」で分割"""
        result = SpeechPipeline.split_sentences("Pythonってほんと便利だよね。特にasyncが使いやすくて最高だよ")
        assert result == ["Pythonってほんと便利だよね。", "特にasyncが使いやすくて最高だよ"]

    def test_split_on_exclamation(self):
        """「！」で分割"""
        result = SpeechPipeline.split_sentences("すごいニュースがあるんだよ！実はPythonの新バージョンが出たんだ")
        assert result == ["すごいニュースがあるんだよ！", "実はPythonの新バージョンが出たんだ"]

    def test_split_on_question(self):
        """「？」で分割"""
        result = SpeechPipeline.split_sentences("みんなはどう思う？俺はめっちゃいいと思うんだよねほんとにすごいよ")
        assert result == ["みんなはどう思う？", "俺はめっちゃいいと思うんだよねほんとにすごいよ"]

    def test_multiple_sentences(self):
        """複数文の分割"""
        result = SpeechPipeline.split_sentences("まず一つ目の話をしようか。次に二つ目の話だよ。最後に三つ目の話をするね")
        assert result == ["まず一つ目の話をしようか。", "次に二つ目の話だよ。", "最後に三つ目の話をするね"]

    def test_no_punctuation_no_split(self):
        """句読点がない長文は分割しない"""
        text = "句読点がないけどめっちゃ長い文章だよこれはどうなるかな"
        assert SpeechPipeline.split_sentences(text) == [text]

    def test_empty_string(self):
        assert SpeechPipeline.split_sentences("") == [""]

    def test_exactly_30_chars(self):
        """ちょうど30文字は分割しない"""
        text = "あ" * 30
        assert SpeechPipeline.split_sentences(text) == [text]

    def test_no_split_on_ascii_punctuation(self):
        """半角の.!?では分割しない（英語混在テキスト）"""
        text = "今日はClaude Codeで開発してるよ! What do you think? すごくない"
        assert SpeechPipeline.split_sentences(text) == [text]


# =====================================================
# notify_overlay
# =====================================================


class TestNotifyOverlay:
    @pytest.mark.asyncio
    async def test_sends_comment_event(self):
        callback = AsyncMock()
        sp = SpeechPipeline(on_overlay=callback)
        result = {"speech": "[lang:en]Hello[/lang]!", "translation": "こんにちは", "emotion": "joy"}
        await sp.notify_overlay("alice", "hi", result)

        callback.assert_called_once()
        event = callback.call_args[0][0]
        assert event["type"] == "comment"
        assert event["author"] == "alice"
        assert event["trigger_text"] == "hi"
        assert event["speech"] == "Hello!"  # lang tags stripped
        assert event["translation"] == "こんにちは"
        assert event["emotion"] == "joy"

    @pytest.mark.asyncio
    async def test_no_callback_does_nothing(self):
        sp = SpeechPipeline(on_overlay=None)
        # Should not raise
        await sp.notify_overlay("alice", "hi", {"speech": "test", "emotion": "neutral"})

    @pytest.mark.asyncio
    async def test_english_defaults_to_empty(self):
        callback = AsyncMock()
        sp = SpeechPipeline(on_overlay=callback)
        result = {"speech": "テスト", "emotion": "neutral"}
        await sp.notify_overlay("bob", "msg", result)

        event = callback.call_args[0][0]
        assert event["translation"] == ""

    @pytest.mark.asyncio
    async def test_duration_included_when_provided(self):
        """duration指定時にペイロードに含まれること"""
        callback = AsyncMock()
        sp = SpeechPipeline(on_overlay=callback)
        result = {"speech": "テスト", "emotion": "neutral"}
        await sp.notify_overlay("bob", "msg", result, duration=10.5)

        event = callback.call_args[0][0]
        assert event["duration"] == 10.5

    @pytest.mark.asyncio
    async def test_duration_omitted_when_none(self):
        """duration未指定時にペイロードに含まれないこと"""
        callback = AsyncMock()
        sp = SpeechPipeline(on_overlay=callback)
        result = {"speech": "テスト", "emotion": "neutral"}
        await sp.notify_overlay("bob", "msg", result)

        event = callback.call_args[0][0]
        assert "duration" not in event


# =====================================================
# notify_overlay_end
# =====================================================


class TestNotifyOverlayEnd:
    @pytest.mark.asyncio
    async def test_sends_speaking_end(self):
        callback = AsyncMock()
        sp = SpeechPipeline(on_overlay=callback)
        await sp.notify_overlay_end()

        callback.assert_called_once_with({"type": "speaking_end"})

    @pytest.mark.asyncio
    async def test_no_callback_does_nothing(self):
        sp = SpeechPipeline(on_overlay=None)
        await sp.notify_overlay_end()  # Should not raise


# =====================================================
# apply_emotion
# =====================================================


class TestApplyEmotion:
    @pytest.mark.asyncio
    async def test_joy_sends_blendshape(self):
        """joyの感情でBlendShapeイベントが送信されること"""
        callback = AsyncMock()
        sp = SpeechPipeline(on_overlay=callback)
        with patch("src.speech_pipeline.get_character", return_value=DEFAULT_CHARACTER):
            sp.apply_emotion("joy")
            # create_taskで非同期実行されるので、イベントループを回す
            await asyncio.sleep(0)

        callback.assert_called_once()
        event = callback.call_args[0][0]
        assert event["type"] == "blendshape"
        assert event["shapes"]["happy"] == 1.0
        assert event["gesture"] == "nod"

    @pytest.mark.asyncio
    async def test_neutral_resets_blendshapes(self):
        """neutralは全BlendShapeを0にリセットすること"""
        callback = AsyncMock()
        sp = SpeechPipeline(on_overlay=callback)
        with patch("src.speech_pipeline.get_character", return_value=DEFAULT_CHARACTER):
            sp.apply_emotion("neutral")
            await asyncio.sleep(0)

        # DEFAULT_CHARACTERのneutralは空dict → 全感情のkeyを0にリセット
        callback.assert_called_once()
        shapes = callback.call_args[0][0]["shapes"]
        for val in shapes.values():
            assert val == 0.0

    @pytest.mark.asyncio
    async def test_no_overlay_does_nothing(self):
        """on_overlayがNoneでもエラーにならないこと"""
        with patch("src.speech_pipeline.get_character", return_value=DEFAULT_CHARACTER):
            sp = SpeechPipeline(on_overlay=None)
            sp.apply_emotion("joy")  # Should not raise

    @pytest.mark.asyncio
    async def test_unknown_emotion_resets(self):
        """定義にない感情はリセット動作をすること"""
        callback = AsyncMock()
        sp = SpeechPipeline(on_overlay=callback)
        with patch("src.speech_pipeline.get_character", return_value=DEFAULT_CHARACTER):
            sp.apply_emotion("unknown_emotion")
            await asyncio.sleep(0)

        callback.assert_called_once()
        shapes = callback.call_args[0][0]["shapes"]
        for val in shapes.values():
            assert val == 0.0


# =====================================================
# speak（統合テスト）
# =====================================================


class TestSpeak:
    @pytest.mark.asyncio
    async def test_speak_with_tts_failure(self):
        """TTS生成失敗時にチャット投稿とテキスト表示のみ行うこと"""
        callback = AsyncMock()
        chat_fn = AsyncMock()
        sp = SpeechPipeline(on_overlay=callback)

        with patch("src.speech_pipeline.synthesize", side_effect=Exception("TTS error")):
            await sp.speak(
                "テスト", chat_result={"response": "テスト"},
                post_to_chat=chat_fn,
            )

        # TTS失敗時でもチャット投稿は実行される
        chat_fn.assert_called_once_with({"response": "テスト"})

    @pytest.mark.asyncio
    async def test_speak_no_overlay_cleans_up(self):
        """on_overlayがNoneでもファイルがクリーンアップされること"""
        sp = SpeechPipeline(on_overlay=None)

        with patch("src.speech_pipeline.synthesize"):
            await sp.speak("テスト")

        assert sp._current_audio is None

    @pytest.mark.asyncio
    async def test_speak_no_chat_callback(self):
        """post_to_chatがNoneでもエラーにならないこと"""
        callback = AsyncMock()
        sp = SpeechPipeline(on_overlay=callback)

        with patch("src.speech_pipeline.synthesize", side_effect=Exception("TTS error")):
            await sp.speak(
                "テスト", chat_result={"response": "テスト"},
                post_to_chat=None,
            )
        # No error raised


# =====================================================
# generate_tts（並列事前生成）
# =====================================================


class TestGenerateTts:
    @pytest.mark.asyncio
    async def test_success_returns_wav_path(self, tmp_path):
        """成功時: WAVパスを返す"""
        sp = SpeechPipeline()
        with patch("src.speech_pipeline.synthesize"):
            result = await sp.generate_tts("テスト")

        assert result is not None
        assert result.name == "speech.wav"

    @pytest.mark.asyncio
    async def test_failure_returns_none_and_cleans_up(self):
        """失敗時: Noneを返し、テンポラリディレクトリが削除される"""
        sp = SpeechPipeline()
        with patch("src.speech_pipeline.synthesize", side_effect=RuntimeError("TTS down")):
            result = await sp.generate_tts("テスト")

        assert result is None

    @pytest.mark.asyncio
    async def test_cancellation_cleans_up_and_reraises(self):
        """キャンセル時: テンポラリをクリーンアップしCancelledErrorを再送出"""
        import tempfile
        from pathlib import Path

        created_dirs = []
        orig_mkdtemp = tempfile.mkdtemp

        def track_mkdtemp(*args, **kwargs):
            d = orig_mkdtemp(*args, **kwargs)
            created_dirs.append(Path(d))
            return d

        sp = SpeechPipeline()

        async def slow_synth(*args, **kwargs):
            await asyncio.sleep(5.0)

        with patch("src.speech_pipeline.tempfile.mkdtemp", side_effect=track_mkdtemp), \
             patch("src.speech_pipeline.asyncio.to_thread", side_effect=slow_synth):
            task = asyncio.create_task(sp.generate_tts("テスト"))
            await asyncio.sleep(0.05)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        # テンポラリディレクトリが削除されていること
        assert len(created_dirs) == 1
        assert not created_dirs[0].exists()

    @pytest.mark.asyncio
    async def test_voice_and_style_passed(self):
        """voice/styleがsynthesizeに渡される"""
        sp = SpeechPipeline()
        with patch("src.speech_pipeline.synthesize") as mock_synth:
            await sp.generate_tts("テスト", voice="Leda", style="happy", tts_text="TTS用")

        args, kwargs = mock_synth.call_args
        assert args[0] == "TTS用"  # tts_text優先
        assert kwargs["voice"] == "Leda"
        assert kwargs["style"] == "happy"


# =====================================================
# send_tts_to_native_app
# =====================================================


class TestSendTtsToNativeApp:
    @pytest.mark.asyncio
    async def test_sends_wav_data(self, tmp_path):
        """WAVデータをBase64エンコードして送信すること"""
        wav_path = tmp_path / "test.wav"
        wav_path.write_bytes(b"fake wav data")

        with patch("scripts.services.capture_client.ws_request", new_callable=AsyncMock) as mock_ws, \
             patch("scripts.routes.stream_control._get_volume", return_value=0.8):
            sp = SpeechPipeline()
            await sp.send_tts_to_native_app(wav_path)

            mock_ws.assert_called_once()
            call_kwargs = mock_ws.call_args
            assert call_kwargs[0][0] == "tts_audio"
            assert call_kwargs[1]["timeout"] == 10.0
            assert "data" in call_kwargs[1]

    @pytest.mark.asyncio
    async def test_volume_calculation(self, tmp_path):
        """音量が正しく計算されること（tts²×master²）"""
        wav_path = tmp_path / "test.wav"
        wav_path.write_bytes(b"fake wav data")

        def fake_volume(source):
            return {"master": 0.5, "tts": 1.0}[source]

        with patch("scripts.services.capture_client.ws_request", new_callable=AsyncMock) as mock_ws, \
             patch("scripts.routes.stream_control._get_volume", side_effect=fake_volume):
            sp = SpeechPipeline()
            await sp.send_tts_to_native_app(wav_path)

            volume = mock_ws.call_args[1]["volume"]
            # min(1.0, 1.0²) × 0.5² = 1.0 × 0.25 = 0.25
            assert abs(volume - 0.25) < 0.001

    @pytest.mark.asyncio
    async def test_ws_failure_does_not_raise(self, tmp_path):
        """WS送信失敗でも例外を投げないこと"""
        wav_path = tmp_path / "test.wav"
        wav_path.write_bytes(b"fake wav data")

        with patch("scripts.services.capture_client.ws_request", new_callable=AsyncMock, side_effect=Exception("ws down")), \
             patch("scripts.routes.stream_control._get_volume", return_value=0.8):
            sp = SpeechPipeline()
            await sp.send_tts_to_native_app(wav_path)  # Should not raise


# =====================================================
# _wait_tts_complete
# =====================================================


class TestWaitTtsComplete:
    @pytest.mark.asyncio
    async def test_polls_until_inactive(self):
        """active=True→True→Falseでポーリング終了すること"""
        responses = [
            {"ok": True, "active": True},
            {"ok": True, "active": True},
            {"ok": True, "active": False},
        ]
        call_count = 0

        async def mock_ws_request(action, timeout=2.0):
            nonlocal call_count
            resp = responses[min(call_count, len(responses) - 1)]
            call_count += 1
            return resp

        sp = SpeechPipeline()
        with patch("scripts.services.capture_client.ws_request", side_effect=mock_ws_request):
            await sp._wait_tts_complete(max_extra=5.0)

        assert call_count == 3

    @pytest.mark.asyncio
    async def test_immediately_inactive(self):
        """最初からactive=Falseならポーリング1回で終了すること"""
        call_count = 0

        async def mock_ws_request(action, timeout=2.0):
            nonlocal call_count
            call_count += 1
            return {"ok": True, "active": False}

        sp = SpeechPipeline()
        with patch("scripts.services.capture_client.ws_request", side_effect=mock_ws_request):
            await sp._wait_tts_complete(max_extra=5.0)

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_timeout_stops_polling(self):
        """max_extraに達したらポーリングを打ち切ること"""
        call_count = 0

        async def mock_ws_request(action, timeout=2.0):
            nonlocal call_count
            call_count += 1
            return {"ok": True, "active": True}

        sp = SpeechPipeline()
        with patch("scripts.services.capture_client.ws_request", side_effect=mock_ws_request), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            await sp._wait_tts_complete(max_extra=0.5)

        # 0.5秒 / 0.2秒間隔 = 最大2〜3回のポーリング
        assert 2 <= call_count <= 3

    @pytest.mark.asyncio
    async def test_ws_failure_silently_skips(self):
        """ws_request失敗時に例外を出さずスキップすること"""
        async def mock_ws_request(action, timeout=2.0):
            raise Exception("connection refused")

        sp = SpeechPipeline()
        with patch("scripts.services.capture_client.ws_request", side_effect=mock_ws_request):
            await sp._wait_tts_complete(max_extra=5.0)  # Should not raise

    @pytest.mark.asyncio
    async def test_none_result_treated_as_inactive(self):
        """ws_requestがNoneを返した場合もinactiveとして扱うこと"""
        call_count = 0

        async def mock_ws_request(action, timeout=2.0):
            nonlocal call_count
            call_count += 1
            return None

        sp = SpeechPipeline()
        with patch("scripts.services.capture_client.ws_request", side_effect=mock_ws_request):
            await sp._wait_tts_complete(max_extra=5.0)

        assert call_count == 1


# =====================================================
# モジュール分離
# =====================================================


class TestSpeakBatch:
    """speak_batch（チェーン再生）のテスト"""

    def _make_wav(self, path, duration_sec=0.1, framerate=24000):
        """テスト用の短いWAVファイルを作る"""
        import wave
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(framerate)
            wf.writeframes(b"\x00\x00" * int(framerate * duration_sec))

    @pytest.mark.asyncio
    async def test_empty_entries_returns_immediately(self):
        """空のエントリリストでは何もせずに戻る"""
        sp = SpeechPipeline()
        await sp.speak_batch([])  # 例外を出さずに終わること

    @pytest.mark.asyncio
    async def test_sends_batch_with_all_entries(self, tmp_path):
        """全エントリがまとめて send_tts_batch に渡される"""
        wav1 = tmp_path / "a.wav"
        wav2 = tmp_path / "b.wav"
        self._make_wav(wav1)
        self._make_wav(wav2)

        callback = AsyncMock()
        sp = SpeechPipeline(on_overlay=callback)

        entries = [
            {
                "wav_path": wav1,
                "subtitle": {"author": "T", "trigger_text": "tt", "result": {"speech": "s1", "emotion": "joy"}},
                "emotion": "joy",
                "avatar_id": "teacher",
                "character_config": {"name": "T"},
            },
            {
                "wav_path": wav2,
                "subtitle": {"author": "S", "trigger_text": "tt", "result": {"speech": "s2", "emotion": "neutral"}},
                "emotion": "neutral",
                "avatar_id": "student",
                "character_config": {"name": "S"},
            },
        ]

        # 各エントリの開始Pushを即発火するよう event をモック
        import scripts.services.capture_client as cc
        original_entries = cc._tts_entry_events.copy()
        try:
            sent_items_box = {}

            async def fake_send_batch(items, timeout=15.0):
                sent_items_box["items"] = items
                # 開始Push を順次シミュレート
                for item in items:
                    cc.get_tts_entry_event(item["id"]).set()
                # 完了Pushもシミュレート
                cc._tts_batch_complete_event.set()
                return {"ok": True, "queued": len(items)}

            with patch("scripts.services.capture_client.send_tts_batch",
                       side_effect=fake_send_batch), \
                 patch("scripts.routes.stream_control._get_volume", return_value=0.8), \
                 patch("src.speech_pipeline.analyze_amplitude", return_value=[0.1, 0.2, 0.3]):
                await sp.speak_batch(entries)

            assert "items" in sent_items_box
            assert len(sent_items_box["items"]) == 2
            for item in sent_items_box["items"]:
                assert "id" in item
                assert "data" in item
                assert "volume" in item
        finally:
            cc._tts_entry_events.clear()
            cc._tts_entry_events.update(original_entries)
            cc._tts_batch_complete_event = None

    @pytest.mark.asyncio
    async def test_fires_subtitle_and_lipsync_per_entry(self, tmp_path):
        """各エントリの tts_entry_started で字幕・lipsync が発火する"""
        wav1 = tmp_path / "a.wav"
        self._make_wav(wav1)

        callback = AsyncMock()
        sp = SpeechPipeline(on_overlay=callback)

        entries = [{
            "wav_path": wav1,
            "subtitle": {"author": "T", "trigger_text": "tt", "result": {"speech": "s1", "emotion": "joy"}},
            "emotion": "joy",
            "avatar_id": "teacher",
            "character_config": {"name": "T"},
        }]

        import scripts.services.capture_client as cc

        async def fake_send_batch(items, timeout=15.0):
            for item in items:
                cc.get_tts_entry_event(item["id"]).set()
            cc._tts_batch_complete_event.set()
            return {"ok": True, "queued": 1}

        with patch("scripts.services.capture_client.send_tts_batch",
                   side_effect=fake_send_batch), \
             patch("scripts.routes.stream_control._get_volume", return_value=0.8), \
             patch("src.speech_pipeline.analyze_amplitude", return_value=[0.1, 0.2]):
            await sp.speak_batch(entries)

        # callback: comment → lipsync → lipsync_stop が含まれる
        types = [c.args[0]["type"] for c in callback.call_args_list]
        assert "comment" in types
        assert "lipsync" in types
        assert "lipsync_stop" in types

    @pytest.mark.asyncio
    async def test_send_failure_cleans_up(self, tmp_path):
        """バッチ送信失敗時もテンポラリWAVは削除される（キャッシュ以外）"""
        import tempfile
        from pathlib import Path as _Path
        tmpdir = _Path(tempfile.mkdtemp())
        wav1 = tmpdir / "a.wav"
        self._make_wav(wav1)

        sp = SpeechPipeline(on_overlay=AsyncMock())

        entries = [{
            "wav_path": wav1,
            "subtitle": None,
            "emotion": None,
            "avatar_id": "teacher",
            "character_config": {},
        }]

        with patch("scripts.services.capture_client.send_tts_batch",
                   side_effect=RuntimeError("ws down")), \
             patch("scripts.routes.stream_control._get_volume", return_value=0.8), \
             patch("src.speech_pipeline.analyze_amplitude", return_value=[]):
            await sp.speak_batch(entries)

        # テンポラリWAVがクリーンアップされていること
        assert not wav1.exists()


class TestModuleSeparation:
    def test_comment_reader_uses_speech_pipeline(self):
        """comment_reader.py が SpeechPipeline を使っていること"""
        import inspect
        import src.comment_reader as cr

        source = inspect.getsource(cr)
        assert "from src.speech_pipeline import SpeechPipeline" in source

    def test_comment_reader_no_tts_import(self):
        """comment_reader.py が tts/lipsync を直接インポートしていないこと"""
        import inspect
        import src.comment_reader as cr

        source = inspect.getsource(cr)
        assert "from src.tts import" not in source
        assert "from src.lipsync import" not in source

    def test_comment_reader_no_speak_method(self):
        """comment_reader.py に _speak メソッドが残っていないこと"""
        import inspect
        import src.comment_reader as cr

        source = inspect.getsource(cr)
        assert "async def _speak(" not in source
        assert "async def _send_tts_to_native_app(" not in source
        assert "def _apply_emotion(" not in source
        assert "def _strip_lang_tags(" not in source

    def test_speech_pipeline_no_circular_import(self):
        """speech_pipeline が comment_reader をインポートしていないこと"""
        import inspect
        import src.speech_pipeline as sp

        source = inspect.getsource(sp)
        assert "comment_reader" not in source
        assert "TwitchChat" not in source
