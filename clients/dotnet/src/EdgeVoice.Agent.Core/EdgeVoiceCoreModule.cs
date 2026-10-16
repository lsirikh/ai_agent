using Autofac;

namespace EdgeVoice.Agent.Core;

/// <summary>
/// Core 서비스 Autofac 등록. 단독 Desktop 앱과, 추후 Dotnet.Ironwall.Monitoring 같은
/// 호스트 프로그램이 같은 모듈을 RegisterModule 해서 에이전트로 붙일 수 있도록 분리했다.
/// </summary>
public sealed class EdgeVoiceCoreModule : Module
{
    private readonly EdgeVoiceOptions _options;

    public EdgeVoiceCoreModule(EdgeVoiceOptions options) => _options = options;

    protected override void Load(ContainerBuilder builder)
    {
        builder.RegisterInstance(_options);
        builder.RegisterType<EdgeVoiceApiClient>().SingleInstance();
        builder.RegisterType<VoiceStateMonitor>().SingleInstance();
        builder.RegisterType<MicrophoneStreamer>().SingleInstance();
    }
}
