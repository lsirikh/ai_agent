using System;
using System.Runtime.InteropServices;
using System.Windows.Forms;
using System.Windows.Threading;
using EdgeVoice.Agent.Core;
using Drawing = System.Drawing;

namespace EdgeVoice.Agent.Desktop.Tray;

/// <summary>
/// 시스템 트레이 아이콘. 음성 상태에 따라 아이콘 자체가 파형 애니메이션을 그리고,
/// 웹/메인 창 없이 트레이 클릭만으로 말하기(마이크 스트리밍)를 켜고 끌 수 있다.
/// </summary>
public sealed class TrayController : IDisposable
{
    private const int IconSize = 32;

    private readonly VoiceStateMonitor _monitor;
    private readonly MicrophoneStreamer _mic;
    private readonly Action _openMainWindow;
    private readonly NotifyIcon _notifyIcon;
    private readonly ToolStripMenuItem _talkItem;
    private readonly ToolStripMenuItem _orbItem;
    private readonly VoiceOrbWindow _orb;
    private readonly DispatcherTimer _timer;

    private VoiceState _serverState = VoiceState.Idle;
    private float _level;
    private double _phase;
    private VoiceState? _lastDrawn;
    private IntPtr _iconHandle;
    private bool _toggling;

    public TrayController(VoiceStateMonitor monitor, MicrophoneStreamer mic, Action openMainWindow)
    {
        _monitor = monitor;
        _mic = mic;
        _openMainWindow = openMainWindow;

        _talkItem = new ToolStripMenuItem("말하기 시작", null, (_, _) => ToggleTalk());
        _orbItem = new ToolStripMenuItem("화면 파형 표시", null, (_, _) => ToggleOrb()) { Checked = true };
        var menu = new ContextMenuStrip();
        menu.Items.Add(_talkItem);
        menu.Items.Add(_orbItem);
        menu.Items.Add("EdgeVoice 창 열기", null, (_, _) => _openMainWindow());
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("종료", null, (_, _) => System.Windows.Application.Current.Shutdown());

        _notifyIcon = new NotifyIcon { Text = "EdgeVoice Agent", ContextMenuStrip = menu, Visible = true };
        _notifyIcon.MouseClick += (_, e) =>
        {
            if (e.Button == MouseButtons.Left)
            {
                ToggleTalk();
            }
        };

        _orb = new VoiceOrbWindow();
        _orb.TalkRequested += ToggleTalk;
        _orb.OpenRequested += _openMainWindow;
        _orb.Show();

        var dispatcher = Dispatcher.CurrentDispatcher;
        _monitor.StateChanged += s => dispatcher.InvokeAsync(() => _serverState = s);
        _mic.LevelChanged += l => _level = l;
        _mic.StreamingChanged += on => dispatcher.InvokeAsync(() => _talkItem.Text = on ? "말하기 중지" : "말하기 시작");

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
        if (!animated && _lastDrawn == state)
        {
            return;
        }

        _phase = (_phase + (state == VoiceState.Listening ? 0.03 + _level * 0.05 : 0.035)) % 1.0;
        _lastDrawn = state;

        using (var bmp = RippleRenderer.Render(IconSize, state, _phase, _level))
        {
            // GetHicon 핸들은 직접 해제해야 하므로, 새 아이콘 적용 후 이전 핸들을 파기한다
            var previous = _iconHandle;
            _iconHandle = bmp.GetHicon();
            _notifyIcon.Icon = Drawing.Icon.FromHandle(_iconHandle);
            if (previous != IntPtr.Zero)
            {
                DestroyIcon(previous);
            }
        }

        _notifyIcon.Text = "EdgeVoice Agent - " + StateText(state);
        _orb.Update(state, _phase, _level, StateText(state));
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
            _notifyIcon.ShowBalloonTip(3000, "EdgeVoice", "음성 연결 실패: " + ex.Message, ToolTipIcon.Error);
        }
        finally
        {
            _toggling = false;
        }
    }

    private void ToggleOrb()
    {
        _orbItem.Checked = !_orbItem.Checked;
        _orb.Visibility = _orbItem.Checked ? System.Windows.Visibility.Visible : System.Windows.Visibility.Hidden;
    }

    public void Dispose()
    {
        _timer.Stop();
        _mic.Stop();
        _notifyIcon.Visible = false;
        _notifyIcon.Dispose();
        _orb.Close();
        if (_iconHandle != IntPtr.Zero)
        {
            DestroyIcon(_iconHandle);
        }
    }

    [DllImport("user32.dll")]
    private static extern bool DestroyIcon(IntPtr handle);
}
