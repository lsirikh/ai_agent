using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Primitives;
using Avalonia.Headless;
using Avalonia.Headless.XUnit;
using Avalonia.Media;
using Avalonia.Styling;
using Avalonia.Threading;
using Avalonia.VisualTree;

namespace EdgeVoice.Agent.Desktop.Tests;

/// <summary>[헤드리스] 페이지별 점검: 설정 콤보박스 = 실행 값, 로그 기본 필터·열 폭, 지식 조각 수, 빈 상태, 대비.</summary>
public class PageConsistencyScenarioTests
{
    // 실행 값(current)과 저장값(saved)이 다른 실제 스택 응답 모양
    private const string RuntimeOptions = """
        {"tts_engines":[{"id":"melo","display_name":"MeloTTS Korean","recommended_for":"한국어"},{"id":"kokoro","display_name":"Kokoro TTS","recommended_for":"영어"}],
         "tts_voices":{"melo":["KR"],"kokoro":["af_heart","af_bella"]},
         "stt_models":[{"id":"small","display_name":"Small","vram_gb":2,"korean_quality":"중간"},{"id":"medium","display_name":"Medium","vram_gb":5,"korean_quality":"좋음"}],
         "llm_models":[{"id":"qwen2.5-7b-instruct-awq","display_name":"Qwen 2.5 7B AWQ","vram_gb":5}],
         "current":{"tts_engine":"melo","tts_voice":"KR","stt_model":"small","llm_model":"qwen2.5-7b-instruct-awq","wake_word_threshold":0.3},
         "saved":{"tts_engine":"melo","tts_voice":"KR","stt_model":"medium","llm_model":"qwen2.5-7b-instruct-awq","wake_word_threshold":0.5},
         "pending_restart":["stt_model","wake_word_threshold"]}
        """;

    private static void Open(Window w, string header)
    {
        var nav = w.FindControl<TabControl>("Nav")!;
        nav.SelectedItem = nav.Items.Cast<TabItem>().Single(t => (string)t.Header! == header);
        Dispatcher.UIThread.RunJobs();
    }

    private static string? Shown(ComboBox combo) => combo.SelectedItem switch
    {
        ViewModels.OptionItem o => o.Label,
        var other => other?.ToString(),
    };

    [AvaloniaFact]
    public async Task 설정_콤보박스는_실행_값을_보여주고_빈_콤보박스가_없다()
    {
        using var s = new Scenario(setup: b => b.Json["/api/settings/options"] = RuntimeOptions);
        var w = s.Show();
        var settings = s.Main.Settings;
        await Scenario.WaitUntil(() => settings.SttModel == "small" && settings.ContextWindowSize == 10);
        Open(w, "Settings");

        Assert.Equal("Small (2GB VRAM, 중간)", Shown(w.FindControl<ComboBox>("SttModelCombo")!));
        Assert.Equal("Qwen 2.5 7B AWQ (5GB VRAM)", Shown(w.FindControl<ComboBox>("LlmModelCombo")!));
        Assert.Equal("MeloTTS Korean (한국어)", Shown(w.FindControl<ComboBox>("TtsEngineCombo")!));
        Assert.Equal("KR", Shown(w.FindControl<ComboBox>("TtsVoiceCombo")!));
        Assert.Equal(0.3, settings.WakeWordThreshold);
        Assert.Equal("English", Shown(w.FindControl<ComboBox>("LanguageCombo")!));

        var page = (Control)w.FindControl<TabControl>("Nav")!.SelectedContent!;
        Assert.All(page.GetVisualDescendants().OfType<ComboBox>(), c => Assert.NotNull(c.SelectedItem));

        // 저장값과 실행값이 다르면 "다시 시작 후 적용" 배지
        Assert.True(w.FindControl<Border>("PendingBadge")!.IsVisible);
        Assert.Contains("음성 인식 모델(저장 medium · 실행 small)", settings.PendingRestart);
    }

    [AvaloniaFact]
    public async Task melo_음성은_KR_뿐이고_엔진을_바꾸면_목록과_기본값이_바뀐다()
    {
        using var s = new Scenario(setup: b => b.Json["/api/settings/options"] = RuntimeOptions);
        var w = s.Show();
        var settings = s.Main.Settings;
        await Scenario.WaitUntil(() => settings.TtsEngine == "melo");
        Open(w, "Settings");

        Assert.Equal(new[] { "KR" }, settings.TtsVoices);

        settings.TtsEngine = "kokoro";
        Dispatcher.UIThread.RunJobs();

        Assert.Equal(new[] { "af_heart", "af_bella" }, settings.TtsVoices);
        Assert.Equal("af_heart", settings.TtsVoice);
        Assert.Equal("af_heart", Shown(w.FindControl<ComboBox>("TtsVoiceCombo")!));
    }

    [AvaloniaFact]
    public async Task 실행_중인_모델이_목록에_없어도_콤보박스가_비지_않는다()
    {
        using var s = new Scenario(setup: b => b.Json["/api/settings/options"] = RuntimeOptions.Replace(
            "\"llm_model\":\"qwen2.5-7b-instruct-awq\",\"wake_word_threshold\":0.3", "\"llm_model\":\"Org/Other-Model\",\"wake_word_threshold\":0.3"));
        s.Show();
        var settings = s.Main.Settings;
        await Scenario.WaitUntil(() => settings.LlmModel == "Org/Other-Model");

        Assert.Contains(settings.LlmModels, o => o.Id == "Org/Other-Model" && o.Label == "Org/Other-Model (실행 중)");
    }

    [AvaloniaFact]
    public async Task 로그_기본_필터는_전체와_INFO_이상이고_레벨_필터가_쿼리에_반영된다()
    {
        using var s = new Scenario();
        var w = s.Show();
        var logs = s.Main.Logs;
        await Scenario.WaitUntil(() => logs.Logs.Count == 1);
        Open(w, "Logs");

        Assert.Equal("전체 서비스", Shown(w.FindControl<ComboBox>("LogServiceCombo")!));
        Assert.Equal("INFO 이상", Shown(w.FindControl<ComboBox>("LogLevelCombo")!));
        Assert.Contains(s.Backend.Queries, q => q.StartsWith("/api/logs?") && q.Contains("min_level=INFO"));

        logs.LevelFilter = "ERROR";
        await Scenario.WaitUntil(() => s.Backend.Queries.Any(q => q.StartsWith("/api/logs?") && q.Contains("level=ERROR")));
        logs.LevelFilter = "";
        await Scenario.WaitUntil(() => s.Backend.Queries.Count(q => q == "/api/logs?limit=100") == 1);
    }

    [AvaloniaFact]
    public async Task 로그_열_머리글과_시간이_잘리지_않는다()
    {
        using var s = new Scenario(setup: b => b.Json["/api/logs"] = """
            {"logs":[{"created_at":"2026-10-17T01:00:31.123","level":"WARNING","service":"audio_gateway","stage":"wake_word_detected","message":"m","duration_ms":12345}]}
            """);
        var w = s.Show();
        await Scenario.WaitUntil(() => s.Main.Logs.Logs.Count == 1);
        Open(w, "Logs");
        await Scenario.Settle(200);
        var grid = w.FindControl<DataGrid>("LogGrid")!;

        Assert.Equal("01:00:31.123", s.Main.Logs.Logs[0].Time);
        var cells = grid.GetVisualDescendants().OfType<Control>()
            .Where(c => c is DataGridColumnHeader || c.GetType().Name == "DataGridCell").ToList();
        Assert.NotEmpty(cells);
        foreach (var cell in cells)
        {
            foreach (var text in cell.GetVisualDescendants().OfType<TextBlock>().Where(t => !string.IsNullOrEmpty(t.Text) && t.IsEffectivelyVisible))
            {
                var x = text.TranslatePoint(default, cell)!.Value.X;
                text.Measure(Size.Infinity);
                Assert.True(x + text.DesiredSize.Width <= cell.Bounds.Width + 0.5,
                    $"'{text.Text}' 가 잘립니다 (필요 {x + text.DesiredSize.Width:0}, 폭 {cell.Bounds.Width:0})");
            }
        }
    }

    [AvaloniaFact]
    public async Task 지식_목록은_doc_id_와_조각_수를_쓴다()
    {
        using var s = new Scenario(setup: b => b.Json["/api/knowledge/documents"] =
            """{"documents":[{"doc_id":"a9b8","filename":"GOP.md","chunk_count":1826,"uploaded_at":"2026-10-17T01:00:00+00:00"}],"total":1}""");
        s.Show();
        var knowledge = s.Main.Knowledge;
        await Scenario.WaitUntil(() => knowledge.Documents.Count == 1);

        Assert.Equal("a9b8", knowledge.Documents[0].Id);
        Assert.StartsWith("1826 chunks | 2026-10-17", knowledge.Documents[0].Meta);
    }

    [AvaloniaFact]
    public async Task 비어_있는_페이지는_안내_문구를_보여준다()
    {
        using var s = new Scenario(setup: b =>
        {
            b.Json["/api/knowledge/documents"] = """{"documents":[]}""";
            b.Json["/api/history"] = """{"messages":[]}""";
            b.Json["/api/logs"] = """{"logs":[]}""";
        });
        var w = s.Show();
        await Scenario.WaitUntil(() => s.Main.History.Status.Length > 0 && s.Main.Knowledge.Status.Length > 0);

        foreach (var (page, name, text) in new[]
                 {
                     ("Chat", "ChatEmpty", "Hey Jarvis 라고 부르거나 메시지를 입력하세요"),
                     ("Knowledge", "KnowledgeEmpty", "등록된 문서가 없습니다"),
                     ("History", "HistoryEmpty", "아직 대화 기록이 없습니다"),
                     ("Logs", "LogsEmpty", "표시할 로그가 없습니다"),
                 })
        {
            Open(w, page);
            var empty = w.FindControl<TextBlock>(name)!;
            Assert.True(empty.IsEffectivelyVisible, $"{page} 빈 상태 문구가 보이지 않습니다");
            Assert.StartsWith(text, empty.Text);
        }
    }

    private static double Luminance(Color c)
    {
        static double Channel(byte v)
        {
            var x = v / 255.0;
            return x <= 0.03928 ? x / 12.92 : Math.Pow((x + 0.055) / 1.055, 2.4);
        }

        return 0.2126 * Channel(c.R) + 0.7152 * Channel(c.G) + 0.0722 * Channel(c.B);
    }

    [AvaloniaTheory]
    [InlineData("Light")]
    [InlineData("Dark")]
    public void 디자인_토큰의_글자_대비가_4_5_대_1_이상이다(string theme)
    {
        var variant = theme == "Light" ? ThemeVariant.Light : ThemeVariant.Dark;
        Color Get(string key)
        {
            Assert.True(Application.Current!.TryGetResource(key, variant, out var value), key);
            return ((ISolidColorBrush)value!).Color;
        }

        foreach (var (fg, bg) in new[]
                 {
                     ("OfficeSubtleTextBrush", "OfficeCardBrush"), ("OfficeSubtleTextBrush", "OfficeCanvasBrush"),
                     ("OfficeAccentTextBrush", "OfficeCardBrush"), ("OfficeAccentTextBrush", "OfficeSelectedBrush"),
                     ("OfficeErrorTextBrush", "OfficeCardBrush"), ("OfficeWarningTextBrush", "OfficeCardBrush"),
                     ("OfficeWarningTextBrush", "OfficeWarningBackgroundBrush"), ("OfficeHeaderForegroundBrush", "OfficeHeaderBrush"),
                 })
        {
            var (a, b) = (Luminance(Get(fg)), Luminance(Get(bg)));
            var ratio = (Math.Max(a, b) + 0.05) / (Math.Min(a, b) + 0.05);
            Assert.True(ratio >= 4.5, $"{theme}: {fg} / {bg} 대비 {ratio:0.00}");
        }
    }

    /// <summary>모든 페이지를 라이트·다크로 렌더링해 PNG 로 남긴다 (bin/.../screenshots, 눈으로 확인용).</summary>
    [AvaloniaFact]
    public async Task 모든_페이지를_라이트_다크로_렌더링해_저장한다()
    {
        using var s = new Scenario(setup: b => b.Json["/api/settings/options"] = RuntimeOptions);
        var w = s.Show();
        await Scenario.WaitUntil(() => s.Main.Settings.SttModel == "small" && s.Main.Logs.Logs.Count == 1);
        var dir = Directory.CreateDirectory(Path.Combine(AppContext.BaseDirectory, "screenshots")).FullName;

        foreach (var dark in new[] { false, true })
        {
            s.Main.IsDarkTheme = dark;
            foreach (var page in new[] { "Dashboard", "Chat", "Knowledge", "Settings", "History", "Logs" })
            {
                Open(w, page);
                await Scenario.Settle(150);
                var file = Path.Combine(dir, $"page-{page.ToLowerInvariant()}-{(dark ? "dark" : "light")}.png");
                w.CaptureRenderedFrame()!.Save(file);
                Assert.True(new FileInfo(file).Length > 5_000, file);
            }
        }
    }
}
