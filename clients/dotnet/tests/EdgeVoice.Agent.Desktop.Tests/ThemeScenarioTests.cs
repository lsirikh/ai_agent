using Avalonia;
using Avalonia.Controls;
using Avalonia.Headless;
using Avalonia.Headless.XUnit;
using Avalonia.Input;
using Avalonia.Media;
using Avalonia.Styling;
using Avalonia.VisualTree;

namespace EdgeVoice.Agent.Desktop.Tests;

/// <summary>[헤드리스] 라이트/다크 테마 전환 시나리오.</summary>
public class ThemeScenarioTests
{
    private static Color CanvasColor(Window w) => ((ISolidColorBrush)w.Background!).Color;

    [AvaloniaFact]
    public void 기본은_라이트_테마이고_Office_캔버스_색을_쓴다()
    {
        using var s = new Scenario();
        var w = s.Show();

        Assert.False(s.Main.IsDarkTheme);
        Assert.Equal(ThemeVariant.Light, w.ActualThemeVariant);
        Assert.Equal(Color.Parse("#F5F5F5"), CanvasColor(w));
        Assert.Equal("☾  다크 모드", s.Main.ThemeLabel);
    }

    [AvaloniaFact]
    public void 테마_명령으로_다크와_라이트를_오간다()
    {
        using var s = new Scenario();
        var w = s.Show();

        s.Main.ToggleThemeCommand.Execute();
        Assert.True(s.Main.IsDarkTheme);
        Assert.Equal(ThemeVariant.Dark, w.ActualThemeVariant);
        Assert.Equal(Color.Parse("#1F1F1F"), CanvasColor(w));
        Assert.Equal("☀  라이트 모드", s.Main.ThemeLabel);

        s.Main.ToggleThemeCommand.Execute();
        Assert.False(s.Main.IsDarkTheme);
        Assert.Equal(Color.Parse("#F5F5F5"), CanvasColor(w));
    }

    [AvaloniaFact]
    public void 앱바_테마_버튼을_마우스로_클릭하면_다크로_바뀐다()
    {
        using var s = new Scenario();
        var w = s.Show();
        var button = w.FindControl<Button>("ThemeButton")!;
        var center = button.TranslatePoint(new Avalonia.Point(button.Bounds.Width / 2, button.Bounds.Height / 2), w)!.Value;

        w.MouseDown(center, MouseButton.Left);
        w.MouseUp(center, MouseButton.Left);

        Assert.True(s.Main.IsDarkTheme);
        Assert.Equal("☀  라이트 모드", button.Content);
    }

    /// <summary>라이트/다크 대시보드를 실제 Skia 로 렌더링해 PNG 로 남긴다 (bin/.../screenshots, 눈으로 확인용).</summary>
    [AvaloniaFact]
    public async Task 라이트_다크_대시보드_화면을_렌더링해_저장한다()
    {
        using var s = new Scenario();
        var w = s.Show();
        await Scenario.WaitUntil(() => s.Main.Dashboard.LogServiceSeries.Length == 1 && s.Main.Dashboard.GpuHistory.Count == 1);
        var dir = Directory.CreateDirectory(Path.Combine(AppContext.BaseDirectory, "screenshots")).FullName;

        // 차트 등장 애니메이션이 끝날 때까지 기다린 뒤 캡처
        await Scenario.Settle(1500);
        var light = w.CaptureRenderedFrame()!;
        light.Save(Path.Combine(dir, "dashboard-light.png"));
        s.Main.IsDarkTheme = true;
        await Scenario.Settle(500);
        var dark = w.CaptureRenderedFrame()!;
        dark.Save(Path.Combine(dir, "dashboard-dark.png"));

        Assert.Equal(w.ClientSize.Width, light.Size.Width);
        Assert.True(new FileInfo(Path.Combine(dir, "dashboard-dark.png")).Length > 10_000);
    }

    [AvaloniaFact]
    public void 다크_테마에서_카드와_앱바도_다크_색으로_바뀐다()
    {
        using var s = new Scenario();
        var w = s.Show();
        var card = w.GetVisualDescendants().OfType<Border>().First(b => b.Classes.Contains("card"));
        var light = ((ISolidColorBrush)card.Background!).Color;

        s.Main.IsDarkTheme = true;

        Assert.Equal(Color.Parse("#FFFFFF"), light);
        Assert.Equal(Color.Parse("#2E2E2E"), ((ISolidColorBrush)card.Background!).Color);
    }
}
