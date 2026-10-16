using EdgeVoice.Agent.Core;
using Xunit;

namespace EdgeVoice.Agent.Core.Tests;

public class VoiceStateMapperTests
{
    // 트레이 파형 구분(듣기=좁쌀, 말하기=물결)은 이 매핑에 달려 있다
    [Theory]
    [InlineData("listening", VoiceState.Listening)]
    [InlineData("stt_processing", VoiceState.Thinking)]
    [InlineData("llm_processing", VoiceState.Thinking)]
    [InlineData("tts_processing", VoiceState.Speaking)]
    [InlineData("SPEAKING", VoiceState.Speaking)]
    [InlineData("error", VoiceState.Error)]
    [InlineData("ready", VoiceState.Idle)]
    [InlineData(null, VoiceState.Idle)]
    public void FromOrchestrator_MapsServerState(string? state, VoiceState expected)
        => Assert.Equal(expected, VoiceStateMapper.FromOrchestrator(state));
}
