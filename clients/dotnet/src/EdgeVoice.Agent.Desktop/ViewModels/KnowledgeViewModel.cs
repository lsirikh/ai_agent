using System;
using System.Collections.ObjectModel;
using System.Net.Http;
using System.Text.Json.Nodes;
using EdgeVoice.Agent.Core;
using Microsoft.Win32;
using Prism.Commands;

namespace EdgeVoice.Agent.Desktop.ViewModels;

public sealed record DocumentItem(string Id, string Filename, string Meta);

/// <summary>지식 베이스: 문서 업로드/목록/삭제.</summary>
public sealed class KnowledgeViewModel : PageViewModel
{
    private readonly EdgeVoiceApiClient _api;

    public KnowledgeViewModel(EdgeVoiceApiClient api)
    {
        _api = api;
        RefreshCommand = new DelegateCommand(Refresh);
        UploadCommand = new DelegateCommand(Upload);
        DeleteCommand = new DelegateCommand<DocumentItem>(Delete);
        Refresh();
    }

    public ObservableCollection<DocumentItem> Documents { get; } = new();

    public DelegateCommand RefreshCommand { get; }

    public DelegateCommand UploadCommand { get; }

    public DelegateCommand<DocumentItem> DeleteCommand { get; }

    private async void Refresh() => await RunAsync(async () =>
    {
        var data = await _api.GetAsync("api/knowledge/documents");
        Documents.Clear();
        foreach (var doc in data?["documents"]?.AsArray() ?? new JsonArray())
        {
            var uploaded = DateTime.TryParse(doc?["uploaded_at"]?.ToString(), out var d) ? d.ToShortDateString() : "-";
            Documents.Add(new DocumentItem(
                doc?["id"]?.ToString() ?? "",
                doc?["filename"]?.ToString() ?? "",
                $"{doc?["chunk_count"] ?? 0} chunks | {uploaded}"));
        }

        Status = $"문서 {Documents.Count}개";
    });

    private async void Upload()
    {
        var dialog = new OpenFileDialog { Multiselect = true, Filter = "문서|*.pdf;*.txt;*.md;*.docx|모든 파일|*.*" };
        if (dialog.ShowDialog() != true)
        {
            return;
        }

        foreach (var file in dialog.FileNames)
        {
            Status = "업로드 중: " + file;
            await RunAsync(() => _api.UploadAsync("api/knowledge/upload", file), "업로드 완료");
        }

        Refresh();
    }

    private async void Delete(DocumentItem? doc)
    {
        if (doc is null || System.Windows.MessageBox.Show($"'{doc.Filename}' 문서를 삭제할까요?", "EdgeVoice",
                System.Windows.MessageBoxButton.YesNo) != System.Windows.MessageBoxResult.Yes)
        {
            return;
        }

        await RunAsync(() => _api.SendAsync(HttpMethod.Delete, $"api/knowledge/documents/{doc.Id}", null));
        Refresh();
    }
}
