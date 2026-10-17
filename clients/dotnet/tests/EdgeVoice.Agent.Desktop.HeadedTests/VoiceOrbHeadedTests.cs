using Avalonia;
using Avalonia.Media.Imaging;
using EdgeVoice.Agent.Core;
using EdgeVoice.Agent.Desktop.Tray;

namespace EdgeVoice.Agent.Desktop.HeadedTests;

/// <summary>[헤디드] 떠 있는 음성 오브(65% 크기, 단계는 아이콘만)를 실제 창으로 띄워 찍는다.</summary>
public class VoiceOrbHeadedTests
{
    [HeadedFact]
    public Task 작아진_오브_창을_단계별로_찍는다() => HeadedApp.Run(async () =>
    {
        var orb = new VoiceOrbWindow();
        orb.Show();
        try
        {
            foreach (var (stage, state) in new[] { (PipelineStage.Listen, VoiceState.Listening), (PipelineStage.Llm, VoiceState.Thinking) })
            {
                orb.SetStage(stage);
                orb.Update(state, 0.3, 0.5f, "");
                await Task.Delay(300);
                using var bmp = new RenderTargetBitmap(new PixelSize((int)orb.Width, (int)orb.Height));
                bmp.Render(orb);
                bmp.Save(Path.Combine(HeadedApp.ShotDir, $"headed-orb-{stage}.png"));
            }

            Assert.Equal(151, orb.Bounds.Width);
            Assert.Equal(127, orb.Bounds.Height);
        }
        finally
        {
            orb.Close();
        }
    });
}
