using System.Net.WebSockets;
using System.Text;
using System.Text.Json.Nodes;
using System.Threading.Channels;
using NAudio.Wave;

namespace EdgeVoice.Agent.Core;

/// <summary>
/// 마이크 → audio-gateway(/ws/audio) 스트리밍 (웹 UI 의 Push-to-Talk 과 동일 포맷:
/// 16kHz mono int16 PCM, 100ms=1600 샘플 단위 바이너리 프레임).
/// 서버는 프레임마다 VAD 결과 JSON({is_speech, probability})을 돌려준다.
/// </summary>
public sealed class MicrophoneStreamer : IMicrophoneStream
{
    private readonly EdgeVoiceOptions _options;
    private WaveInEvent? _waveIn;
    private ClientWebSocket? _socket;
    private Channel<byte[]>? _frames;
    private CancellationTokenSource? _cts;

    public MicrophoneStreamer(EdgeVoiceOptions options) => _options = options;

    public bool IsStreaming { get; private set; }

    /// <summary>입력 레벨(0~1, RMS 기반). 파형 크기에 사용.</summary>
    public event Action<float>? LevelChanged;

    public event Action<bool>? SpeechDetected;

    public event Action<bool>? StreamingChanged;

    /// <summary>게이트웨이가 보낸 답변 음성(float32 24kHz mono) 조각.</summary>
    public event Action<byte[]>? AudioReceived;

    public async Task StartAsync()
    {
        if (IsStreaming)
        {
            return;
        }

        _cts = new CancellationTokenSource();
        _socket = new ClientWebSocket();
        await _socket.ConnectAsync(new Uri(_options.AudioGatewayWsUrl), _cts.Token);

        _frames = Channel.CreateUnbounded<byte[]>();
        _ = Task.Run(() => SendLoopAsync(_socket, _frames.Reader, _cts.Token));
        _ = Task.Run(() => ReceiveLoopAsync(_socket, _cts.Token));

        _waveIn = new WaveInEvent { WaveFormat = new WaveFormat(16000, 16, 1), BufferMilliseconds = 100 };
        _waveIn.DataAvailable += OnDataAvailable;
        _waveIn.StartRecording();

        IsStreaming = true;
        StreamingChanged?.Invoke(true);
    }

    public void Stop()
    {
        if (!IsStreaming)
        {
            return;
        }

        IsStreaming = false;
        _waveIn?.StopRecording();
        _waveIn?.Dispose();
        _waveIn = null;
        _frames?.Writer.TryComplete();
        _cts?.Cancel();
        _socket?.Dispose();
        _socket = null;
        LevelChanged?.Invoke(0f);
        SpeechDetected?.Invoke(false);
        StreamingChanged?.Invoke(false);
    }

    private void OnDataAvailable(object? sender, WaveInEventArgs e)
    {
        var frame = e.Buffer.AsSpan(0, e.BytesRecorded).ToArray();
        _frames?.Writer.TryWrite(frame);

        double sum = 0;
        var samples = frame.Length / 2;
        for (var i = 0; i < samples; i++)
        {
            double s = BitConverter.ToInt16(frame, i * 2) / 32768.0;
            sum += s * s;
        }

        var rms = samples == 0 ? 0 : Math.Sqrt(sum / samples);
        LevelChanged?.Invoke((float)Math.Min(1.0, rms * 5));
    }

    private async Task SendLoopAsync(ClientWebSocket socket, ChannelReader<byte[]> reader, CancellationToken ct)
    {
        try
        {
            await foreach (var frame in reader.ReadAllAsync(ct))
            {
                await socket.SendAsync(new ArraySegment<byte>(frame), WebSocketMessageType.Binary, true, ct);
            }
        }
        catch (Exception) when (!IsStreaming || ct.IsCancellationRequested)
        {
        }
        catch (Exception)
        {
            Stop();
        }
    }

    private async Task ReceiveLoopAsync(ClientWebSocket socket, CancellationToken ct)
    {
        var buffer = new byte[8192];
        var text = new StringBuilder();
        var audio = new MemoryStream();
        try
        {
            while (socket.State == WebSocketState.Open && !ct.IsCancellationRequested)
            {
                var result = await socket.ReceiveAsync(new ArraySegment<byte>(buffer), ct);
                if (result.MessageType == WebSocketMessageType.Close)
                {
                    break;
                }

                // 바이너리 프레임 = 재생할 답변 음성, 텍스트 프레임 = VAD 결과 JSON
                if (result.MessageType == WebSocketMessageType.Binary)
                {
                    audio.Write(buffer, 0, result.Count);
                    if (result.EndOfMessage)
                    {
                        AudioReceived?.Invoke(audio.ToArray());
                        audio.SetLength(0);
                    }

                    continue;
                }

                text.Append(Encoding.UTF8.GetString(buffer, 0, result.Count));
                if (!result.EndOfMessage)
                {
                    continue;
                }

                var isSpeech = JsonNode.Parse(text.ToString())?["is_speech"]?.GetValue<bool>() ?? false;
                text.Clear();
                SpeechDetected?.Invoke(isSpeech);
            }
        }
        catch (Exception)
        {
            // 연결 종료/취소: 아래에서 정리
        }

        if (IsStreaming)
        {
            Stop();
        }
    }
}
