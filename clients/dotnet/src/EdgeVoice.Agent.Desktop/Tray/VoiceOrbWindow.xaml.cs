using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.Windows;
using System.Windows.Input;
using System.Windows.Media.Imaging;
using EdgeVoice.Agent.Core;
using Rectangle = System.Drawing.Rectangle;

namespace EdgeVoice.Agent.Desktop.Tray;

/// <summary>작업 표시줄 트레이 근처에 떠 있는 큰 파형 오버레이. 웹을 열지 않고도 상태를 볼 수 있다.</summary>
public partial class VoiceOrbWindow : Window
{
    private const int OrbSize = 120;

    public VoiceOrbWindow()
    {
        InitializeComponent();
        var area = SystemParameters.WorkArea;
        Left = area.Right - Width - 16;
        Top = area.Bottom - Height - 16;
    }

    public event Action? TalkRequested;

    public event Action? OpenRequested;

    public void Update(VoiceState state, double phase, float level, string text)
    {
        using var bmp = RippleRenderer.Render(OrbSize, state, phase, level);
        var data = bmp.LockBits(new Rectangle(0, 0, OrbSize, OrbSize), ImageLockMode.ReadOnly, PixelFormat.Format32bppArgb);
        try
        {
            RippleImage.Source = BitmapSource.Create(
                OrbSize, OrbSize, 96, 96, System.Windows.Media.PixelFormats.Bgra32, null,
                data.Scan0, data.Stride * OrbSize, data.Stride);
        }
        finally
        {
            bmp.UnlockBits(data);
        }

        StateLabel.Text = text;
    }

    protected override void OnMouseLeftButtonDown(MouseButtonEventArgs e)
    {
        base.OnMouseLeftButtonDown(e);
        var (left, top) = (Left, Top);
        DragMove();
        if (Math.Abs(Left - left) < 3 && Math.Abs(Top - top) < 3)
        {
            TalkRequested?.Invoke();
        }
    }

    protected override void OnMouseRightButtonUp(MouseButtonEventArgs e)
    {
        base.OnMouseRightButtonUp(e);
        OpenRequested?.Invoke();
    }
}
