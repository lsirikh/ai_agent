using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Threading.Tasks;

namespace EdgeVoice.Agent.Desktop;

/// <summary>
/// 백엔드가 서비스를 다시 만들지 못할 때(컨테이너 안에 docker 가 없음) 이 PC 의 docker 로 다시 만든다.
/// 백엔드 포트를 publish 한 컨테이너의 compose 라벨(프로젝트·폴더·파일)로 같은 프로젝트를 찾으므로
/// 백엔드가 이 PC 의 docker 에 없으면(원격·테스트용 가짜 백엔드) 아무것도 실행하지 않는다.
/// </summary>
public static class HostCompose
{
    /// <returns>다시 만들었으면 null, 못 했으면 이유.</returns>
    public static async Task<string?> RestartAsync(Uri backend, string service)
    {
        if (!backend.IsLoopback)
        {
            return "백엔드가 이 PC 에 있지 않아 다시 만들 수 없습니다";
        }

        try
        {
            var (_, found) = await RunAsync("ps", "--filter", $"publish={backend.Port}", "--format",
                "{{.Label \"com.docker.compose.project\"}}|{{.Label \"com.docker.compose.project.working_dir\"}}|{{.Label \"com.docker.compose.project.config_files\"}}");
            var labels = found.Split('\n', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
                .FirstOrDefault()?.Split('|');
            if (labels is not [{ Length: > 0 } project, { Length: > 0 } folder, { Length: > 0 } files])
            {
                return "이 PC 의 docker 에서 백엔드 컨테이너를 찾지 못했습니다";
            }

            var args = new List<string> { "compose", "-p", project, "--project-directory", folder };
            foreach (var file in files.Split(','))
            {
                args.Add("-f");
                args.Add(file);
            }

            args.AddRange(new[] { "up", "-d", service });
            var (exit, output) = await RunAsync(args.ToArray());
            return exit == 0 ? null : output.Trim();
        }
        catch (Exception ex)
        {
            // docker 가 설치되어 있지 않은 PC
            return ex.Message;
        }
    }

    private static async Task<(int Exit, string Output)> RunAsync(params string[] args)
    {
        var info = new ProcessStartInfo("docker")
        {
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true,
        };
        foreach (var arg in args)
        {
            info.ArgumentList.Add(arg);
        }

        using var process = Process.Start(info)!;
        var stdout = process.StandardOutput.ReadToEndAsync();
        var stderr = process.StandardError.ReadToEndAsync();
        await process.WaitForExitAsync();
        return (process.ExitCode, await stdout + await stderr);
    }
}
