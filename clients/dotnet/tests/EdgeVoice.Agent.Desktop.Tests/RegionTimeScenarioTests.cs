using System.Text.Json.Nodes;
using Avalonia.Headless.XUnit;
using EdgeVoice.Agent.Core;
using Xunit;

namespace EdgeVoice.Agent.Desktop.Tests;

/// <summary>
/// 설정 화면 "지역 및 시간": 시간대·날씨 기준 지역·날씨 켜기, PC 시간대 따르기,
/// 서버 시각과 PC 시각 비교 표시 (사용자 요청 2026-10-17).
/// </summary>
public class RegionTimeScenarioTests
{
    private const string ServerTools = """
        {"internet_enabled":true,"search_provider":"searxng","timezone":"America/New_York",
         "locale":"ko-KR","location":"부산","weather_enabled":true,"follow_pc_timezone":false,
         "tools":["get_time","get_weather"],"server_time":"2026년 10월 16일 (금요일) 20시 52분 EDT(UTC-0400)"}
        """;

    private static JsonNode LastToolsPut(FakeBackend backend)
        => JsonNode.Parse(backend.Requests.Last(r => r.Request == "PUT /api/settings/tools").Body)!;

    [AvaloniaFact]
    public async Task 서버의_지역과_시간_설정을_보여준다()
    {
        using var s = new Scenario(setup: b => b.Json["/api/settings/tools"] = ServerTools);
        var settings = s.Main.Settings;

        await Scenario.WaitUntil(() => settings.Location == "부산");

        Assert.Equal("America/New_York", settings.TimeZone);
        Assert.True(settings.WeatherEnabled);
        Assert.False(settings.FollowPcTimeZone);
        Assert.Contains("20시 52분", settings.TimeComparison);
        Assert.Contains("PC", settings.TimeComparison);
    }

    [AvaloniaFact]
    public async Task PC_시간대_따르기를_켜고_저장하면_PC_시간대가_전송된다()
    {
        using var s = new Scenario(setup: b => b.Json["/api/settings/tools"] = ServerTools);
        var settings = s.Main.Settings;
        await Scenario.WaitUntil(() => settings.Location == "부산");

        settings.FollowPcTimeZone = true;
        settings.Location = "제주";
        settings.SaveToolsCommand.Execute();
        await Scenario.WaitUntil(() => s.Backend.Requests.Any(r => r.Request == "PUT /api/settings/tools"));

        var body = LastToolsPut(s.Backend);
        Assert.Equal(PcTimeZone.IanaId(), body["timezone"]!.ToString());
        Assert.Equal("제주", body["location"]!.ToString());
        Assert.True(body["follow_pc_timezone"]!.GetValue<bool>());
        Assert.True(body["internet_enabled"]!.GetValue<bool>());
    }

    [AvaloniaFact]
    public async Task 시작할_때_PC_시간대를_따르게_되어_있으면_서버를_PC_시간대로_맞춘다()
    {
        var follow = ServerTools.Replace("\"follow_pc_timezone\":false", "\"follow_pc_timezone\":true");
        using var s = new Scenario(setup: b => b.Json["/api/settings/tools"] = follow);

        await Scenario.WaitUntil(() => s.Backend.Requests.Any(r => r.Request == "PUT /api/settings/tools"));

        Assert.Equal(PcTimeZone.IanaId(), LastToolsPut(s.Backend)["timezone"]!.ToString());
    }

    [Fact]
    public void PC_시간대는_IANA_이름으로_바꾼다()
    {
        var id = PcTimeZone.IanaId();

        Assert.Contains("/", id);
        Assert.NotNull(TimeZoneInfo.FindSystemTimeZoneById(id));
    }
}
