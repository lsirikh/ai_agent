using System;
using System.Linq;
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
    private readonly string? _placementFile;

    public VoiceOrbWindow()
        : this(null)
    {
    }

    /// <param name="placementFile">옮긴 자리를 적어 둘 파일(없으면 기억하지 않는다)</param>
    public VoiceOrbWindow(string? placementFile)
    {
        _placementFile = placementFile;
        InitializeComponent();
        StopButton.Click += (_, _) => StopRequested?.Invoke();
        MuteButton.Click += (_, _) => TalkRequested?.Invoke();
        if (Screens.Primary is { } screen)
        {
            var area = screen.WorkingArea;
            var scale = screen.Scaling;
            var size = new PixelSize((int)(Width * scale), (int)(Height * scale));
            var saved = placementFile is null ? null : OrbPlacement.Load(placementFile);
            Position = OrbPlacement.Fit(saved, Screens.All.Select(s => s.WorkingArea), size)
                ?? new PixelPoint(
                    area.Right - (int)((Width + 16) * scale),
                    area.Bottom - (int)((Height + 16) * scale));
        }

        if (placementFile is not null)
        {
            PositionChanged += (_, e) => OrbPlacement.Save(placementFile, e.Point);
        }
    }

    /// <summary>마이크 버튼: 음소거 / 해제.</summary>
    public event Action? TalkRequested;

    /// <summary>파형을 짧게 눌렀다: 대기면 듣기, 듣거나 답하는 중이면 멈춤(사용자 요청 2026-10-19).</summary>
    public event Action? OrbClicked;

    public event Action? OpenRequested;

    /// <summary>[중단] 버튼: 말하던 답을 멈추고 대기로(사용자 요청 2026-10-18).</summary>
    public event Action? StopRequested;

    private static readonly (PipelineStage Stage, Color Accent)[] StageAccents =
    {
        (PipelineStage.Listen, Color.FromRgb(59, 130, 246)),
        (PipelineStage.Stt, Color.FromRgb(6, 182, 212)),
        (PipelineStage.Llm, Color.FromRgb(167, 139, 250)),
        (PipelineStage.Tts, Color.FromRgb(34, 197, 94)),
    };

    /// <summary>단계 칸 점등: 지금 단계는 불을 켜고, 이번 턴에서 지나간 단계는 반투명으로 남긴다.</summary>
    public void SetStage(PipelineStage stage)
    {
        var cells = new[] { StageListen, StageStt, StageLlm, StageTts };
        for (var i = 0; i < cells.Length; i++)
        {
            var (cellStage, accent) = StageAccents[i];
            var active = cellStage == stage;
            var done = stage != PipelineStage.None && cellStage < stage;
            cells[i].Classes.Set("active", active);
            cells[i].Classes.Set("done", done);
            cells[i].Background = active
                ? new SolidColorBrush(accent)
                : done ? new SolidColorBrush(accent, 0.35) : null;
        }
    }

    public void Update(VoiceState state, double phase, float level, string text)
    {
        Ripple.State = state;
        Ripple.Phase = phase;
        Ripple.Level = level;
        Ripple.InvalidateVisual();
        StateLabel.Text = text;
        StateLabel.IsVisible = text.Length > 0;
    }

    // 짧게 누르고 떼면 듣기/멈춤, 누른 채 움직이면 창 이동(옮긴 자리는 기억한다)
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
            OrbClicked?.Invoke();
        }

        _press = null;
        _pressPoint = null;
    }
}
