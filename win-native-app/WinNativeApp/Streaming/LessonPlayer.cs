using System.Text.Json;
using Serilog;

namespace WinNativeApp.Streaming;

// =====================================================
// データクラス
// =====================================================

public class DialogueData
{
    public int Index { get; set; }
    public string Speaker { get; set; } = "teacher";
    public string AvatarId { get; set; } = "teacher";
    public string Content { get; set; } = "";
    public string TtsText { get; set; } = "";
    public string Emotion { get; set; } = "neutral";
    public string? Gesture { get; set; }
    public float[]? LipsyncFrames { get; set; }
    public double Duration { get; set; }
    public byte[]? WavData { get; set; }
}

public class QuestionData
{
    public double WaitSeconds { get; set; } = 8.0;
    public List<DialogueData> AnswerDialogues { get; set; } = new();
}

public class SectionData
{
    public int LessonId { get; set; }
    public int SectionIndex { get; set; }
    public int TotalSections { get; set; }
    public string SectionType { get; set; } = "dialogue";
    public string? DisplayText { get; set; }
    public JsonElement? DisplayProperties { get; set; }
    public List<DialogueData> Dialogues { get; set; } = new();
    public QuestionData? Question { get; set; }
    public double WaitSeconds { get; set; } = 2.0;
    public double PaceScale { get; set; } = 1.0;
}

// =====================================================
// LessonPlayer — セクションデータを受け取りdialogue順次再生
// =====================================================

/// <summary>
/// 授業セクションの再生エンジン。
/// MainFormからコールバック経由で音声再生・JS注入・WebSocket通知を行う。
/// Pythonサーバーなしで独立して再生を完了できる。
/// </summary>
public class LessonPlayer
{
    // コールバック（MainFormが設定）
    /// <summary>WAV音声を再生し、PlaybackStopped または duration ベースのフォールバックで Task が完了する。
    /// duration: 音声長さ（秒、フォールバックタイマーに使用）。ct: 停止時にフォールバックも止める</summary>
    public Func<byte[], float, double, CancellationToken, Task>? PlayAudio { get; set; }
    /// <summary>現在の音声再生を停止する</summary>
    public Action? StopAudio { get; set; }
    /// <summary>現在の音声再生を一時停止する</summary>
    public Action? PauseAudio { get; set; }
    /// <summary>一時停止した音声再生を再開する</summary>
    public Action? ResumeAudio { get; set; }
    /// <summary>WebView2にJavaScriptを注入する</summary>
    public Action<string>? InjectJs { get; set; }
    /// <summary>全WebSocketクライアントにPush通知を送信する</summary>
    public Func<object, Task>? BroadcastEvent { get; set; }
    /// <summary>コントロールパネルに授業進捗を通知する</summary>
    public Action<object>? NotifyPanel { get; set; }

    // 状態（全セクション一括）
    private List<SectionData>? _sections;
    private int _lessonId;
    private double _paceScale = 1.0;

    private volatile bool _playing;
    private volatile bool _paused;
    private CancellationTokenSource? _cts;
    private TaskCompletionSource? _resumeTcs;

    // ステータストラッキング
    private int _currentSectionIndex = -1;
    private int _currentDialogueIndex = -1;
    private int _totalDialogues;
    private string _state = "idle"; // idle, loaded, playing, paused
    private List<DialogueData>? _currentDialogues; // 現在再生中のダイアログ配列（main または answer）
    private string _currentKind = "main"; // 現在再生中の種別（"main" | "answer"）

    /// <summary>再生可能か（授業がロード済みかつ再生中でない）</summary>
    public bool CanPlay => _sections != null && !_playing;
    /// <summary>再生中か</summary>
    public bool IsPlaying => _playing;
    /// <summary>一時停止中か</summary>
    public bool IsPaused => _paused;

    // =====================================================
    // 公開メソッド
    // =====================================================

    /// <summary>全セクションを一括ロードする。再生中の場合は停止してからロードする。</summary>
    public void LoadLesson(JsonElement json)
    {
        if (_playing)
            Stop();

        _lessonId = json.TryGetProperty("lesson_id", out var lid) ? lid.GetInt32() : 0;
        _paceScale = json.TryGetProperty("pace_scale", out var ps) ? ps.GetDouble() : 1.0;
        var totalSections = json.TryGetProperty("total_sections", out var ts) ? ts.GetInt32() : 0;

        _sections = new List<SectionData>();

        if (json.TryGetProperty("sections", out var sectionsEl) && sectionsEl.ValueKind == JsonValueKind.Array)
        {
            foreach (var s in sectionsEl.EnumerateArray())
            {
                var section = ParseSectionData(s);
                // lesson_load のメタデータで上書き
                section.LessonId = _lessonId;
                section.PaceScale = _paceScale;
                section.TotalSections = totalSections;
                _sections.Add(section);
            }
        }

        _state = "loaded";
        _currentSectionIndex = -1;
        _currentDialogueIndex = -1;
        _currentKind = "main";

        var totalDialogues = _sections.Sum(s => s.Dialogues.Count);
        Log.Information("[Lesson] Lesson loaded: id={LessonId} sections={Count} totalDialogues={Dialogues} paceScale={Pace}",
            _lessonId, _sections.Count, totalDialogues, _paceScale);

        SendOutlineToPanel();
        SendPanelUpdate();
    }

    /// <summary>コントロールパネルに全セクションの軽量outlineを送信する（WAV/lipsync除く）。LoadLesson時に1回発火。</summary>
    private void SendOutlineToPanel()
    {
        if (_sections == null || NotifyPanel == null) return;

        NotifyPanel(new
        {
            type = "lesson_outline",
            lesson_id = _lessonId,
            total_sections = _sections.Count,
            sections = _sections.Select(s => new
            {
                section_index = s.SectionIndex,
                section_type = s.SectionType,
                display_text = s.DisplayText,
                dialogues = s.Dialogues.Select(d => new
                {
                    index = d.Index,
                    kind = "main",
                    speaker = d.Speaker,
                    content = d.Content,
                    tts_text = d.TtsText,
                    emotion = d.Emotion,
                }).ToArray(),
                question = s.Question == null ? null : (object)new
                {
                    answer_dialogues = s.Question.AnswerDialogues.Select(d => new
                    {
                        index = d.Index,
                        kind = "answer",
                        speaker = d.Speaker,
                        content = d.Content,
                        tts_text = d.TtsText,
                        emotion = d.Emotion,
                    }).ToArray(),
                },
            }).ToArray(),
        });
    }

    /// <summary>ロード済み授業の再生を開始する。完了またはキャンセルまでawaitする。</summary>
    public async Task PlayAsync()
    {
        if (_sections == null || _sections.Count == 0)
            throw new InvalidOperationException("No lesson loaded");
        if (_playing) throw new InvalidOperationException("Already playing");

        _playing = true;
        _paused = false;
        _state = "playing";
        _cts = new CancellationTokenSource();
        _currentSectionIndex = 0;
        string reason = "completed";

        try
        {
            for (int i = 0; i < _sections.Count; i++)
            {
                _cts.Token.ThrowIfCancellationRequested();
                await WaitIfPausedAsync(_cts.Token);
                _currentSectionIndex = i;
                _currentDialogueIndex = -1;

                Log.Information("[Lesson] Playing section {Index}/{Total}",
                    i + 1, _sections.Count);

                SendPanelUpdate();
                await PlaySectionInternalAsync(_sections[i], _cts.Token);
            }
        }
        catch (OperationCanceledException)
        {
            reason = "stopped";
            Log.Information("[Lesson] Lesson playback cancelled at section {Index}/{Total}",
                _currentSectionIndex + 1, _sections.Count);
        }
        catch (Exception ex)
        {
            reason = "error";
            Log.Error(ex, "[Lesson] Lesson playback error at section {Index}/{Total}",
                _currentSectionIndex + 1, _sections.Count);
        }
        finally
        {
            _playing = false;
            _state = "idle";
            _cts = null;

            // 授業全体の完了通知
            if (BroadcastEvent != null)
            {
                await BroadcastEvent(new
                {
                    type = "lesson_complete",
                    lesson_id = _lessonId,
                    sections_played = _currentSectionIndex + (reason == "completed" ? 1 : 0),
                    reason,
                });
            }

            var sectionsPlayed = _currentSectionIndex + (reason == "completed" ? 1 : 0);
            Log.Information("[Lesson] Lesson {Id} finished: reason={Reason} sections_played={Played}/{Total}",
                _lessonId, reason, sectionsPlayed, _sections?.Count ?? 0);

            _sections = null;
            _currentSectionIndex = -1;
            _currentDialogueIndex = -1;
            _currentDialogues = null;
            _currentKind = "main";

            SendPanelUpdate();
        }
    }

    /// <summary>再生を一時停止する。</summary>
    public void Pause()
    {
        if (!_playing || _paused) return;
        _paused = true;
        _state = "paused";
        PauseAudio?.Invoke();
        InjectJs?.Invoke("if(window.lesson)window.lesson.pause()");
        Log.Information("[Lesson] Paused at dialogue {Index}/{Total}",
            _currentDialogueIndex + 1, _totalDialogues);
        SendPanelUpdate();
    }

    /// <summary>一時停止を解除する。</summary>
    public void Resume()
    {
        if (!_playing || !_paused) return;
        _paused = false;
        _state = "playing";
        ResumeAudio?.Invoke();
        InjectJs?.Invoke("if(window.lesson)window.lesson.resume()");
        _resumeTcs?.TrySetResult();
        Log.Information("[Lesson] Resumed");
        SendPanelUpdate();
    }

    /// <summary>再生を停止する。</summary>
    public void Stop()
    {
        if (!_playing)
        {
            _state = "idle";
            _sections = null;
            _currentDialogues = null;
            SendPanelUpdate();
            return;
        }

        _state = "idle";
        _paused = false;
        _resumeTcs?.TrySetResult();  // pause待ちを解除
        try { _cts?.Cancel(); } catch (ObjectDisposedException) { }
        StopAudio?.Invoke();
        InjectJs?.Invoke("if(window.lesson)window.lesson.endDialogue()");
        InjectJs?.Invoke("if(window.lesson)window.lesson.hideText()");
        Log.Information("[Lesson] Stopped");
        // _playing は PlayAsync の finally で false に設定される
    }

    /// <summary>現在の再生状態を返す。</summary>
    public object GetStatus()
    {
        if (_sections != null)
        {
            return new
            {
                ok = true,
                state = _state,
                lesson_id = _lessonId,
                section_index = _currentSectionIndex,
                total_sections = _sections.Count,
                dialogue_index = _currentDialogueIndex,
                total_dialogues = _totalDialogues,
                remaining_duration = CalcRemainingDuration(),
            };
        }

        return new
        {
            ok = true,
            state = _state,
            lesson_id = 0,
            section_index = -1,
            dialogue_index = _currentDialogueIndex,
            total_dialogues = _totalDialogues,
        };
    }

    /// <summary>残り再生時間（秒）を概算する。</summary>
    private double CalcRemainingDuration()
    {
        if (_sections == null || _currentSectionIndex < 0) return 0;

        double remaining = 0;
        for (int i = _currentSectionIndex; i < _sections.Count; i++)
        {
            var sec = _sections[i];
            var dialogues = (i == _currentSectionIndex && _currentDialogueIndex >= 0)
                ? sec.Dialogues.Skip(_currentDialogueIndex)
                : sec.Dialogues;

            foreach (var dlg in dialogues)
                remaining += dlg.Duration;

            if (sec.Question != null)
            {
                remaining += sec.Question.WaitSeconds * sec.PaceScale;
                foreach (var dlg in sec.Question.AnswerDialogues)
                    remaining += dlg.Duration;
            }

            remaining += sec.WaitSeconds * sec.PaceScale;
        }

        return Math.Round(remaining, 1);
    }

    /// <summary>コントロールパネルに現在の授業進捗を送信する。</summary>
    private void SendPanelUpdate()
    {
        if (NotifyPanel == null) return;

        // 授業未ロード
        if (_sections == null || _sections.Count == 0)
        {
            NotifyPanel(new
            {
                type = "lesson",
                state = _state,
                lesson_id = 0,
                section_index = -1,
                total_sections = 0,
                section_type = (string?)null,
                dialogue_index = -1,
                total_dialogues = 0,
                kind = "main",
            });
            return;
        }

        var sectionIdx = Math.Max(0, Math.Min(_currentSectionIndex, _sections.Count - 1));
        var section = _sections[sectionIdx];
        var dialogues = _currentDialogues ?? section.Dialogues;

        NotifyPanel(new
        {
            type = "lesson",
            state = _state,
            lesson_id = _lessonId,
            section_index = _currentSectionIndex,
            total_sections = _sections.Count,
            section_type = section.SectionType,
            dialogue_index = _currentDialogueIndex,
            total_dialogues = dialogues.Count,
            kind = _currentKind,
        });
    }

    // =====================================================
    // 再生ロジック
    // =====================================================

    /// <summary>単一セクションの再生。PlayAsync から順次呼ばれる。</summary>
    private async Task PlaySectionInternalAsync(SectionData section, CancellationToken ct)
    {
        Log.Information("[Lesson] Playing section {Index}/{Total}: type={Type}, dialogues={Count}",
            section.SectionIndex + 1, section.TotalSections, section.SectionType, section.Dialogues.Count);

        // 教材テキスト表示
        if (!string.IsNullOrEmpty(section.DisplayText))
        {
            var textEscaped = JsonSerializer.Serialize(section.DisplayText);
            var propsJson = section.DisplayProperties.HasValue
                ? JsonSerializer.Serialize(section.DisplayProperties.Value)
                : "null";
            InjectJs?.Invoke($"if(window.lesson)window.lesson.showText({textEscaped},{propsJson})");
        }

        // メインdialogue再生
        await PlayDialoguesAsync(section.Dialogues, "main", ct);

        // questionセクション: 待機→回答再生
        if (section.SectionType == "question" && section.Question != null)
        {
            var waitMs = (int)(section.Question.WaitSeconds * section.PaceScale * 1000);
            Log.Information("[Lesson] Question wait: {Ms}ms", waitMs);
            await PauseAwareDelayAsync(waitMs, ct);

            await PlayDialoguesAsync(section.Question.AnswerDialogues, "answer", ct);
        }

        // 教材テキスト非表示
        InjectJs?.Invoke("if(window.lesson)window.lesson.hideText()");

        // セクション間の間
        if (section.WaitSeconds > 0)
        {
            var gapMs = (int)(section.WaitSeconds * section.PaceScale * 1000);
            await PauseAwareDelayAsync(gapMs, ct);
        }

        _currentDialogueIndex = -1;
        Log.Information("[Lesson] Section {Index} complete", section.SectionIndex);
    }

    private async Task PlayDialoguesAsync(List<DialogueData> dialogues, string kind, CancellationToken ct)
    {
        _totalDialogues = dialogues.Count;
        _currentDialogues = dialogues;
        _currentKind = kind;

        for (int i = 0; i < dialogues.Count; i++)
        {
            ct.ThrowIfCancellationRequested();
            await WaitIfPausedAsync(ct);

            _currentDialogueIndex = i;
            var dlg = dialogues[i];

            Log.Debug("[Lesson] Dialogue {I}/{Total}: speaker={Speaker} content=\"{Content}\"",
                i + 1, dialogues.Count, dlg.Speaker,
                dlg.Content.Length > 40 ? dlg.Content[..40] + "..." : dlg.Content);

            SendPanelUpdate();

            // broadcast.htmlに表示指示
            var dlgJson = JsonSerializer.Serialize(new
            {
                content = dlg.Content,
                speaker = dlg.Speaker,
                avatarId = dlg.AvatarId,
                emotion = dlg.Emotion,
                gesture = dlg.Gesture,
                lipsyncFrames = dlg.LipsyncFrames,
                duration = dlg.Duration,
            });
            InjectJs?.Invoke($"if(window.lesson)window.lesson.startDialogue({dlgJson})");

            // 音声再生 → PlaybackStopped待ち（または duration ベースのフォールバック）
            if (PlayAudio != null && dlg.WavData is { Length: > 0 })
            {
                await PlayAudio(dlg.WavData, 1.0f, dlg.Duration, ct);
            }
            else if (dlg.Duration > 0)
            {
                // 音声データなし — 表示時間だけ待つ
                await PauseAwareDelayAsync((int)(dlg.Duration * 1000), ct);
            }

            ct.ThrowIfCancellationRequested();

            // 表示終了
            InjectJs?.Invoke("if(window.lesson)window.lesson.endDialogue()");

            // dialogue間の間（300ms）
            if (i < dialogues.Count - 1)
            {
                await PauseAwareDelayAsync(300, ct);
            }
        }
    }

    // =====================================================
    // Pause / Delay ヘルパー
    // =====================================================

    private async Task WaitIfPausedAsync(CancellationToken ct)
    {
        while (_paused)
        {
            ct.ThrowIfCancellationRequested();
            _resumeTcs = new TaskCompletionSource();
            using var reg = ct.Register(() => _resumeTcs.TrySetCanceled());
            try
            {
                await _resumeTcs.Task;
            }
            catch (TaskCanceledException)
            {
                ct.ThrowIfCancellationRequested();
            }
        }
    }

    private async Task PauseAwareDelayAsync(int totalMs, CancellationToken ct)
    {
        const int step = 100;
        var remaining = totalMs;
        while (remaining > 0)
        {
            ct.ThrowIfCancellationRequested();
            await WaitIfPausedAsync(ct);
            var wait = Math.Min(remaining, step);
            await Task.Delay(wait, ct);
            remaining -= wait;
        }
    }

    // =====================================================
    // JSONパース
    // =====================================================

    private static SectionData ParseSectionData(JsonElement json)
    {
        var section = new SectionData
        {
            LessonId = json.TryGetProperty("lesson_id", out var lid) ? lid.GetInt32() : 0,
            SectionIndex = json.TryGetProperty("section_index", out var si) ? si.GetInt32() : 0,
            TotalSections = json.TryGetProperty("total_sections", out var ts) ? ts.GetInt32() : 0,
            SectionType = json.TryGetProperty("section_type", out var st) ? st.GetString() ?? "dialogue" : "dialogue",
            DisplayText = json.TryGetProperty("display_text", out var dt) ? dt.GetString() : null,
            WaitSeconds = json.TryGetProperty("wait_seconds", out var ws) ? ws.GetDouble() : 2.0,
            PaceScale = json.TryGetProperty("pace_scale", out var ps) ? ps.GetDouble() : 1.0,
        };

        if (json.TryGetProperty("display_properties", out var dp) && dp.ValueKind != JsonValueKind.Null)
            section.DisplayProperties = dp.Clone();

        if (json.TryGetProperty("dialogues", out var dialoguesEl) && dialoguesEl.ValueKind == JsonValueKind.Array)
        {
            foreach (var d in dialoguesEl.EnumerateArray())
                section.Dialogues.Add(ParseDialogue(d));
        }

        if (json.TryGetProperty("question", out var q) && q.ValueKind != JsonValueKind.Null)
        {
            section.Question = new QuestionData
            {
                WaitSeconds = q.TryGetProperty("wait_seconds", out var qws) ? qws.GetDouble() : 8.0,
            };
            if (q.TryGetProperty("answer_dialogues", out var ad) && ad.ValueKind == JsonValueKind.Array)
            {
                foreach (var d in ad.EnumerateArray())
                    section.Question.AnswerDialogues.Add(ParseDialogue(d));
            }
        }

        return section;
    }

    private static DialogueData ParseDialogue(JsonElement d)
    {
        byte[]? wavData = null;
        if (d.TryGetProperty("wav_b64", out var wb) && wb.ValueKind == JsonValueKind.String)
        {
            var b64 = wb.GetString();
            if (!string.IsNullOrEmpty(b64))
                wavData = Convert.FromBase64String(b64);
        }

        float[]? lipsyncFrames = null;
        if (d.TryGetProperty("lipsync_frames", out var lf) && lf.ValueKind == JsonValueKind.Array)
        {
            var frames = new List<float>();
            foreach (var f in lf.EnumerateArray())
                frames.Add((float)f.GetDouble());
            lipsyncFrames = frames.ToArray();
        }

        return new DialogueData
        {
            Index = d.TryGetProperty("index", out var idx) ? idx.GetInt32() : 0,
            Speaker = d.TryGetProperty("speaker", out var sp) ? sp.GetString() ?? "teacher" : "teacher",
            AvatarId = d.TryGetProperty("avatar_id", out var ai) ? ai.GetString() ?? "teacher" : "teacher",
            Content = d.TryGetProperty("content", out var c) ? c.GetString() ?? "" : "",
            TtsText = d.TryGetProperty("tts_text", out var tt) ? tt.GetString() ?? "" : "",
            Emotion = d.TryGetProperty("emotion", out var em) ? em.GetString() ?? "neutral" : "neutral",
            Gesture = d.TryGetProperty("gesture", out var g) && g.ValueKind == JsonValueKind.String ? g.GetString() : null,
            LipsyncFrames = lipsyncFrames,
            Duration = d.TryGetProperty("duration", out var dur) ? dur.GetDouble() : 0,
            WavData = wavData,
        };
    }
}
