using System;
using System.IO;
using System.Text.Json;
using Autofac;
using Avalonia;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Markup.Xaml;
using EdgeVoice.Agent.Core;
using EdgeVoice.Agent.Desktop.Tray;
using EdgeVoice.Agent.Desktop.ViewModels;

namespace EdgeVoice.Agent.Desktop;

/// <summary>
/// 트레이 상주형 EdgeVoice 에이전트(Avalonia). 시작 시 메인 창 없이 트레이 아이콘 + 파형 오버레이만 띄우고,
/// 메인 창(기존 웹 대시보드 기능)은 요청 시 생성한다.
/// </summary>
public partial class App : Application
{
    private IContainer? _container;
    private TrayController? _tray;

    public override void Initialize() => AvaloniaXamlLoader.Load(this);

    public override void OnFrameworkInitializationCompleted()
    {
        if (ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
        {
            var path = Path.Combine(AppContext.BaseDirectory, "appsettings.json");
            var options = File.Exists(path)
                ? JsonSerializer.Deserialize<EdgeVoiceOptions>(File.ReadAllText(path)) ?? new EdgeVoiceOptions()
                : new EdgeVoiceOptions();

            _container = BuildContainer(options);
            _container.Resolve<VoiceStateMonitor>().Start();
            _tray = new TrayController(
                this,
                _container.Resolve<VoiceStateMonitor>(),
                _container.Resolve<MicrophoneStreamer>(),
                OpenMainWindow,
                () => desktop.Shutdown());

            desktop.Exit += (_, _) =>
            {
                _tray?.Dispose();
                _container?.Dispose();
            };
        }

        base.OnFrameworkInitializationCompleted();
    }

    /// <summary>메인 화면 DI 구성. 헤드리스 시나리오 테스트도 같은 구성을 쓴다.</summary>
    public static IContainer BuildContainer(EdgeVoiceOptions options)
    {
        var builder = new ContainerBuilder();
        builder.RegisterModule(new EdgeVoiceCoreModule(options));
        builder.RegisterType<DashboardViewModel>().SingleInstance();
        builder.RegisterType<ChatViewModel>().SingleInstance();
        builder.RegisterType<KnowledgeViewModel>().SingleInstance();
        builder.RegisterType<SettingsViewModel>().SingleInstance();
        builder.RegisterType<HistoryViewModel>().SingleInstance();
        builder.RegisterType<LogsViewModel>().SingleInstance();
        builder.RegisterType<MainViewModel>().SingleInstance();
        builder.RegisterType<MainWindow>().SingleInstance();
        return builder.Build();
    }

    private void OpenMainWindow()
    {
        var window = _container!.Resolve<MainWindow>();
        window.Show();
        window.Activate();
    }
}
