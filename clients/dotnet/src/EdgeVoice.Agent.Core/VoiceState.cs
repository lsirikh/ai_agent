namespace EdgeVoice.Agent.Core;

/// <summary>트레이/오버레이 파형 표시에 쓰는 음성 상태.</summary>
public enum VoiceState
{
    Idle,
    Listening,
    Thinking,
    Speaking,
    Error,
}

public static class VoiceStateMapper
{
    /// <summary>Orchestrator 상태 문자열(off/ready/listening/stt_processing/...)을 VoiceState 로 변환한다.</summary>
    public static VoiceState FromOrchestrator(string? state) => state?.ToLowerInvariant() switch
    {
        "listening" => VoiceState.Listening,
        "stt_processing" or "llm_processing" => VoiceState.Thinking,
        "tts_processing" or "speaking" => VoiceState.Speaking,
        "error" => VoiceState.Error,
        _ => VoiceState.Idle,
    };
}
