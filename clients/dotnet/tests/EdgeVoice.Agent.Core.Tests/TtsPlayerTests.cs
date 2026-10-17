using EdgeVoice.Agent.Core;
using NAudio.Wave;
using Xunit;

namespace EdgeVoice.Agent.Core.Tests;

/// <summary>
/// 게이트웨이가 보내는 답변 음성(float32 24kHz mono)을 스피커로 재생한다.
/// 출력 장치는 바꿔 끼울 수 있어 장치 없이 검증한다.
/// </summary>
public class TtsPlayerTests
{
    private sealed class FakeOutput : IWavePlayer
    {
        public IWaveProvider? Source { get; private set; }

        public int PlayCalls { get; private set; }

        public float Volume { get; set; } = 1;

        public PlaybackState PlaybackState { get; private set; } = PlaybackState.Stopped;

        public WaveFormat OutputWaveFormat => Source!.WaveFormat;

        public event EventHandler<StoppedEventArgs>? PlaybackStopped
        {
            add { }
            remove { }
        }

        public void Init(IWaveProvider waveProvider) => Source = waveProvider;

        public void Play()
        {
            PlayCalls++;
            PlaybackState = PlaybackState.Playing;
        }

        public void Stop() => PlaybackState = PlaybackState.Stopped;

        public void Pause() => PlaybackState = PlaybackState.Paused;

        public void Dispose()
        {
        }
    }

    private static byte[] Samples(int count) => new byte[count * sizeof(float)];

    [Fact]
    public void Output_IsFloat24kMono_AndStartsPlaying()
    {
        var output = new FakeOutput();
        using var player = new TtsPlayer(() => output);

        Assert.Equal(24000, output.Source!.WaveFormat.SampleRate);
        Assert.Equal(1, output.Source.WaveFormat.Channels);
        Assert.Equal(WaveFormatEncoding.IeeeFloat, output.Source.WaveFormat.Encoding);
        Assert.Equal(1, output.PlayCalls);
    }

    [Fact]
    public void Enqueue_BuffersReceivedAudio()
    {
        var output = new FakeOutput();
        using var player = new TtsPlayer(() => output);

        player.Enqueue(Samples(24000));

        Assert.Equal(TimeSpan.FromSeconds(1), player.Buffered);
    }

    [Fact]
    public void Enqueue_IgnoresTrailingPartialSample()
    {
        var output = new FakeOutput();
        using var player = new TtsPlayer(() => output);

        player.Enqueue(new byte[sizeof(float) * 2 + 3]);

        Assert.Equal(TimeSpan.FromSeconds(2.0 / 24000), player.Buffered);
    }

    [Fact]
    public void Stop_DropsQueuedAudio()
    {
        var output = new FakeOutput();
        using var player = new TtsPlayer(() => output);
        player.Enqueue(Samples(24000));

        player.Stop();

        Assert.Equal(TimeSpan.Zero, player.Buffered);
    }

    [Fact]
    public void NoOutputDevice_DoesNotThrow_AndOpensWhenDeviceReturns()
    {
        // 실측: 원격 데스크톱이 끊겨 '원격 오디오' 가 사라지면 waveOutOpen 이 BadDeviceId 로 실패해
        // 앱이 시작하자마자 죽었다. 재생기는 장치가 돌아올 때 다시 연다.
        var output = new FakeOutput();
        var deviceReady = false;
        var player = new TtsPlayer(() => deviceReady ? output : throw new InvalidOperationException("BadDeviceId"));

        player.Enqueue(Samples(10));
        Assert.Null(output.Source);

        deviceReady = true;
        player.Enqueue(Samples(10));

        Assert.NotNull(output.Source);
        Assert.Equal(1, output.PlayCalls);
        player.Dispose();
    }
}
