using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;
using Avalonia;
using Avalonia.Media;
using Avalonia.Media.Imaging;
using Avalonia.Platform;
using EdgeVoice.Agent.Core;

namespace EdgeVoice.Agent.Desktop.Tray;

/// <summary>
/// 파형 가운데에 그리는 움직이는 줄리아 집합 프랙탈.
/// 상수 c 를 원 위에서 계속 돌려 모양이 살아 움직이게 하고, 상태 색으로 물들인다.
/// 크기별 비트맵을 재사용해 프레임마다 할당하지 않는다.
/// </summary>
public static class FractalRenderer
{
    private const int MaxIterations = 48;

    private static readonly Stopwatch Clock = Stopwatch.StartNew();
    private static readonly Dictionary<int, (WriteableBitmap Bitmap, int[] Pixels)> Buffers = new();
    private static double _angle;
    private static double _lastSeconds;

    /// <summary>상태별 회전 속도(rad/s). 듣기는 마이크 레벨만큼 빨라진다.</summary>
    private static double SpeedOf(VoiceState state, float level) => state switch
    {
        VoiceState.Listening => 0.45 + level * 1.6,
        VoiceState.Thinking => 1.1,
        VoiceState.Speaking => 0.7,
        VoiceState.Error => 0.05,
        _ => 0.12,
    };

    /// <summary>지름 <paramref name="diameter"/> 픽셀의 원형 프랙탈을 그린다.</summary>
    public static void Draw(DrawingContext g, Point center, double diameter, VoiceState state, float level)
    {
        var size = Math.Max(8, (int)Math.Round(diameter));
        Advance(state, level);

        var (bitmap, pixels) = BufferFor(size);
        Fill(pixels, size, RippleRenderer.ColorOf(state), level);
        using (var frame = bitmap.Lock())
        {
            Marshal.Copy(pixels, 0, frame.Address, pixels.Length);
        }

        g.DrawImage(bitmap, new Rect(center.X - diameter / 2, center.Y - diameter / 2, diameter, diameter));
    }

    private static void Advance(VoiceState state, float level)
    {
        var now = Clock.Elapsed.TotalSeconds;
        var dt = Math.Clamp(now - _lastSeconds, 0, 0.25);
        _lastSeconds = now;
        _angle = (_angle + dt * SpeedOf(state, level)) % (2 * Math.PI);
    }

    private static (WriteableBitmap, int[]) BufferFor(int size)
    {
        if (!Buffers.TryGetValue(size, out var buffer))
        {
            var bitmap = new WriteableBitmap(
                new PixelSize(size, size), new Vector(96, 96), PixelFormat.Bgra8888, AlphaFormat.Premul);
            buffer = (bitmap, new int[size * size]);
            Buffers[size] = buffer;
        }

        return buffer;
    }

    private static void Fill(int[] pixels, int size, Color tint, float level)
    {
        // c 를 반지름 0.7885 원 위에서 돌리면 연결된 줄리아 집합이 계속 모양을 바꾼다
        var cr = 0.7885 * Math.Cos(_angle);
        var ci = 0.7885 * Math.Sin(_angle);
        var zoom = 1.45 - level * 0.25;
        var half = size / 2.0;

        for (var py = 0; py < size; py++)
        {
            for (var px = 0; px < size; px++)
            {
                var nx = (px + 0.5 - half) / half;
                var ny = (py + 0.5 - half) / half;
                var r2 = nx * nx + ny * ny;
                if (r2 > 1)
                {
                    pixels[py * size + px] = 0;
                    continue;
                }

                var zr = nx * zoom;
                var zi = ny * zoom;
                var i = 0;
                while (i < MaxIterations && zr * zr + zi * zi < 16)
                {
                    var t = zr * zr - zi * zi + cr;
                    zi = 2 * zr * zi + ci;
                    zr = t;
                    i++;
                }

                double v;
                if (i == MaxIterations)
                {
                    v = 0.08; // 집합 내부는 어둡게
                }
                else
                {
                    // 부드러운 반복 횟수로 띠 없이 밝기를 준다
                    var smooth = i + 1 - Math.Log(Math.Log(Math.Sqrt(zr * zr + zi * zi))) / Math.Log(2);
                    v = Math.Clamp(smooth / MaxIterations, 0, 1);
                    v = Math.Sqrt(v);
                }

                // 가장자리는 부드럽게 사라지게
                var edge = Math.Clamp((1 - Math.Sqrt(r2)) * half / 1.5, 0, 1);
                pixels[py * size + px] = Shade(tint, v, edge);
            }
        }
    }

    /// <summary>상태 색을 밝기 v 로 칠하고 밝은 곳은 흰색 쪽으로 섞는다. 미리 곱한 알파(BGRA).</summary>
    private static int Shade(Color tint, double v, double alpha)
    {
        var white = Math.Max(0, v - 0.65) / 0.35;
        double Channel(byte c) => (c * v * (1 - white) + 255 * white) * alpha;
        var a = (int)(255 * alpha);
        var r = (int)Math.Min(255, Channel(tint.R));
        var gr = (int)Math.Min(255, Channel(tint.G));
        var b = (int)Math.Min(255, Channel(tint.B));
        return (a << 24) | (r << 16) | (gr << 8) | b;
    }
}
