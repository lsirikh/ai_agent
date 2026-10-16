using System.Collections.ObjectModel;
using System.Text.Json.Nodes;
using EdgeVoice.Agent.Core;
using Prism.Commands;

namespace EdgeVoice.Agent.Desktop.ViewModels;

public sealed record HistoryItem(string Time, string Query, string Response);

/// <summary>대화 히스토리 조회.</summary>
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
        var data = await _api.GetAsync("api/history");
        Items.Clear();
        foreach (var item in data?["conversations"]?.AsArray() ?? new JsonArray())
        {
            Items.Add(new HistoryItem(
                item?["timestamp"]?.ToString() ?? "-",
                item?["query"]?.ToString() ?? "",
                item?["response"]?.ToString() ?? ""));
        }

        Status = Items.Count == 0 ? "대화 기록이 없습니다." : $"{Items.Count}건";
    });
}
