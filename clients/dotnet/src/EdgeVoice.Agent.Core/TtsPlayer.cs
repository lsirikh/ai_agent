using NAudio.Wave;

namespace EdgeVoice.Agent.Core;

/// <summary>
/// 게이트웨이(/ws/audio)가 바이너리 프레임으로 보내는 답변 음성(float32 24kHz mono)을 스피커로 재생한다.
/// 게이트웨이는 컨테이너 안에서 돌아 직접 재생할 수 없으므로 이 클라이언트가 재생을 맡는다.
/// </summary>
public sealed class TtsPlayer : IDisposable
{
    public static readonly WaveFormat Format = WaveFormat.CreateIeeeFloatWaveFormat(24000, 1);

    private readonly BufferedWaveProvider _buffer = new(Format)
    {
        BufferDuration = TimeSpan.FromMinutes(2),
        DiscardOnBufferOverflow = true,
        // 버퍼가 비면 무음을 채워 출력 장치를 계속 열어 둔다(다음 문장이 끊김 없이 이어진다)
        ReadFully = true,
    };

    private readonly IWavePlayer _output;

    public TtsPlayer(Func<IWavePlayer>? outputFactory = null)
    {
        _output = (outputFactory ?? (() => new WaveOutEvent { DesiredLatency = 150 }))();
        _output.Init(_buffer);
        _output.Play();
    }

    /// <summary>아직 재생되지 않고 남은 음성 길이.</summary>
    public TimeSpan Buffered => _buffer.BufferedDuration;

    public void Enqueue(byte[] float32Pcm)
    {
        var usable = float32Pcm.Length - float32Pcm.Length % sizeof(float);
        if (usable > 0)
        {
            _buffer.AddSamples(float32Pcm, 0, usable);
        }
    }

    /// <summary>남은 음성을 버린다(끼어들기·새 질문 시).</summary>
    public void Stop() => _buffer.ClearBuffer();

    public void Dispose()
    {
        _output.Stop();
        _output.Dispose();
    }
}
