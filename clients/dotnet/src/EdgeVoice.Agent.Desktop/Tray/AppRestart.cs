using System;
using System.Diagnostics;

namespace EdgeVoice.Agent.Desktop.Tray;

/// <summary>트레이 '다시 시작': 같은 프로그램을 새로 띄운 뒤 지금 것을 끝낸다(설정·연결을 새로 읽는다).</summary>
public static class AppRestart
{
    /// <returns>새로 띄웠으면 true. 띄우지 못하면 지금 것을 끄지 않는다.</returns>
    public static bool Restart(Func<ProcessStartInfo, Process?> start, Action exit)
    {
        var path = Environment.ProcessPath;
        if (string.IsNullOrEmpty(path))
        {
            return false;
        }

        try
        {
            start(new ProcessStartInfo(path)
            {
                UseShellExecute = false,
                WorkingDirectory = AppContext.BaseDirectory,
            });
        }
        catch (Exception)
        {
            return false;
        }

        exit();
        return true;
    }
}
