namespace EdgeVoice.Agent.Core;

/// <summary>
/// /api/status/stream(1초 주기)을 상시 구독해 Orchestrator 상태를 VoiceState 로 알린다.
/// 연결이 끊기면 5초 후 재연결한다. 이벤트는 백그라운드 스레드에서 발생한다.
/// </summary>
public sealed class VoiceStateMonitor : IDisposable
{
    private readonly EdgeVoiceApiClient _api;
    private readonly CancellationTokenSource _cts = new();

    public VoiceStateMonitor(EdgeVoiceApiClient api) => _api = api;

    public VoiceState State { get; private set; } = VoiceState.Idle;

    public event Action<VoiceState>? StateChanged;

    public void Start() => _ = Task.Run(() => RunAsync(_cts.Token));

    private async Task RunAsync(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            try
            {
                await foreach (var ev in _api.StreamAsync("api/status/stream", ct))
                {
                    var state = ev.Type switch
                    {
                        "init" => ev.Json?["orchestrator_state"]?["state"],
                        "orchestrator_state" => ev.Json?["state"],
                        _ => null,
                    };
                    if (state is not null)
                    {
                        SetState(VoiceStateMapper.FromOrchestrator(state.GetValue<string>()));
                    }
                }
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested)
            {
                return;
            }
            catch (Exception)
            {
                // 백엔드 미기동/네트워크 오류: 아래에서 재시도
            }

            SetState(VoiceState.Idle);
            try
            {
                await Task.Delay(TimeSpan.FromSeconds(5), ct);
            }
            catch (OperationCanceledException)
            {
                return;
            }
        }
    }

    private void SetState(VoiceState state)
    {
        if (State == state)
        {
            return;
        }

        State = state;
        StateChanged?.Invoke(state);
    }

    public void Dispose() => _cts.Cancel();
}
