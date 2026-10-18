using System.Net.Http.Json;
using System.Text.Json.Nodes;
using Avalonia.Controls;
using Avalonia.VisualTree;
using EdgeVoice.Agent.Core;

namespace EdgeVoice.Agent.Desktop.HeadedTests;

/// <summary>[헤디드] 실제 창 + 실제 백엔드: 설정 "지역 및 시간" 카드가 서버 값·PC 시간대와 맞는다.</summary>
public class RegionTimeHeadedTests
{
    private static T Named<T>(Window w, string name) where T : Control
        => w.GetVisualDescendants().OfType<T>().Single(x => x.Name == name);

    [HeadedFact]
    public Task 지역_및_시간_카드가_서버_설정과_PC_시간대를_보여준다() => HeadedApp.Run(async () =>
    {
        using var http = new HttpClient { BaseAddress = new Uri(HeadedApp.BackendUrl) };
        var server = (await http.GetFromJsonAsync<JsonNode>("api/settings/tools"))!;
        var (c, w, main) = HeadedApp.Open();
        try
        {
            var s = main.Settings;
            await HeadedApp.WaitUntil(() => s.TimeComparison.Length > 0 && s.Location.Length > 0);
            var nav = w.FindControl<TabControl>("Nav")!;
            nav.SelectedItem = nav.Items.Cast<TabItem>().Single(t => (string)t.Header! == "Settings");
            await Task.Delay(500);
            Named<TextBox>(w, "LocationBox").BringIntoView();
            await Task.Delay(500);
            HeadedApp.Shot(w, "headed-region-time");

            Assert.Equal(server["location"]!.ToString(), s.Location);
            Assert.Equal(server["follow_pc_timezone"]!.GetValue<bool>(), s.FollowPcTimeZone);
            if (s.FollowPcTimeZone)
            {
                Assert.Equal(PcTimeZone.IanaId(), s.TimeZone);
                Assert.False(Named<ComboBox>(w, "TimeZoneCombo").IsEnabled);
            }

            Assert.Contains("서버 시각", s.TimeComparison);
            Assert.Contains("PC 시각", s.TimeComparison);
        }
        finally
        {
            HeadedApp.Close(c, w, main);
        }
    });
}
