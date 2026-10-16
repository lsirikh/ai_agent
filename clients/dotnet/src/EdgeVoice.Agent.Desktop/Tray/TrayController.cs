using System;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Threading;
using EdgeVoice.Agent.Core;

namespace EdgeVoice.Agent.Desktop.Tray;

/// <summary>
/// 시스템 트레이 아이콘(Avalonia TrayIcon). 음성 상태에 따라 아이콘 자체가 파형 애니메이션을 그리고,
/// 웹/메인 창 없이 트레이 클릭만으로 말하기(마이크 스트리밍)를 켜고 끌 수 있다.
/// </summary>
public sealed class TrayController : IDisposable
{
    private const int IconSize = 32;

    private readonly MicrophoneStreamer _mic;
    private readonly TrayIcon _trayIcon;
    private readonly NativeMenuItem _talkItem;
    private readonly NativeMenuItem _orbItem;
    private readonly VoiceOrbWindow _orb;
    private readonly DispatcherTimer _timer;

    private VoiceState _serverState = VoiceState.Idle;
    private float _level;
    private double _phase;
    private VoiceState? _lastDrawn;
    private bool _toggling;
    private string? _error;
    private DateTime _errorUntil;

    public TrayController(Application app, VoiceStateMonitor monitor, MicrophoneStreamer mic, Action openMainWindow, Action exit)
    {
        _mic = mic;

        _talkItem = new NativeMenuItem("말하기 시작");
        _talkItem.Click += (_, _) => ToggleTalk();
        _orbItem = new NativeMenuItem("화면 파형 표시") { ToggleType = NativeMenuItemToggleType.CheckBox, IsChecked = true };
        _orbItem.Click += (_, _) => ToggleOrb();
        var openItem = new NativeMenuItem("EdgeVoice 창 열기");
        openItem.Click += (_, _) => openMainWindow();
        var exitItem = new NativeMenuItem("종료");
        exitItem.Click += (_, _) => exit();

        _trayIcon = new TrayIcon
        {
            ToolTipText = "EdgeVoice Agent",
            Menu = new NativeMenu { _talkItem, _orbItem, openItem, new NativeMenuItemSeparator(), exitItem },
            IsVisible = true,
        };
        _trayIcon.Clicked += (_, _) => ToggleTalk();
        TrayIcon.SetIcons(app, new TrayIcons { _trayIcon });

        _orb = new VoiceOrbWindow();
        _orb.TalkRequested += ToggleTalk;
        _orb.OpenRequested += openMainWindow;
        _orb.Show();

        monitor.StateChanged += s => Dispatcher.UIThread.Post(() => _serverState = s);
        monitor.StageChanged += st => Dispatcher.UIThread.Post(() => _orb.SetStage(st));
        _mic.LevelChanged += l => _level = l;
        _mic.StreamingChanged += on => Dispatcher.UIThread.Post(() => _talkItem.Header = on ? "말하기 중지" : "말하기 시작");

        _timer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(60) };
        _timer.Tick += (_, _) => Animate();
        _timer.Start();
    }

    /// <summary>서버가 대기 상태여도 로컬 마이크 스트리밍 중이면 '듣는 중'으로 표시한다.</summary>
    private VoiceState EffectiveState
        => _serverState == VoiceState.Idle && _mic.IsStreaming ? VoiceState.Listening : _serverState;

    private void Animate()
    {
        var state = EffectiveState;
        var animated = state is VoiceState.Listening or VoiceState.Speaking or VoiceState.Thinking;
        _phase = (_phase + (state == VoiceState.Listening ? 0.03 + _level * 0.05 : 0.035)) % 1.0;

        if (_error is not null && DateTime.Now > _errorUntil)
        {
            _error = null;
        }

        // 오버레이의 프랙탈은 대기 중에도 천천히 움직이므로 매 프레임 그린다.
        // 글자는 오류일 때만 보인다(상태는 파형과 단계 아이콘이 보여 준다).
        _orb.Update(state, _phase, _level, _error ?? string.Empty);

        // 트레이 아이콘은 움직이는 상태이거나 바뀌었을 때만 다시 그린다
        if (!animated && _lastDrawn == state && _error is null)
        {
            return;
        }

        _lastDrawn = state;
        using (var bmp = RippleRenderer.RenderBitmap(IconSize, state, _phase, _level))
        {
            _trayIcon.Icon = new WindowIcon(bmp);
        }

        _trayIcon.ToolTipText = "EdgeVoice Agent - " + (_error ?? StateText(state));
    }

    public static string StateText(VoiceState state) => state switch
    {
        VoiceState.Listening => "듣는 중",
        VoiceState.Thinking => "생각 중",
        VoiceState.Speaking => "말하는 중",
        VoiceState.Error => "오류",
        _ => "대기",
    };

    private async void ToggleTalk()
    {
        if (_toggling)
        {
            return;
        }

        _toggling = true;
        try
        {
            if (_mic.IsStreaming)
            {
                _mic.Stop();
            }
            else
            {
                await _mic.StartAsync();
            }
        }
        catch (Exception ex)
        {
            _mic.Stop();

            // Avalonia 트레이는 풍선 알림이 없어 오버레이 라벨/툴팁에 3초간 표시한다
            _error = "음성 연결 실패: " + ex.Message;
            _errorUntil = DateTime.Now.AddSeconds(3);
        }
        finally
        {
            _toggling = false;
        }
    }

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
        _mic.Stop();
        _trayIcon.Dispose();
        _orb.Close();
    }
}
