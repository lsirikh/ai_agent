using System;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Threading;
using EdgeVoice.Agent.Core;

namespace EdgeVoice.Agent.Desktop.Tray;

/// <summary>
/// 시스템 트레이 아이콘(Avalonia TrayIcon). 음성 상태에 따라 아이콘 자체가 파형 애니메이션을 그린다.
/// 마이크는 앱이 켜지면 상시 스트리밍되어 "Hey Jarvis" 만으로 바로 깨어난다.
/// 트레이·오버레이 클릭은 음소거를 켜고 끈다.
/// </summary>
public sealed class TrayController : IDisposable
{
    private const int IconSize = 32;

    private readonly MicrophoneStreamer _mic;
    private readonly AlwaysOnMicrophone _alwaysOn;
    private readonly TrayIcon _trayIcon;
    private readonly NativeMenuItem _muteItem;
    private readonly NativeMenuItem _orbItem;
    private readonly VoiceOrbWindow _orb;
    private readonly DispatcherTimer _timer;

    private VoiceState _serverState = VoiceState.Idle;
    private float _level;
    private double _phase;
    private VoiceState? _lastDrawn;
    private string? _lastNotice;

    public TrayController(Application app, VoiceStateMonitor monitor, MicrophoneStreamer mic, Action openMainWindow, Action exit)
    {
        _mic = mic;
        _alwaysOn = new AlwaysOnMicrophone(mic);

        _muteItem = new NativeMenuItem("마이크 음소거");
        _muteItem.Click += (_, _) => ToggleMute();
        _orbItem = new NativeMenuItem("화면 파형 표시") { ToggleType = NativeMenuItemToggleType.CheckBox, IsChecked = true };
        _orbItem.Click += (_, _) => ToggleOrb();
        var openItem = new NativeMenuItem("EdgeVoice 창 열기");
        openItem.Click += (_, _) => openMainWindow();
        var exitItem = new NativeMenuItem("종료");
        exitItem.Click += (_, _) => exit();

        _trayIcon = new TrayIcon
        {
            ToolTipText = "EdgeVoice Agent",
            Menu = new NativeMenu { _muteItem, _orbItem, openItem, new NativeMenuItemSeparator(), exitItem },
            IsVisible = true,
        };
        _trayIcon.Clicked += (_, _) => ToggleMute();
        TrayIcon.SetIcons(app, new TrayIcons { _trayIcon });

        _orb = new VoiceOrbWindow();
        _orb.TalkRequested += ToggleMute;
        _orb.OpenRequested += openMainWindow;
        _orb.Show();

        monitor.StateChanged += s => Dispatcher.UIThread.Post(() => _serverState = s);
        monitor.StageChanged += st => Dispatcher.UIThread.Post(() => _orb.SetStage(st));
        _mic.LevelChanged += l => _level = l;
        _alwaysOn.MutedChanged += muted => Dispatcher.UIThread.Post(
            () => _muteItem.Header = muted ? "마이크 음소거 해제" : "마이크 음소거");

        _timer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(60) };
        _timer.Tick += (_, _) => Animate();
        _timer.Start();

        // 클릭 없이 바로 대기: 웨이크워드 감지는 마이크 소리가 게이트웨이로 들어와야 동작한다
        _alwaysOn.Start();
    }

    /// <summary>오버레이·툴팁에 보일 안내. 평상시에는 없다(상태는 파형과 단계 아이콘이 보여 준다).</summary>
    private string? Notice
    {
        get
        {
            if (_alwaysOn.IsMuted)
            {
                return "마이크 음소거";
            }

            if (!_mic.IsStreaming && _alwaysOn.LastError is { } error)
            {
                return "음성 연결 대기: " + error;
            }

            return null;
        }
    }

    private void Animate()
    {
        var state = _serverState;
        var animated = state is VoiceState.Listening or VoiceState.Speaking or VoiceState.Thinking;
        _phase = (_phase + (state == VoiceState.Listening ? 0.03 + _level * 0.05 : 0.035)) % 1.0;

        var notice = Notice;

        // 오버레이의 프랙탈은 대기 중에도 천천히 움직이므로 매 프레임 그린다
        _orb.Update(state, _phase, _level, notice ?? string.Empty);

        // 트레이 아이콘은 움직이는 상태이거나 바뀌었을 때만 다시 그린다
        if (!animated && _lastDrawn == state && notice == _lastNotice)
        {
            return;
        }

        _lastDrawn = state;
        _lastNotice = notice;
        using (var bmp = RippleRenderer.RenderBitmap(IconSize, state, _phase, _level))
        {
            _trayIcon.Icon = new WindowIcon(bmp);
        }

        _trayIcon.ToolTipText = "EdgeVoice Agent - " + (notice ?? StateText(state));
    }

    public static string StateText(VoiceState state) => state switch
    {
        VoiceState.Listening => "듣는 중",
        VoiceState.Thinking => "생각 중",
        VoiceState.Speaking => "말하는 중",
        VoiceState.Error => "오류",
        _ => "\"Hey Jarvis\" 대기",
    };

    private void ToggleMute() => _alwaysOn.IsMuted = !_alwaysOn.IsMuted;

    private void ToggleOrb()
    {
        _orbItem.IsChecked = !_orbItem.IsChecked;
        if (_orbItem.IsChecked)
        {
            _orb.Show();
        }
        else
        {
            _orb.Hide();
        }
    }

    public void Dispose()
    {
        _timer.Stop();
        _alwaysOn.Dispose();
        _trayIcon.Dispose();
        _orb.Close();
    }
}
