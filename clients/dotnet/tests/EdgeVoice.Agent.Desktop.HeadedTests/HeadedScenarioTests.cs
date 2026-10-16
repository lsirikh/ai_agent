using Avalonia.Controls;
using Avalonia.Media;
using Avalonia.Styling;

namespace EdgeVoice.Agent.Desktop.HeadedTests;

/// <summary>[헤디드] 실제 창 + 실제 백엔드 시나리오. 단계마다 bin/.../screenshots 에 화면을 남긴다.</summary>
public class HeadedScenarioTests
{
    [HeadedFact]
    public Task 실제_창에서_6개_페이지를_순회하며_라이트_다크_화면을_남긴다() => HeadedApp.Run(async () =>
    {
        var (c, w, main) = HeadedApp.Open();
        try
        {
            await HeadedApp.WaitUntil(() => main.Dashboard.Services.Count > 0 && main.Dashboard.LogLevelSeries.Length == 1);
            await Task.Delay(1500); // 차트 애니메이션
            Assert.True(w.IsVisible);
            Assert.NotNull(w.TryGetPlatformHandle());

            var nav = w.FindControl<TabControl>("Nav")!;
            foreach (var dark in new[] { false, true })
            {
                main.IsDarkTheme = dark;
                Assert.Equal(dark ? ThemeVariant.Dark : ThemeVariant.Light, w.ActualThemeVariant);
                Assert.Equal(Color.Parse(dark ? "#1F1F1F" : "#F5F5F5"), ((ISolidColorBrush)w.Background!).Color);
                for (var i = 0; i < nav.ItemCount; i++)
                {
                    nav.SelectedIndex = i;
                    await Task.Delay(400);
                    var header = ((TabItem)nav.Items[i]!).Header;
                    var path = HeadedApp.Shot(w, $"headed-{(dark ? "dark" : "light")}-{i + 1}-{header}");
                    Assert.True(new FileInfo(path).Length > 5_000);
                }
            }
        }
        finally
        {
            HeadedApp.Close(c, w, main);
        }
    });

    [HeadedFact]
    public Task 실제_백엔드_대시보드_KPI와_차트가_채워진다() => HeadedApp.Run(async () =>
    {
        var (c, w, main) = HeadedApp.Open();
        try
        {
            var d = main.Dashboard;
            await HeadedApp.WaitUntil(() => d.Services.Count > 0 && d.ServiceHealthSeries.Length == 2 && d.LogServiceSeries.Length == 1);

            Assert.StartsWith("갱신:", d.Status);
            Assert.Contains(d.SystemStatus, new[] { "System Online", "Some Services Offline" });
            Assert.Single(d.GpuHistory);
            Assert.NotEqual("-", d.Gpu);
            Assert.NotEmpty(d.LogLevelXAxes[0].Labels!);
        }
        finally
        {
            HeadedApp.Close(c, w, main);
        }
    });

    [HeadedFact]
    public Task 실제_백엔드_설정_지식_히스토리_로그를_불러온다() => HeadedApp.Run(async () =>
    {
        var (c, w, main) = HeadedApp.Open();
        try
        {
            await HeadedApp.WaitUntil(() => main.Settings.TtsEngines.Count > 0 && main.Logs.Stats.Length > 0
                && main.Knowledge.Status.Length > 0 && main.History.Status.Length > 0);

            Assert.NotNull(main.Settings.TtsEngine);
            Assert.StartsWith("Total", main.Logs.Stats);
            Assert.StartsWith("문서", main.Knowledge.Status);
            Assert.DoesNotContain("오류", main.History.Status);
        }
        finally
        {
            HeadedApp.Close(c, w, main);
        }
    });

    [HeadedFact]
    public Task 실제_LLM_에_채팅을_보내면_응답이_스트리밍된다() => HeadedApp.Run(async () =>
    {
        var (c, w, main) = HeadedApp.Open();
        try
        {
            var chat = main.Chat;
            w.FindControl<TabControl>("Nav")!.SelectedIndex = 1;
            // 채팅은 활성 세션 히스토리를 먼저 불러온다 → 그 뒤에 붙는 두 말풍선을 본다
            await HeadedApp.WaitUntil(() => chat.SessionId is not null);
            await Task.Delay(1000);
            var before = chat.Messages.Count;
            chat.UseRag = false;
            chat.Input = "한 문장으로 인사해 줘.";
            chat.SendCommand.Execute();

            await HeadedApp.WaitUntil(() => !chat.IsBusy && chat.Messages.Count == before + 2, 120_000);
            HeadedApp.Shot(w, "headed-chat");

            Assert.False(string.IsNullOrWhiteSpace(chat.Messages[^1].Text), chat.Status);
            Assert.DoesNotContain("Error", chat.Messages[^1].Text);
        }
        finally
        {
            HeadedApp.Close(c, w, main);
        }
    });
}
