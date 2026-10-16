using System;
using System.Collections.ObjectModel;
using System.Linq;
using System.Text.Json.Nodes;
using EdgeVoice.Agent.Core;
using Prism.Commands;

namespace EdgeVoice.Agent.Desktop.ViewModels;

public sealed record HistoryItem(string Time, string Query, string Response);

/// <summary>대화 히스토리 조회 (모든 세션, 음성 턴 포함).</summary>
public sealed class HistoryViewModel : PageViewModel
{
    private readonly EdgeVoiceApiClient _api;

    public HistoryViewModel(EdgeVoiceApiClient api)
    {
        _api = api;
        RefreshCommand = new DelegateCommand(Refresh);
        Refresh();
    }

    public ObservableCollection<HistoryItem> Items { get; } = new();

    public DelegateCommand RefreshCommand { get; }

    private async void Refresh() => await RunAsync(async () =>
    {
        // 백엔드는 최신순 messages 를 준다 → 시간순으로 돌려 질문·응답을 짝짓고 최신 대화를 위에 둔다
        var data = await _api.GetAsync("api/history?limit=500");
        var messages = (data?["messages"]?.AsArray() ?? new JsonArray()).Reverse();
        Items.Clear();
        HistoryItem? pending = null;
        foreach (var m in messages)
        {
            var content = m?["content"]?.ToString() ?? "";
            if (m?["role"]?.ToString() == "user")
            {
                if (pending is not null)
                {
                    Items.Insert(0, pending);
                }

                var voice = m["source"]?.ToString() == "voice" ? "🎙 " : "";
                pending = new HistoryItem(FormatTime(m["timestamp"]?.ToString()), voice + content, "");
            }
            else if (m?["role"]?.ToString() == "assistant")
            {
                Items.Insert(0, (pending ?? new HistoryItem(FormatTime(m["timestamp"]?.ToString()), "", "")) with { Response = content });
                pending = null;
            }
        }

        if (pending is not null)
        {
            Items.Insert(0, pending);
        }

        Status = Items.Count == 0 ? "대화 기록이 없습니다." : $"{Items.Count}건";
    });

    private static string FormatTime(string? value) =>
        DateTime.TryParse(value, out var t) ? t.ToLocalTime().ToString("yyyy-MM-dd HH:mm") : value ?? "-";
}
