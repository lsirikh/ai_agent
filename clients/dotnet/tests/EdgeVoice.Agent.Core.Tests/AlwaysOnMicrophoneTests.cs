using EdgeVoice.Agent.Core;
using Xunit;

namespace EdgeVoice.Agent.Core.Tests;

/// <summary>
/// 웨이크워드로 깨우려면 마이크가 클릭 없이 상시 스트리밍돼야 한다.
/// 끊기면 다시 붙고, 음소거 중에는 붙지 않는다.
/// </summary>
public class AlwaysOnMicrophoneTests
{
    private sealed class FakeMic : IMicrophoneStream
    {
        public int StartCalls { get; private set; }

        public int FailNextStarts { get; set; }

        public bool IsStreaming { get; private set; }

        public event Action<bool>? StreamingChanged;

        public Task StartAsync()
        {
            StartCalls++;
            if (FailNextStarts > 0)
            {
                FailNextStarts--;
                throw new InvalidOperationException("gateway down");
            }

            IsStreaming = true;
            StreamingChanged?.Invoke(true);
            return Task.CompletedTask;
        }

        public void Stop()
        {
            if (!IsStreaming)
            {
                return;
            }

            IsStreaming = false;
            StreamingChanged?.Invoke(false);
        }

        // 게이트웨이 재시작 등으로 서버 쪽에서 연결이 끊긴 상황
        public void Disconnect() => Stop();
    }

    private static AlwaysOnMicrophone Create(FakeMic mic)
        => new(mic, retryDelay: (_, _) => Task.CompletedTask);

    private static async Task Eventually(Func<bool> condition)
    {
        for (var i = 0; i < 100 && !condition(); i++)
        {
            await Task.Delay(10);
        }

        Assert.True(condition());
    }

    [Fact]
    public async Task Start_StreamsWithoutClick()
    {
        var mic = new FakeMic();
        using var keeper = Create(mic);

        keeper.Start();

        await Eventually(() => mic.IsStreaming);
    }

    [Fact]
    public async Task Disconnect_ReconnectsAutomatically()
    {
        var mic = new FakeMic();
        using var keeper = Create(mic);
        keeper.Start();
        await Eventually(() => mic.IsStreaming);

        mic.Disconnect();

        await Eventually(() => mic.IsStreaming && mic.StartCalls == 2);
    }

    [Fact]
    public async Task StartFailure_RetriesUntilConnected()
    {
        var mic = new FakeMic { FailNextStarts = 2 };
        using var keeper = Create(mic);

        keeper.Start();

        await Eventually(() => mic.IsStreaming && mic.StartCalls == 3);
    }

    [Fact]
    public async Task Mute_StopsAndStaysStopped_UnmuteResumes()
    {
        var mic = new FakeMic();
        using var keeper = Create(mic);
        keeper.Start();
        await Eventually(() => mic.IsStreaming);

        keeper.IsMuted = true;
        await Task.Delay(50);
        Assert.False(mic.IsStreaming);

        keeper.IsMuted = false;
        await Eventually(() => mic.IsStreaming);
    }
}
