using System.Text.Json.Nodes;
using Avalonia.Controls;
using Avalonia.Headless.XUnit;
using Avalonia.Threading;
using Avalonia.VisualTree;
using Xunit;

namespace EdgeVoice.Agent.Desktop.Tests;

/// <summary>
/// 설정 화면 "MCP 서버"·"스킬": 목록 + 체크박스(켜기/끄기) + 추가/수정/삭제 + 연결 상태 (사용자 요청 2026-10-18).
/// </summary>
public class ExtensionSettingsScenarioTests
{
    private const string ServerMcp = """
        {"servers":[
          {"name":"browser","url":"http://host.docker.internal:8931/mcp","command":null,"args":[],"env":null,
           "allowed_tools":["browser_navigate","browser_click"],"trusted":true,"always_confirm":["browser_click"],
           "no_confirm":["browser_navigate"],"timeout":60,"enabled":true,
           "status":"connected","error":"","tools":["browser_navigate","browser_click","browser_snapshot"]},
          {"name":"desktop","url":"http://host.docker.internal:8932/mcp","command":null,"args":[],"env":null,
           "allowed_tools":["open_app"],"trusted":true,"always_confirm":[],"no_confirm":[],"timeout":120,"enabled":false,
           "status":"disabled","error":"","tools":[]}]}
        """;

    private const string ServerSkills = """
        {"builtin":[{"name":"get_time","description":"지금 시각 알려 주기","enabled":true,"active":true},
                    {"name":"web_search","description":"인터넷 검색","enabled":true,"active":false}],
         "disabled_tools":[],
         "prompts":[{"name":"존댓말","description":"항상 존댓말","instructions":"항상 존댓말로 답한다.","enabled":true}]}
        """;

    private static Scenario Open() => new(setup: b =>
    {
        // 백엔드는 추가·수정·삭제 뒤에도 서버 목록 전체를 돌려준다
        b.Json["/api/settings/mcp"] = ServerMcp;
        b.Json["/api/settings/mcp/browser"] = ServerMcp;
        b.Json["/api/settings/mcp/desktop"] = ServerMcp;
        b.Json["/api/settings/skills"] = ServerSkills;
    });

    private static JsonNode LastBody(FakeBackend backend, string request)
        => JsonNode.Parse(backend.Requests.Last(r => r.Request == request).Body)!;

    private static async Task Loaded(Scenario s)
        => await Scenario.WaitUntil(() => s.Main.Settings.McpServers.Count == 2 && s.Main.Settings.PromptSkills.Count == 1);

    [AvaloniaFact]
    public async Task MCP_서버와_스킬을_연결_상태와_함께_보여준다()
    {
        using var s = Open();
        await Loaded(s);
        var settings = s.Main.Settings;

        var browser = settings.McpServers[0];
        Assert.Equal("browser", browser.Name);
        Assert.True(browser.Enabled);
        Assert.Contains("연결됨", browser.Detail);
        Assert.Contains("browser_snapshot", browser.Detail);
        Assert.False(settings.McpServers[1].Enabled);
        Assert.Contains("꺼짐", settings.McpServers[1].Detail);

        Assert.Equal(new[] { "get_time", "web_search" }, settings.BuiltinSkills.Select(x => x.Name));
        Assert.Contains("지금 사용 안 됨", settings.BuiltinSkills[1].Detail);
        Assert.Equal("존댓말", settings.PromptSkills[0].Name);
    }

    [AvaloniaFact]
    public async Task MCP_체크를_끄고_저장하면_그_서버를_끄는_요청을_보낸다()
    {
        using var s = Open();
        await Loaded(s);

        s.Main.Settings.McpServers[0].Enabled = false;
        Assert.DoesNotContain(s.Backend.Requests, r => r.Request == "PUT /api/settings/mcp/browser");
        s.Main.Settings.SaveCommand.Execute();
        await Scenario.WaitUntil(() => s.Backend.Requests.Any(r => r.Request == "PUT /api/settings/mcp/browser"));

        var body = LastBody(s.Backend, "PUT /api/settings/mcp/browser");
        Assert.False(body["enabled"]!.GetValue<bool>());
        // 다른 설정은 그대로 보낸다
        Assert.Equal("http://host.docker.internal:8931/mcp", body["url"]!.ToString());
        Assert.Equal(2, body["allowed_tools"]!.AsArray().Count);
    }

    [AvaloniaFact]
    public async Task 편집_칸으로_MCP_서버를_추가하고_고치고_지운다()
    {
        using var s = Open();
        await Loaded(s);
        var settings = s.Main.Settings;

        settings.McpName = "files";
        settings.McpCommand = "python";
        settings.McpArgs = "server.py, --root, C:/data";
        settings.McpAllowedTools = "list, read";
        settings.McpNoConfirm = "list";
        settings.AddMcpServerCommand.Execute();
        await Scenario.WaitUntil(() => s.Backend.Requests.Any(r => r.Request == "POST /api/settings/mcp"));

        var added = LastBody(s.Backend, "POST /api/settings/mcp");
        Assert.Equal("files", added["name"]!.ToString());
        Assert.Equal("python", added["command"]!.ToString());
        Assert.Equal(new[] { "server.py", "--root", "C:/data" }, added["args"]!.AsArray().Select(a => a!.ToString()));
        Assert.Equal(new[] { "list", "read" }, added["allowed_tools"]!.AsArray().Select(a => a!.ToString()));
        Assert.True(added["enabled"]!.GetValue<bool>());

        // 목록에서 고르면 편집 칸에 채워지고, 고쳐서 저장 막대로 저장하면 그 이름으로 PUT
        settings.SelectedMcpServer = settings.McpServers[1];
        Assert.Equal("desktop", settings.McpName);
        Assert.Equal("open_app", settings.McpAllowedTools);
        Assert.False(settings.HasChanges);
        settings.McpAllowedTools = "open_app, write_document";
        Assert.Contains("MCP 서버 'desktop' 설정", settings.ChangeSummary);
        settings.SaveCommand.Execute();
        await Scenario.WaitUntil(() => s.Backend.Requests.Any(r => r.Request == "PUT /api/settings/mcp/desktop"));

        var updated = LastBody(s.Backend, "PUT /api/settings/mcp/desktop");
        Assert.Equal(2, updated["allowed_tools"]!.AsArray().Count);
        Assert.False(updated["enabled"]!.GetValue<bool>());

        settings.DeleteMcpServerCommand.Execute();
        await Scenario.WaitUntil(() => s.Backend.Requests.Any(r => r.Request == "DELETE /api/settings/mcp/desktop"));
    }

    [AvaloniaFact]
    public async Task 내장_스킬_체크를_끄고_저장하면_끈_도구_목록을_저장한다()
    {
        using var s = Open();
        await Loaded(s);

        s.Main.Settings.BuiltinSkills[0].Enabled = false;
        s.Main.Settings.SaveCommand.Execute();
        await Scenario.WaitUntil(() => s.Backend.Requests.Any(r => r.Request == "PUT /api/settings/skills"));

        var body = LastBody(s.Backend, "PUT /api/settings/skills");
        Assert.Equal(new[] { "get_time" }, body["disabled_tools"]!.AsArray().Select(a => a!.ToString()));
        // 프롬프트 스킬은 그대로 함께 보낸다
        Assert.Equal("항상 존댓말로 답한다.", body["prompts"]![0]!["instructions"]!.ToString());
    }

    [AvaloniaFact]
    public async Task 프롬프트_스킬을_추가하고_지운다()
    {
        using var s = Open();
        await Loaded(s);
        var settings = s.Main.Settings;

        settings.SkillName = "짧게";
        settings.SkillDescription = "한 문장 답";
        settings.SkillInstructions = "한 문장으로만 답한다.";
        settings.AddSkillCommand.Execute();
        await Scenario.WaitUntil(() => s.Backend.Requests.Any(r => r.Request == "PUT /api/settings/skills"));

        var prompts = LastBody(s.Backend, "PUT /api/settings/skills")["prompts"]!.AsArray();
        Assert.Equal(new[] { "존댓말", "짧게" }, prompts.Select(p => p!["name"]!.ToString()));
        Assert.True(prompts[1]!["enabled"]!.GetValue<bool>());

        settings.SelectedPromptSkill = settings.PromptSkills[0];
        Assert.Equal("항상 존댓말로 답한다.", settings.SkillInstructions);
        var before = s.Backend.Requests.Count(r => r.Request == "PUT /api/settings/skills");
        settings.DeleteSkillCommand.Execute();
        await Scenario.WaitUntil(() => s.Backend.Requests.Count(r => r.Request == "PUT /api/settings/skills") > before);

        Assert.Empty(LastBody(s.Backend, "PUT /api/settings/skills")["prompts"]!.AsArray());
    }

    [AvaloniaFact]
    public async Task 설정_탭에_MCP_목록과_스킬_목록이_그려진다()
    {
        using var s = Open();
        var window = s.Show();
        var nav = window.GetVisualDescendants().OfType<TabControl>().First();
        nav.SelectedIndex = 3;
        await Loaded(s);
        Dispatcher.UIThread.RunJobs();

        var lists = window.GetVisualDescendants().OfType<ListBox>().ToDictionary(l => l.Name ?? "", l => l);
        Assert.Equal(2, lists["McpServerList"].ItemCount);
        Assert.Equal(2, lists["BuiltinSkillList"].ItemCount);
        Assert.Equal(1, lists["PromptSkillList"].ItemCount);
        Assert.Contains(lists["McpServerList"].GetVisualDescendants().OfType<CheckBox>(), c => c.IsChecked == true);
    }
}
