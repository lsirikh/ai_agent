namespace EdgeVoice.Agent.Core;

/// <summary>
/// 마이크 자동 음량 보정(16kHz mono int16 PCM).
/// 원격 데스크톱 마이크처럼 소리가 작으면 VAD·웨이크워드가 반응하지 않아(실측 VAD 최대 0.19,
/// 웨이크워드 최대 20%), 말소리로 보이는 구간을 목표 크기까지 천천히 키운다.
/// 잡음 수준을 따로 추적해 조용할 때 잡음은 키우지 않는다. 줄이는 일은 하지 않는다.
/// </summary>
public sealed class MicAutoGain
{
    /// <summary>말소리 목표 RMS(약 -20 dBFS).</summary>
    private const double TargetRms = 0.1;

    /// <summary>잡음 수준의 몇 배를 넘으면 말소리로 보는지.</summary>
    private const double SpeechOverNoise = 3.0;

    private readonly double _maxGain;
    private double _noiseFloor = -1;

    public MicAutoGain(double maxGain = 20) => _maxGain = maxGain;

    /// <summary>지금 적용 중인 배율(1 = 그대로).</summary>
    public double Gain { get; private set; } = 1;

    public byte[] Process(byte[] pcm)
    {
        var samples = pcm.Length / 2;
        if (samples == 0)
        {
            return pcm;
        }

        var rms = Rms(pcm, samples);
        TrackNoise(rms);

        var isSpeech = rms > SpeechOverNoise * _noiseFloor && rms > 1e-4;
        if (isSpeech)
        {
            var wanted = Math.Clamp(TargetRms / rms, 1, _maxGain);

            // 줄일 때는 바로(찢어지는 소리 방지), 키울 때는 천천히
            Gain = wanted < Gain ? wanted : Gain + (wanted - Gain) * 0.2;
        }

        if (Gain <= 1.0001)
        {
            return pcm;
        }

        var output = new byte[samples * 2];
        for (var i = 0; i < samples; i++)
        {
            var value = BitConverter.ToInt16(pcm, i * 2) * Gain;
            var clipped = (short)Math.Clamp(value, short.MinValue, short.MaxValue);
            BitConverter.TryWriteBytes(output.AsSpan(i * 2), clipped);
        }

        return output;
    }

    private void TrackNoise(double rms)
    {
        if (_noiseFloor < 0)
        {
            _noiseFloor = rms;
            return;
        }

        // 내려갈 때는 빨리, 올라갈 때는 아주 천천히 따라간다(말소리가 잡음으로 학습되지 않게)
        _noiseFloor = rms < _noiseFloor ? rms : _noiseFloor + (rms - _noiseFloor) * 0.002;
    }

    private static double Rms(byte[] pcm, int samples)
    {
        double sum = 0;
        for (var i = 0; i < samples; i++)
        {
            var s = BitConverter.ToInt16(pcm, i * 2) / 32768.0;
            sum += s * s;
        }

        return Math.Sqrt(sum / samples);
    }
}
