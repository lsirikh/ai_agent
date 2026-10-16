using System.Net.Http.Json;
using System.Text.Json.Nodes;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Primitives;
using Avalonia.VisualTree;
using EdgeVoice.Agent.Desktop.ViewModels;

namespace EdgeVoice.Agent.Desktop.HeadedTests;

/// <summary>[헤디드] 실제 창 + 실제 백엔드: 설정 콤보박스 = 실행 값, 로그 기본 필터·머리글, 지식 조각 수, 빈 상태 문구.</summary>
public class PageConsistencyHeadedTests
{
    private static async Task<JsonNode> Get(string path)
    {
        using var http = new HttpClient { BaseAddress = new Uri(HeadedApp.BackendUrl) };
        return (await http.GetFromJsonAsync<JsonNode>(path))!;
    }

    private static Control Open(Window w, string header)
    {
        var nav = w.FindControl<TabControl>("Nav")!;
        nav.SelectedItem = nav.Items.Cast<TabItem>().Single(t => (string)t.Header! == header);
        return (Control)nav.SelectedContent!;
    }

    [HeadedFact]
    public Task 설정_콤보박스_표시값이_실행_값과_같고_빈_콤보박스가_없다() => HeadedApp.Run(async () =>
    {
        var current = (await Get("api/settings/options"))["current"]!;
        var (c, w, main) = HeadedApp.Open();
        try
        {
            var s = main.Settings;
            await HeadedApp.WaitUntil(() => s.LlmModel is not null && s.TtsVoice is not null);
            var page = Open(w, "Settings");
            await Task.Delay(500);
            HeadedApp.Shot(w, "headed-settings-runtime");

            Assert.Equal(current["llm_model"]!.ToString(), s.LlmModel);
            Assert.Equal(current["stt_model"]!.ToString(), s.SttModel);
            Assert.Equal(current["tts_engine"]!.ToString(), s.TtsEngine);
            Assert.Equal(current["tts_voice"]!.ToString(), s.TtsVoice);
            Assert.Equal(current["wake_word_threshold"]!.GetValue<double>(), s.WakeWordThreshold);
            Assert.All(page.GetVisualDescendants().OfType<ComboBox>(), combo => Assert.NotNull(combo.SelectedItem));
            Assert.Equal(s.LlmModel, ((OptionItem)w.FindControl<ComboBox>("LlmModelCombo")!.SelectedItem!).Id);
        }
        finally
        {
            HeadedApp.Close(c, w, main);
        }
    });

    [HeadedFact]
    public Task 로그_콤보박스_기본값과_열_머리글이_잘리지_않는다() => HeadedApp.Run(async () =>
    {
        var (c, w, main) = HeadedApp.Open();
        try
        {
            await HeadedApp.WaitUntil(() => main.Logs.Logs.Count > 0);
            Open(w, "Logs");
            await Task.Delay(500);
            HeadedApp.Shot(w, "headed-logs-default");

            Assert.Equal("전체 서비스", ((OptionItem)w.FindControl<ComboBox>("LogServiceCombo")!.SelectedItem!).Label);
            Assert.Equal("INFO 이상", ((OptionItem)w.FindControl<ComboBox>("LogLevelCombo")!.SelectedItem!).Label);
            Assert.True(main.Logs.Logs.Count(l => l.IsDebug) * 2 < main.Logs.Logs.Count, "기본 목록의 절반 이상이 DEBUG");
            foreach (var header in w.FindControl<DataGrid>("LogGrid")!.GetVisualDescendants().OfType<DataGridColumnHeader>())
            {
                foreach (var text in header.GetVisualDescendants().OfType<TextBlock>().Where(t => !string.IsNullOrEmpty(t.Text)))
                {
                    var x = text.TranslatePoint(default, header)!.Value.X;
                    text.Measure(Size.Infinity);
                    Assert.True(x + text.DesiredSize.Width <= header.Bounds.Width + 0.5, $"머리글 '{text.Text}' 잘림");
                }
            }
        }
        finally
        {
            HeadedApp.Close(c, w, main);
        }
    });

    [HeadedFact]
    public Task 지식_조각_수가_실제_값으로_보인다() => HeadedApp.Run(async () =>
    {
        var docs = (await Get("api/knowledge/documents"))["documents"]!.AsArray();
        var (c, w, main) = HeadedApp.Open();
        try
        {
            await HeadedApp.WaitUntil(() => main.Knowledge.Documents.Count == docs.Count && main.Knowledge.Status.Length > 0);
            Open(w, "Knowledge");
            await Task.Delay(400);
            HeadedApp.Shot(w, "headed-knowledge");

            foreach (var doc in docs)
            {
                var item = main.Knowledge.Documents.Single(d => d.Id == doc!["doc_id"]!.ToString());
                Assert.StartsWith($"{doc!["chunk_count"]} chunks", item.Meta);
            }
        }
        finally
        {
            HeadedApp.Close(c, w, main);
        }
    });

    [HeadedFact]
    public Task 빈_상태_문구는_목록이_비었을_때만_보인다() => HeadedApp.Run(async () =>
    {
        var (c, w, main) = HeadedApp.Open();
        try
        {
            await HeadedApp.WaitUntil(() => main.Knowledge.Status.Length > 0 && main.History.Status.Length > 0 && main.Dashboard.Services.Count > 0);
            foreach (var (page, name, count) in new (string, string, Func<int>)[]
                     {
                         ("Dashboard", "DashboardEmpty", () => main.Dashboard.Services.Count),
                         ("Chat", "ChatEmpty", () => main.Chat.Messages.Count),
                         ("Knowledge", "KnowledgeEmpty", () => main.Knowledge.Documents.Count),
                         ("History", "HistoryEmpty", () => main.History.Items.Count),
                         ("Logs", "LogsEmpty", () => main.Logs.Logs.Count),
                     })
            {
                Open(w, page);
                await Task.Delay(300);
                Assert.Equal(count() == 0, w.FindControl<TextBlock>(name)!.IsEffectivelyVisible);
            }
        }
        finally
        {
            HeadedApp.Close(c, w, main);
        }
    });
}
