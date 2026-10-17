using EdgeVoice.Agent.Core;
using Xunit;

namespace EdgeVoice.Agent.Core.Tests;

/// <summary>
/// 원격 데스크톱(RDP) 마이크처럼 소리가 매우 작으면 VAD(최대 0.19)·웨이크워드(최대 20%)가
/// 반응하지 않았다(실측). 말소리 구간을 기준으로 천천히 키우고, 조용할 때 잡음은 키우지 않는다.
/// </summary>
public class MicAutoGainTests
{
    private static byte[] Tone(double amplitude, int samples = 1600, double freq = 220)
    {
        var bytes = new byte[samples * 2];
        for (var i = 0; i < samples; i++)
        {
            var v = (short)(amplitude * short.MaxValue * Math.Sin(2 * Math.PI * freq * i / 16000));
            BitConverter.GetBytes(v).CopyTo(bytes, i * 2);
        }

        return bytes;
    }

    private static double Rms(byte[] pcm)
    {
        double sum = 0;
        var n = pcm.Length / 2;
        for (var i = 0; i < n; i++)
        {
            var s = BitConverter.ToInt16(pcm, i * 2) / 32768.0;
            sum += s * s;
        }

        return Math.Sqrt(sum / n);
    }

    [Fact]
    public void QuietSpeech_IsBoostedTowardTarget()
    {
        var agc = new MicAutoGain();
        for (var i = 0; i < 20; i++)
        {
            agc.Process(Tone(0.0005)); // 조용한 배경 → 잡음 수준 학습
        }

        byte[] output = Array.Empty<byte>();
        for (var i = 0; i < 60; i++)
        {
            output = agc.Process(Tone(0.01)); // 아주 작은 말소리(RMS 약 0.007)
        }

        Assert.True(Rms(output) > 0.04, $"rms={Rms(output)} gain={agc.Gain}");
    }

    [Fact]
    public void NormalSpeech_IsNotAmplified()
    {
        var agc = new MicAutoGain();
        var input = Tone(0.3);
        byte[] output = input;
        for (var i = 0; i < 60; i++)
        {
            output = agc.Process(input);
        }

        Assert.InRange(agc.Gain, 1.0, 1.01);
        Assert.Equal(Rms(input), Rms(output), 3);
    }

    [Fact]
    public void Silence_IsNotAmplified()
    {
        var agc = new MicAutoGain();
        for (var i = 0; i < 100; i++)
        {
            agc.Process(Tone(0.0005));
        }

        Assert.InRange(agc.Gain, 1.0, 1.5);
    }

    [Fact]
    public void Gain_IsCapped_AndOutputDoesNotWrap()
    {
        var agc = new MicAutoGain(maxGain: 8);
        for (var i = 0; i < 200; i++)
        {
            agc.Process(Tone(0.002));
        }

        Assert.True(agc.Gain <= 8.0001);
        var loud = agc.Process(Tone(0.9));
        Assert.True(Rms(loud) <= 1.0);
    }
}
