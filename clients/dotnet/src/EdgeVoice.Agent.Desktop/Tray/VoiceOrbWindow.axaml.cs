using System;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Media;
using EdgeVoice.Agent.Core;

namespace EdgeVoice.Agent.Desktop.Tray;

/// <summary>오버레이 안에서 파형을 직접 그리는 컨트롤.</summary>
public sealed class RippleView : Control
{
    public VoiceState State { get; set; }

    public double Phase { get; set; }

    public float Level { get; set; }

    public override void Render(DrawingContext context)
        => RippleRenderer.Draw(context, Math.Min(Bounds.Width, Bounds.Height), State, Phase, Level);
}

/// <summary>작업 표시줄 트레이 근처에 떠 있는 큰 파형 오버레이. 웹을 열지 않고도 상태를 볼 수 있다.</summary>
public partial class VoiceOrbWindow : Window
{
    private PointerPressedEventArgs? _press;
    private Point? _pressPoint;

    public VoiceOrbWindow()
    {
        InitializeComponent();
        if (Screens.Primary is { } screen)
        {
            var area = screen.WorkingArea;
            var scale = screen.Scaling;
            Position = new PixelPoint(
                area.Right - (int)((Width + 16) * scale),
                area.Bottom - (int)((Height + 16) * scale));
        }
    }

    public event Action? TalkRequested;

    public event Action? OpenRequested;

    public void Update(VoiceState state, double phase, float level, string text)
    {
        Ripple.State = state;
        Ripple.Phase = phase;
        Ripple.Level = level;
        Ripple.InvalidateVisual();
        StateLabel.Text = text;
    }

    // 짧게 누르고 떼면 말하기 토글, 누른 채 움직이면 창 이동
    protected override void OnPointerPressed(PointerPressedEventArgs e)
    {
        base.OnPointerPressed(e);
        if (e.GetCurrentPoint(this).Properties.IsLeftButtonPressed)
        {
            _press = e;
            _pressPoint = e.GetPosition(this);
        }
    }

    protected override void OnPointerMoved(PointerEventArgs e)
    {
        base.OnPointerMoved(e);
        if (_press is not null && _pressPoint is { } start)
        {
            var delta = e.GetPosition(this) - start;
            if (Math.Abs(delta.X) > 3 || Math.Abs(delta.Y) > 3)
            {
                var press = _press;
                _press = null;
                _pressPoint = null;
                BeginMoveDrag(press);
            }
        }
    }

    protected override void OnPointerReleased(PointerReleasedEventArgs e)
    {
        base.OnPointerReleased(e);
        if (e.InitialPressMouseButton == MouseButton.Right)
        {
            OpenRequested?.Invoke();
        }
        else if (_pressPoint is not null)
        {
            TalkRequested?.Invoke();
        }

        _press = null;
        _pressPoint = null;
    }
}
