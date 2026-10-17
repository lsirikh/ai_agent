using Avalonia.Controls;
using Avalonia.Headless.XUnit;
using Avalonia.LogicalTree;
using EdgeVoice.Agent.Desktop.Tray;
using Xunit;

namespace EdgeVoice.Agent.Desktop.Tests;

/// <summary>떠 있는 음성 오브: 사용자 요청(2026-10-17)으로 가로·세로 35% 줄이고 단계는 아이콘만.</summary>
public class VoiceOrbWindowTests
{
    [AvaloniaFact]
    public void 오브_창은_예전의_65퍼센트_크기다()
    {
        var orb = new VoiceOrbWindow();

        Assert.Equal(151, orb.Width); // 232 × 0.65
        Assert.Equal(127, orb.Height); // 196 × 0.65
        Assert.Equal(78, orb.FindControl<RippleView>("Ripple")!.Width); // 120 × 0.65
    }

    [AvaloniaFact]
    public void 단계_칸은_글자_없이_아이콘만_있고_이름은_툴팁으로_남는다()
    {
        var orb = new VoiceOrbWindow();
        var stages = orb.FindControl<StackPanel>("Stages")!;
        var cells = stages.Children.OfType<Border>().ToList();

        Assert.Equal(4, cells.Count);
        Assert.Empty(stages.GetLogicalDescendants().OfType<TextBlock>());
        Assert.All(cells, cell =>
        {
            Assert.Single(cell.GetLogicalDescendants().OfType<PathIcon>());
            Assert.False(string.IsNullOrEmpty(ToolTip.GetTip(cell) as string));
        });
    }
}
