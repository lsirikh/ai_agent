using Autofac;
using Avalonia;
using Avalonia.Headless;
using Avalonia.Styling;
using Avalonia.Threading;
using EdgeVoice.Agent.Core;
using EdgeVoice.Agent.Desktop.Tests;
using EdgeVoice.Agent.Desktop.ViewModels;

[assembly: AvaloniaTestApplication(typeof(TestAppBuilder))]

namespace EdgeVoice.Agent.Desktop.Tests;

/// <summary>실제 App(App.axaml 의 테마·리소스 포함)을 헤드리스 플랫폼 + Skia 렌더링으로 띄운다.</summary>
public static class TestAppBuilder
{
    public static AppBuilder BuildAvaloniaApp() => AppBuilder.Configure<App>()
        .UseSkia()
        .UseHeadless(new AvaloniaHeadlessPlatformOptions { UseHeadlessDrawing = false });
}

/// <summary>시나리오 하나: 가짜 백엔드 + 앱과 같은 DI 구성 + 메인 창.</summary>
public sealed class Scenario : IDisposable
{
    /// <param name="setup">화면 VM 이 만들어지며 첫 요청을 보내기 전에 가짜 백엔드 응답을 바꾼다.</param>
    public Scenario(bool offline = false, Action<FakeBackend>? setup = null)
    {
        Backend = new FakeBackend();
        setup?.Invoke(Backend);
        if (offline)
        {
            Backend.Dispose();
        }

        Application.Current!.RequestedThemeVariant = ThemeVariant.Light;
        Container = App.BuildContainer(new EdgeVoiceOptions { BackendUrl = Backend.Url });
        Window = Container.Resolve<MainWindow>();
        Main = Container.Resolve<MainViewModel>();
    }

    public FakeBackend Backend { get; }

    public IContainer Container { get; }

    public MainWindow Window { get; }

    public MainViewModel Main { get; }

    public MainWindow Show()
    {
        Window.Show();
        Dispatcher.UIThread.RunJobs();
        return Window;
    }

    /// <summary>UI 스레드 작업을 돌리면서 조건이 참이 될 때까지 기다린다 (백엔드 응답 대기).</summary>
    public static async Task WaitUntil(Func<bool> condition, int timeoutMs = 5000)
    {
        var until = DateTime.UtcNow.AddMilliseconds(timeoutMs);
        while (!condition())
        {
            Assert.True(DateTime.UtcNow < until, "시간 내에 조건이 충족되지 않았습니다");
            Dispatcher.UIThread.RunJobs();
            await Task.Delay(20);
        }

        Dispatcher.UIThread.RunJobs();
    }

    /// <summary>애니메이션 등 시간 기반 UI 작업을 주어진 시간 동안 돌린다.</summary>
    public static async Task Settle(int ms)
    {
        var until = DateTime.UtcNow.AddMilliseconds(ms);
        while (DateTime.UtcNow < until)
        {
            Dispatcher.UIThread.RunJobs();
            await Task.Delay(20);
        }
    }

    public void Dispose()
    {
        Main.Logs.ToggleLiveCommand.Execute();
        Window.Close();
        Container.Dispose();
        Backend.Dispose();
        Application.Current!.RequestedThemeVariant = ThemeVariant.Light;
    }
}
