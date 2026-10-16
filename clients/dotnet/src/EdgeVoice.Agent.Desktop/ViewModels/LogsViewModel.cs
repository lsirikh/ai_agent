using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using EdgeVoice.Agent.Core;
using Prism.Commands;

namespace EdgeVoice.Agent.Desktop.ViewModels;

public sealed record LogItem(string Time, string Level, string Service, string Stage, string Message, string Duration)
{
    // 레벨 색 구분용 (MainWindow 의 TextBlock.lvError/lvWarning/lvDebug)
    public bool IsError => Level is "ERROR" or "CRITICAL";

    public bool IsWarning => Level == "WARNING";

    public bool IsDebug => Level == "DEBUG";
}

/// <summary>파이프라인 로그: 필터 조회, 실시간 스트림(Live/Paused), 통계.</summary>
public sealed class LogsViewModel : PageViewModel
{
    private const int MaxEntries = 500;

    private readonly EdgeVoiceApiClient _api;
    private CancellationTokenSource? _live;
    private const string InfoAndAbove = "INFO+";

    private string _serviceFilter = "";
    // 기본 "INFO 이상": VAD 확률 같은 고빈도 DEBUG 는 숨기고, "전체" 를 고르면 보인다
    private string _levelFilter = InfoAndAbove;
    private string _stats = "";

    public LogsViewModel(EdgeVoiceApiClient api)
    {
        _api = api;
        RefreshCommand = new DelegateCommand(Refresh);
        ClearCommand = new DelegateCommand(Logs.Clear);
        ToggleLiveCommand = new DelegateCommand(ToggleLive);
        RefreshStatsCommand = new DelegateCommand(RefreshStats);
        Refresh();
        RefreshStats();
        ToggleLive();
    }

    public ObservableCollection<LogItem> Logs { get; } = new();

    public IReadOnlyList<OptionItem> Services { get; } = new[] { new OptionItem("", "전체 서비스") }
        .Concat(new[] { "orchestrator", "audio_gateway", "wake_word", "stt", "llm", "tts", "rag" }.Select(s => new OptionItem(s, s)))
        .ToArray();

    public IReadOnlyList<OptionItem> Levels { get; } = new[]
    {
        new OptionItem(InfoAndAbove, "INFO 이상"), new OptionItem("", "전체(DEBUG 포함)"),
        new OptionItem("DEBUG", "DEBUG"), new OptionItem("INFO", "INFO"), new OptionItem("WARNING", "WARNING"), new OptionItem("ERROR", "ERROR"),
    };

    public DelegateCommand RefreshCommand { get; }

    public DelegateCommand ClearCommand { get; }

    public DelegateCommand ToggleLiveCommand { get; }

    public DelegateCommand RefreshStatsCommand { get; }

    public bool IsLive => _live is not null;

    public string Stats { get => _stats; set => SetProperty(ref _stats, value); }

    public string ServiceFilter
    {
        get => _serviceFilter;
        set
        {
            // 콤보박스가 항목을 다시 그리는 동안 잠깐 보내는 null 은 무시한다
            if (value is not null && SetProperty(ref _serviceFilter, value))
            {
                OnFilterChanged();
            }
        }
    }

    public string LevelFilter
    {
        get => _levelFilter;
        set
        {
            if (value is not null && SetProperty(ref _levelFilter, value))
            {
                OnFilterChanged();
            }
        }
    }

    private string Query =>
        (ServiceFilter.Length > 0 ? $"&service={ServiceFilter}" : "") + LevelFilter switch
        {
            "" => "",
            InfoAndAbove => "&min_level=INFO",
            _ => $"&level={LevelFilter}",
        };

    private void OnFilterChanged()
    {
        Refresh();
        if (IsLive)
        {
            ToggleLive();
            ToggleLive();
        }
    }

    private async void Refresh() => await RunAsync(async () =>
    {
        var data = await _api.GetAsync("api/logs?limit=100" + Query);
        var logs = data as JsonArray ?? data?["logs"]?.AsArray() ?? new JsonArray();
        Logs.Clear();
        foreach (var log in logs.Reverse())
        {
            Logs.Add(ToItem(log));
        }
    });

    private async void ToggleLive()
    {
        if (_live is not null)
        {
            _live.Cancel();
            _live = null;
            RaisePropertyChanged(nameof(IsLive));
            return;
        }

        var cts = _live = new CancellationTokenSource();
        RaisePropertyChanged(nameof(IsLive));
        while (!cts.IsCancellationRequested)
        {
            try
            {
                await foreach (var ev in _api.StreamAsync("api/logs/stream?" + Query.TrimStart('&'), cts.Token))
                {
                    if (ev.Type != "log")
                    {
                        continue;
                    }

                    Logs.Add(ToItem(ev.Json));
                    while (Logs.Count > MaxEntries)
                    {
                        Logs.RemoveAt(0);
                    }
                }
            }
            catch (OperationCanceledException)
            {
                return;
            }
            catch (Exception ex)
            {
                Status = "로그 스트림 오류(5초 후 재연결): " + ex.Message;
            }

            try
            {
                await Task.Delay(5000, cts.Token);
            }
            catch (OperationCanceledException)
            {
                return;
            }
        }
    }

    private async void RefreshStats() => await RunAsync(async () =>
    {
        var data = await _api.GetAsync("api/logs/stats");
        var parts = new List<string> { $"Total {data?["total"] ?? 0}" };
        parts.AddRange((data?["by_level"]?.AsObject() ?? new JsonObject()).Select(p => $"{p.Key} {p.Value}"));
        parts.AddRange((data?["by_service"]?.AsObject() ?? new JsonObject()).Select(p => $"{p.Key} {p.Value}"));
        Stats = string.Join("  |  ", parts);
    });

    private static LogItem ToItem(JsonNode? log)
    {
        var time = DateTime.TryParse(log?["created_at"]?.ToString(), out var t) ? t.ToString("HH:mm:ss.fff") : "";
        var duration = log?["duration_ms"] is { } d ? $"{d}ms" : "";
        return new LogItem(time, log?["level"]?.ToString() ?? "", log?["service"]?.ToString() ?? "",
            log?["stage"]?.ToString() ?? "", log?["message"]?.ToString() ?? "", duration);
    }
}
