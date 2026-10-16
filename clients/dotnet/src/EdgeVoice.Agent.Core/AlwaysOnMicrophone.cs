namespace EdgeVoice.Agent.Core;

/// <summary>마이크 → 게이트웨이 스트림 (테스트에서 가짜로 바꿀 수 있게 분리).</summary>
public interface IMicrophoneStream
{
    bool IsStreaming { get; }

    event Action<bool>? StreamingChanged;

    Task StartAsync();

    void Stop();
}

/// <summary>
/// 웨이크워드("Hey Jarvis")로 바로 깨어나도록 마이크를 클릭 없이 상시 스트리밍한다.
/// 연결이 끊기거나 시작에 실패하면 잠시 뒤 다시 붙고, 음소거 중에는 붙지 않는다.
/// </summary>
public sealed class AlwaysOnMicrophone : IDisposable
{
    private static readonly TimeSpan DefaultRetryDelay = TimeSpan.FromSeconds(3);

    private readonly IMicrophoneStream _mic;
    private readonly Func<TimeSpan, CancellationToken, Task> _retryDelay;
    private readonly CancellationTokenSource _cts = new();
    private readonly SemaphoreSlim _wake = new(0);
    private volatile bool _isMuted;

    public AlwaysOnMicrophone(IMicrophoneStream mic, Func<TimeSpan, CancellationToken, Task>? retryDelay = null)
    {
        _mic = mic;
        _retryDelay = retryDelay ?? Task.Delay;
        _mic.StreamingChanged += _ => _wake.Release();
    }

    /// <summary>음소거 상태가 바뀌면 알린다(트레이 메뉴·오버레이 표시용).</summary>
    public event Action<bool>? MutedChanged;

    /// <summary>마지막 연결 실패 메시지(연결되면 null).</summary>
    public string? LastError { get; private set; }

    public bool IsMuted
    {
        get => _isMuted;
        set
        {
            if (_isMuted == value)
            {
                return;
            }

            _isMuted = value;
            if (value)
            {
                _mic.Stop();
            }

            MutedChanged?.Invoke(value);
            _wake.Release();
        }
    }

    public void Start() => _ = Task.Run(() => KeepAliveAsync(_cts.Token));

    private async Task KeepAliveAsync(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            if (!_isMuted && !_mic.IsStreaming)
            {
                try
                {
                    await _mic.StartAsync();
                    LastError = null;
                }
                catch (Exception ex)
                {
                    LastError = ex.Message;
                    await DelayAsync(ct);
                    continue;
                }
            }

            // 끊김·음소거 변경이 있을 때까지 기다린다
            try
            {
                await _wake.WaitAsync(ct);
            }
            catch (OperationCanceledException)
            {
                return;
            }

            if (!_isMuted && !_mic.IsStreaming)
            {
                await DelayAsync(ct);
            }
        }
    }

    private async Task DelayAsync(CancellationToken ct)
    {
        try
        {
            await _retryDelay(DefaultRetryDelay, ct);
        }
        catch (OperationCanceledException)
        {
        }
    }

    public void Dispose()
    {
        _cts.Cancel();
        _mic.Stop();
    }
}
