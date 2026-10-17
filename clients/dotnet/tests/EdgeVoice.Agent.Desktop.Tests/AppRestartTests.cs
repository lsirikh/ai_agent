using System;
using System.Collections.Generic;
using Avalonia.Headless.XUnit;
using EdgeVoice.Agent.Desktop.Tray;

namespace EdgeVoice.Agent.Desktop.Tests;

/// <summary>트레이 '다시 시작' (사용자 요청 2026-10-18): 같은 프로그램을 새로 띄운 뒤 지금 것을 끝낸다.</summary>
public class AppRestartTests
{
    [Fact]
    public void 같은_프로그램을_새로_띄운_뒤_종료한다()
    {
        var calls = new List<string>();

        AppRestart.Restart(psi => { calls.Add("start:" + psi.FileName); return null; }, () => calls.Add("exit"));

        Assert.Equal(new[] { "start:" + Environment.ProcessPath, "exit" }, calls);
    }

    [Fact]
    public void 새로_띄우지_못하면_끄지_않는다()
    {
        var exited = false;

        var ok = AppRestart.Restart(_ => throw new InvalidOperationException("no"), () => exited = true);

        Assert.False(ok);
        Assert.False(exited);
    }

    [AvaloniaFact]
    public void 트레이_메뉴에_다시_시작이_있다() =>
        Assert.Contains("다시 시작", TrayController.MenuTexts);
}
