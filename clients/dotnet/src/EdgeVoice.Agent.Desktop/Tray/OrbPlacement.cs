using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Avalonia;

namespace EdgeVoice.Agent.Desktop.Tray;

/// <summary>
/// 파형 창을 끌어 옮긴 자리를 기억한다(사용자 요청 2026-10-19: 구석에 박혀 있지 않게).
/// 그 화면이 없어졌으면(모니터를 뗌) 기본 자리(오른쪽 아래)에 띄운다.
/// </summary>
public static class OrbPlacement
{
    public static string DefaultPath { get; } = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "EdgeVoice", "orb-position.txt");

    /// <summary>저장한 자리에 창이 한 화면 안에 다 들어가면 그 자리, 아니면 null.</summary>
    public static PixelPoint? Fit(PixelPoint? saved, IEnumerable<PixelRect> workingAreas, PixelSize size)
    {
        if (saved is not { } point)
        {
            return null;
        }

        var window = new PixelRect(point, size);
        return workingAreas.Any(area => area.Contains(window)) ? point : null;
    }

    public static PixelPoint? Load(string path)
    {
        try
        {
            var parts = File.ReadAllText(path).Split(',');
            return new PixelPoint(int.Parse(parts[0]), int.Parse(parts[1]));
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException
                                      or FormatException or IndexOutOfRangeException)
        {
            return null;
        }
    }

    public static void Save(string path, PixelPoint point)
    {
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            File.WriteAllText(path, $"{point.X},{point.Y}");
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException)
        {
            // 자리를 못 적어도 창은 그대로 쓴다(다음에 기본 자리에 뜰 뿐)
        }
    }
}
