namespace EdgeVoice.Agent.Core;

/// <summary>오버레이의 단계 아이콘(듣기 → STT → LLM → TTS) 중 지금 처리 중인 단계.</summary>
public enum PipelineStage
{
    None,
    Listen,
    Stt,
    Llm,
    Tts,
}

public static class PipelineStageMapper
{
    /// <summary>Orchestrator 상태 문자열을 처리 단계로 변환한다. 대기·오류는 None.</summary>
    public static PipelineStage FromOrchestrator(string? state) => state?.ToLowerInvariant() switch
    {
        "listening" => PipelineStage.Listen,
        "stt_processing" => PipelineStage.Stt,
        "llm_processing" or "processing" => PipelineStage.Llm,
        "tts_processing" or "speaking" => PipelineStage.Tts,
        _ => PipelineStage.None,
    };
}
