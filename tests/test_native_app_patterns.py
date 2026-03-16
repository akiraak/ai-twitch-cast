"""C#ネイティブアプリのコードパターン検証テスト。

バグ修正で発見された危険なパターンの再発を防止する。
実行環境にWindowsや音声デバイスは不要（ソースコード解析のみ）。
"""

import re
from pathlib import Path

NATIVE_APP_DIR = Path(__file__).parent.parent / "win-native-app" / "WinNativeApp"


def read_cs(relative_path: str) -> str:
    """C#ソースファイルを読み込む"""
    return (NATIVE_APP_DIR / relative_path).read_text(encoding="utf-8-sig")


# === AudioLoopback.cs ===


def test_audio_stop_no_wait_handle():
    """AudioLoopback.Stop()でManualResetEvent+WaitOneを使わないこと。

    WaitOneタイムアウト後にタイマー内部がハンドルをSignalしようとして
    ObjectDisposedException→プロセスクラッシュの原因となる。
    """
    source = read_cs("Streaming/AudioLoopback.cs")
    stop_match = re.search(r"public void Stop\(\)(.*?)(?=public )", source, re.DOTALL)
    assert stop_match, "Stop() method not found"
    stop_body = stop_match.group(1)
    # コメント行を除去してコードのみ検査
    code_lines = [
        line for line in stop_body.splitlines()
        if line.strip() and not line.strip().startswith("//")
    ]
    code_only = "\n".join(code_lines)
    assert "ManualResetEvent" not in code_only, (
        "Stop()でManualResetEventを使うとクラッシュする。timer?.Dispose()のみ使用すること"
    )
    assert ".WaitOne(" not in code_only, (
        "Stop()でWaitOneを使うとクラッシュする。timer?.Dispose()のみ使用すること"
    )


def test_audio_stop_nulls_timer_before_dispose():
    """AudioLoopback.Stop()で_silenceTimerをnull設定してからDisposeすること。

    DataAvailableコールバックが_silenceTimer?.Change()を呼ぶため、
    Dispose後もフィールドが非nullだとObjectDisposedExceptionが発生する。
    """
    source = read_cs("Streaming/AudioLoopback.cs")
    stop_match = re.search(r"public void Stop\(\)(.*?)(?=public )", source, re.DOTALL)
    assert stop_match, "Stop() method not found"
    stop_body = stop_match.group(1)
    null_pos = stop_body.find("_silenceTimer = null")
    dispose_pos = stop_body.find(".Dispose()")
    assert null_pos != -1, "_silenceTimer = null が Stop() に存在しない"
    assert dispose_pos != -1, "timer.Dispose() が Stop() に存在しない"
    assert null_pos < dispose_pos, (
        "_silenceTimerをnullにする前にDisposeしている。レースコンディションの原因"
    )


def test_audio_silence_timer_skips_when_data_active():
    """サイレンスタイマーが実データ受信中にサイレンスを送らないこと。

    サイレンスと実データの二重書き込みはFFmpegに余分なデータを送り、
    音声途切れの原因となる。
    """
    source = read_cs("Streaming/AudioLoopback.cs")
    assert "lastDataTick" in source, (
        "サイレンスタイマーにlastDataTickガードがない。二重書き込みで音声が途切れる"
    )


def test_audio_dispose_suppresses_finalizer():
    """AudioLoopback.Dispose()でGC.SuppressFinalizeを呼ぶこと。

    NAudioのWasapiLoopbackCapture.Dispose()はUIスレッドでハング、
    他スレッドでネイティブクラッシュするため、ファイナライザも抑制が必要。
    """
    source = read_cs("Streaming/AudioLoopback.cs")
    dispose_match = re.search(
        r"public void Dispose\(\)(.*?)(?=\n    })", source, re.DOTALL
    )
    assert dispose_match, "Dispose() method not found"
    dispose_body = dispose_match.group(1)
    assert "SuppressFinalize" in dispose_body, (
        "Dispose()でGC.SuppressFinalizeを呼んでいない。GCファイナライザでクラッシュする"
    )


# === MainForm.cs: StopStreamingAsync ===


def test_stop_clears_callback_before_ffmpeg_null():
    """StopStreamingAsyncでOnFrameReady=nullを_ffmpeg=nullより先に実行すること。

    逆順だとキャプチャスレッドのコールバックがnull._ffmpegを参照して
    NullReferenceException→プロセスクラッシュする。
    """
    source = read_cs("MainForm.cs")
    stop_match = re.search(
        r"(public async Task StopStreamingAsync\(\).*?)(?=\n    public |\n    private )",
        source,
        re.DOTALL,
    )
    assert stop_match, "StopStreamingAsync() method not found"
    stop_body = stop_match.group(1)
    callback_null_pos = stop_body.find("OnFrameReady = null")
    ffmpeg_null_pos = stop_body.find("_ffmpeg = null")
    assert callback_null_pos != -1, "OnFrameReady = null が StopStreamingAsync に存在しない"
    assert ffmpeg_null_pos != -1, "_ffmpeg = null が StopStreamingAsync に存在しない"
    assert callback_null_pos < ffmpeg_null_pos, (
        "OnFrameReady=nullが_ffmpeg=nullより後にある。"
        "キャプチャコールバックがnull._ffmpegを参照してクラッシュする"
    )


def test_stop_clears_fields_before_cleanup():
    """StopStreamingAsyncでフィールドクリアをクリーンアップ処理より先に行うこと。

    _ffmpeg=nullを即座に設定しないと、OnTrayUpdateやOnFormClosingが
    配信中と誤判定し、UIが更新されない/×ボタンが効かない。
    """
    source = read_cs("MainForm.cs")
    stop_match = re.search(
        r"(public async Task StopStreamingAsync\(\).*?)(?=\n    public |\n    private )",
        source,
        re.DOTALL,
    )
    assert stop_match, "StopStreamingAsync() method not found"
    stop_body = stop_match.group(1)
    ffmpeg_null_pos = stop_body.find("_ffmpeg = null")
    stop_async_pos = stop_body.find("StopAsync()")
    assert ffmpeg_null_pos != -1, "_ffmpeg = null が存在しない"
    assert stop_async_pos != -1, "StopAsync() が存在しない"
    assert ffmpeg_null_pos < stop_async_pos, (
        "_ffmpeg=nullがStopAsync()より後にある。UI更新が最大9秒遅延する"
    )


# === FrameCapture.cs ===


def test_frame_capture_callback_null_safe():
    """FrameCaptureのOnFrameReady呼び出しがNullReferenceExceptionをcatchすること。"""
    source = read_cs("Capture/FrameCapture.cs")
    assert "catch (NullReferenceException)" in source, (
        "OnFrameReady呼び出しのNullReferenceExceptionがcatchされていない。"
        "配信停止中のコールバックでクラッシュする"
    )


def test_frame_capture_uses_local_callback():
    """FrameCaptureがOnFrameReadyをローカル変数にキャプチャしてからnullチェックすること。

    フィールド直接参照だとnullチェック後〜Invoke前に別スレッドで
    nullに設定されるレースコンディションが起きる。
    """
    source = read_cs("Capture/FrameCapture.cs")
    assert re.search(r"var callback = OnFrameReady", source), (
        "OnFrameReadyをローカル変数にキャプチャしていない。TOCTOU レースの原因"
    )


# === Program.cs ===


def test_unhandled_exception_handlers_registered():
    """Program.csで未処理例外ハンドラが登録されていること。"""
    source = read_cs("Program.cs")
    assert "UnhandledException" in source, (
        "AppDomain.UnhandledExceptionハンドラが未登録"
    )
    assert "ThreadException" in source, (
        "Application.ThreadExceptionハンドラが未登録"
    )
