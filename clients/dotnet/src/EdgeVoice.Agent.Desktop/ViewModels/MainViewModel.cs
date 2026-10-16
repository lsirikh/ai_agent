using Prism.Mvvm;

namespace EdgeVoice.Agent.Desktop.ViewModels;

/// <summary>기존 웹 대시보드의 6개 탭을 그대로 옮긴 메인 화면.</summary>
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
    }

    public DashboardViewModel Dashboard { get; }

    public ChatViewModel Chat { get; }

    public KnowledgeViewModel Knowledge { get; }

    public SettingsViewModel Settings { get; }

    public HistoryViewModel History { get; }

    public LogsViewModel Logs { get; }
}
