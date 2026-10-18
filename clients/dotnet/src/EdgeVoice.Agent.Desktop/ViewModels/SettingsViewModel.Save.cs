using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Prism.Commands;

namespace EdgeVoice.Agent.Desktop.ViewModels;

/// <summary>
/// 설정 탭 저장 막대: 모든 카드의 바뀐 값을 모아 한 번에 저장하고, 항목마다 언제 반영되는지 알려 준다.
/// 다시 시작해야 반영되는 항목은 확인을 받은 뒤 그 서비스를 다시 만들고, 실행 값이 저장값과 같아지면 '반영됨' 을 보인다.
/// </summary>
public sealed partial class SettingsViewModel
{
    private enum Effect
    {
        Now,
        NextTurn,
        Restart,
    }

    /// <summary>저장 막대가 지켜보는 설정 하나. Saved = 서버에 저장된 값, Service = 반영하는 서비스.</summary>
    private sealed record Tracked(string Key, string Name, object? Value, object? Saved, Effect Effect, string Service, Action<object?> Revert);

    // 다시 만드는 서비스: 보일 이름 · 대략 걸리는 시간(초) · 다 됐는지 볼 실행 값 · 저장한 값
    private static readonly Dictionary<string, (string Name, int Seconds, string RuntimeKey, string TrackedKey)> Restartable = new()
    {
        ["llm"] = ("언어 모델(LLM)", 90, "llm_model", "models.llm"),
        ["stt"] = ("음성 인식(STT)", 30, "stt_model", "models.stt"),
        ["tts"] = ("답변 음성(TTS)", 30, "tts_engine", "models.tts_engine"),
    };

    // 저장 막대 자신의 표시 속성 — 바뀌어도 바뀐 항목을 다시 세지 않는다
    private static readonly HashSet<string> BarProperties = new()
    {
        nameof(ChangeCount), nameof(HasChanges), nameof(ChangeSummary), nameof(SaveResult),
        nameof(RestartPrompt), nameof(HasRestartPrompt), nameof(Status),
    };

    private readonly Dictionary<string, object?> _saved = new();
    private List<string> _restartServices = new();
    private int _changeCount;
    private string _changeSummary = "";
    private string _saveResult = "";
    private string _restartPrompt = "";

    public DelegateCommand SaveCommand { get; private set; } = null!;

    public DelegateCommand RevertCommand { get; private set; } = null!;

    public DelegateCommand RestartCommand { get; private set; } = null!;

    public DelegateCommand LaterCommand { get; private set; } = null!;

    /// <summary>백엔드가 서비스를 다시 만들지 못할 때 이 PC 의 docker 로 다시 만든다. 성공하면 null, 실패하면 이유.</summary>
    public Func<string, Task<string?>>? HostRestart { get; set; }

    public int ChangeCount
    {
        get => _changeCount;
        private set
        {
            if (SetProperty(ref _changeCount, value))
            {
                RaisePropertyChanged(nameof(HasChanges));
            }
        }
    }

    public bool HasChanges => ChangeCount > 0;

    /// <summary>'저장하지 않은 변경 n개: …' 또는 바뀐 것이 없다는 안내.</summary>
    public string ChangeSummary { get => _changeSummary; private set => SetProperty(ref _changeSummary, value); }

    /// <summary>저장·다시 시작 결과 (항목마다 한 줄).</summary>
    public string SaveResult { get => _saveResult; private set => SetProperty(ref _saveResult, value); }

    /// <summary>'○○을(를) 다시 시작합니다(약 N초)' — [다시 시작] [나중에] 를 기다린다.</summary>
    public string RestartPrompt
    {
        get => _restartPrompt;
        private set
        {
            if (SetProperty(ref _restartPrompt, value))
            {
                RaisePropertyChanged(nameof(HasRestartPrompt));
            }
        }
    }

    public bool HasRestartPrompt => RestartPrompt.Length > 0;

    private void CreateSaveCommands()
    {
        SaveCommand = new DelegateCommand(Save, () => HasChanges).ObservesProperty(() => HasChanges);
        RevertCommand = new DelegateCommand(Revert, () => HasChanges).ObservesProperty(() => HasChanges);
        RestartCommand = new DelegateCommand(Restart);
        LaterCommand = new DelegateCommand(() => RestartPrompt = "");
        PropertyChanged += (_, e) =>
        {
            if (!BarProperties.Contains(e.PropertyName ?? ""))
            {
                RefreshChanges();
            }
        };
        RefreshChanges();
    }

    private IEnumerable<Tracked> TrackedSettings()
    {
        // 아직 서버 값을 받지 못한 항목은 바뀐 것으로 치지 않는다
        Tracked Field(string key, string name, object? value, Effect effect, string service, Action<object?> revert)
            => new(key, name, value, _saved.TryGetValue(key, out var saved) ? saved : value, effect, service, revert);

        // 일반: 서비스에 바로 전파된다 (Service = 받는 서비스)
        yield return Field("general.wake_word", "호출어", WakeWord, Effect.Now, "wake_word", v => WakeWord = (string)v!);
        yield return Field("general.threshold", "호출어 민감도", WakeWordThreshold, Effect.Now, "wake_word", v => WakeWordThreshold = (double)v!);
        yield return Field("general.end_pause", "말 끝 판단 무음", EndPauseSeconds, Effect.Now, "orchestrator", v => EndPauseSeconds = (double)v!);
        yield return Field("general.timeout", "듣기 제한 시간", ListeningTimeoutSeconds, Effect.Now, "orchestrator", v => ListeningTimeoutSeconds = (double)v!);
        yield return Field("general.speed", "말하기 속도", VoiceSpeed, Effect.Now, "tts", v => VoiceSpeed = (double)v!);
        yield return Field("general.language", "언어", Language, Effect.Now, "stt", v => Language = (string)v!);

        // 모델: 그 서비스를 다시 만들어야 반영된다 (엔진을 먼저 되돌려야 음성 목록이 맞는다)
        yield return Field("models.stt", "음성 인식 모델", SttModel, Effect.Restart, "stt", v => SttModel = (string?)v);
        yield return Field("models.tts_engine", "답변 음성 엔진", TtsEngine, Effect.Restart, "tts", v => TtsEngine = (string?)v);
        yield return Field("models.tts_voice", "답변 음성", TtsVoice, Effect.Restart, "tts", v => TtsVoice = (string?)v);
        yield return Field("models.llm", "언어 모델", LlmModel, Effect.Restart, "llm", v => LlmModel = (string?)v);

        // 대화·도구·지역·시간: 턴마다 읽는다
        yield return Field("context.enabled", "이전 대화 기억", ContextEnabled, Effect.NextTurn, "", v => ContextEnabled = (bool)v!);
        yield return Field("context.size", "기억할 메시지 수", ContextWindowSize, Effect.NextTurn, "", v => ContextWindowSize = (int)v!);
        yield return Field("tools.internet", "인터넷 검색", InternetToolsEnabled, Effect.NextTurn, "", v => InternetToolsEnabled = (bool)v!);
        yield return Field("tools.follow_pc", "PC 시간대 따르기", FollowPcTimeZone, Effect.NextTurn, "", v => FollowPcTimeZone = (bool)v!);
        yield return Field("tools.timezone", "시간대", TimeZone, Effect.NextTurn, "", v => TimeZone = (string)v!);
        yield return Field("tools.location", "날씨 기준 지역", Location, Effect.NextTurn, "", v => Location = (string)v!);
        yield return Field("tools.weather", "날씨 알려 주기", WeatherEnabled, Effect.NextTurn, "", v => WeatherEnabled = (bool)v!);

        // MCP·스킬: 서버가 준 원본(Data)과 비교한다
        foreach (var item in McpServers)
        {
            yield return new($"mcp.{item.Name}", $"MCP 서버 '{item.Name}'", item.Enabled, item.Data?["enabled"]?.GetValue<bool>() ?? true,
                Effect.NextTurn, "", v => item.Enabled = (bool)v!);
        }

        if (SelectedMcpServer is { } server)
        {
            yield return new($"mcp-edit.{server.Name}", $"MCP 서버 '{server.Name}' 설정", McpEditorText(), McpDataText(server),
                Effect.NextTurn, "", _ => FillMcpEditor(server));
        }

        foreach (var item in BuiltinSkills.Concat(PromptSkills))
        {
            yield return new($"skill.{item.Name}", $"스킬 '{item.Name}'", item.Enabled, item.Data?["enabled"]?.GetValue<bool>() ?? true,
                Effect.NextTurn, "", v => item.Enabled = (bool)v!);
        }

        if (SelectedPromptSkill is { } prompt)
        {
            yield return new($"prompt-edit.{prompt.Name}", $"스킬 '{prompt.Name}' 지시문", SkillEditorText(), SkillDataText(prompt),
                Effect.NextTurn, "", _ => FillSkillEditor(prompt));
        }
    }

    private List<Tracked> Changes() => TrackedSettings().Where(t => !Equals(t.Value, t.Saved)).ToList();

    private void RefreshChanges()
    {
        var changes = Changes();
        ChangeCount = changes.Count;
        ChangeSummary = changes.Count == 0
            ? "바뀐 설정이 없습니다"
            : $"저장하지 않은 변경 {changes.Count}개: {string.Join(", ", changes.Select(c => c.Name))}";
    }

    /// <summary>서버에서 받은 값을 그 묶음(general·models·context·tools)의 저장값으로 삼는다.</summary>
    private void Remember(string group)
    {
        Remember(TrackedSettings().Where(t => t.Key.StartsWith(group + ".", StringComparison.Ordinal)));
    }

    private void Remember(IEnumerable<Tracked> items)
    {
        foreach (var t in items.ToList())
        {
            _saved[t.Key] = t.Value;
        }

        RefreshChanges();
    }

    private void Revert()
    {
        foreach (var t in Changes())
        {
            t.Revert(t.Saved);
        }

        SaveResult = "";
    }

    private static string Group(string key) => key[..key.IndexOf('.')] switch
    {
        "mcp-edit" => "mcp",
        "prompt-edit" => "skill",
        var group => group,
    };

    private static IEnumerable<string> Lines(IEnumerable<Tracked> items, string text) => items.Select(t => $"{t.Name}: {text}");

    private async void Save()
    {
        var changes = Changes();
        if (changes.Count == 0)
        {
            return;
        }

        SaveResult = "저장하는 중...";
        var lines = new List<string>();
        var restart = new List<string>();
        foreach (var group in changes.GroupBy(c => Group(c.Key)))
        {
            var items = group.ToList();
            try
            {
                lines.AddRange(await SaveGroup(group.Key, items, restart));
            }
            catch (Exception ex)
            {
                // 한 묶음이 실패해도 나머지는 저장한다. 실패한 항목은 '바뀐 항목' 으로 남는다
                lines.Add($"{string.Join(", ", items.Select(t => t.Name))}: 저장하지 못했습니다 — {ex.Message}");
            }
        }

        _restartServices = restart.Distinct().ToList();
        RestartPrompt = _restartServices.Count == 0
            ? ""
            : $"{string.Join(", ", _restartServices.Select(s => Restartable[s].Name))}을(를) 다시 시작합니다" +
              $"(약 {_restartServices.Sum(s => Restartable[s].Seconds)}초). 그동안 그 기능은 잠시 멈춥니다.";
        SaveResult = string.Join("\n", lines);
        RefreshChanges();
    }

    private async Task<IEnumerable<string>> SaveGroup(string group, List<Tracked> items, List<string> restart)
    {
        switch (group)
        {
            case "general":
            {
                var res = await _api.SendAsync(HttpMethod.Put, "api/settings/general", GeneralBody());
                Remember(items);
                // 전파에 실패한 서비스는 다시 시작될 때 백엔드가 다시 보낸다 (settings_resync)
                var down = (res?["propagation_results"] as JsonObject ?? new JsonObject())
                    .Where(p => p.Value is JsonObject r && r["success"]?.GetValue<bool>() == false)
                    .Select(p => p.Key)
                    .ToHashSet();
                return items.Select(t => $"{t.Name}: " +
                    (down.Contains(t.Service) ? "저장됨 (서비스가 응답하지 않음 — 다시 시작되면 반영)" : "바로 반영됨"));
            }

            case "models":
            {
                // 바꾼 종류만 보낸다 (다른 서비스의 저장값을 실행 값으로 덮지 않게)
                var services = items.Select(t => t.Service).ToHashSet();
                var changes = new Dictionary<string, object>();
                if (services.Contains("stt"))
                {
                    changes["stt"] = new { model_size = SttModel };
                }

                if (services.Contains("tts"))
                {
                    changes["tts"] = new { engine = TtsEngine, voice = TtsVoice };
                }

                if (services.Contains("llm"))
                {
                    changes["llm"] = new { model = LlmModel };
                }

                var res = await _api.SendAsync(HttpMethod.Post, "api/settings/apply", new { changes });
                var errors = res?["errors"] as JsonObject;
                var saved = items.Where(t => errors?[t.Service] is null).ToList();
                Remember(saved);
                restart.AddRange(saved.Select(t => t.Service));
                return items.Select(t => errors?[t.Service] is { } error
                    ? $"{t.Name}: 저장하지 못했습니다 — {error}"
                    : $"{t.Name}: 다시 시작해야 반영됨");
            }

            case "context":
                await _api.SendAsync(HttpMethod.Put, "api/settings/llm/context", ContextBody());
                Remember(items);
                return Lines(items, "다음 질문부터");

            case "tools":
                ShowTools(await _api.SendAsync(HttpMethod.Put, "api/settings/tools", ToolSettingsBody()));
                Remember("tools");
                return Lines(items, "다음 질문부터");

            case "mcp":
            {
                // 보낼 본문을 먼저 만든다 (첫 응답이 목록을 다시 그리면 나머지 체크가 사라진다)
                var bodies = items.Select(t => t.Key[(t.Key.IndexOf('.') + 1)..]).Distinct()
                    .Select(name => McpServers.First(x => x.Name == name))
                    .Select(item => (item.Name, Body: items.Any(t => t.Key == $"mcp-edit.{item.Name}")
                        ? McpBody(item.Enabled, item.Data?["env"])
                        : EnabledBody(item)))
                    .ToList();
                foreach (var (name, body) in bodies)
                {
                    ShowMcp(await _api.SendAsync(HttpMethod.Put, McpPath(name), body));
                }

                return Lines(items, "다음 질문부터");
            }

            default:
            {
                var editing = items.Any(t => t.Key.StartsWith("prompt-edit.", StringComparison.Ordinal));
                var prompts = PromptSkills.Select(p => editing && p == SelectedPromptSkill ? EditorPrompt(p.Enabled) : PromptBody(p));
                ShowSkills(await _api.SendAsync(HttpMethod.Put, "api/settings/skills", SkillsBody(prompts)));
                return Lines(items, "다음 질문부터");
            }
        }
    }

    private async void Restart()
    {
        var services = _restartServices;
        _restartServices = new();
        RestartPrompt = "";
        var lines = new List<string>();
        foreach (var service in services)
        {
            var (name, seconds, runtimeKey, trackedKey) = Restartable[service];
            SaveResult = $"{name} 다시 시작하는 중... (약 {seconds}초)";
            var failure = await RestartService(service);
            if (failure is not null)
            {
                lines.Add($"{name}: 다시 시작하지 못했습니다 — {failure}");
            }
            else if (await Reflected(runtimeKey, _saved.GetValueOrDefault(trackedKey)?.ToString(), seconds))
            {
                lines.Add($"{name}: 다시 시작 완료 — 반영됨");
            }
            else
            {
                lines.Add($"{name}: 다시 시작했지만 아직 반영되지 않았습니다 (준비되면 설정 탭을 다시 열어 확인하세요)");
            }
        }

        // 콤보박스·'다시 시작 후 적용' 배지를 새 실행 값으로
        await LoadOptions();
        SaveResult = string.Join("\n", lines);
    }

    private async Task<string?> RestartService(string service)
    {
        try
        {
            await _api.SendAsync(HttpMethod.Post, $"api/services/{service}/restart", null);
            return null;
        }
        catch (Exception ex)
        {
            // 백엔드 컨테이너 안에는 docker 가 없는 경우가 많다 → 이 PC 의 docker 로 같은 프로젝트를 다시 만든다
            if (HostRestart is null)
            {
                return ex.Message;
            }

            var host = await HostRestart(service);
            return host is null ? null : $"{ex.Message} / 이 PC 에서도 실패: {host}";
        }
    }

    // 실행 중인 서비스가 저장한 값으로 응답할 때까지 기다린다 (걸리는 시간의 4배까지)
    private async Task<bool> Reflected(string runtimeKey, string? expected, int seconds)
    {
        var until = DateTime.UtcNow.AddSeconds(seconds * 4);
        while (true)
        {
            try
            {
                var options = await _api.GetAsync("api/settings/options");
                if (options?["runtime"]?[runtimeKey]?.ToString() == expected)
                {
                    return true;
                }
            }
            catch (Exception)
            {
                // 다시 만드는 동안 잠깐 응답하지 않을 수 있다
            }

            if (DateTime.UtcNow > until)
            {
                return false;
            }

            await Task.Delay(TimeSpan.FromSeconds(2));
        }
    }
}
