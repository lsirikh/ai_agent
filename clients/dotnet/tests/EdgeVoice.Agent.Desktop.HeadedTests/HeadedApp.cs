using Autofac;
using Avalonia;
using Avalonia.Media.Imaging;
using Avalonia.Styling;
using Avalonia.Threading;
using EdgeVoice.Agent.Core;
using EdgeVoice.Agent.Desktop.ViewModels;

[assembly: CollectionBehavior(DisableTestParallelization = true)]

namespace EdgeVoice.Agent.Desktop.HeadedTests;

/// <summary>
/// 헤디드 시나리오: 실제 플랫폼(Win32 등)으로 화면에 창을 띄우고 실행 중인 EdgeVoice 백엔드(docker)에 붙는다.
/// 디스플레이와 백엔드가 필요해 기본은 건너뛰고, EDGEVOICE_HEADED=1 일 때만 실행한다.
///   dotnet test tests/EdgeVoice.Agent.Desktop.HeadedTests -e EDGEVOICE_HEADED=1 [-e EDGEVOICE_BACKEND_URL=http://localhost:11000]
/// </summary>
public sealed class HeadedFactAttribute : FactAttribute
{
    public HeadedFactAttribute()
    {
        if (Environment.GetEnvironmentVariable("EDGEVOICE_HEADED") != "1")
        {
            Skip = "헤디드 테스트: EDGEVOICE_HEADED=1 일 때만 실행";
        }
    }
}

public static class HeadedApp
{
    private static readonly Lazy<Task> Started = new(Start);

    public static string BackendUrl =>
        Environment.GetEnvironmentVariable("EDGEVOICE_BACKEND_URL") ?? "http://localhost:11000";

    public static string ShotDir => Directory.CreateDirectory(Path.Combine(AppContext.BaseDirectory, "screenshots")).FullName;

    /// <summary>Avalonia UI 스레드를 한 번만 띄우고, 시나리오를 그 스레드에서 실행한다.</summary>
    public static async Task Run(Func<Task> scenario)
    {
        await Started.Value;
        await Dispatcher.UIThread.InvokeAsync(scenario);
    }

    private static Task Start()
    {
        var ready = new TaskCompletionSource();
        var thread = new Thread(() =>
        {
            try
            {
                Program.BuildAvaloniaApp().SetupWithoutStarting();
                ready.SetResult();
                Dispatcher.UIThread.MainLoop(CancellationToken.None);
            }
            catch (Exception ex)
            {
                ready.TrySetException(ex);
            }
        }) { IsBackground = true };
        if (OperatingSystem.IsWindows())
        {
            thread.SetApartmentState(ApartmentState.STA);
        }

        thread.Start();
        return ready.Task;
    }

    public static (IContainer Container, MainWindow Window, MainViewModel Main) Open()
    {
        Application.Current!.RequestedThemeVariant = ThemeVariant.Light;
        var container = App.BuildContainer(new EdgeVoiceOptions { BackendUrl = BackendUrl });
        var window = container.Resolve<MainWindow>();
        window.Show();
        window.Activate();
        return (container, window, container.Resolve<MainViewModel>());
    }

    public static async Task WaitUntil(Func<bool> condition, int timeoutMs = 15000)
    {
        var until = DateTime.UtcNow.AddMilliseconds(timeoutMs);
        while (!condition())
        {
            Assert.True(DateTime.UtcNow < until, "시간 내에 조건이 충족되지 않았습니다");
            await Task.Delay(50);
        }
    }

    /// <summary>화면에 떠 있는 창을 실제 렌더러로 PNG 저장.</summary>
    public static string Shot(MainWindow window, string name)
    {
        var size = new PixelSize((int)window.ClientSize.Width, (int)window.ClientSize.Height);
        using var bmp = new RenderTargetBitmap(size);
        bmp.Render(window);
        var path = Path.Combine(ShotDir, name + ".png");
        bmp.Save(path);
        return path;
    }

    public static void Close(IContainer container, MainWindow window, MainViewModel main)
    {
        main.Logs.ToggleLiveCommand.Execute();
        window.Close();
        container.Dispose();
        Application.Current!.RequestedThemeVariant = ThemeVariant.Light;
    }
}
