using Autofac;
using Avalonia.Controls;
using Avalonia.Headless.XUnit;
using Avalonia.Threading;
using EdgeVoice.Agent.Core;

namespace EdgeVoice.Agent.Desktop.Tests;

/// <summary>[헤드리스] 음성·채팅 통합 대화: 활성 세션 히스토리, 음성 턴 말풍선, 새 대화, 음소거 토글.</summary>
public class ChatSessionScenarioTests
{
    // SSE data 는 한 줄이어야 한다
    private const string Init =
        """{"session_id":"s1","messages":[{"id":"m1","session_id":"s1","role":"user","content":"이전 질문","source":"web"},"""
        + """{"id":"m2","session_id":"s1","role":"assistant","content":"이전 답","source":"web"}]}""";

    private static void ActiveSession(FakeBackend b)
    {
        b.Json["/api/sessions/active"] = """{"session_id":"s1"}""";
        b.Sse["/api/chat/stream"] = new[]
        {
            ("init", Init),
            ("message", """{"id":"m3","session_id":"s1","role":"user","content":"음성 질문","source":"voice"}"""),
            ("message", """{"id":"m4","session_id":"s1","role":"assistant","content":"음성 답","source":"voice"}"""),
            // 텍스트 턴 저장 알림은 보낸 화면이 이미 그리고 있으므로 다시 붙지 않는다
            ("message", """{"id":"m5","session_id":"s1","role":"user","content":"다른 창 텍스트","source":"web"}"""),
        };
    }

    [AvaloniaFact]
    public async Task 시작하면_활성_세션_히스토리를_불러오고_음성_턴을_음성_표시와_함께_붙인다()
    {
        using var s = new Scenario(setup: ActiveSession);
        s.Show();
        var chat = s.Main.Chat;

        await Scenario.WaitUntil(() => chat.Messages.Count == 4);

        Assert.Equal(new[] { "이전 질문", "이전 답", "음성 질문", "음성 답" }, chat.Messages.Select(m => m.Text));
        Assert.Equal(new[] { "User", "AI", "User", "AI" }, chat.Messages.Select(m => m.Role));
        Assert.Equal(new[] { false, false, true, true }, chat.Messages.Select(m => m.IsVoice));
        Assert.Equal("s1", chat.SessionId);
        Assert.Contains(s.Backend.Requests, r => r.Request == "GET /api/chat/stream");
    }

    [AvaloniaFact]
    public async Task 텍스트_질문은_음성과_같은_활성_세션으로_보낸다()
    {
        using var s = new Scenario(setup: ActiveSession);
        s.Show();
        var chat = s.Main.Chat;
        await Scenario.WaitUntil(() => chat.Messages.Count == 4);

        chat.Input = "내 이름 뭐야?";
        chat.SendCommand.Execute();
        await Scenario.WaitUntil(() => !chat.IsBusy && chat.Messages.Count == 6);

        var request = s.Backend.Requests.Single(r => r.Request == "POST /api/chat/message");
        Assert.Contains("\"session_id\":\"s1\"", request.Body);
    }

    [AvaloniaFact]
    public async Task 새_대화를_누르면_새_세션을_만들고_목록을_비운다()
    {
        using var s = new Scenario(setup: ActiveSession);
        var w = s.Show();
        var chat = s.Main.Chat;
        await Scenario.WaitUntil(() => chat.Messages.Count == 4);

        s.Backend.Json["/api/sessions/active"] = """{"session_id":"s2"}""";
        s.Backend.Sse["/api/chat/stream"] = new[] { ("init", """{"session_id":"s2","messages":[]}""") };
        w.FindControl<TabControl>("Nav")!.SelectedIndex = 1;
        Dispatcher.UIThread.RunJobs();
        w.FindControl<Button>("NewConversation")!.Command!.Execute(null);

        await Scenario.WaitUntil(() => chat.Status == "새 대화를 시작했습니다." && chat.SessionId == "s2");

        Assert.Empty(chat.Messages);
        Assert.Contains(s.Backend.Requests, r => r.Request == "POST /api/sessions");
    }

    [AvaloniaFact]
    public async Task 채팅의_마이크_버튼은_트레이와_같은_상시_마이크를_음소거한다()
    {
        using var s = new Scenario();
        var w = s.Show();
        var chat = s.Main.Chat;
        var alwaysOn = s.Container.Resolve<AlwaysOnMicrophone>();
        w.FindControl<TabControl>("Nav")!.SelectedIndex = 1;
        Dispatcher.UIThread.RunJobs();
        var toggle = w.FindControl<Avalonia.Controls.Primitives.ToggleButton>("MuteToggle")!;

        toggle.Command!.Execute(null);
        await Scenario.WaitUntil(() => chat.IsMuted);
        Assert.True(alwaysOn.IsMuted);
        Assert.True(toggle.IsChecked);

        toggle.Command!.Execute(null);
        await Scenario.WaitUntil(() => !chat.IsMuted);
        Assert.False(alwaysOn.IsMuted);
    }
}
