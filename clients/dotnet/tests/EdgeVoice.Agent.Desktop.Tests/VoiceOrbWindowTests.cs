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
        // 196 × 0.65 = 127 에 버튼 줄(중단·음소거, 사용자 요청 2026-10-18) 30 을 더했다
        Assert.Equal(157, orb.Height);
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
    [AvaloniaFact]
    public void 오른쪽_아래_버튼_줄에서_중단을_누르면_중단을_요청한다()
    {
        // 사용자 요청(2026-10-18): 자비스가 말을 한번 시작하면 중단을 못 한다
        var orb = new VoiceOrbWindow();
        var stopped = 0;
        orb.StopRequested += () => stopped++;
        var stop = orb.FindControl<Button>("StopButton")!;

        stop.RaiseEvent(new Avalonia.Interactivity.RoutedEventArgs(Button.ClickEvent));

        Assert.Equal(1, stopped);
        Assert.Equal(Avalonia.Layout.HorizontalAlignment.Right,
            orb.FindControl<StackPanel>("Buttons")!.HorizontalAlignment);
        Assert.False(string.IsNullOrEmpty(ToolTip.GetTip(stop) as string));
    }

    [AvaloniaFact]
    public void 버튼_줄의_음소거는_마이크를_끄고_켠다()
    {
        var orb = new VoiceOrbWindow();
        var toggled = 0;
        orb.TalkRequested += () => toggled++;

        orb.FindControl<Button>("MuteButton")!.RaiseEvent(
            new Avalonia.Interactivity.RoutedEventArgs(Button.ClickEvent));

        Assert.Equal(1, toggled);
    }
}
