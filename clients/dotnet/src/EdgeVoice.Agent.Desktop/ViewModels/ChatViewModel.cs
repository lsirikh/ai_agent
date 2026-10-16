using System;
using System.Collections.ObjectModel;
using System.Linq;
using System.Net.Http;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Avalonia.Threading;
using EdgeVoice.Agent.Core;
using Prism.Commands;
using Prism.Mvvm;

namespace EdgeVoice.Agent.Desktop.ViewModels;

public sealed class ChatMessage : BindableBase
{
    private string _text;

    public ChatMessage(string role, string text, bool isVoice = false)
    {
        Role = role;
        _text = text;
        IsVoice = isVoice;
    }

    public string Role { get; }

    /// <summary>음성("Hey Jarvis")으로 나눈 턴이면 true — 말풍선에 음성 표시가 붙는다.</summary>
    public bool IsVoice { get; }

    public string Text { get => _text; set => SetProperty(ref _text, value); }
}

/// <summary>
/// 채팅: 음성과 같은 활성 세션을 쓴다. 시작하면 세션 히스토리를 불러오고 /api/chat/stream 을 상시 구독해
/// 음성 턴을 말풍선으로 보여 준다. 텍스트 질문은 스트리밍 응답(RAG 출처 표시), 마이크 버튼은 상시 마이크 음소거 토글.
/// LLM 이 도구를 쓰면 "🔎 검색함"·출처 링크를 답에 붙이고, 확인이 필요한 도구는 실행 전에 묻는다.
/// </summary>
public sealed class ChatViewModel : PageViewModel, IDisposable
{
    private const int ReconnectDelayMs = 5000;

    private readonly EdgeVoiceApiClient _api;
    private readonly AlwaysOnMicrophone _mic;
    private CancellationTokenSource? _stream;
    private string? _sessionId;
    private string _input = "";
    private bool _useRag = true;
    private bool _isBusy;
    private bool _isMuted;

    public ChatViewModel(EdgeVoiceApiClient api, AlwaysOnMicrophone mic)
    {
        _api = api;
        _mic = mic;
        SendCommand = new DelegateCommand(Send, () => !IsBusy && !string.IsNullOrWhiteSpace(Input))
            .ObservesProperty(() => IsBusy)
            .ObservesProperty(() => Input);
        ToggleMuteCommand = new DelegateCommand(() => _mic.IsMuted = !_mic.IsMuted);
        NewConversationCommand = new DelegateCommand(NewConversation, () => !IsBusy).ObservesProperty(() => IsBusy);

        _isMuted = mic.IsMuted;
        mic.MutedChanged += muted => Dispatcher.UIThread.Post(() => IsMuted = muted);
        Connect();
    }

    public ObservableCollection<ChatMessage> Messages { get; } = new();

    public DelegateCommand SendCommand { get; }

    public DelegateCommand ToggleMuteCommand { get; }

    public DelegateCommand NewConversationCommand { get; }

    public string Input { get => _input; set => SetProperty(ref _input, value); }

    public bool UseRag { get => _useRag; set => SetProperty(ref _useRag, value); }

    public bool IsBusy { get => _isBusy; set => SetProperty(ref _isBusy, value); }

    public bool IsMuted { get => _isMuted; set => SetProperty(ref _isMuted, value); }

    /// <summary>지금 이어 쓰는 세션 ID(백엔드의 활성 세션).</summary>
    public string? SessionId => _sessionId;

    private async void Send()
    {
        var text = Input.Trim();
        Input = "";
        Messages.Add(new ChatMessage("User", text));
        var reply = new ChatMessage("AI", "");
        Messages.Add(reply);
        IsBusy = true;

        await RunAsync(async () =>
        {
            // RAG 문서(rag_context)와 웹 검색·페이지(tool_result) 출처
            var sources = new JsonArray();
            await foreach (var ev in _api.ChatAsync(text, _sessionId, UseRag))
            {
                var json = ev.Json;
                _sessionId ??= json?["session_id"]?.ToString();
                switch (json?["type"]?.ToString())
                {
                    case "token":
                        reply.Text += json["content"]?.ToString();
                        break;
                    case "rag_context":
                    case "tool_result":
                        foreach (var source in json["sources"]?.AsArray() ?? new JsonArray())
                        {
                            sources.Add(source?.DeepClone());
                        }

                        break;
                    case "tool_call":
                        Status = "🔎 도구 사용: " + json["tool"];
                        break;
                    case "tool_confirm":
                        // 쓰기·파괴적 MCP 도구: 사용자가 승인해야 실행된다
                        var approved = await Dialogs.ConfirmAsync(
                            "도구 실행 확인", $"'{json["tool"]}' 을(를) 실행할까요?\n{json["arguments"]}");
                        await _api.SendAsync(HttpMethod.Post, "api/chat/confirm",
                            new { confirm_id = json["id"]?.ToString(), approved });
                        break;
                    case "complete":
                        reply.Text += FormatSources(sources);
                        break;
                    case "error":
                        reply.Text = "Error: " + json["content"];
                        break;
                }
            }
        });
        IsBusy = false;
    }

    private async void NewConversation() => await RunAsync(async () =>
    {
        await _api.SendAsync(HttpMethod.Post, "api/sessions", null);
        Messages.Clear();
        Connect();
    }, "새 대화를 시작했습니다.");

    /// <summary>활성 세션의 대화 스트림에 붙는다(끊기면 잠시 뒤 다시 붙고, 그때마다 히스토리를 새로 받는다).</summary>
    private async void Connect()
    {
        _stream?.Cancel();
        var cts = _stream = new CancellationTokenSource();
        while (!cts.IsCancellationRequested)
        {
            try
            {
                _sessionId = (await _api.GetAsync("api/sessions/active", cts.Token))?["session_id"]?.ToString();
                await foreach (var ev in _api.StreamAsync("api/chat/stream?session_id=" + _sessionId, cts.Token))
                {
                    if (ev.Type == "init")
                    {
                        LoadHistory(ev.Json?["messages"]?.AsArray());
                    }
                    else if (ev.Type == "message")
                    {
                        OnStoredMessage(ev.Json);
                    }
                }
            }
            catch (OperationCanceledException) when (cts.IsCancellationRequested)
            {
                return;
            }
            catch (Exception ex)
            {
                Status = $"대화 연결 오류({ReconnectDelayMs / 1000}초 후 재연결): " + ex.Message;
            }

            try
            {
                await Task.Delay(ReconnectDelayMs, cts.Token);
            }
            catch (OperationCanceledException)
            {
                return;
            }
        }
    }

    private void LoadHistory(JsonArray? messages)
    {
        // 보내는 중인 답 말풍선을 지우지 않는다(끝나면 다음 연결 때 히스토리에 들어 있다)
        if (IsBusy || messages is null)
        {
            return;
        }

        Messages.Clear();
        foreach (var m in messages.Where(IsBubble))
        {
            Messages.Add(ToChatMessage(m));
        }
    }

    /// <summary>
    /// 저장 알림. 텍스트 턴은 보낸 화면이 이미 그리고 있으므로 음성 턴만 추가한다.
    /// </summary>
    private void OnStoredMessage(JsonNode? message)
    {
        if (message?["source"]?.ToString() == "voice" && IsBubble(message))
        {
            Messages.Add(ToChatMessage(message));
        }
    }

    /// <summary>도구 결과(role=tool)는 말풍선으로 띄우지 않는다 — 답 말풍선에 "검색함"·출처로 붙는다.</summary>
    private static bool IsBubble(JsonNode? m) => m?["role"]?.ToString() != "tool";

    private static ChatMessage ToChatMessage(JsonNode? m) => new(
        m?["role"]?.ToString() == "user" ? "User" : "AI",
        (m?["content"]?.ToString() ?? "") + FormatSources(m?["sources"] as JsonArray),
        m?["source"]?.ToString() == "voice");

    /// <summary>답에 붙일 출처: RAG 문서 이름, 웹 검색·페이지는 "🔎 검색함" 과 링크.</summary>
    public static string FormatSources(JsonArray? sources)
    {
        if (sources is null)
        {
            return "";
        }

        var files = sources.Where(s => s?["url"] is null && s?["tool"] is null)
            .Select(s => (s?["filename"] ?? s?["doc_id"])?.ToString())
            .Where(name => !string.IsNullOrEmpty(name))
            .ToList();
        var links = sources.Where(s => s?["url"] is not null)
            .Select(s => $"- {s!["title"]} ({s["url"]})")
            .Distinct()
            .ToList();
        var text = files.Count > 0 ? "\n\nSources: " + string.Join(", ", files) : "";
        if (links.Count > 0)
        {
            text += "\n\n🔎 검색함 · 출처\n" + string.Join("\n", links);
        }

        return text;
    }

    public void Dispose() => _stream?.Cancel();
}
