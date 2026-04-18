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


# === LessonPlayer.cs ===


def test_dialogue_data_has_tts_text():
    """DialogueDataにTtsTextプロパティが存在し、ParseDialogueで読み込まれること。

    授業のアウトラインにTTSテキストを含めてUI表示するために必要。
    """
    source = read_cs("Streaming/LessonPlayer.cs")
    assert re.search(r"public string TtsText \{ get; set; \}", source), (
        "DialogueDataにTtsTextプロパティが存在しない"
    )
    assert re.search(r'TtsText = d\.TryGetProperty\("tts_text"', source), (
        "ParseDialogueでtts_textがTtsTextに読み込まれていない"
    )
    assert re.search(r"tts_text = d\.TtsText", source), (
        "SendOutlineToPanelのdialogue/answer_dialoguesでtts_textが送信されていない"
    )


# === Lesson control buttons (control-panel.html + MainForm.cs) ===


def test_control_panel_has_lesson_control_buttons():
    """control-panel.html の Lesson タブに再生/一時停止/停止ボタンが存在すること。"""
    path = NATIVE_APP_DIR / "control-panel.html"
    html = path.read_text(encoding="utf-8")
    assert 'id="lessonPlayBtn"' in html, "lessonPlayBtn (▶再生) が存在しない"
    assert 'id="lessonPauseBtn"' in html, "lessonPauseBtn (⏸一時停止) が存在しない"
    assert 'id="lessonStopBtn"' in html, "lessonStopBtn (■停止) が存在しない"
    # 初期状態で全ボタン disabled
    for btn_id in ("lessonPlayBtn", "lessonPauseBtn", "lessonStopBtn"):
        assert re.search(
            rf'id="{btn_id}"[^>]*\bdisabled\b', html
        ), f"{btn_id} が初期 disabled になっていない"
    # state に応じたボタン更新関数
    assert "_updateLessonButtons" in html, (
        "_updateLessonButtons がない — state 遷移でボタンが更新されない"
    )


def test_control_panel_sends_lesson_actions():
    """control-panel.html が lesson_play/pause/stop アクションを C# に送信すること。"""
    html = (NATIVE_APP_DIR / "control-panel.html").read_text(encoding="utf-8")
    assert "action:'lesson_play'" in html, "lesson_play 送信が欠落"
    assert "action:'lesson_pause'" in html, "lesson_pause 送信が欠落"
    assert "action:'lesson_stop'" in html, "lesson_stop 送信が欠落"


def test_mainform_handles_panel_lesson_actions():
    """MainForm.OnPanelMessage が lesson_play/pause/stop を分岐処理すること。"""
    source = read_cs("MainForm.cs")
    assert 'case "lesson_play":' in source, "lesson_play 分岐が MainForm に存在しない"
    assert 'case "lesson_pause":' in source, "lesson_pause 分岐が MainForm に存在しない"
    assert 'case "lesson_stop":' in source, "lesson_stop 分岐が MainForm に存在しない"
    assert "HandlePanelLessonPlay" in source, "HandlePanelLessonPlay メソッドが存在しない"
    assert "HandlePanelLessonPause" in source, "HandlePanelLessonPause メソッドが存在しない"
    assert "HandlePanelLessonStop" in source, "HandlePanelLessonStop メソッドが存在しない"


def test_lesson_player_exposes_is_paused():
    """LessonPlayer に IsPaused プロパティがあり、MainForm から再開判定に使えること。"""
    source = read_cs("Streaming/LessonPlayer.cs")
    assert re.search(r"public bool IsPaused", source), (
        "LessonPlayer.IsPaused が存在しない — MainForm が再生/再開を判別できない"
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
