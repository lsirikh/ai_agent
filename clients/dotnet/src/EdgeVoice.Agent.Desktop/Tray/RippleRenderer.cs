using System;
using Avalonia;
using Avalonia.Media;
using Avalonia.Media.Imaging;
using EdgeVoice.Agent.Core;

namespace EdgeVoice.Agent.Desktop.Tray;

/// <summary>
/// 상태별 파형 그리기. 트레이 아이콘(작은 비트맵)과 오버레이(큰 컨트롤)가 같은 그림을 쓴다.
/// - Listening(사용자 음성 수신): 파란 "좁쌀" 점들이 바깥으로 퍼짐, 마이크 레벨에 따라 점 크기 변화
/// - Speaking(에이전트 발화): 초록 "물결" 원이 바깥으로 퍼짐
/// - Thinking(STT/LLM 처리): 보라 점 3개가 회전
/// - Idle: 회색 점, Error: 빨간 점
/// </summary>
public static class RippleRenderer
{
    public static Color ColorOf(VoiceState state) => state switch
    {
        VoiceState.Listening => Color.FromRgb(59, 130, 246),
        VoiceState.Speaking => Color.FromRgb(34, 197, 94),
        VoiceState.Thinking => Color.FromRgb(167, 139, 250),
        VoiceState.Error => Color.FromRgb(239, 68, 68),
        _ => Color.FromRgb(113, 113, 122),
    };

    /// <summary>트레이 아이콘용 비트맵.</summary>
    public static Bitmap RenderBitmap(int size, VoiceState state, double phase, float level)
    {
        var bmp = new RenderTargetBitmap(new PixelSize(size, size));
        using (var ctx = bmp.CreateDrawingContext())
        {
            Draw(ctx, size, state, phase, level);
        }

        return bmp;
    }

    /// <param name="phase">0~1 을 반복하는 애니메이션 위상</param>
    /// <param name="level">마이크 입력 레벨 0~1</param>
    public static void Draw(DrawingContext g, double size, VoiceState state, double phase, float level)
    {
        var color = ColorOf(state);
        var center = new Point(size / 2, size / 2);
        var core = size * 0.16;
        var maxR = size / 2 - 1;

        switch (state)
        {
            case VoiceState.Speaking:
                for (var k = 0; k < 3; k++)
                {
                    var t = (phase + k / 3.0) % 1.0;
                    var r = core + (maxR - core) * t;
                    var pen = new Pen(new SolidColorBrush(color, 1 - t), Math.Max(1.5, size / 14));
                    g.DrawEllipse(null, pen, center, r, r);
                }

                break;

            case VoiceState.Listening:
                {
                    const int dots = 10;
                    var dotR = Math.Max(1, size / 22 * (0.7 + level * 1.5));
                    for (var k = 0; k < 3; k++)
                    {
                        var t = (phase + k / 3.0) % 1.0;
                        var r = core + (maxR - core - dotR) * t;
                        var brush = new SolidColorBrush(color, 1 - t);
                        for (var i = 0; i < dots; i++)
                        {
                            var a = 2 * Math.PI * (i + k * 0.5) / dots;
                            g.DrawEllipse(brush, null, center + new Point(r * Math.Cos(a), r * Math.Sin(a)), dotR, dotR);
                        }
                    }
                }

                break;

            case VoiceState.Thinking:
                {
                    var brush = new SolidColorBrush(color);
                    var r = maxR * 0.65;
                    var dotR = Math.Max(1.5, size / 12);
                    for (var i = 0; i < 3; i++)
                    {
                        var a = 2 * Math.PI * (phase + i / 3.0);
                        g.DrawEllipse(brush, null, center + new Point(r * Math.Cos(a), r * Math.Sin(a)), dotR, dotR);
                    }
                }

                break;
        }

        // 가운데는 상태 색으로 물든 움직이는 프랙탈(작은 트레이 아이콘은 점이 더 잘 보인다)
        if (size >= 64)
        {
            FractalRenderer.Draw(g, center, size * 0.5, state, level);
        }
        else
        {
            g.DrawEllipse(new SolidColorBrush(color), null, center, core, core);
        }
    }
}
