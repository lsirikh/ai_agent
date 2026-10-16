using Avalonia;
using Avalonia.Headless.XUnit;
using Avalonia.Media.Imaging;
using Avalonia.Platform;
using EdgeVoice.Agent.Core;
using EdgeVoice.Agent.Desktop.Tray;

namespace EdgeVoice.Agent.Desktop.Tests;

/// <summary>[헤드리스] 트레이 아이콘 파형(듣기=좁쌀, 말하기=물결) 렌더링 시나리오.</summary>
public class TrayScenarioTests
{
    private static byte[] Pixels(Bitmap bmp)
    {
        var size = bmp.PixelSize;
        var buffer = new byte[size.Width * size.Height * 4];
        var handle = System.Runtime.InteropServices.GCHandle.Alloc(buffer, System.Runtime.InteropServices.GCHandleType.Pinned);
        try
        {
            bmp.CopyPixels(new PixelRect(size), handle.AddrOfPinnedObject(), buffer.Length, size.Width * 4);
        }
        finally
        {
            handle.Free();
        }

        return buffer;
    }

    [AvaloniaTheory]
    [InlineData(VoiceState.Idle)]
    [InlineData(VoiceState.Listening)]
    [InlineData(VoiceState.Thinking)]
    [InlineData(VoiceState.Speaking)]
    [InlineData(VoiceState.Error)]
    public void 모든_상태에서_32px_트레이_아이콘이_그려진다(VoiceState state)
    {
        using var bmp = RippleRenderer.RenderBitmap(32, state, 0.3, 0.5f);

        Assert.Equal(new PixelSize(32, 32), bmp.PixelSize);
        Assert.Contains(Pixels(bmp), b => b != 0);
    }

    [AvaloniaFact]
    public void 듣기와_말하기_파형은_서로_다르게_그려진다()
    {
        using var listening = RippleRenderer.RenderBitmap(32, VoiceState.Listening, 0.3, 0.5f);
        using var speaking = RippleRenderer.RenderBitmap(32, VoiceState.Speaking, 0.3, 0.5f);

        Assert.NotEqual(Pixels(listening), Pixels(speaking));
    }

    [AvaloniaFact]
    public void 파형은_위상에_따라_움직인다()
    {
        using var a = RippleRenderer.RenderBitmap(32, VoiceState.Speaking, 0.1, 0);
        using var b = RippleRenderer.RenderBitmap(32, VoiceState.Speaking, 0.6, 0);

        Assert.NotEqual(Pixels(a), Pixels(b));
    }

    [Theory]
    [InlineData(VoiceState.Listening, "듣는 중")]
    [InlineData(VoiceState.Speaking, "말하는 중")]
    [InlineData(VoiceState.Thinking, "생각 중")]
    [InlineData(VoiceState.Error, "오류")]
    // 마이크가 상시 켜져 있으므로 대기 툴팁은 깨우는 말을 안내한다
    [InlineData(VoiceState.Idle, "\"Hey Jarvis\" 대기")]
    public void 상태_문구(VoiceState state, string text) => Assert.Equal(text, TrayController.StateText(state));
}
