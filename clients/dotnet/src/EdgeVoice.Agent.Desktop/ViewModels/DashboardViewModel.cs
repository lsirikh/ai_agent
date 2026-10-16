using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using System.Text.Json.Nodes;
using Avalonia.Threading;
using EdgeVoice.Agent.Core;
using LiveChartsCore;
using LiveChartsCore.Measure;
using LiveChartsCore.SkiaSharpView;
using LiveChartsCore.SkiaSharpView.Painting;
using Prism.Commands;
using SkiaSharp;

namespace EdgeVoice.Agent.Desktop.ViewModels;

public sealed record ServiceItem(string Name, string Status)
{
    public bool IsHealthy => Status is "healthy" or "ready" or "READY";
}

/// <summary>대시보드: KPI 카드, GPU 추이·서비스 상태·로그 통계 차트, 서비스 목록 (10초 주기 갱신).</summary>
public sealed class DashboardViewModel : PageViewModel
{
    // GPU 추이 차트에 남길 샘플 수 (10초 주기 → 5분)
    public const int GpuHistorySize = 30;

    // Office(Fluent 2) 데이터 시각화 팔레트: 라이트/다크 배경 모두에서 읽히는 중간 명도
    private static readonly SKColor Blue = SKColor.Parse("#2886DE");
    private static readonly SKColor Green = SKColor.Parse("#13A10E");
    private static readonly SKColor Red = SKColor.Parse("#D13438");
    private static readonly SKColor Purple = SKColor.Parse("#8764B8");
    private static readonly SKColor Gray = SKColor.Parse("#8A8886");

    private readonly EdgeVoiceApiClient _api;
    private string _orchestratorState = "-";
    private string _gpu = "-";
    private string _sessions = "-";
    private string _documents = "-";
    private string _systemStatus = "-";
    private ISeries[] _serviceHealthSeries = Array.Empty<ISeries>();
    private ISeries[] _logLevelSeries = Array.Empty<ISeries>();
    private ISeries[] _logServiceSeries = Array.Empty<ISeries>();

    public DashboardViewModel(EdgeVoiceApiClient api, VoiceStateMonitor monitor)
    {
        _api = api;
        RefreshCommand = new DelegateCommand(Refresh);

        GpuSeries = new ISeries[]
        {
            new LineSeries<double>
            {
                Name = "GPU %",
                Values = GpuHistory,
                Stroke = new SolidColorPaint(Blue, 2),
                Fill = new SolidColorPaint(Blue.WithAlpha(40)),
                GeometrySize = 6,
                GeometryFill = new SolidColorPaint(Blue),
                GeometryStroke = null,
                LineSmoothness = 0.4,
            },
        };

        monitor.StateChanged += s => Dispatcher.UIThread.Post(() => OrchestratorState = s.ToString());

        var timer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(10) };
        timer.Tick += (_, _) => Refresh();
        timer.Start();
        Refresh();
    }

    public ObservableCollection<ServiceItem> Services { get; } = new();

    public ObservableCollection<double> GpuHistory { get; } = new();

    public DelegateCommand RefreshCommand { get; }

    public string OrchestratorState { get => _orchestratorState; set => SetProperty(ref _orchestratorState, value); }

    public string Gpu { get => _gpu; set => SetProperty(ref _gpu, value); }

    public string Sessions { get => _sessions; set => SetProperty(ref _sessions, value); }

    public string Documents { get => _documents; set => SetProperty(ref _documents, value); }

    public string SystemStatus { get => _systemStatus; set => SetProperty(ref _systemStatus, value); }

    public ISeries[] GpuSeries { get; }

    public Axis[] GpuXAxes { get; } = { new() { IsVisible = false } };

    public Axis[] GpuYAxes { get; } = { NeutralAxis(min: 0, max: 100) };

    public ISeries[] ServiceHealthSeries { get => _serviceHealthSeries; private set => SetProperty(ref _serviceHealthSeries, value); }

    public ISeries[] LogLevelSeries { get => _logLevelSeries; private set => SetProperty(ref _logLevelSeries, value); }

    public Axis[] LogLevelXAxes { get; } = { NeutralAxis() };

    public Axis[] LogLevelYAxes { get; } = { NeutralAxis(min: 0) };

    public ISeries[] LogServiceSeries { get => _logServiceSeries; private set => SetProperty(ref _logServiceSeries, value); }

    public Axis[] LogServiceXAxes { get; } = { NeutralAxis(min: 0) };

    public Axis[] LogServiceYAxes { get; } = { NeutralAxis() };

    public SolidColorPaint LegendTextPaint { get; } = new(Gray);

    private async void Refresh()
    {
        await RunAsync(async () =>
        {
            var data = await _api.GetAsync("api/dashboard/init");
            Services.Clear();
            foreach (var (name, info) in data?["services"]?.AsObject() ?? new JsonObject())
            {
                var status = info is JsonObject o ? (o["status"] ?? o["state"])?.ToString() : info?.ToString();
                Services.Add(new ServiceItem(name, status ?? "unknown"));
            }

            SystemStatus = Services.All(s => s.IsHealthy) ? "System Online" : "Some Services Offline";
            var healthy = Services.Count(s => s.IsHealthy);
            ServiceHealthSeries = new ISeries[]
            {
                Slice("정상", healthy, Green),
                Slice("비정상", Services.Count - healthy, Red),
            };

            var orchestrator = data?["services"]?["orchestrator"]?["state"]?.ToString();
            if (orchestrator is not null)
            {
                OrchestratorState = orchestrator;
            }

            var system = data?["system"];
            var gpu = system?["gpu"];
            var available = gpu?["available"]?.GetValue<bool>() == true;
            Gpu = available
                ? $"{gpu!["used_gb"]?.GetValue<double>():0.0}/{gpu["total_gb"]?.GetValue<double>():0.0} GB ({gpu["utilization_percent"]?.GetValue<double>():0}%)"
                : "N/A";
            GpuHistory.Add(available ? gpu!["utilization_percent"]?.GetValue<double>() ?? 0 : 0);
            while (GpuHistory.Count > GpuHistorySize)
            {
                GpuHistory.RemoveAt(0);
            }

            Sessions = system?["sessions"]?["active"]?.ToString() ?? "0";
            Documents = system?["documents"]?["count"]?.ToString() ?? "0";
        }, $"갱신: {DateTime.Now:HH:mm:ss}");

        // 로그 통계 실패가 서비스 상태 표시를 막지 않도록 따로 조회
        await RunAsync(async () =>
        {
            var stats = await _api.GetAsync("api/logs/stats");
            var levels = Counts(stats?["by_level"]);
            LogLevelXAxes[0].Labels = levels.Select(p => p.Key).ToArray();
            LogLevelSeries = new ISeries[]
            {
                new ColumnSeries<double>
                {
                    Name = "로그",
                    Values = levels.Select(p => p.Value).ToArray(),
                    Fill = new SolidColorPaint(Blue),
                    MaxBarWidth = 36,
                },
            };

            var services = Counts(stats?["by_service"]);
            LogServiceYAxes[0].Labels = services.Select(p => p.Key).ToArray();
            LogServiceSeries = new ISeries[]
            {
                new RowSeries<double>
                {
                    Name = "로그",
                    Values = services.Select(p => p.Value).ToArray(),
                    Fill = new SolidColorPaint(Purple),
                    MaxBarWidth = 22,
                },
            };
        });
    }

    private static List<KeyValuePair<string, double>> Counts(JsonNode? node)
        => (node as JsonObject ?? new JsonObject())
            .Select(p => new KeyValuePair<string, double>(p.Key, double.TryParse(p.Value?.ToString(), out var v) ? v : 0))
            .ToList();

    private static PieSeries<double> Slice(string name, double value, SKColor color) => new()
    {
        Name = name,
        Values = new[] { value },
        Fill = new SolidColorPaint(color),
        MaxRadialColumnWidth = 32,
        DataLabelsPaint = new SolidColorPaint(SKColors.White),
        DataLabelsPosition = PolarLabelsPosition.Middle,
        DataLabelsFormatter = p => p.Coordinate.PrimaryValue > 0 ? p.Coordinate.PrimaryValue.ToString("0") : "",
    };

    private static Axis NeutralAxis(double? min = null, double? max = null) => new()
    {
        MinLimit = min,
        MaxLimit = max,
        LabelsPaint = new SolidColorPaint(Gray),
        SeparatorsPaint = new SolidColorPaint(Gray.WithAlpha(50)),
        TextSize = 12,
    };
}
