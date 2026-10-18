using System.Text.Json.Nodes;
using Avalonia.Controls;
using Avalonia.Headless.XUnit;
using Avalonia.Threading;
using Avalonia.VisualTree;
using Xunit;

namespace EdgeVoice.Agent.Desktop.Tests;

/// <summary>
/// 설정 탭 저장 막대: 바뀐 항목 수 · [저장] [되돌리기] · 항목별 반영 안내 · 다시 시작 안내와 확인 (사용자 요청 2026-10-18).
/// </summary>
public class SettingsSaveScenarioTests
{
    private const string Options = """
        {"tts_engines":[{"id":"melo","display_name":"MeloTTS","recommended_for":"ko"}],
         "tts_voices":{"melo":["KR"]},
         "stt_models":[{"id":"small","display_name":"Small","vram_gb":2,"korean_quality":"중간"}],
         "llm_models":[{"id":"qwen","display_name":"Qwen","vram_gb":8},{"id":"phi","display_name":"Phi","vram_gb":4}],
         "current":{"tts_engine":"melo","tts_voice":"KR","stt_model":"small","llm_model":"qwen"},
         "saved":{"tts_engine":"melo","tts_voice":"KR","stt_model":"small","llm_model":"qwen"},
         "runtime":{"tts_engine":"melo","tts_voice":"KR","stt_model":"small","llm_model":"qwen"},
         "pending_restart":[]}
        """;

    private const string Mcp = """
        {"servers":[{"name":"browser","url":"http://host.docker.internal:8931/mcp","command":null,"args":[],"env":null,
          "allowed_tools":["browser_navigate"],"trusted":true,"always_confirm":[],"no_confirm":[],"timeout":60,"enabled":true,
          "status":"connected","error":"","tools":["browser_navigate"]}]}
        """;

    private static Scenario Open(Action<FakeBackend>? setup = null) => new(setup: b =>
    {
        b.Json["/api/settings/options"] = Options;
        b.Json["/api/settings/mcp"] = Mcp;
        b.Json["/api/settings/mcp/browser"] = Mcp;
        b.Json["/api/settings/apply"] = """{"applied":{"llm":true},"restart_required":["llm"],"errors":{},"message":"저장"}""";
        setup?.Invoke(b);
    });

    private static async Task Loaded(Scenario s)
        => await Scenario.WaitUntil(() => s.Main.Settings.LlmModel == "qwen" && s.Main.Settings.ContextWindowSize == 10
                                          && s.Main.Settings.McpServers.Count == 1);

    private static JsonNode Body(FakeBackend backend, string request)
        => JsonNode.Parse(backend.Requests.Last(r => r.Request == request).Body)!;

    [AvaloniaFact]
    public async Task 열면_저장된_값이_보이고_바뀐_항목은_없다()
    {
        using var s = Open();
        await Loaded(s);
        var settings = s.Main.Settings;

        Assert.Equal("alexa", settings.WakeWord);
        Assert.Equal(1.5, settings.VoiceSpeed);
        Assert.False(settings.ContextEnabled);
        Assert.True(settings.McpServers[0].Enabled);
        Assert.False(settings.HasChanges);
        Assert.Equal(0, settings.ChangeCount);
    }

    [AvaloniaFact]
    public async Task 여러_카드를_바꾸면_바뀐_수가_보이고_저장_한_번에_모두_보낸다()
    {
        using var s = Open();
        await Loaded(s);
        var settings = s.Main.Settings;

        settings.VoiceSpeed = 1.2;
        settings.ContextWindowSize = 30;
        settings.Location = "제주";
        settings.McpServers[0].Enabled = false;

        Assert.Equal(4, settings.ChangeCount);
        Assert.Contains("저장하지 않은 변경 4개", settings.ChangeSummary);
        // 체크박스도 저장 막대로 모은다 (바로 보내지 않는다)
        Assert.DoesNotContain(s.Backend.Requests, r => r.Request.StartsWith("PUT"));

        settings.SaveCommand.Execute();
        await Scenario.WaitUntil(() => settings.SaveResult.Contains("MCP 서버"));
        Assert.False(settings.HasChanges);

        Assert.Equal(1.2, Body(s.Backend, "PUT /api/settings/general")["voice_speed"]!.GetValue<double>());
        Assert.Equal(30, Body(s.Backend, "PUT /api/settings/llm/context")["context_window_size"]!.GetValue<int>());
        Assert.Equal("제주", Body(s.Backend, "PUT /api/settings/tools")["location"]!.ToString());
        Assert.False(Body(s.Backend, "PUT /api/settings/mcp/browser")["enabled"]!.GetValue<bool>());
        // 모델은 바꾸지 않았으니 apply 는 보내지 않는다
        Assert.DoesNotContain(s.Backend.Requests, r => r.Request == "POST /api/settings/apply");

        Assert.Contains("말하기 속도: 바로 반영됨", settings.SaveResult);
        Assert.Contains("기억할 메시지 수: 다음 질문부터", settings.SaveResult);
        Assert.Contains("날씨 기준 지역: 다음 질문부터", settings.SaveResult);
        Assert.Contains("MCP 서버 'browser': 다음 질문부터", settings.SaveResult);
        Assert.False(settings.HasRestartPrompt);
    }

    [AvaloniaFact]
    public async Task 되돌리기는_저장된_값으로_돌린다()
    {
        using var s = Open();
        await Loaded(s);
        var settings = s.Main.Settings;

        settings.VoiceSpeed = 1.9;
        settings.WakeWord = "hey_mycroft";
        settings.McpServers[0].Enabled = false;
        settings.RevertCommand.Execute();

        Assert.Equal(1.5, settings.VoiceSpeed);
        Assert.Equal("alexa", settings.WakeWord);
        Assert.True(settings.McpServers[0].Enabled);
        Assert.False(settings.HasChanges);
        Assert.DoesNotContain(s.Backend.Requests, r => r.Request.StartsWith("PUT"));
    }

    [AvaloniaFact]
    public async Task 서비스가_응답하지_않은_일반_설정은_다시_시작될_때_반영된다고_알린다()
    {
        using var s = Open(b => b.Json["/api/settings/general"] = """
            {"wake_word":"alexa","language":"en","voice_speed":1.5,"wake_word_threshold":0.6,"end_pause_seconds":2,"listening_timeout_seconds":20,
             "propagation_results":{"tts":{"success":false,"error":"Connection failed"},"wake_word":{"success":true}}}
            """);
        await Loaded(s);
        var settings = s.Main.Settings;

        settings.VoiceSpeed = 1.2;
        settings.WakeWordThreshold = 0.4;
        settings.SaveCommand.Execute();
        await Scenario.WaitUntil(() => settings.SaveResult.Contains("말하기 속도:"));

        Assert.Contains("말하기 속도: 저장됨 (서비스가 응답하지 않음 — 다시 시작되면 반영)", settings.SaveResult);
        Assert.Contains("호출어 민감도: 바로 반영됨", settings.SaveResult);
    }

    [AvaloniaFact]
    public async Task LLM_모델은_다시_시작_안내를_보이고_확인하면_다시_시작해_반영됨을_보인다()
    {
        using var s = Open();
        await Loaded(s);
        var settings = s.Main.Settings;

        settings.LlmModel = "phi";
        settings.SaveCommand.Execute();
        await Scenario.WaitUntil(() => settings.HasRestartPrompt);

        var apply = Body(s.Backend, "POST /api/settings/apply")["changes"]!.AsObject();
        Assert.Equal(new[] { "llm" }, apply.Select(p => p.Key));
        Assert.Equal("phi", apply["llm"]!["model"]!.ToString());
        Assert.Contains("언어 모델: 다시 시작해야 반영됨", settings.SaveResult);
        Assert.Contains("언어 모델(LLM)을(를) 다시 시작합니다(약 90초)", settings.RestartPrompt);
        Assert.DoesNotContain(s.Backend.Requests, r => r.Request.EndsWith("/restart"));
        Assert.False(settings.HasChanges);

        // 다시 만든 뒤 vLLM 이 새 모델로 응답한다
        s.Backend.Json["/api/settings/options"] = Options.Replace("\"llm_model\":\"qwen\"", "\"llm_model\":\"phi\"");
        settings.RestartCommand.Execute();
        await Scenario.WaitUntil(() => settings.SaveResult.Contains("다시 시작 완료 — 반영됨"));

        Assert.Contains(s.Backend.Requests, r => r.Request == "POST /api/services/llm/restart");
        Assert.Contains("언어 모델(LLM)", settings.SaveResult);
        Assert.False(settings.HasRestartPrompt);
        Assert.Equal("phi", settings.LlmModel);
    }

    [AvaloniaFact]
    public async Task 나중에를_누르면_다시_시작하지_않는다()
    {
        using var s = Open();
        await Loaded(s);
        var settings = s.Main.Settings;

        settings.LlmModel = "phi";
        settings.SaveCommand.Execute();
        await Scenario.WaitUntil(() => settings.HasRestartPrompt);
        settings.LaterCommand.Execute();

        Assert.False(settings.HasRestartPrompt);
        Assert.DoesNotContain(s.Backend.Requests, r => r.Request.EndsWith("/restart"));
    }

    [AvaloniaFact]
    public async Task 백엔드가_다시_만들지_못하면_이_PC_에서_다시_만든다()
    {
        using var s = Open(b =>
        {
            b.Json["/api/services/llm/restart"] = """{"service":"llm","status":"failed","message":"docker 가 없습니다. 호스트에서 직접 실행하세요: docker compose up -d llm"}""";
            b.StatusCodes["/api/services/llm/restart"] = 503;
        });
        await Loaded(s);
        var settings = s.Main.Settings;
        var host = new List<string>();
        settings.HostRestart = service =>
        {
            host.Add(service);
            return Task.FromResult<string?>(null);
        };

        settings.LlmModel = "phi";
        settings.SaveCommand.Execute();
        await Scenario.WaitUntil(() => settings.HasRestartPrompt);
        s.Backend.Json["/api/settings/options"] = Options.Replace("\"llm_model\":\"qwen\"", "\"llm_model\":\"phi\"");
        settings.RestartCommand.Execute();
        await Scenario.WaitUntil(() => settings.SaveResult.Contains("다시 시작 완료 — 반영됨"));

        Assert.Equal(new[] { "llm" }, host);
    }

    [AvaloniaFact]
    public async Task 다시_만들지_못하면_실패와_직접_실행할_명령을_보인다()
    {
        using var s = Open(b =>
        {
            b.Json["/api/services/llm/restart"] = """{"service":"llm","status":"failed","message":"docker 가 없습니다. 호스트에서 직접 실행하세요: docker compose up -d llm"}""";
            b.StatusCodes["/api/services/llm/restart"] = 503;
        });
        await Loaded(s);
        var settings = s.Main.Settings;
        settings.HostRestart = _ => Task.FromResult<string?>("이 PC 의 docker 에서 백엔드 컨테이너를 찾지 못했습니다");

        settings.LlmModel = "phi";
        settings.SaveCommand.Execute();
        await Scenario.WaitUntil(() => settings.HasRestartPrompt);
        settings.RestartCommand.Execute();
        await Scenario.WaitUntil(() => settings.SaveResult.Contains("다시 시작하지 못했습니다"));

        Assert.Contains("503", settings.SaveResult);
        Assert.Contains("docker compose up -d llm", settings.SaveResult);
        Assert.Contains("백엔드 컨테이너를 찾지 못했습니다", settings.SaveResult);
    }

    [AvaloniaFact]
    public async Task 설정_탭_아래에_저장_막대가_늘_보이고_카드별_저장_버튼은_없다()
    {
        using var s = Open();
        var w = s.Show();
        var nav = w.FindControl<TabControl>("Nav")!;
        nav.SelectedItem = nav.Items.Cast<TabItem>().Single(t => (string)t.Header! == "Settings");
        await Loaded(s);
        Dispatcher.UIThread.RunJobs();

        var page = (Control)nav.SelectedContent!;
        var bar = page.GetVisualDescendants().OfType<Border>().Single(b => b.Name == "SaveBar");
        Assert.True(bar.IsVisible);
        var save = bar.GetVisualDescendants().OfType<Button>().Single(b => b.Name == "SaveButton");
        Assert.False(save.IsEffectivelyEnabled);

        s.Main.Settings.VoiceSpeed = 1.2;
        Dispatcher.UIThread.RunJobs();
        Assert.True(save.IsEffectivelyEnabled);
        Assert.Contains(bar.GetVisualDescendants().OfType<TextBlock>(), t => t.Text?.Contains("저장하지 않은 변경 1개") == true);

        // 저장은 저장 막대 한 곳에서만
        var buttons = page.GetVisualDescendants().OfType<Button>().Select(b => b.Content as string).ToList();
        Assert.Single(buttons, c => c?.Contains("저장") == true);
        Assert.DoesNotContain("모델 적용", buttons);
        Assert.DoesNotContain("LLM 다시 만들기", buttons);
    }
}
