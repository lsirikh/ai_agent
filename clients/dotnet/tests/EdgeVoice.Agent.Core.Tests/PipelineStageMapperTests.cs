using EdgeVoice.Agent.Core;
using Xunit;

namespace EdgeVoice.Agent.Core.Tests;

public class PipelineStageMapperTests
{
    // 오버레이의 듣기 → STT → LLM → TTS 단계 아이콘 점등은 이 매핑에 달려 있다
    [Theory]
    [InlineData("listening", PipelineStage.Listen)]
    [InlineData("stt_processing", PipelineStage.Stt)]
    [InlineData("llm_processing", PipelineStage.Llm)]
    [InlineData("processing", PipelineStage.Llm)]
    [InlineData("tts_processing", PipelineStage.Tts)]
    [InlineData("SPEAKING", PipelineStage.Tts)]
    [InlineData("ready", PipelineStage.None)]
    [InlineData("error", PipelineStage.None)]
    [InlineData(null, PipelineStage.None)]
    public void FromOrchestrator_MapsServerStateToStage(string? state, PipelineStage expected)
        => Assert.Equal(expected, PipelineStageMapper.FromOrchestrator(state));
}
