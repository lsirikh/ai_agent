using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.IO;
using System.Net.Http;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using EdgeVoice.Agent.Core;
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
        RefreshCommand = new DelegateCommand(() => _ = Refresh());
        UploadCommand = new DelegateCommand(Upload);
        DeleteCommand = new DelegateCommand<DocumentItem>(Delete);
        _ = Refresh();
    }

    public string SupportedFormats => "지원 형식: .txt .md .pdf .docx .ppt .pptx";

    public ObservableCollection<DocumentItem> Documents { get; } = new();

    public DelegateCommand RefreshCommand { get; }

    public DelegateCommand UploadCommand { get; }

    public DelegateCommand<DocumentItem> DeleteCommand { get; }

    private Task Refresh() => RunAsync(async () =>
    {
        var data = await _api.GetAsync("api/knowledge/documents");
        Documents.Clear();
        foreach (var doc in data?["documents"]?.AsArray() ?? new JsonArray())
        {
            var uploaded = DateTime.TryParse(doc?["uploaded_at"]?.ToString(), out var d) ? d.ToLocalTime().ToString("yyyy-MM-dd HH:mm") : "-";
            Documents.Add(new DocumentItem(
                // 백엔드는 doc_id 로 준다 (예전 형식 id 도 받는다)
                (doc?["doc_id"] ?? doc?["id"])?.ToString() ?? "",
                doc?["filename"]?.ToString() ?? "",
                $"{doc?["chunk_count"] ?? 0} chunks | {uploaded}"));
        }

        Status = $"문서 {Documents.Count}개";
    });

    private async void Upload()
    {
        var files = await Dialogs.OpenFilesAsync();
        if (files.Count == 0)
        {
            return;
        }

        var results = new List<string>();
        for (var i = 0; i < files.Count; i++)
        {
            var name = Path.GetFileName(files[i]);
            Status = $"업로드 중 ({i + 1}/{files.Count}): {name}";
            try
            {
                var res = await _api.UploadAsync("api/knowledge/upload", files[i]);
                results.Add($"{name} 성공({res?["chunk_count"] ?? 0}개 조각)");
            }
            catch (Exception ex)
            {
                results.Add($"{name} 실패: {ex.Message}");
            }
        }

        await Refresh();
        Status = "업로드 결과: " + string.Join(" / ", results);
    }

    private async void Delete(DocumentItem? doc)
    {
        if (doc is null || !await Dialogs.ConfirmAsync("EdgeVoice", $"'{doc.Filename}' 문서를 삭제할까요?"))
        {
            return;
        }

        await RunAsync(() => _api.SendAsync(HttpMethod.Delete, $"api/knowledge/documents/{doc.Id}", null));
        await Refresh();
    }
}
