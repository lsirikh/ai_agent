using System.IO;
using Avalonia;
using EdgeVoice.Agent.Core;
using EdgeVoice.Agent.Desktop.Tray;
using Xunit;

namespace EdgeVoice.Agent.Desktop.Tests;

/// <summary>
/// 사용자 요청(2026-10-19): 파형 창을 끌어 옮기고(구석에 박혀 있지 않게 — 옮긴 자리를 기억),
/// 파형을 한 번 누르면 입력받고 한 번 더 누르면 정지.
/// </summary>
public class OrbClickAndPlacementTests
{
    [Theory]
    [InlineData(VoiceState.Idle, OrbAction.Listen)]
    [InlineData(VoiceState.Error, OrbAction.Listen)]
    [InlineData(VoiceState.Listening, OrbAction.Stop)]
    [InlineData(VoiceState.Thinking, OrbAction.Stop)]
    [InlineData(VoiceState.Speaking, OrbAction.Stop)]
    public void 파형을_누르면_대기에서는_듣고_듣거나_답하는_중에는_멈춘다(VoiceState state, OrbAction expected)
    {
        Assert.Equal(expected, TrayController.ActionFor(state));
    }

    private static readonly PixelRect[] TwoScreens =
    {
        new(0, 0, 1920, 1040),
        new(1920, 0, 1920, 1040),
    };

    [Fact]
    public void 옮겨_둔_자리가_화면_안이면_그_자리에_띄운다()
    {
        var size = new PixelSize(151, 127);

        Assert.Equal(new PixelPoint(2500, 300), OrbPlacement.Fit(new PixelPoint(2500, 300), TwoScreens, size));
        Assert.Equal(new PixelPoint(100, 100), OrbPlacement.Fit(new PixelPoint(100, 100), TwoScreens, size));
    }

    [Fact]
    public void 화면이_없어졌거나_저장한_자리가_없으면_기본_자리에_띄운다()
    {
        var size = new PixelSize(151, 127);

        Assert.Null(OrbPlacement.Fit(new PixelPoint(5000, 300), TwoScreens, size)); // 떼어 낸 모니터
        Assert.Null(OrbPlacement.Fit(null, TwoScreens, size));
    }

    [Fact]
    public void 옮긴_자리를_파일에_적고_다시_읽는다()
    {
        var path = Path.Combine(Path.GetTempPath(), $"orb-{System.Guid.NewGuid():N}", "orb-position.txt");
        try
        {
            Assert.Null(OrbPlacement.Load(path));

            OrbPlacement.Save(path, new PixelPoint(2564, 1226));

            Assert.Equal(new PixelPoint(2564, 1226), OrbPlacement.Load(path));
        }
        finally
        {
            Directory.Delete(Path.GetDirectoryName(path)!, recursive: true);
        }
    }
}
