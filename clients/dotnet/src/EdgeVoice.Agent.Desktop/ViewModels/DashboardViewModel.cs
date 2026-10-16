using System;
using System.Collections.ObjectModel;
using System.Linq;
using System.Text.Json.Nodes;
using Avalonia.Threading;
using EdgeVoice.Agent.Core;
using Prism.Commands;

namespace EdgeVoice.Agent.Desktop.ViewModels;

public sealed record ServiceItem(string Name, string Status);

/// <summary>대시보드: 서비스 상태, GPU, 세션/문서 수, Orchestrator 상태 (10초 주기 갱신).</summary>
public sealed class DashboardViewModel : PageViewModel
{
    private readonly EdgeVoiceApiClient _api;
    private string _orchestratorState = "-";
    private string _gpu = "-";
    private string _sessions = "-";
    private string _documents = "-";
    private string _systemStatus = "-";

    public DashboardViewModel(EdgeVoiceApiClient api, VoiceStateMonitor monitor)
    {
        _api = api;
        RefreshCommand = new DelegateCommand(Refresh);

        monitor.StateChanged += s => Dispatcher.UIThread.Post(() => OrchestratorState = s.ToString());

        var timer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(10) };
        timer.Tick += (_, _) => Refresh();
        timer.Start();
        Refresh();
    }

    public ObservableCollection<ServiceItem> Services { get; } = new();

    public DelegateCommand RefreshCommand { get; }

    public string OrchestratorState { get => _orchestratorState; set => SetProperty(ref _orchestratorState, value); }

    public string Gpu { get => _gpu; set => SetProperty(ref _gpu, value); }

    public string Sessions { get => _sessions; set => SetProperty(ref _sessions, value); }

    public string Documents { get => _documents; set => SetProperty(ref _documents, value); }

    public string SystemStatus { get => _systemStatus; set => SetProperty(ref _systemStatus, value); }

    private async void Refresh() => await RunAsync(async () =>
    {
        var data = await _api.GetAsync("api/dashboard/init");
        Services.Clear();
        foreach (var (name, info) in data?["services"]?.AsObject() ?? new JsonObject())
        {
            var status = info is JsonObject o ? (o["status"] ?? o["state"])?.ToString() : info?.ToString();
            Services.Add(new ServiceItem(name, status ?? "unknown"));
        }

        SystemStatus = Services.All(s => s.Status is "healthy" or "ready" or "READY")
            ? "System Online"
            : "Some Services Offline";

        var orchestrator = data?["services"]?["orchestrator"]?["state"]?.ToString();
        if (orchestrator is not null)
        {
            OrchestratorState = orchestrator;
        }

        var system = data?["system"];
        var gpu = system?["gpu"];
        Gpu = gpu?["available"]?.GetValue<bool>() == true
            ? $"{gpu["used_gb"]?.GetValue<double>():0.0}/{gpu["total_gb"]?.GetValue<double>():0.0} GB ({gpu["utilization_percent"]?.GetValue<double>():0}%)"
            : "N/A";
        Sessions = system?["sessions"]?["active"]?.ToString() ?? "0";
        Documents = system?["documents"]?["count"]?.ToString() ?? "0";
    }, $"갱신: {DateTime.Now:HH:mm:ss}");
}
