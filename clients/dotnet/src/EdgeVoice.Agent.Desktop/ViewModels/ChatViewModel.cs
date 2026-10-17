using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Avalonia.Media.Imaging;
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

/// <summary>채팅에 첨부한 이미지(전송 전). 서버로는 data URL 로 보낸다.</summary>
public sealed class ChatAttachment
{
    public ChatAttachment(string name, string mime, byte[] bytes)
    {
        Name = name;
        DataUrl = $"data:{mime};base64,{Convert.ToBase64String(bytes)}";
        try
        {
            Preview = new Bitmap(new MemoryStream(bytes));
        }
        catch (Exception)
        {
            Preview = null; // 미리보기만 못 그린다(형식은 머리 바이트로 확인했다)
        }
    }

    public string Name { get; }

    public string DataUrl { get; }

    public Bitmap? Preview { get; }
}

/// <summary>
/// 채팅: 음성과 같은 활성 세션을 쓴다. 시작하면 세션 히스토리를 불러오고 /api/chat/stream 을 상시 구독해
/// 음성 턴을 말풍선으로 보여 준다. 텍스트 질문은 스트리밍 응답(RAG 출처 표시), 마이크 버튼은 상시 마이크 음소거 토글.
/// LLM 이 도구를 쓰면 "🔎 검색함"·출처 링크를 답에 붙이고, 확인이 필요한 도구는 실행 전에 묻는다.
/// </summary>
public sealed class ChatViewModel : PageViewModel, IDisposable
{
    private const int ReconnectDelayMs = 5000;

    /// <summary>서버(shared/vision.py)와 같은 제한.</summary>
    public const int MaxImages = 2;

    public const int MaxImageBytes = 8 * 1024 * 1024;

    /// <summary>글 없이 이미지만 보낼 때의 질문.</summary>
    public const string ImageOnlyQuestion = "이 이미지를 보고 무엇인지 설명해 줘.";

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
        SendCommand = new DelegateCommand(Send, () => !IsBusy && (!string.IsNullOrWhiteSpace(Input) || Attachments.Count > 0))
            .ObservesProperty(() => IsBusy)
            .ObservesProperty(() => Input);
        Attachments.CollectionChanged += (_, _) =>
        {
            SendCommand.RaiseCanExecuteChanged();
            RaisePropertyChanged(nameof(HasAttachments));
        };
        RemoveAttachmentCommand = new DelegateCommand<ChatAttachment>(a => Attachments.Remove(a));
        AttachFileCommand = new DelegateCommand(AttachFromPicker);
        ToggleMuteCommand = new DelegateCommand(() => _mic.IsMuted = !_mic.IsMuted);
        NewConversationCommand = new DelegateCommand(NewConversation, () => !IsBusy).ObservesProperty(() => IsBusy);

        _isMuted = mic.IsMuted;
        mic.MutedChanged += muted => Dispatcher.UIThread.Post(() => IsMuted = muted);
        Connect();
    }

    public ObservableCollection<ChatMessage> Messages { get; } = new();

    public DelegateCommand SendCommand { get; }

    /// <summary>전송 전 첨부 이미지(최대 2장).</summary>
    public ObservableCollection<ChatAttachment> Attachments { get; } = new();

    public bool HasAttachments => Attachments.Count > 0;

    public DelegateCommand<ChatAttachment> RemoveAttachmentCommand { get; }

    /// <summary>📎: 창이 넣어 주는 파일 선택기(ImagePicker)로 이미지를 고른다.</summary>
    public DelegateCommand AttachFileCommand { get; }

    /// <summary>이미지 파일 선택기 (이름, 바이트). 창(MainWindow)이 StorageProvider 로 채운다.</summary>
    public Func<Task<IReadOnlyList<(string Name, byte[] Bytes)>>>? ImagePicker { get; set; }

    /// <summary>
    /// 이미지 첨부(📎·붙여넣기). PNG·JPEG·GIF·BMP·WEBP 만, 8MB·2장까지. 첨부했으면 true.
    /// </summary>
    public bool AttachImage(byte[] bytes, string name)
    {
        var mime = ImageMime(bytes);
        if (mime is null || bytes.Length > MaxImageBytes)
        {
            Status = $"이미지만 첨부할 수 있습니다(PNG·JPEG·GIF·BMP·WEBP, 8MB 이하): {name}";
            return false;
        }

        if (Attachments.Count >= MaxImages)
        {
            Status = $"이미지는 {MaxImages}장까지 첨부할 수 있습니다.";
            return false;
        }

        Attachments.Add(new ChatAttachment(name, mime, bytes));
        Status = $"이미지 첨부: {name}";
        return true;
    }

    /// <summary>여러 파일(끌어다 놓기 등) 중 이미지만 첨부한다. 첨부한 개수.</summary>
    public int AttachFiles(IEnumerable<(string Name, byte[] Bytes)> files)
        => files.Count(f => ImageMime(f.Bytes) is not null && AttachImage(f.Bytes, f.Name));

    /// <summary>머리 바이트로 이미지 형식을 알아낸다(확장자는 믿지 않는다).</summary>
    public static string? ImageMime(byte[] b) => b switch
    {
        [0x89, 0x50, 0x4E, 0x47, ..] => "image/png",
        [0xFF, 0xD8, 0xFF, ..] => "image/jpeg",
        [0x47, 0x49, 0x46, 0x38, ..] => "image/gif",
        [0x42, 0x4D, ..] => "image/bmp",
        [0x52, 0x49, 0x46, 0x46, _, _, _, _, 0x57, 0x45, 0x42, 0x50, ..] => "image/webp",
        _ => null,
    };

    private async void AttachFromPicker()
    {
        if (ImagePicker is null)
        {
            return;
        }

        foreach (var (name, bytes) in await ImagePicker())
        {
            AttachImage(bytes, name);
        }
    }

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
        var images = Attachments.Select(a => a.DataUrl).ToList();
        var text = Input.Trim();
        if (text.Length == 0)
        {
            text = ImageOnlyQuestion;
        }

        Input = "";
        Attachments.Clear();
        var user = new ChatMessage("User", images.Count > 0 ? $"{text}\n🖼 이미지 {images.Count}장" : text);
        Messages.Add(user);
        var reply = new ChatMessage("AI", "");
        Messages.Add(reply);
        IsBusy = true;

        await RunAsync(async () =>
        {
            // RAG 문서(rag_context)와 웹 검색·페이지(tool_result) 출처
            var sources = new JsonArray();
            await foreach (var ev in _api.ChatAsync(text, _sessionId, UseRag, images))
            {
                var json = ev.Json;
                _sessionId ??= json?["session_id"]?.ToString();
                switch (json?["type"]?.ToString())
                {
                    case "token":
                        reply.Text += json["content"]?.ToString();
                        break;
                    case "image_description":
                        // LLM 이 첨부 화면을 어떻게 이해했는지(비전 모델 설명) — 저장된 기록과 같은 꼴
                        user.Text = $"{text}\n\n{json["content"]}";
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
