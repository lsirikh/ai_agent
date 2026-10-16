using Avalonia;
using Avalonia.Styling;
using Prism.Commands;
using Prism.Mvvm;

namespace EdgeVoice.Agent.Desktop.ViewModels;

/// <summary>기존 웹 대시보드의 6개 탭을 그대로 옮긴 메인 화면 + 라이트/다크 테마 전환.</summary>
public sealed class MainViewModel : BindableBase
{
    public MainViewModel(
        DashboardViewModel dashboard,
        ChatViewModel chat,
        KnowledgeViewModel knowledge,
        SettingsViewModel settings,
        HistoryViewModel history,
        LogsViewModel logs)
    {
        Dashboard = dashboard;
        Chat = chat;
        Knowledge = knowledge;
        Settings = settings;
        History = history;
        Logs = logs;
        ToggleThemeCommand = new DelegateCommand(() => IsDarkTheme = !IsDarkTheme);
    }

    public DashboardViewModel Dashboard { get; }

    public ChatViewModel Chat { get; }

    public KnowledgeViewModel Knowledge { get; }

    public SettingsViewModel Settings { get; }

    public HistoryViewModel History { get; }

    public LogsViewModel Logs { get; }

    public DelegateCommand ToggleThemeCommand { get; }

    /// <summary>앱 전체(메인 창·대화상자) 테마. 처음에는 OS 설정을 따른다.</summary>
    public bool IsDarkTheme
    {
        get => Application.Current?.ActualThemeVariant == ThemeVariant.Dark;
        set
        {
            if (Application.Current is { } app && value != IsDarkTheme)
            {
                app.RequestedThemeVariant = value ? ThemeVariant.Dark : ThemeVariant.Light;
                RaisePropertyChanged();
                RaisePropertyChanged(nameof(ThemeLabel));
            }
        }
    }

    public string ThemeLabel => IsDarkTheme ? "☀  라이트 모드" : "☾  다크 모드";
}
