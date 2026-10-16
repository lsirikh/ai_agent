using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using System.Net.Http;
using System.Text.Json.Nodes;
using System.Windows;
using EdgeVoice.Agent.Core;
using Prism.Commands;

namespace EdgeVoice.Agent.Desktop.ViewModels;

public sealed record OptionItem(string Id, string Label);

/// <summary>설정: 모델 선택/적용·LLM 재시작, 일반 설정, Wake Word 등록, LLM 컨텍스트.</summary>
public sealed class SettingsViewModel : PageViewModel
{
    private readonly EdgeVoiceApiClient _api;
    private string? _ttsEngine;
    private string? _ttsVoice;
    private string? _sttModel;
    private string? _llmModel;
    private string _wakeWord = "hey_jarvis";
    private string _language = "ko";
    private double _voiceSpeed = 1.0;
    private double _wakeWordThreshold = 0.5;
    private double _endPauseSeconds = 3.0;
    private double _listeningTimeoutSeconds = 10.0;
    private bool _contextEnabled = true;
    private int _contextWindowSize = 20;

    public SettingsViewModel(EdgeVoiceApiClient api)
    {
        _api = api;
        ApplyModelsCommand = new DelegateCommand(ApplyModels);
        RestartLlmCommand = new DelegateCommand(RestartLlm);
        SaveGeneralCommand = new DelegateCommand(SaveGeneral);
        RegisterWakeWordCommand = new DelegateCommand(RegisterWakeWord);
        SaveContextCommand = new DelegateCommand(SaveContext);
        Load();
    }

    public ObservableCollection<OptionItem> TtsEngines { get; } = new();

    public ObservableCollection<OptionItem> SttModels { get; } = new();

    public ObservableCollection<OptionItem> LlmModels { get; } = new();

    // 웹 UI 의 음성 목록과 동일 (엔진별 사용 가능 음성)
    public IReadOnlyList<string> TtsVoices { get; } = new[]
    {
        "KR", "EN", "EN-US", "EN-BR", "ES", "FR", "ZH", "JP",
        "af_heart", "af_bella", "af_nicole", "am_adam", "am_michael",
        "ko-KR-SunHiNeural", "ko-KR-InJoonNeural", "en-US-JennyNeural", "en-US-GuyNeural",
    };

    public IReadOnlyList<string> WakeWords { get; } = new[] { "hey_jarvis", "alexa", "hey_mycroft" };

    public IReadOnlyList<string> Languages { get; } = new[] { "ko", "en", "ja" };

    public DelegateCommand ApplyModelsCommand { get; }

    public DelegateCommand RestartLlmCommand { get; }

    public DelegateCommand SaveGeneralCommand { get; }

    public DelegateCommand RegisterWakeWordCommand { get; }

    public DelegateCommand SaveContextCommand { get; }

    public string? TtsEngine { get => _ttsEngine; set => SetProperty(ref _ttsEngine, value); }

    public string? TtsVoice { get => _ttsVoice; set => SetProperty(ref _ttsVoice, value); }

    public string? SttModel { get => _sttModel; set => SetProperty(ref _sttModel, value); }

    public string? LlmModel { get => _llmModel; set => SetProperty(ref _llmModel, value); }

    public string WakeWord { get => _wakeWord; set => SetProperty(ref _wakeWord, value); }

    public string Language { get => _language; set => SetProperty(ref _language, value); }

    public double VoiceSpeed { get => _voiceSpeed; set => SetProperty(ref _voiceSpeed, value); }

    public double WakeWordThreshold { get => _wakeWordThreshold; set => SetProperty(ref _wakeWordThreshold, value); }

    public double EndPauseSeconds { get => _endPauseSeconds; set => SetProperty(ref _endPauseSeconds, value); }

    public double ListeningTimeoutSeconds { get => _listeningTimeoutSeconds; set => SetProperty(ref _listeningTimeoutSeconds, value); }

    public bool ContextEnabled { get => _contextEnabled; set => SetProperty(ref _contextEnabled, value); }

    public int ContextWindowSize
    {
        get => _contextWindowSize;
        set
        {
            if (SetProperty(ref _contextWindowSize, value))
            {
                RaisePropertyChanged(nameof(EstimatedTokens));
            }
        }
    }

    // 웹 UI 와 같은 추정식: system 200 + 메시지당 50 + 새 메시지 30
    public string EstimatedTokens => $"~{200 + ContextWindowSize * 50 + 30} tokens";

    private async void Load()
    {
        await RunAsync(async () =>
        {
            var data = await _api.GetAsync("api/settings/options");
            Fill(TtsEngines, data?["tts_engines"], m => $"{m["display_name"]} ({m["recommended_for"]})");
            Fill(SttModels, data?["stt_models"], m => $"{m["display_name"]} ({m["vram_gb"]}GB VRAM, {m["korean_quality"]})");
            Fill(LlmModels, data?["llm_models"], m => $"{m["display_name"]} ({m["vram_gb"]}GB VRAM)");
            var current = data?["current"];
            TtsEngine = current?["tts_engine"]?.ToString();
            TtsVoice = current?["tts_voice"]?.ToString();
            SttModel = current?["stt_model"]?.ToString();
            LlmModel = current?["llm_model"]?.ToString();
        });

        await RunAsync(async () =>
        {
            var g = await _api.GetAsync("api/settings/general");
            WakeWord = g?["wake_word"]?.ToString() ?? WakeWord;
            Language = g?["language"]?.ToString() ?? Language;
            VoiceSpeed = g?["voice_speed"]?.GetValue<double>() ?? VoiceSpeed;
            WakeWordThreshold = g?["wake_word_threshold"]?.GetValue<double>() ?? WakeWordThreshold;
            EndPauseSeconds = g?["end_pause_seconds"]?.GetValue<double>() ?? EndPauseSeconds;
            ListeningTimeoutSeconds = g?["listening_timeout_seconds"]?.GetValue<double>() ?? ListeningTimeoutSeconds;
        });

        await RunAsync(async () =>
        {
            var c = await _api.GetAsync("api/settings/llm/context");
            ContextEnabled = c?["context_enabled"]?.GetValue<bool>() ?? true;
            ContextWindowSize = c?["context_window_size"]?.GetValue<int>() ?? 20;
        });
    }

    private static void Fill(ObservableCollection<OptionItem> target, JsonNode? items, System.Func<JsonNode, string> label)
    {
        target.Clear();
        foreach (var m in items?.AsArray().OfType<JsonNode>() ?? Enumerable.Empty<JsonNode>())
        {
            target.Add(new OptionItem(m["id"]?.ToString() ?? "", label(m)));
        }
    }

    private async void ApplyModels() => await RunAsync(async () =>
    {
        var changes = new
        {
            tts = new { engine = TtsEngine, voice = TtsVoice },
            stt = new { model_size = SttModel },
            llm = new { model = LlmModel },
        };
        var res = await _api.SendAsync(HttpMethod.Post, "api/settings/apply", new { changes });
        var restart = res?["restart_required"]?.AsArray().Select(n => n?.ToString()).ToList();
        Status = "설정 저장 완료";
        if (restart is { Count: > 0 } && MessageBox.Show(
                $"다음 서비스 재시작이 필요합니다: {string.Join(", ", restart)}\n" +
                "LLM 재시작 시 진행 중인 대화가 중단됩니다. 지금 재시작할까요?",
                "Restart Required", MessageBoxButton.YesNo) == MessageBoxResult.Yes)
        {
            RestartLlm();
        }
    });

    private async void RestartLlm() => await RunAsync(async () =>
    {
        Status = "LLM 재시작 중...";
        var res = await _api.SendAsync(HttpMethod.Post, "api/services/llm/restart", null);
        Status = $"LLM: {res?["status"]} - {res?["message"]}";
    });

    private async void SaveGeneral() => await RunAsync(() => _api.SendAsync(HttpMethod.Put, "api/settings/general", new
    {
        wake_word = WakeWord,
        language = Language,
        voice_speed = VoiceSpeed,
        wake_word_threshold = WakeWordThreshold,
        end_pause_seconds = EndPauseSeconds,
        listening_timeout_seconds = ListeningTimeoutSeconds,
    }), "일반 설정 저장 완료");

    private async void RegisterWakeWord() => await RunAsync(async () =>
    {
        var res = await _api.SendAsync(HttpMethod.Put, "api/settings/wake-word", new { wake_word = WakeWord });
        Status = $"Wake word 등록: {res?["wake_word"]}";
    });

    private async void SaveContext() => await RunAsync(() => _api.SendAsync(HttpMethod.Put, "api/settings/llm/context", new
    {
        context_enabled = ContextEnabled,
        context_window_size = ContextWindowSize,
    }), "LLM 컨텍스트 설정 저장 완료");
}
