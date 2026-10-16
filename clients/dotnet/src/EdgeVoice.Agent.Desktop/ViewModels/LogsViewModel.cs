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

public sealed record LogItem(string Time, string Level, string Service, string Stage, string Message, string Duration);

/// <summary>파이프라인 로그: 필터 조회, 실시간 스트림(Live/Paused), 통계.</summary>
public sealed class LogsViewModel : PageViewModel
{
    private const int MaxEntries = 500;

    private readonly EdgeVoiceApiClient _api;
    private CancellationTokenSource? _live;
    private string _serviceFilter = "";
    private string _levelFilter = "";
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

    public IReadOnlyList<string> Services { get; } = new[] { "", "orchestrator", "stt", "llm", "tts", "wake_word" };

    public IReadOnlyList<string> Levels { get; } = new[] { "", "DEBUG", "INFO", "WARNING", "ERROR" };

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
            if (SetProperty(ref _serviceFilter, value))
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
            if (SetProperty(ref _levelFilter, value))
            {
                OnFilterChanged();
            }
        }
    }

    private string Query =>
        (ServiceFilter.Length > 0 ? $"&service={ServiceFilter}" : "") + (LevelFilter.Length > 0 ? $"&level={LevelFilter}" : "");

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
