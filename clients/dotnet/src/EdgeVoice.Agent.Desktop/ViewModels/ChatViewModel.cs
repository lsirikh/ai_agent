using System;
using System.Collections.ObjectModel;
using System.Linq;
using Avalonia.Threading;
using EdgeVoice.Agent.Core;
using Prism.Commands;
using Prism.Mvvm;

namespace EdgeVoice.Agent.Desktop.ViewModels;

public sealed class ChatMessage : BindableBase
{
    private string _text;

    public ChatMessage(string role, string text)
    {
        Role = role;
        _text = text;
    }

    public string Role { get; }

    public string Text { get => _text; set => SetProperty(ref _text, value); }
}

/// <summary>채팅: 스트리밍 응답(RAG 출처 표시) + 마이크 스트리밍 토글(웹의 Push-to-Talk 대응).</summary>
public sealed class ChatViewModel : PageViewModel
{
    private readonly EdgeVoiceApiClient _api;
    private readonly MicrophoneStreamer _mic;
    private string? _sessionId;
    private string _input = "";
    private bool _useRag = true;
    private bool _isBusy;
    private bool _isRecording;

    public ChatViewModel(EdgeVoiceApiClient api, MicrophoneStreamer mic)
    {
        _api = api;
        _mic = mic;
        SendCommand = new DelegateCommand(Send, () => !IsBusy && !string.IsNullOrWhiteSpace(Input))
            .ObservesProperty(() => IsBusy)
            .ObservesProperty(() => Input);
        ToggleMicCommand = new DelegateCommand(ToggleMic);

        mic.StreamingChanged += on => Dispatcher.UIThread.Post(() => IsRecording = on);
    }

    public ObservableCollection<ChatMessage> Messages { get; } = new();

    public DelegateCommand SendCommand { get; }

    public DelegateCommand ToggleMicCommand { get; }

    public string Input { get => _input; set => SetProperty(ref _input, value); }

    public bool UseRag { get => _useRag; set => SetProperty(ref _useRag, value); }

    public bool IsBusy { get => _isBusy; set => SetProperty(ref _isBusy, value); }

    public bool IsRecording { get => _isRecording; set => SetProperty(ref _isRecording, value); }

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
            var sources = "";
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
                        sources = string.Join(", ", json["sources"]?.AsArray()
                            .Select(s => (s?["filename"] ?? s?["doc_id"])?.ToString()) ?? Array.Empty<string?>());
                        break;
                    case "complete" when sources.Length > 0:
                        reply.Text += "\n\nSources: " + sources;
                        break;
                    case "error":
                        reply.Text = "Error: " + json["content"];
                        break;
                }
            }
        });
        IsBusy = false;
    }

    private async void ToggleMic() => await RunAsync(async () =>
    {
        if (_mic.IsStreaming)
        {
            _mic.Stop();
        }
        else
        {
            await _mic.StartAsync();
        }
    });
}
