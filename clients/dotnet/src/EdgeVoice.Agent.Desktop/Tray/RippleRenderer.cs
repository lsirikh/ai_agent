using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using EdgeVoice.Agent.Core;

namespace EdgeVoice.Agent.Desktop.Tray;

/// <summary>
/// 상태별 파형 그리기. 트레이 아이콘(작은 크기)과 오버레이(큰 크기)가 같은 그림을 쓴다.
/// - Listening(사용자 음성 수신): 파란 "좁쌀" 점들이 바깥으로 퍼짐, 마이크 레벨에 따라 점 크기 변화
/// - Speaking(에이전트 발화): 초록 "물결" 원이 바깥으로 퍼짐
/// - Thinking(STT/LLM 처리): 보라 점 3개가 회전
/// - Idle: 회색 점, Error: 빨간 점
/// </summary>
public static class RippleRenderer
{
    public static Color ColorOf(VoiceState state) => state switch
    {
        VoiceState.Listening => Color.FromArgb(59, 130, 246),
        VoiceState.Speaking => Color.FromArgb(34, 197, 94),
        VoiceState.Thinking => Color.FromArgb(167, 139, 250),
        VoiceState.Error => Color.FromArgb(239, 68, 68),
        _ => Color.FromArgb(113, 113, 122),
    };

    /// <param name="phase">0~1 을 반복하는 애니메이션 위상</param>
    /// <param name="level">마이크 입력 레벨 0~1</param>
    public static Bitmap Render(int size, VoiceState state, double phase, float level)
    {
        var bmp = new Bitmap(size, size, System.Drawing.Imaging.PixelFormat.Format32bppArgb);
        using var g = Graphics.FromImage(bmp);
        g.SmoothingMode = SmoothingMode.AntiAlias;
        g.Clear(Color.Transparent);

        var color = ColorOf(state);
        float c = size / 2f;
        float core = size * 0.16f;
        float maxR = size / 2f - 1;

        switch (state)
        {
            case VoiceState.Speaking:
                using (var pen = new Pen(color, Math.Max(1.5f, size / 14f)))
                {
                    for (var k = 0; k < 3; k++)
                    {
                        var t = (phase + k / 3.0) % 1.0;
                        float r = core + (float)((maxR - core) * t);
                        pen.Color = Color.FromArgb((int)(255 * (1 - t)), color);
                        g.DrawEllipse(pen, c - r, c - r, r * 2, r * 2);
                    }
                }

                break;

            case VoiceState.Listening:
                {
                    const int dots = 10;
                    float dotR = Math.Max(1f, size / 22f * (0.7f + level * 1.5f));
                    for (var k = 0; k < 3; k++)
                    {
                        var t = (phase + k / 3.0) % 1.0;
                        float r = core + (float)((maxR - core - dotR) * t);
                        using var brush = new SolidBrush(Color.FromArgb((int)(255 * (1 - t)), color));
                        for (var i = 0; i < dots; i++)
                        {
                            var a = 2 * Math.PI * (i + k * 0.5) / dots;
                            float x = c + r * (float)Math.Cos(a);
                            float y = c + r * (float)Math.Sin(a);
                            g.FillEllipse(brush, x - dotR, y - dotR, dotR * 2, dotR * 2);
                        }
                    }
                }

                break;

            case VoiceState.Thinking:
                using (var brush = new SolidBrush(color))
                {
                    float r = maxR * 0.65f;
                    float dotR = Math.Max(1.5f, size / 12f);
                    for (var i = 0; i < 3; i++)
                    {
                        var a = 2 * Math.PI * (phase + i / 3.0);
                        float x = c + r * (float)Math.Cos(a);
                        float y = c + r * (float)Math.Sin(a);
                        g.FillEllipse(brush, x - dotR, y - dotR, dotR * 2, dotR * 2);
                    }
                }

                break;
        }

        using (var brush = new SolidBrush(color))
        {
            g.FillEllipse(brush, c - core, c - core, core * 2, core * 2);
        }

        return bmp;
    }
}
