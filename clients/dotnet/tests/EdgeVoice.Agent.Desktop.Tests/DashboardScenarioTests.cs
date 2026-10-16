using Avalonia.Headless.XUnit;
using Avalonia.VisualTree;
using EdgeVoice.Agent.Desktop.ViewModels;
using LiveChartsCore.SkiaSharpView;
using LiveChartsCore.SkiaSharpView.Avalonia;

namespace EdgeVoice.Agent.Desktop.Tests;

/// <summary>[헤드리스] 대시보드 KPI·차트 시나리오 (가짜 백엔드 응답 기준).</summary>
public class DashboardScenarioTests
{
    [AvaloniaFact]
    public async Task KPI_카드에_백엔드_값이_표시된다()
    {
        using var s = new Scenario();
        s.Show();
        var d = s.Main.Dashboard;

        await Scenario.WaitUntil(() => d.Services.Count == 3);

        Assert.Equal("IDLE", d.OrchestratorState);
        Assert.Equal("6.5/16.0 GB (42%)", d.Gpu);
        Assert.Equal("3", d.Sessions);
        Assert.Equal("7", d.Documents);
        Assert.Equal("Some Services Offline", d.SystemStatus);
        Assert.StartsWith("갱신:", d.Status);
    }

    [AvaloniaFact]
    public async Task 서비스_상태_도넛은_정상_2_비정상_1()
    {
        using var s = new Scenario();
        s.Show();
        var d = s.Main.Dashboard;

        await Scenario.WaitUntil(() => d.ServiceHealthSeries.Length == 2);

        var values = d.ServiceHealthSeries.Cast<PieSeries<double>>()
            .ToDictionary(p => p.Name!, p => p.Values!.Single());
        Assert.Equal(2, values["정상"]);
        Assert.Equal(1, values["비정상"]);
    }

    [AvaloniaFact]
    public async Task 로그_통계가_레벨별_서비스별_막대로_그려진다()
    {
        using var s = new Scenario();
        s.Show();
        var d = s.Main.Dashboard;

        await Scenario.WaitUntil(() => d.LogLevelSeries.Length == 1 && d.LogServiceSeries.Length == 1);

        Assert.Equal(new[] { "INFO", "WARNING", "ERROR" }, d.LogLevelXAxes[0].Labels);
        Assert.Equal(new[] { 8d, 3, 1 }, ((ColumnSeries<double>)d.LogLevelSeries[0]).Values);
        Assert.Equal(new[] { "stt", "llm" }, d.LogServiceYAxes[0].Labels);
        Assert.Equal(new[] { 5d, 7 }, ((RowSeries<double>)d.LogServiceSeries[0]).Values);
    }

    [AvaloniaFact]
    public async Task GPU_추이는_갱신마다_쌓이고_최대_샘플_수를_넘지_않는다()
    {
        using var s = new Scenario();
        s.Show();
        var d = s.Main.Dashboard;
        await Scenario.WaitUntil(() => d.GpuHistory.Count == 1);

        // 한도보다 3번 더 갱신 (마지막 3번은 가장 오래된 샘플을 밀어낸다)
        for (var i = 2; i <= DashboardViewModel.GpuHistorySize + 3; i++)
        {
            var expected = Math.Min(i, DashboardViewModel.GpuHistorySize);
            d.RefreshCommand.Execute();
            await Scenario.WaitUntil(() =>
                s.Backend.Requests.Count(r => r.Request == "GET /api/logs/stats") >= i && d.GpuHistory.Count == expected);
        }

        Assert.Equal(DashboardViewModel.GpuHistorySize, d.GpuHistory.Count);
        Assert.All(d.GpuHistory, v => Assert.Equal(42, v));
    }

    [AvaloniaFact]
    public async Task 모든_서비스가_정상이면_System_Online()
    {
        using var s = new Scenario(setup: b => b.Json["/api/dashboard/init"] = """
            {"services":{"stt":{"status":"healthy"},"llm":{"status":"ready"}},"system":{"gpu":{"available":false}}}
            """);
        s.Show();
        var d = s.Main.Dashboard;

        await Scenario.WaitUntil(() => d.SystemStatus == "System Online");

        Assert.Equal("N/A", d.Gpu);
        Assert.Equal(0, d.GpuHistory.Last());
        Assert.Equal("0", d.Sessions);
    }

    [AvaloniaFact]
    public async Task 백엔드가_꺼져_있으면_오류를_표시하고_앱은_계속_동작한다()
    {
        using var s = new Scenario(offline: true);
        s.Show();
        var d = s.Main.Dashboard;

        await Scenario.WaitUntil(() => d.Status.StartsWith("오류:"));

        Assert.Empty(d.Services);
        Assert.Empty(d.ServiceHealthSeries);
        s.Main.IsDarkTheme = true;
        Assert.True(s.Main.IsDarkTheme);
    }

    [AvaloniaFact]
    public async Task 대시보드에_차트_4개가_시리즈와_함께_렌더링된다()
    {
        using var s = new Scenario();
        var w = s.Show();
        await Scenario.WaitUntil(() => s.Main.Dashboard.LogServiceSeries.Length == 1);

        var cartesian = w.GetVisualDescendants().OfType<CartesianChart>().ToList();
        var pie = w.GetVisualDescendants().OfType<PieChart>().Single();

        Assert.Equal(3, cartesian.Count);
        Assert.All(cartesian, c => Assert.NotEmpty(c.Series!));
        Assert.Equal(2, pie.Series!.Count());
        Assert.All(cartesian, c => Assert.True(c.Bounds.Height > 100));
    }
}
