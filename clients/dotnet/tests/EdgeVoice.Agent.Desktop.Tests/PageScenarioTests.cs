using Avalonia.Controls;
using Avalonia.Headless;
using Avalonia.Headless.XUnit;
using Avalonia.Input;
using Avalonia.Threading;

namespace EdgeVoice.Agent.Desktop.Tests;

/// <summary>[헤드리스] 내비게이션과 각 페이지(채팅·지식·설정·히스토리·로그) 시나리오.</summary>
public class PageScenarioTests
{
    [AvaloniaFact]
    public void 왼쪽_탐색에_웹의_6개_페이지가_모두_있고_각각_열린다()
    {
        using var s = new Scenario();
        var w = s.Show();
        var nav = w.FindControl<TabControl>("Nav")!;

        var headers = nav.Items.Cast<TabItem>().Select(t => t.Header).ToArray();
        Assert.Equal(new object[] { "Dashboard", "Chat", "Knowledge", "Settings", "History", "Logs" }, headers);
        Assert.Equal(Avalonia.Controls.Dock.Left, nav.TabStripPlacement);

        for (var i = 0; i < headers.Length; i++)
        {
            nav.SelectedIndex = i;
            Dispatcher.UIThread.RunJobs();
            var content = Assert.IsAssignableFrom<Control>(nav.SelectedContent);
            Assert.True(content.IsVisible);
            Assert.True(content.Bounds.Width > 0, $"{headers[i]} 페이지가 배치되지 않았습니다");
        }
    }

    [AvaloniaFact]
    public async Task 채팅_입력_후_Enter_로_보내면_스트리밍_응답과_출처가_붙는다()
    {
        using var s = new Scenario();
        var w = s.Show();
        w.FindControl<TabControl>("Nav")!.SelectedIndex = 1;
        Dispatcher.UIThread.RunJobs();
        var input = w.FindControl<TextBox>("ChatInput")!;
        var chat = s.Main.Chat;

        Assert.False(chat.SendCommand.CanExecute());
        input.Focus();
        w.KeyTextInput("안녕?");
        Assert.True(chat.SendCommand.CanExecute());
        w.KeyPress(Key.Enter, RawInputModifiers.None, PhysicalKey.Enter, null);

        await Scenario.WaitUntil(() => chat.Messages.Count == 2 && !chat.IsBusy);

        Assert.Equal(("User", "안녕?"), (chat.Messages[0].Role, chat.Messages[0].Text));
        Assert.Equal("안녕하세요\n\nSources: manual.pdf", chat.Messages[1].Text);
        Assert.Equal("", chat.Input);
        var request = s.Backend.Requests.Single(r => r.Request == "POST /api/chat/message");
        Assert.Contains("\"use_rag\":true", request.Body);
    }

    [AvaloniaFact]
    public async Task 채팅_오류_이벤트는_오류_메시지로_표시된다()
    {
        using var s = new Scenario(setup: b =>
            b.Sse["/api/chat/message"] = new[] { ("message", """{"type":"error","content":"LLM down"}""") });
        s.Show();
        var chat = s.Main.Chat;

        chat.Input = "test";
        chat.SendCommand.Execute();
        await Scenario.WaitUntil(() => !chat.IsBusy && chat.Messages.Count == 2);

        Assert.Equal("Error: LLM down", chat.Messages[1].Text);
    }

    [AvaloniaFact]
    public async Task 설정은_백엔드_값을_불러오고_저장하면_PUT_으로_보낸다()
    {
        using var s = new Scenario();
        s.Show();
        var settings = s.Main.Settings;
        await Scenario.WaitUntil(() => settings.ContextWindowSize == 10 && settings.LlmModel == "qwen");

        Assert.Equal("alexa", settings.WakeWord);
        Assert.Equal(1.5, settings.VoiceSpeed);
        Assert.False(settings.ContextEnabled);
        Assert.Equal("~730 tokens", settings.EstimatedTokens);
        Assert.Single(settings.TtsEngines);

        settings.VoiceSpeed = 1.2;
        settings.SaveCommand.Execute();
        await Scenario.WaitUntil(() => settings.SaveResult.Contains("말하기 속도: 바로 반영됨"));

        var put = s.Backend.Requests.Single(r => r.Request == "PUT /api/settings/general");
        Assert.Contains("\"voice_speed\":1.2", put.Body);
    }

    [AvaloniaFact]
    public async Task 지식_베이스와_히스토리_목록이_표시된다()
    {
        using var s = new Scenario();
        s.Show();

        await Scenario.WaitUntil(() => s.Main.Knowledge.Documents.Count == 1 && s.Main.History.Items.Count == 1);

        Assert.Equal("manual.pdf", s.Main.Knowledge.Documents[0].Filename);
        Assert.StartsWith("12 chunks", s.Main.Knowledge.Documents[0].Meta);
        Assert.Equal("문서 1개", s.Main.Knowledge.Status);
        Assert.Equal("반가워요", s.Main.History.Items[0].Response);
        Assert.Equal("1건", s.Main.History.Status);
    }

    [AvaloniaFact]
    public async Task 히스토리가_비면_안내_문구를_보여준다()
    {
        using var s = new Scenario(setup: b => b.Json["/api/history"] = """{"conversations":[]}""");
        s.Show();

        await Scenario.WaitUntil(() => s.Main.History.Status.Length > 0);

        Assert.Equal("대화 기록이 없습니다.", s.Main.History.Status);
    }

    [AvaloniaFact]
    public async Task 로그_조회와_통계_Live_토글()
    {
        using var s = new Scenario();
        s.Show();
        var logs = s.Main.Logs;

        await Scenario.WaitUntil(() => logs.Logs.Count == 1 && logs.Stats.Length > 0);

        Assert.Equal("transcribe", logs.Logs[0].Stage);
        Assert.Equal("120ms", logs.Logs[0].Duration);
        Assert.Equal("Total 12  |  INFO 8  |  WARNING 3  |  ERROR 1  |  stt 5  |  llm 7", logs.Stats);
        Assert.True(logs.IsLive);

        logs.ToggleLiveCommand.Execute();
        Assert.False(logs.IsLive);
        logs.ToggleLiveCommand.Execute();
        Assert.True(logs.IsLive);
    }
}
