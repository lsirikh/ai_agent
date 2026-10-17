using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using System.Net.Http;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Prism.Commands;
using Prism.Mvvm;

namespace EdgeVoice.Agent.Desktop.ViewModels;

/// <summary>설정 화면 체크박스 한 줄 (MCP 서버·스킬). 체크를 바꾸면 바로 저장한다.</summary>
public sealed class ToggleItem : BindableBase
{
    private readonly Action<ToggleItem> _changed;
    private bool _enabled;

    public ToggleItem(string name, string detail, bool enabled, JsonNode? data, Action<ToggleItem> changed)
    {
        Name = name;
        Detail = detail;
        Data = data;
        _enabled = enabled;
        _changed = changed;
    }

    public string Name { get; }

    /// <summary>설명 또는 연결 상태.</summary>
    public string Detail { get; }

    /// <summary>서버가 준 원본 (수정·켜기/끄기 때 나머지 값을 그대로 다시 보낸다).</summary>
    public JsonNode? Data { get; }

    public bool Enabled
    {
        get => _enabled;
        set
        {
            if (SetProperty(ref _enabled, value))
            {
                _changed(this);
            }
        }
    }
}

/// <summary>설정: MCP 서버(등록·켜기/끄기·연결 상태)와 스킬(내장 도구 켜기/끄기·프롬프트 스킬).</summary>
public sealed partial class SettingsViewModel
{
    private static readonly Dictionary<string, string> McpStatusNames = new()
    {
        ["connected"] = "연결됨",
        ["disconnected"] = "연결 안 됨",
        ["disabled"] = "꺼짐",
    };

    private ToggleItem? _selectedMcpServer;
    private string _mcpName = "";
    private string _mcpUrl = "";
    private string _mcpCommand = "";
    private string _mcpArgs = "";
    private string _mcpAllowedTools = "";
    private string _mcpAlwaysConfirm = "";
    private string _mcpNoConfirm = "";
    private bool _mcpTrusted;
    private double _mcpTimeout = 30;
    private ToggleItem? _selectedPromptSkill;
    private string _skillName = "";
    private string _skillDescription = "";
    private string _skillInstructions = "";

    public ObservableCollection<ToggleItem> McpServers { get; } = new();

    public ObservableCollection<ToggleItem> BuiltinSkills { get; } = new();

    public ObservableCollection<ToggleItem> PromptSkills { get; } = new();

    public DelegateCommand AddMcpServerCommand { get; private set; } = null!;

    public DelegateCommand UpdateMcpServerCommand { get; private set; } = null!;

    public DelegateCommand DeleteMcpServerCommand { get; private set; } = null!;

    public DelegateCommand RefreshMcpCommand { get; private set; } = null!;

    public DelegateCommand AddSkillCommand { get; private set; } = null!;

    public DelegateCommand UpdateSkillCommand { get; private set; } = null!;

    public DelegateCommand DeleteSkillCommand { get; private set; } = null!;

    /// <summary>목록에서 고른 서버 → 편집 칸에 채운다.</summary>
    public ToggleItem? SelectedMcpServer
    {
        get => _selectedMcpServer;
        set
        {
            if (SetProperty(ref _selectedMcpServer, value) && value?.Data is { } d)
            {
                McpName = value.Name;
                McpUrl = d["url"]?.ToString() ?? "";
                McpCommand = d["command"]?.ToString() ?? "";
                McpArgs = Join(d["args"]);
                McpAllowedTools = Join(d["allowed_tools"]);
                McpAlwaysConfirm = Join(d["always_confirm"]);
                McpNoConfirm = Join(d["no_confirm"]);
                McpTrusted = d["trusted"]?.GetValue<bool>() ?? false;
                McpTimeout = d["timeout"]?.GetValue<double>() ?? 30;
            }
        }
    }

    public string McpName { get => _mcpName; set => SetProperty(ref _mcpName, value); }

    /// <summary>streamable HTTP 주소 (예: http://host.docker.internal:8931/mcp).</summary>
    public string McpUrl { get => _mcpUrl; set => SetProperty(ref _mcpUrl, value); }

    /// <summary>또는 stdio 로 띄울 명령.</summary>
    public string McpCommand { get => _mcpCommand; set => SetProperty(ref _mcpCommand, value); }

    // 아래 목록 칸은 모두 쉼표로 구분한다
    public string McpArgs { get => _mcpArgs; set => SetProperty(ref _mcpArgs, value); }

    public string McpAllowedTools { get => _mcpAllowedTools; set => SetProperty(ref _mcpAllowedTools, value); }

    public string McpAlwaysConfirm { get => _mcpAlwaysConfirm; set => SetProperty(ref _mcpAlwaysConfirm, value); }

    public string McpNoConfirm { get => _mcpNoConfirm; set => SetProperty(ref _mcpNoConfirm, value); }

    public bool McpTrusted { get => _mcpTrusted; set => SetProperty(ref _mcpTrusted, value); }

    public double McpTimeout { get => _mcpTimeout; set => SetProperty(ref _mcpTimeout, value); }

    /// <summary>목록에서 고른 프롬프트 스킬 → 편집 칸에 채운다.</summary>
    public ToggleItem? SelectedPromptSkill
    {
        get => _selectedPromptSkill;
        set
        {
            if (SetProperty(ref _selectedPromptSkill, value) && value?.Data is { } d)
            {
                SkillName = value.Name;
                SkillDescription = d["description"]?.ToString() ?? "";
                SkillInstructions = d["instructions"]?.ToString() ?? "";
            }
        }
    }

    public string SkillName { get => _skillName; set => SetProperty(ref _skillName, value); }

    public string SkillDescription { get => _skillDescription; set => SetProperty(ref _skillDescription, value); }

    /// <summary>켜면 시스템 프롬프트 뒤에 붙는 지시문.</summary>
    public string SkillInstructions { get => _skillInstructions; set => SetProperty(ref _skillInstructions, value); }

    private void CreateExtensionCommands()
    {
        AddMcpServerCommand = new DelegateCommand(AddMcpServer);
        UpdateMcpServerCommand = new DelegateCommand(UpdateMcpServer);
        DeleteMcpServerCommand = new DelegateCommand(DeleteMcpServer);
        RefreshMcpCommand = new DelegateCommand(async () => await RunAsync(async () => ShowMcp(await _api.GetAsync("api/settings/mcp")), "MCP 연결 상태를 새로 받았습니다"));
        AddSkillCommand = new DelegateCommand(AddSkill);
        UpdateSkillCommand = new DelegateCommand(UpdateSkill);
        DeleteSkillCommand = new DelegateCommand(DeleteSkill);
    }

    private async Task LoadExtensions()
    {
        await RunAsync(async () => ShowMcp(await _api.GetAsync("api/settings/mcp")));
        await RunAsync(async () => ShowSkills(await _api.GetAsync("api/settings/skills")));
    }

    private static List<string> Split(string text)
        => text.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries).ToList();

    private static string Join(JsonNode? list)
        => string.Join(", ", list?.AsArray().Select(x => x?.ToString()) ?? Enumerable.Empty<string?>());

    private static string McpPath(string name) => "api/settings/mcp/" + Uri.EscapeDataString(name);

    // ===== MCP 서버 =====

    private void ShowMcp(JsonNode? res)
    {
        var selected = SelectedMcpServer?.Name;
        McpServers.Clear();
        foreach (var server in res?["servers"]?.AsArray().OfType<JsonNode>() ?? Enumerable.Empty<JsonNode>())
        {
            var status = server["status"]?.ToString() ?? "";
            var detail = $"{McpStatusNames.GetValueOrDefault(status, status)} · {server["url"] ?? server["command"]}";
            if (server["tools"]?.AsArray() is { Count: > 0 } tools)
            {
                detail += " · 서버 도구: " + Join(tools);
            }

            if (server["error"]?.ToString() is { Length: > 0 } error)
            {
                detail += " · 오류: " + error;
            }

            McpServers.Add(new ToggleItem(server["name"]?.ToString() ?? "", detail,
                server["enabled"]?.GetValue<bool>() ?? true, server, ToggleMcpServer));
        }

        // 목록을 다시 그려도 고른 서버를 유지한다
        _selectedMcpServer = McpServers.FirstOrDefault(x => x.Name == selected);
        RaisePropertyChanged(nameof(SelectedMcpServer));
    }

    private object McpBody(bool enabled, JsonNode? env = null) => new
    {
        name = McpName.Trim(),
        url = McpUrl.Trim() is { Length: > 0 } url ? url : null,
        command = McpCommand.Trim() is { Length: > 0 } command ? command : null,
        args = Split(McpArgs),
        // 편집 칸에 없는 환경 변수는 고칠 때 원래 값을 그대로 보낸다
        env,
        allowed_tools = Split(McpAllowedTools),
        trusted = McpTrusted,
        always_confirm = Split(McpAlwaysConfirm),
        no_confirm = Split(McpNoConfirm),
        timeout = McpTimeout,
        enabled,
    };

    // 켜면 연결하고 끄면 닫는다 (채팅은 바로, 음성은 다음 질문부터)
    private async void ToggleMcpServer(ToggleItem item) => await RunAsync(async () =>
    {
        var body = item.Data!.DeepClone().AsObject();
        body["enabled"] = item.Enabled;
        ShowMcp(await _api.SendAsync(HttpMethod.Put, McpPath(item.Name), body));
    }, $"MCP 서버 '{item.Name}' {(item.Enabled ? "켬" : "끔")}");

    private async void AddMcpServer() => await RunAsync(async () =>
        ShowMcp(await _api.SendAsync(HttpMethod.Post, "api/settings/mcp", McpBody(enabled: true))),
        $"MCP 서버 '{McpName}' 추가");

    private async void UpdateMcpServer()
    {
        if (SelectedMcpServer is not { } item)
        {
            Status = "고칠 MCP 서버를 목록에서 먼저 고르세요";
            return;
        }

        await RunAsync(async () =>
            ShowMcp(await _api.SendAsync(HttpMethod.Put, McpPath(item.Name), McpBody(item.Enabled, item.Data?["env"]))),
            $"MCP 서버 '{McpName}' 저장");
    }

    private async void DeleteMcpServer()
    {
        if (SelectedMcpServer is not { } item)
        {
            Status = "지울 MCP 서버를 목록에서 먼저 고르세요";
            return;
        }

        await RunAsync(async () =>
            ShowMcp(await _api.SendAsync(HttpMethod.Delete, McpPath(item.Name), null)),
            $"MCP 서버 '{item.Name}' 삭제");
    }

    // ===== 스킬 =====

    private void ShowSkills(JsonNode? res)
    {
        BuiltinSkills.Clear();
        foreach (var skill in res?["builtin"]?.AsArray().OfType<JsonNode>() ?? Enumerable.Empty<JsonNode>())
        {
            var enabled = skill["enabled"]?.GetValue<bool>() ?? true;
            var detail = skill["description"]?.ToString() ?? "";
            if (enabled && skill["active"]?.GetValue<bool>() == false)
            {
                detail += " (지금 사용 안 됨)";
            }

            BuiltinSkills.Add(new ToggleItem(skill["name"]?.ToString() ?? "", detail, enabled, skill, _ => SaveSkillsFromList()));
        }

        var selected = SelectedPromptSkill?.Name;
        PromptSkills.Clear();
        foreach (var skill in res?["prompts"]?.AsArray().OfType<JsonNode>() ?? Enumerable.Empty<JsonNode>())
        {
            PromptSkills.Add(new ToggleItem(skill["name"]?.ToString() ?? "", skill["description"]?.ToString() ?? "",
                skill["enabled"]?.GetValue<bool>() ?? true, skill, _ => SaveSkillsFromList()));
        }

        _selectedPromptSkill = PromptSkills.FirstOrDefault(x => x.Name == selected);
        RaisePropertyChanged(nameof(SelectedPromptSkill));
    }

    private static object PromptBody(ToggleItem p) => new
    {
        name = p.Name,
        description = p.Data?["description"]?.ToString() ?? "",
        instructions = p.Data?["instructions"]?.ToString() ?? "",
        enabled = p.Enabled,
    };

    private object EditorPrompt(bool enabled) => new
    {
        name = SkillName.Trim(),
        description = SkillDescription,
        instructions = SkillInstructions,
        enabled,
    };

    private async void SaveSkills(IEnumerable<object> prompts, string done) => await RunAsync(async () =>
        ShowSkills(await _api.SendAsync(HttpMethod.Put, "api/settings/skills", new
        {
            disabled_tools = BuiltinSkills.Where(x => !x.Enabled).Select(x => x.Name).ToList(),
            prompts = prompts.ToList(),
        })), done);

    private void SaveSkillsFromList() => SaveSkills(PromptSkills.Select(PromptBody), "스킬 설정 저장 완료");

    private void AddSkill() => SaveSkills(PromptSkills.Select(PromptBody).Append(EditorPrompt(enabled: true)), $"스킬 '{SkillName}' 추가");

    private void UpdateSkill()
    {
        if (SelectedPromptSkill is not { } item)
        {
            Status = "고칠 스킬을 목록에서 먼저 고르세요";
            return;
        }

        SaveSkills(PromptSkills.Select(p => p == item ? EditorPrompt(p.Enabled) : PromptBody(p)), $"스킬 '{SkillName}' 저장");
    }

    private void DeleteSkill()
    {
        if (SelectedPromptSkill is not { } item)
        {
            Status = "지울 스킬을 목록에서 먼저 고르세요";
            return;
        }

        SaveSkills(PromptSkills.Where(p => p != item).Select(PromptBody), $"스킬 '{item.Name}' 삭제");
    }
}
