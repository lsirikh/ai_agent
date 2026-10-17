using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using System.Net.Http;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using EdgeVoice.Agent.Core;
using Prism.Commands;

namespace EdgeVoice.Agent.Desktop.ViewModels;

public sealed record OptionItem(string Id, string Label);

/// <summary>설정: 모델 선택/적용·LLM 재시작, 일반 설정, Wake Word 바꾸기, LLM 컨텍스트. 선택값은 실행 중인 서비스 값.</summary>
public sealed class SettingsViewModel : PageViewModel
{
    // 저장값과 실행값이 다를 때 배지에 보일 이름
    private static readonly Dictionary<string, string> PendingNames = new()
    {
        ["llm_model"] = "언어 모델",
        ["stt_model"] = "음성 인식 모델",
        ["tts_engine"] = "답변 음성 엔진",
        ["tts_voice"] = "답변 음성",
        ["wake_word_threshold"] = "호출어 민감도",
    };

    private readonly EdgeVoiceApiClient _api;
    private Dictionary<string, List<string>> _voicesByEngine = new();
    private double? _runtimeThreshold;
    private string? _ttsEngine;
    private string? _ttsVoice;
    private string? _sttModel;
    private string? _llmModel;
    private string _pendingRestart = "";
    private string _wakeWord = "hey_jarvis";
    private string _language = "ko";
    private double _voiceSpeed = 1.0;
    private double _wakeWordThreshold = 0.5;
    private double _endPauseSeconds = 3.0;
    private double _listeningTimeoutSeconds = 10.0;
    private bool _contextEnabled = true;
    private int _contextWindowSize = 20;
    private bool _internetToolsEnabled;
    private string _availableTools = "";
    private string _timeZone = "Asia/Seoul";
    private string _location = "서울";
    private bool _weatherEnabled = true;
    private bool _followPcTimeZone = true;
    private string _timeComparison = "";
    private JsonNode? _toolSettings;

    public SettingsViewModel(EdgeVoiceApiClient api)
    {
        _api = api;
        ApplyModelsCommand = new DelegateCommand(ApplyModels);
        RestartLlmCommand = new DelegateCommand(RestartLlm);
        SaveGeneralCommand = new DelegateCommand(SaveGeneral);
        RegisterWakeWordCommand = new DelegateCommand(RegisterWakeWord);
        SaveContextCommand = new DelegateCommand(SaveContext);
        SaveToolsCommand = new DelegateCommand(SaveTools);
        Load();
    }

    public ObservableCollection<OptionItem> TtsEngines { get; } = new();

    public ObservableCollection<OptionItem> SttModels { get; } = new();

    public ObservableCollection<OptionItem> LlmModels { get; } = new();

    // 선택된 엔진의 음성만 (melo → KR, kokoro → 영어 음성, edge → ko-KR-*)
    public ObservableCollection<string> TtsVoices { get; } = new();

    public IReadOnlyList<string> WakeWords { get; } = new[] { "hey_jarvis", "alexa", "hey_mycroft" };

    public IReadOnlyList<OptionItem> Languages { get; } = new[]
    {
        new OptionItem("ko", "한국어"), new OptionItem("en", "English"), new OptionItem("ja", "日本語"),
    };

    public DelegateCommand ApplyModelsCommand { get; }

    public DelegateCommand RestartLlmCommand { get; }

    public DelegateCommand SaveGeneralCommand { get; }

    public DelegateCommand RegisterWakeWordCommand { get; }

    public DelegateCommand SaveContextCommand { get; }

    public DelegateCommand SaveToolsCommand { get; }

    /// <summary>LLM 인터넷 도구(web_search·web_fetch). 기본 꺼짐.</summary>
    public bool InternetToolsEnabled { get => _internetToolsEnabled; set => SetProperty(ref _internetToolsEnabled, value); }

    /// <summary>지금 LLM 에 노출되는 도구 이름들 (검색 제공자가 없으면 인터넷 도구는 빠진다).</summary>
    public string AvailableTools { get => _availableTools; set => SetProperty(ref _availableTools, value); }

    /// <summary>시각 근거·get_time 의 시간대(IANA, 예: Asia/Seoul).</summary>
    public string TimeZone { get => _timeZone; set => SetProperty(ref _timeZone, value); }

    /// <summary>날씨 기준 지역(예: 서울, 부산).</summary>
    public string Location { get => _location; set => SetProperty(ref _location, value); }

    /// <summary>날씨 도구(인터넷 도구가 켜져 있을 때만 동작).</summary>
    public bool WeatherEnabled { get => _weatherEnabled; set => SetProperty(ref _weatherEnabled, value); }

    /// <summary>켜면 이 PC 의 시간대를 서버 시간대로 쓴다(앱 시작 때도 맞춘다).</summary>
    public bool FollowPcTimeZone
    {
        get => _followPcTimeZone;
        set
        {
            if (SetProperty(ref _followPcTimeZone, value) && value)
            {
                TimeZone = PcTimeZone.IanaId();
            }
        }
    }

    /// <summary>서버 시각과 PC 시각을 나란히 보여 준다(어긋나면 바로 보이게).</summary>
    public string TimeComparison { get => _timeComparison; set => SetProperty(ref _timeComparison, value); }

    public IReadOnlyList<string> TimeZones { get; } = new[]
    {
        "Asia/Seoul", "Asia/Tokyo", "Asia/Shanghai", "Asia/Singapore", "UTC",
        "Europe/London", "Europe/Berlin", "America/New_York", "America/Los_Angeles",
    };

    // 콤보박스가 항목을 다시 그리는 동안 잠깐 보내는 null 은 무시한다 (선택값 유지)
    public string? TtsEngine
    {
        get => _ttsEngine;
        set
        {
            var voice = TtsVoice;
            if (value is not null && SetProperty(ref _ttsEngine, value))
            {
                FillVoices(voice);
            }
        }
    }

    public string? TtsVoice { get => _ttsVoice; set => SetProperty(ref _ttsVoice, value); }

    public string? SttModel { get => _sttModel; set { if (value is not null) SetProperty(ref _sttModel, value); } }

    public string? LlmModel { get => _llmModel; set { if (value is not null) SetProperty(ref _llmModel, value); } }

    /// <summary>저장값이 실행값과 다른 항목 ("다시 시작 후 적용" 배지). 없으면 빈 문자열.</summary>
    public string PendingRestart
    {
        get => _pendingRestart;
        private set
        {
            if (SetProperty(ref _pendingRestart, value))
            {
                RaisePropertyChanged(nameof(HasPendingRestart));
            }
        }
    }

    public bool HasPendingRestart => PendingRestart.Length > 0;

    public string WakeWord { get => _wakeWord; set { if (value is not null) SetProperty(ref _wakeWord, value); } }

    public string Language { get => _language; set { if (value is not null) SetProperty(ref _language, value); } }

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
        await LoadOptions();

        await RunAsync(async () =>
        {
            var g = await _api.GetAsync("api/settings/general");
            WakeWord = g?["wake_word"]?.ToString() ?? WakeWord;
            Language = g?["language"]?.ToString() ?? Language;
            VoiceSpeed = g?["voice_speed"]?.GetValue<double>() ?? VoiceSpeed;
            // 호출어 민감도는 웨이크워드 서비스가 실제로 쓰는 값
            WakeWordThreshold = _runtimeThreshold ?? g?["wake_word_threshold"]?.GetValue<double>() ?? WakeWordThreshold;
            EndPauseSeconds = g?["end_pause_seconds"]?.GetValue<double>() ?? EndPauseSeconds;
            ListeningTimeoutSeconds = g?["listening_timeout_seconds"]?.GetValue<double>() ?? ListeningTimeoutSeconds;
        });

        await RunAsync(async () =>
        {
            var c = await _api.GetAsync("api/settings/llm/context");
            ContextEnabled = c?["context_enabled"]?.GetValue<bool>() ?? true;
            ContextWindowSize = c?["context_window_size"]?.GetValue<int>() ?? 20;
        });

        await RunAsync(async () =>
        {
            ShowTools(await _api.GetAsync("api/settings/tools"));

            // "PC 시간대 따르기" 면 시작할 때 서버 시간대를 이 PC 에 맞춘다
            if (FollowPcTimeZone && TimeZone != PcTimeZone.IanaId())
            {
                TimeZone = PcTimeZone.IanaId();
                ShowTools(await _api.SendAsync(HttpMethod.Put, "api/settings/tools", ToolSettingsBody()));
            }
        });
    }

    private void ShowTools(JsonNode? tools)
    {
        _toolSettings = tools;
        InternetToolsEnabled = tools?["internet_enabled"]?.GetValue<bool>() ?? false;
        TimeZone = tools?["timezone"]?.ToString() ?? TimeZone;
        Location = tools?["location"]?.ToString() ?? Location;
        WeatherEnabled = tools?["weather_enabled"]?.GetValue<bool>() ?? WeatherEnabled;
        _followPcTimeZone = tools?["follow_pc_timezone"]?.GetValue<bool>() ?? true;
        RaisePropertyChanged(nameof(FollowPcTimeZone));
        TimeComparison = $"서버 시각: {tools?["server_time"]} · PC 시각: {PcTimeZone.NowText()} ({PcTimeZone.IanaId()})";
        AvailableTools = "사용 중인 도구: " + string.Join(", ",
            tools?["tools"]?.AsArray().Select(t => t?.ToString()) ?? Enumerable.Empty<string?>());
    }

    private async void SaveTools() => await RunAsync(async () =>
        ShowTools(await _api.SendAsync(HttpMethod.Put, "api/settings/tools", ToolSettingsBody())),
        "도구·지역 설정 저장 완료");

    private object ToolSettingsBody() => new
    {
        internet_enabled = InternetToolsEnabled,
        search_provider = _toolSettings?["search_provider"]?.ToString() ?? "searxng",
        timezone = FollowPcTimeZone ? PcTimeZone.IanaId() : TimeZone,
        locale = _toolSettings?["locale"]?.ToString() ?? "ko-KR",
        location = Location,
        weather_enabled = WeatherEnabled,
        follow_pc_timezone = FollowPcTimeZone,
    };

    private Task LoadOptions() => RunAsync(async () =>
    {
        var data = await _api.GetAsync("api/settings/options");
        var current = data?["current"];
        var saved = data?["saved"];
        _voicesByEngine = (data?["tts_voices"]?.AsObject() ?? new JsonObject())
            .ToDictionary(p => p.Key, p => p.Value?.AsArray().Select(v => v?.ToString() ?? "").ToList() ?? new List<string>());
        Fill(TtsEngines, data?["tts_engines"], m => $"{m["display_name"]} ({m["recommended_for"]})", current?["tts_engine"]);
        Fill(SttModels, data?["stt_models"], m => $"{m["display_name"]} ({m["vram_gb"]}GB VRAM, {m["korean_quality"]})", current?["stt_model"]);
        Fill(LlmModels, data?["llm_models"], m => $"{m["display_name"]} ({m["vram_gb"]}GB VRAM)", current?["llm_model"]);
        _ttsVoice = current?["tts_voice"]?.ToString();
        _ttsEngine = null;
        TtsEngine = current?["tts_engine"]?.ToString();
        SttModel = current?["stt_model"]?.ToString();
        LlmModel = current?["llm_model"]?.ToString();
        _runtimeThreshold = current?["wake_word_threshold"]?.GetValue<double>();
        PendingRestart = string.Join(", ", (data?["pending_restart"]?.AsArray() ?? new JsonArray())
            .Select(n => n?.ToString() ?? "")
            .Select(key => $"{PendingNames.GetValueOrDefault(key, key)}(저장 {saved?[key]} · 실행 {current?[key]})"));
    });

    private static void Fill(ObservableCollection<OptionItem> target, JsonNode? items, System.Func<JsonNode, string> label, JsonNode? current)
    {
        target.Clear();
        foreach (var m in items?.AsArray().OfType<JsonNode>() ?? Enumerable.Empty<JsonNode>())
        {
            target.Add(new OptionItem(m["id"]?.ToString() ?? "", label(m)));
        }

        // 실행 중인 값이 목록에 없어도 콤보박스가 비지 않게 한다
        if (current?.ToString() is { Length: > 0 } id && target.All(o => o.Id != id))
        {
            target.Add(new OptionItem(id, $"{id} (실행 중)"));
        }
    }

    private void FillVoices(string? keep)
    {
        var voices = TtsEngine is not null && _voicesByEngine.TryGetValue(TtsEngine, out var v) ? v : new List<string>();
        TtsVoices.Clear();
        foreach (var voice in voices)
        {
            TtsVoices.Add(voice);
        }

        if (keep is not null && TtsVoices.Count == 0)
        {
            TtsVoices.Add(keep);
        }

        TtsVoice = keep is not null && TtsVoices.Contains(keep) ? keep : TtsVoices.FirstOrDefault();
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
        await LoadOptions();
        Status = res?["message"]?.ToString() ?? "설정 저장 완료";
        if (restart is { Count: > 0 } && await Dialogs.ConfirmAsync(
                "다시 시작 필요",
                $"다음 서비스를 다시 만들어야 적용됩니다: {string.Join(", ", restart)}\n" +
                "LLM 을 다시 만들면 진행 중인 대화가 중단됩니다. 지금 시도할까요?"))
        {
            RestartLlm();
        }
    });

    // 재생성할 수 없는 환경이면 백엔드가 503 과 직접 실행할 명령을 돌려준다 → 상태줄에 그대로 보인다
    private async void RestartLlm() => await RunAsync(async () =>
    {
        Status = "LLM 다시 만드는 중...";
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
        Status = $"호출어를 바꿨습니다: {res?["wake_word"]}";
    });

    private async void SaveContext() => await RunAsync(() => _api.SendAsync(HttpMethod.Put, "api/settings/llm/context", new
    {
        context_enabled = ContextEnabled,
        context_window_size = ContextWindowSize,
    }), "LLM 컨텍스트 설정 저장 완료");
}
