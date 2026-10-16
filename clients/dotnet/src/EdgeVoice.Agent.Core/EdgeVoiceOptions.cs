namespace EdgeVoice.Agent.Core;

/// <summary>EdgeVoice 백엔드 접속 설정 (docker-compose.dev.yml 기본 호스트 포트 기준).</summary>
public sealed class EdgeVoiceOptions
{
    public string BackendUrl { get; set; } = "http://localhost:11000";

    public string AudioGatewayWsUrl { get; set; } = "ws://localhost:11008/ws/audio";
}
